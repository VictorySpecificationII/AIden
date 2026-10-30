"""model-steward: the only part of AIden that can change which models are served.

AIden picks models; the steward does the work, and enforces the limits itself, so a
mistake (or a confused model) in AIden can't go past them:
- sources: Hugging Face models of ALLOWED_ORG only, with a licence in ALLOWED_LICENCES,
  text generation only, built for the device (NPU builds end in -cw-ov);
- disk: candidates (everything but the active and previous models) stay under DISK_CAP_GB;
- memory: a trial only starts if MIN_FREE_GB stays free with the candidate loaded;
- one trial per device; the active and previous models are never deleted.

How models are served: each device's OVMS reads CONFIG_DIR/config_<device>.json and
re-reads it when it changes. That file holds the active model and the trial, if any.
STATE_FILE remembers, per device, the active, previous and trial model.

API (every request but /health needs X-Steward-Token):
    GET  /health, /state, /jobs/<id>
    POST /pull       {"source": "OpenVINO/x", "device": "npu"}   -> {"job": id}
    POST /trial      {"device", "name"}     load a pulled model next to the active one
    POST /end-trial  {"device"}
    POST /activate   {"device", "name"}     the trial becomes active, active becomes previous
    POST /rollback   {"device"}             the previous model becomes active again
    POST /delete     {"name"}               remove a pulled model from disk
Standard library only.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = os.environ.get("MODELS_DIR", "/home/ovms/models")
STATE_FILE = os.path.join(MODELS, "aiden-models.json")
TOKEN = os.environ.get("STEWARD_TOKEN", "")
PORT = int(os.environ.get("STEWARD_PORT", "8770"))
ALLOWED_ORG = os.environ.get("ALLOWED_ORG", "OpenVINO")
ALLOWED_LICENCES = set(os.environ.get("ALLOWED_LICENCES", "apache-2.0,mit").split(","))
DISK_CAP_GB = float(os.environ.get("DISK_CAP_GB", "20"))
MIN_FREE_GB = float(os.environ.get("MIN_FREE_GB", "4"))
HF = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
# Per device: OVMS target, the build suffix it needs, extra pull options, the server to ask
DEVICES = {
    "npu": {"target": "NPU", "suffix": "-cw-ov", "pull_args": ["--max_prompt_len", "2000"],
            "server": os.environ.get("NPU_SERVER", "http://ovms-npu:8001")},
}
# The model each device served before the steward existed (adopted on first start)
ADOPT = {"npu": (os.environ.get("ADOPT_NPU_SOURCE", ""), os.environ.get("ADOPT_NPU_NAME", ""))}

lock = threading.Lock()
jobs = {}


class Refused(Exception):
    """A request outside the limits; the message says why."""


# --- State and OVMS config -----------------------------------------------------------

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"devices": {}, "models": {}}


def save(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)
    for device, slots in state["devices"].items():
        served = [n for n in (slots.get("active"), slots.get("trial")) if n]
        config = {"model_config_list": [], "mediapipe_config_list": [
            {"name": n, "base_path": state["models"][n]["path"]} for n in served]}
        path = os.path.join(MODELS, f"config_{device}.json")
        with open(path + ".tmp", "w") as f:
            json.dump(config, f, indent=2)
        os.replace(path + ".tmp", path)  # OVMS sees the change within a second


def adopt():
    """First start: take over the model each device already serves, so nothing changes."""
    with lock:
        state = load_state()
        for device, (source, name) in ADOPT.items():
            if source and name and device not in state["devices"]:
                state["models"][name] = {"source": source, "device": device, "path": os.path.join(MODELS, source),
                                         "size_gb": None, "pulled_at": None, "adopted": True}
                state["devices"][device] = {"active": name, "previous": None, "trial": None}
        save(state)


# --- Checks the steward enforces ------------------------------------------------------

def hf_info(source):
    with urllib.request.urlopen(f"{HF}/api/models/{source}?blobs=true", timeout=30) as response:
        return json.load(response)


def check_source(source, device):
    org, _, repo = source.partition("/")
    if org != ALLOWED_ORG or not re.fullmatch(r"[A-Za-z0-9._-]+", repo):
        raise Refused(f"only {ALLOWED_ORG}/<model> sources are allowed")
    if device not in DEVICES:
        raise Refused(f"unknown device {device}")
    if not repo.endswith(DEVICES[device]["suffix"]):
        raise Refused(f"{device} needs a build ending in {DEVICES[device]['suffix']}")
    info = hf_info(source)
    licence = ((info.get("cardData") or {}).get("license") or "").lower()
    if licence not in ALLOWED_LICENCES:
        raise Refused(f"licence {licence or 'unknown'} is not allowed ({', '.join(sorted(ALLOWED_LICENCES))})")
    if info.get("pipeline_tag") not in (None, "text-generation"):
        raise Refused(f"not a text-generation model ({info.get('pipeline_tag')})")
    size_gb = sum(f.get("size") or 0 for f in info.get("siblings", [])) / 1e9
    state = load_state()
    kept = {n for slots in state["devices"].values() for n in (slots.get("active"), slots.get("previous"))}
    candidates = sum(m.get("size_gb") or 0 for n, m in state["models"].items() if n not in kept)
    if candidates + size_gb > DISK_CAP_GB:
        raise Refused(f"over the {DISK_CAP_GB:.0f} GB candidate budget ({candidates:.1f} GB used, needs {size_gb:.1f} GB)")
    if shutil.disk_usage(MODELS).free / 1e9 < size_gb + 10:
        raise Refused("not enough free disk")
    return size_gb, licence


def free_memory_gb():
    with open("/proc/meminfo") as f:
        fields = dict(re.findall(r"^(\w+):\s+(\d+) kB", f.read(), re.M))
    return int(fields["MemAvailable"]) / 1024 / 1024


# --- Actions ------------------------------------------------------------------------

def pull(source, device):
    size_gb, licence = check_source(source, device)
    if any(j["state"] == "running" for j in jobs.values()):
        raise Refused("a pull is already running")
    name = source.split("/", 1)[1].lower()
    job = {"id": uuid.uuid4().hex[:8], "state": "running", "source": source, "name": name, "started": time.time()}
    jobs[job["id"]] = job

    def run():
        spec = DEVICES[device]
        result = subprocess.run(["/ovms/bin/ovms", "--pull", "--source_model", source, "--model_repository_path", MODELS,
                                 "--task", "text_generation", "--target_device", spec["target"],
                                 "--cache_dir", os.path.join(MODELS, ".ov_cache"), *spec["pull_args"]],
                                capture_output=True, text=True, timeout=3 * 3600)
        if result.returncode != 0:
            job.update(state="failed", error=(result.stderr or result.stdout)[-500:])
            return
        with lock:
            state = load_state()
            state["models"][name] = {"source": source, "device": device, "path": os.path.join(MODELS, source),
                                     "size_gb": round(size_gb, 2), "licence": licence, "pulled_at": time.time()}
            save(state)
        job.update(state="done", finished=time.time())

    threading.Thread(target=run, daemon=True).start()
    return {"job": job["id"], "name": name, "size_gb": round(size_gb, 2)}


def slots_for(state, device):
    if device not in state["devices"]:
        raise Refused(f"no models on {device}")
    return state["devices"][device]


def trial(device, name):
    with lock:
        state = load_state()
        slots = slots_for(state, device)
        model = state["models"].get(name)
        if not model or model["device"] != device:
            raise Refused(f"{name} isn't a pulled {device} model")
        if slots.get("trial"):
            raise Refused(f"{slots['trial']} is already on trial")
        if name == slots.get("active"):
            raise Refused(f"{name} is already active")
        if free_memory_gb() - (model.get("size_gb") or 0) * 1.2 < MIN_FREE_GB:
            raise Refused(f"loading it would leave less than {MIN_FREE_GB:.0f} GB of memory free")
        slots["trial"] = name
        save(state)
    return slots


def end_trial(device):
    with lock:
        state = load_state()
        slots = slots_for(state, device)
        slots["trial"] = None
        save(state)
    return slots


def activate(device, name):
    with lock:
        state = load_state()
        slots = slots_for(state, device)
        if slots.get("trial") != name:
            raise Refused("only the model on trial can be activated (it is already loaded and tested)")
        slots.update(previous=slots.get("active"), active=name, trial=None, switched_at=time.time())
        save(state)
    return slots


def rollback(device):
    with lock:
        state = load_state()
        slots = slots_for(state, device)
        if not slots.get("previous"):
            raise Refused("there is no previous model")
        slots.update(active=slots["previous"], previous=slots["active"], trial=None, switched_at=None)
        save(state)
    return slots


def delete(name):
    with lock:
        state = load_state()
        in_use = {n for slots in state["devices"].values() for n in slots.values() if n}
        if name in in_use:
            raise Refused(f"{name} is active, previous or on trial")
        model = state["models"].pop(name, None)
        if not model:
            raise Refused(f"no model {name}")
        path = os.path.realpath(model["path"])
        if not path.startswith(os.path.realpath(MODELS) + os.sep) or model.get("adopted"):
            raise Refused("refusing to delete outside the models directory or an adopted model")
        if any(os.path.realpath(m["path"]) == path for m in state["models"].values()):
            raise Refused("another model entry uses the same files")
        shutil.rmtree(path, ignore_errors=True)
        save(state)
    return {"deleted": name}


# --- HTTP ---------------------------------------------------------------------------

ROUTES = {
    "/pull": lambda b: pull(b["source"], b["device"]),
    "/trial": lambda b: trial(b["device"], b["name"]),
    "/end-trial": lambda b: end_trial(b["device"]),
    "/activate": lambda b: activate(b["device"], b["name"]),
    "/rollback": lambda b: rollback(b["device"]),
    "/delete": lambda b: delete(b["name"]),
}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorised(self):
        return TOKEN and self.headers.get("X-Steward-Token") == TOKEN

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"ok": True, "configured": bool(TOKEN)})
        if not self.authorised():
            return self.reply(403, {"error": "bad token"})
        if self.path == "/state":
            return self.reply(200, {**load_state(), "limits": {
                "org": ALLOWED_ORG, "licences": sorted(ALLOWED_LICENCES), "disk_cap_gb": DISK_CAP_GB,
                "min_free_gb": MIN_FREE_GB, "devices": {d: s["suffix"] for d, s in DEVICES.items()}}})
        match = re.fullmatch(r"/jobs/([0-9a-f]{8})", self.path)
        if match and match[1] in jobs:
            return self.reply(200, jobs[match[1]])
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.authorised():
            return self.reply(403, {"error": "bad token"})
        action = ROUTES.get(self.path)
        if not action:
            return self.reply(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self.reply(200, action(body))
        except Refused as exc:
            self.reply(409, {"error": str(exc)})
        except (KeyError, ValueError) as exc:
            self.reply(400, {"error": f"bad request: {exc}"})
        except Exception as exc:  # report, keep serving
            self.reply(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    adopt()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

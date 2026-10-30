"""AIden choosing their own models: browse, pull, trial (with model-steward's hands).

AIden decides; model-steward (tools/model-steward) does the pulling and config edits and
enforces the limits itself. This module:
- reads the steward's state: which model is active, previous and on trial per device;
- browses OpenVINO's catalog on Hugging Face for candidates that fit a device and the
  limits, best first, skipping models already tried;
- pulls a candidate and puts it on trial next to the active model, waiting until it is
  loaded and answering.
Scoring and switching build on this (see evaluate/scout below). Every step is recorded
as experience (kind "model"), which is also AIden's journal of model decisions.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter
from opentelemetry import metrics

import experience

STEWARD_URL = os.environ.get("STEWARD_URL", "http://model-steward:8770")
STEWARD_TOKEN = os.environ.get("STEWARD_TOKEN", "")
HF = "https://huggingface.co"
# Device -> the backend serving it
SERVERS = {"npu": ("ovms-npu", "http://ovms-npu:8001")}
CATALOG_SIZE = 40
LOAD_TIMEOUT_S = 30 * 60   # NPU compilation of a new model can take minutes
PULL_TIMEOUT_S = 3 * 3600

logger = logging.getLogger("aiden.models")
_state: Dict[str, Any] = {"at": 0.0, "value": None}
_state_lock = threading.Lock()


class StewardError(Exception):
    pass


def steward(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.request(method, f"{STEWARD_URL}{path}", json=body, timeout=60,
                                headers={"X-Steward-Token": STEWARD_TOKEN})
    data = response.json()
    if response.status_code != 200:
        raise StewardError(data.get("error", f"HTTP {response.status_code}"))
    return data


def state(max_age_s: float = 10) -> Optional[Dict[str, Any]]:
    """The steward's state (cached briefly); None when there is no steward."""
    if not STEWARD_TOKEN:
        return None
    with _state_lock:
        if _state["value"] is None or time.time() - _state["at"] > max_age_s:
            try:
                _state.update(value=steward("GET", "/state"), at=time.time())
            except (requests.RequestException, ValueError, StewardError) as exc:
                logger.warning("Could not read the model steward's state: %s", exc)
                return _state["value"]
        return _state["value"]


def active_model(backend: str) -> Optional[str]:
    """The model a backend should answer with: the steward's active one, if it manages it."""
    current = state()
    for device, (name, _) in SERVERS.items():
        if name == backend and current and device in current["devices"]:
            return current["devices"][device]["active"]
    return None


def journal(action: str, **fields):
    experience.record("model", {"action": action, **fields})
    logger.info("Models: %s %s", action, json.dumps(fields, default=str)[:300])


def tried() -> set:
    """Models AIden has already pulled or judged (so the same one isn't tried twice)."""
    seen = set()
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR)) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if path.endswith(".jsonl"):
            with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
                for line in f:
                    if '"kind": "model"' in line:
                        source = json.loads(line).get("source")
                        if source:
                            seen.add(source)
    return seen


def catalog(device: str) -> List[Dict[str, Any]]:
    """Candidates for a device within the steward's limits, most-used first."""
    current = state()
    if not current:
        return []
    limits = current["limits"]
    suffix = limits["devices"][device]
    listed = requests.get(f"{HF}/api/models", timeout=30, params={
        "author": limits["org"], "search": suffix, "sort": "downloads", "limit": CATALOG_SIZE}).json()
    have = {m["source"] for m in current["models"].values()} | tried()
    found = []
    for item in listed:
        source = item["id"]
        if not source.endswith(suffix) or source in have:
            continue
        info = requests.get(f"{HF}/api/models/{source}", params={"blobs": "true"}, timeout=30).json()
        licence = ((info.get("cardData") or {}).get("license") or "").lower()
        if licence not in limits["licences"] or info.get("pipeline_tag") not in (None, "text-generation"):
            continue
        size_gb = sum(f.get("size") or 0 for f in info.get("siblings", [])) / 1e9
        found.append({"source": source, "size_gb": round(size_gb, 1), "licence": licence,
                      "downloads": item.get("downloads", 0)})
    return found


def wait_until_answering(device: str, name: str, timeout_s: float = LOAD_TIMEOUT_S) -> bool:
    _, server = SERVERS[device]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if requests.get(f"{server}/v2/models/{name}/ready", timeout=5).status_code == 200:
                reply = requests.post(f"{server}/v3/chat/completions", timeout=120, json={
                    "model": name, "max_tokens": 5, "messages": [{"role": "user", "content": "Say OK."}]})
                if reply.status_code == 200:
                    return True
        except requests.RequestException:
            pass
        time.sleep(15)
    return False


def pull(source: str, device: str) -> str:
    job = steward("POST", "/pull", {"source": source, "device": device})
    journal("pull", source=source, device=device, size_gb=job["size_gb"])
    deadline = time.time() + PULL_TIMEOUT_S
    while time.time() < deadline:
        status = steward("GET", f"/jobs/{job['job']}")
        if status["state"] == "done":
            return job["name"]
        if status["state"] == "failed":
            raise StewardError(f"pull failed: {status.get('error', '')[-200:]}")
        time.sleep(20)
    raise StewardError("pull timed out")


def start_trial(source: str, device: str) -> str:
    """Pull a candidate, load it next to the active model and wait until it answers."""
    name = pull(source, device)
    steward("POST", "/trial", {"device": device, "name": name})
    journal("trial", source=source, device=device, name=name)
    if not wait_until_answering(device, name):
        steward("POST", "/end-trial", {"device": device})
        journal("trial_failed", source=source, device=device, name=name, reason="never answered")
        raise StewardError(f"{name} didn't load on the {device}")
    _state["at"] = 0  # re-read the steward's state next time
    return name


# --- Scoring ------------------------------------------------------------------------

MIN_TOKENS_PER_S = float(os.environ.get("AIDEN_MODEL_MIN_TPS", "5"))
ROUTING_SAMPLES = 40


# Known answers every candidate faces, so a model can't pass without being asked (in the
# user's world: their notes hold projects, clients, plans and decisions)
BENCHMARK = [(p, True) for p in [
    "What did I decide about MinIO for the AIden stack?", "Summarise my notes on the burn-in plan",
    "What are my client deliverables for next month?", "Remind me what we said about the Ceph upgrade",
    "What's in my Brazilian Portuguese notes about verb tenses?", "How did I set up Bitwarden secrets for Claude?",
    "What's the status of my HPC engineering project?", "Which decisions did I record about the NPU adaptation?",
    "What did I write about the Marina Ayia Napa pitch?", "List the open tasks in my LSDT HPC notes",
]] + [(p, False) for p in [
    "Explain how TCP slow start works", "What is the capital of France?", "Write a haiku about autumn",
    "How do I reverse a list in Python?", "What is the difference between RAID 5 and RAID 6?",
    "Translate 'good morning' into Spanish", "What does a TLB do in a CPU?", "How many days are in a leap year?",
    "Give me a recipe for pancakes", "What is Kubernetes used for?",
]]


def routing_questions(limit: int = ROUTING_SAMPLES) -> List[Dict[str, Any]]:
    """Prompts whose answer is known: the built-in benchmark plus turns the rules decided."""
    picked: Dict[bool, List[Dict[str, Any]]] = {True: [], False: []}
    for prompt, needs in BENCHMARK:
        picked[needs].append({"prompt": prompt, "needs_notes": needs})
    seen = {prompt for prompt, _ in BENCHMARK}
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR), reverse=True) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if not path.endswith(".jsonl"):
            continue
        with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                decision = record.get("decision") or {}
                prompt = record.get("prompt") or ""
                if record.get("kind") == "turn" and decision.get("decided_by") == "rule" and prompt not in seen:
                    seen.add(prompt)
                    picked[bool(decision.get("needs_notes"))].append({"prompt": prompt, "needs_notes": bool(decision["needs_notes"])})
    half = limit // 2
    return picked[True][:half] + picked[False][:limit - min(half, len(picked[True]))]


def routing_accuracy(model: str, questions: List[Dict[str, Any]]) -> Optional[float]:
    from router import classify_with_npu
    if not questions:
        return None
    right = sum(classify_with_npu(q["prompt"], model)[0] == q["needs_notes"] for q in questions)
    return round(right / len(questions), 3)


def speed(device: str, model: str) -> Optional[float]:
    _, server = SERVERS[device]
    start = time.time()
    try:
        response = requests.post(f"{server}/v3/chat/completions", timeout=180, json={
            "model": model, "max_tokens": 100, "temperature": 0,
            "messages": [{"role": "user", "content": "Explain in a short paragraph what an operating system does."}]})
        response.raise_for_status()
        tokens = response.json()["usage"]["completion_tokens"]
        return round(tokens / (time.time() - start), 1)
    except (requests.RequestException, KeyError, ValueError):
        return None


def evaluate(device: str, model: str, questions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One model's scores: tool protocol, routing accuracy on known answers, speed."""
    import senses
    _, server = SERVERS[device]
    tools, tools_detail = senses.follows_tool_protocol(f"{server}/v3", model)
    questions = questions if questions is not None else routing_questions()
    return {"model": model, "tools": tools, "tools_detail": tools_detail,
            "routing": routing_accuracy(model, questions), "routing_questions": len(questions),
            "tokens_per_s": speed(device, model)}


def better(candidate: Dict[str, Any], active: Dict[str, Any]) -> Tuple[bool, str]:
    """Switch only to a candidate that is at least as good everywhere and better somewhere."""
    if candidate["routing"] is None:
        return False, "couldn't measure its routing"
    if candidate["tokens_per_s"] is None or candidate["tokens_per_s"] < MIN_TOKENS_PER_S:
        return False, f"too slow ({candidate['tokens_per_s']} tok/s, need {MIN_TOKENS_PER_S:.0f})"
    if (candidate["routing"] or 0) < (active["routing"] or 0):
        return False, f"routes worse ({candidate['routing']} vs {active['routing']})"
    if active["tools"] and not candidate["tools"]:
        return False, "can't use tools, the active model can"
    gains = []
    if candidate["tools"] and not active["tools"]:
        gains.append("can use tools")
    if (candidate["routing"] or 0) > (active["routing"] or 0):
        gains.append(f"routes better ({candidate['routing']} vs {active['routing']})")
    if not gains:
        return False, "no better than the active model"
    return True, "; ".join(gains)


# --- Deciding, on their own -----------------------------------------------------------

SCOUT_INTERVAL_S = int(os.environ.get("AIDEN_MODEL_SCOUT_INTERVAL", str(24 * 3600)))
FIRST_SCOUT_AFTER_S = 3600
IDLE_LOAD = 2.0
IDLE_AFTER_CHAT_S = 15 * 60
ROLLBACK_WINDOW_S = 24 * 3600
ROLLBACK_AFTER_FAILURES = 2

_activity = {"last_chat": 0.0}
_scouting = threading.Lock()
switch_counter = metrics.get_meter("aiden").create_counter(
    name="aiden_model_switches", description="Models AIden switched to or rolled back from, by device and action", unit="1")


def note_chat():
    _activity["last_chat"] = time.time()


def idle() -> bool:
    return os.getloadavg()[0] < IDLE_LOAD and time.time() - _activity["last_chat"] > IDLE_AFTER_CHAT_S


def scout(device: str) -> Dict[str, Any]:
    """One round of looking for a better model for a device, and switching if one is found."""
    if not _scouting.acquire(blocking=False):
        return {"outcome": "busy", "reason": "already scouting"}
    try:
        current = state(max_age_s=0)
        if not current or device not in current["devices"]:
            return {"outcome": "skipped", "reason": f"no steward-managed models on the {device}"}
        slots = current["devices"][device]
        if slots.get("trial"):  # left over from an interrupted round
            steward("POST", "/end-trial", {"device": device})
        candidates = catalog(device)
        if not candidates:
            journal("scouted", device=device, outcome="nothing new to try")
            return {"outcome": "nothing new to try"}
        name = source = None
        for candidate in candidates:
            try:
                source, name = candidate["source"], start_trial(candidate["source"], device)
                break
            except StewardError as exc:
                # Not recorded under "source": a limit today (memory, budget) may pass another day
                journal("skipped", device=device, candidate=candidate["source"], reason=str(exc))
                name = None
        if not name:
            return {"outcome": "no candidate could be tried"}
        questions = routing_questions()
        result = evaluate(device, name, questions)
        baseline = evaluate(device, slots["active"], questions)
        switch, reason = better(result, baseline)
        journal("judged", device=device, source=source, name=name, candidate=result, active=baseline,
                switch=switch, reason=reason)
        if switch:
            steward("POST", "/activate", {"device": device, "name": name})
            switch_counter.add(1, {"device": device, "action": "switch"})
            journal("switched", device=device, source=source, name=name, previous=slots["active"], reason=reason)
            outcome = "switched"
        else:
            steward("POST", "/end-trial", {"device": device})
            steward("POST", "/delete", {"name": name})
            journal("rejected", device=device, source=source, name=name, reason=reason)
            outcome = "rejected"
        _state["at"] = 0
        return {"outcome": outcome, "candidate": name, "reason": reason, "scores": {"candidate": result, "active": baseline}}
    except (StewardError, requests.RequestException) as exc:
        journal("scout_failed", device=device, reason=f"{type(exc).__name__}: {exc}")
        return {"outcome": "failed", "reason": str(exc)}
    finally:
        _scouting.release()


def watch(backend: str, sensed: Dict[str, Any]):
    """After a switch, a model that keeps failing its probes is rolled back on AIden's own."""
    current = state()
    for device, (name, _) in SERVERS.items():
        if name != backend or not current or device not in current["devices"]:
            continue
        slots = current["devices"][device]
        recent = slots.get("switched_at") and time.time() - slots["switched_at"] < ROLLBACK_WINDOW_S
        if recent and slots.get("previous") and not sensed.get("generating") and sensed.get("failures", 0) >= ROLLBACK_AFTER_FAILURES:
            try:
                steward("POST", "/rollback", {"device": device})
                switch_counter.add(1, {"device": device, "action": "rollback"})
                journal("rolled_back", device=device, name=slots["active"], back_to=slots["previous"],
                        reason=f"failed {sensed['failures']} probes after the switch")
                _state["at"] = 0
            except (StewardError, requests.RequestException) as exc:
                logger.error("Rollback on the %s failed: %s", device, exc)


def recent(days: int = 7) -> List[Dict[str, Any]]:
    """Model decisions from the journal (newest last)."""
    cutoff = time.time() - days * 86400
    found = []
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR)) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if path.endswith(".jsonl"):
            with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
                for line in f:
                    if '"kind": "model"' in line:
                        record = json.loads(line)
                        if datetime.fromisoformat(record["at"]).timestamp() >= cutoff:
                            found.append(record)
    return found


def run_forever():
    """Scout each device once per SCOUT_INTERVAL_S, at a moment the machine is idle."""
    time.sleep(FIRST_SCOUT_AFTER_S)
    last: Dict[str, float] = {}
    while True:
        for device in SERVERS:
            if time.time() - last.get(device, 0) >= SCOUT_INTERVAL_S and idle():
                last[device] = time.time()
                logger.info("Scouted the %s: %s", device, scout(device).get("outcome"))
        time.sleep(600)


def start():
    if STEWARD_TOKEN:
        threading.Thread(target=run_forever, daemon=True, name="model-scout").start()


api = APIRouter()


@api.get("/models", summary="AIden's models: what is active, previous or on trial, and recent decisions")
def models_endpoint():
    return {"steward": state(max_age_s=0), "recent": recent()}


@api.post("/models/scout", summary="Look for a better model for a device now (runs in the background)")
def scout_endpoint(device: str = "npu"):
    if device not in SERVERS:
        return {"error": f"unknown device {device}"}
    threading.Thread(target=scout, args=(device,), daemon=True, name=f"scout-{device}").start()
    return {"started": device}

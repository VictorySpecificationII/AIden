"""AIden's read-only terminal: a fixed set of commands for looking at their own machine.

Read-only is enforced below AIden, not by AIden being careful:
- the host is visible only through read-only mounts (/sys at HOST_SYS, the journal at
  JOURNAL_DIR) and AIden's own /proc view (uptime, memory and load are the host's);
- Docker only through docker-ro-proxy, which answers a few GET requests;
- commands are named and fixed: no shell, no free-form arguments, a timeout and an
  output cap. AIden runs as a non-root user.

run(command, **args) returns {"command", "ok", "output"| "error"}; COMMANDS lists them.
"""
import os
import re
import struct
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List

import requests

HOST_SYS = os.environ.get("HOST_SYS", "/host/sys")
JOURNAL_DIR = os.environ.get("JOURNAL_DIR", "/host/journal")
DOCKER_PROXY_URL = os.environ.get("DOCKER_PROXY_URL", "http://docker-ro-proxy:2375")
TIMEOUT_S = 20
MAX_LINES = 200
# Containers AIden may name in a command: their own body
CONTAINERS = ("ovms-gpu", "ovms-npu", "ovms-cpu-embed", "AIden", "qdrant", "ollama", "ollama-webui")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def uptime() -> Dict[str, Any]:
    seconds = float(read("/proc/uptime").split()[0])
    booted = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return {"up_seconds": int(seconds), "booted_at": booted.astimezone().isoformat(timespec="seconds")}


def memory() -> Dict[str, Any]:
    fields = dict(re.findall(r"^(\w+):\s+(\d+) kB", read("/proc/meminfo"), re.M))
    gib = lambda key: round(int(fields[key]) / 1024 / 1024, 1)
    return {"total_gib": gib("MemTotal"), "available_gib": gib("MemAvailable"), "swap_free_gib": gib("SwapFree")}


def load() -> Dict[str, Any]:
    one, five, fifteen = read("/proc/loadavg").split()[:3]
    return {"load_1m": float(one), "load_5m": float(five), "load_15m": float(fifteen), "cpus": os.cpu_count()}


def suspends() -> Dict[str, Any]:
    stats = os.path.join(HOST_SYS, "power/suspend_stats")
    return {"since_boot": int(read(os.path.join(stats, "success"))),
            "failed": int(read(os.path.join(stats, "fail"))),
            "last_hw_sleep_s": round(int(read(os.path.join(stats, "last_hw_sleep"))) / 1e6, 1)}


def journal(*args: str) -> List[str]:
    """journalctl over the read-only system journal of the current boot (never the user's
    own session journal), no shell. Lines come back oldest first."""
    result = subprocess.run(["journalctl", "-D", JOURNAL_DIR, "--system", "-b", "--no-pager", "-o", "short-iso",
                             "-q", *args], capture_output=True, text=True, timeout=TIMEOUT_S)
    if result.returncode not in (0, 1):  # 1 = no matches
        raise RuntimeError(result.stderr.strip()[:200] or f"journalctl exited {result.returncode}")
    # Across several journal files the order isn't guaranteed: sort by the timestamp
    lines = sorted(result.stdout.splitlines(), key=lambda line: datetime.fromisoformat(line.split()[0]))
    return lines[-MAX_LINES:]


def sleep_log() -> List[str]:
    return journal("-g", "PM: suspend entry|returned from sleep", "-n", str(MAX_LINES))


def gpu_kernel_log() -> List[str]:
    return journal("-k", "-g", "i915|GPU HANG|GuC|reset", "-p", "warning", "-n", str(MAX_LINES))


def proxy(path: str, **params) -> requests.Response:
    response = requests.get(f"{DOCKER_PROXY_URL}{path}", params=params, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response


def containers() -> List[Dict[str, Any]]:
    return [{"name": c["Names"][0].lstrip("/"), "state": c["State"], "status": c["Status"]}
            for c in proxy("/containers/json").json()]


def container(name: str) -> Dict[str, Any]:
    if name not in CONTAINERS:
        raise ValueError(f"not one of AIden's containers: {name}")
    data = proxy(f"/containers/{name}/json").json()
    state = data["State"]
    return {"name": name, "status": state["Status"], "restarts": data["RestartCount"],
            "started_at": state["StartedAt"], "health": (state.get("Health") or {}).get("Status")}


def demux(raw: bytes) -> List[str]:
    """Docker's log stream for non-TTY containers: 8-byte frame headers, then the payload."""
    lines, i = [], 0
    while i + 8 <= len(raw):
        size = struct.unpack(">I", raw[i + 4:i + 8])[0]
        lines += raw[i + 8:i + 8 + size].decode("utf-8", "replace").splitlines()
        i += 8 + size
    return lines


def container_errors(name: str, hours: int = 24) -> List[str]:
    if name not in CONTAINERS:
        raise ValueError(f"not one of AIden's containers: {name}")
    since = int(time.time() - min(hours, 72) * 3600)
    raw = proxy(f"/containers/{name}/logs", since=since, tail=5000).content
    return [l for l in demux(raw) if re.search(r"error|exception|CL_OUT_OF|fatal", l, re.I)][-MAX_LINES:]


COMMANDS: Dict[str, Callable[..., Any]] = {
    "uptime": uptime, "memory": memory, "load": load, "suspends": suspends,
    "sleep-log": sleep_log, "gpu-kernel-log": gpu_kernel_log,
    "containers": containers, "container": container, "container-errors": container_errors,
}


def run(command: str, /, **args) -> Dict[str, Any]:
    if command not in COMMANDS:
        return {"command": command, "ok": False, "error": "unknown command"}
    try:
        return {"command": command, "ok": True, "output": COMMANDS[command](**args)}
    except Exception as exc:  # report, never raise: a check that fails is itself a finding
        return {"command": command, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}

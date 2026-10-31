"""/capabilities: AIden's view of the machine they're running on (hardware, model
backends, mentor), with a plain-language summary."""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter
from pydantic import BaseModel

import mentor
import senses
from telemetry import tracer

api = APIRouter()

# --- Capabilities Models ---
class HardwareStatus(BaseModel):
    present: bool
    busy_percent: Optional[float] = None

class BackendStatus(BaseModel):
    name: str
    tier: str
    url: str
    available: bool
    models: List[str] = []
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    # From AIden's last generation probe (see senses.py); None = not probed yet
    generating: Optional[bool] = None
    generating_checked_at: Optional[str] = None
    # Whether the model passed AIden's tool-protocol test; None = not tested yet
    tools: Optional[bool] = None

class MentorStatus(BaseModel):
    name: str
    reachable: bool
    configured: bool

class CapabilitiesResponse(BaseModel):
    checked_at: str
    profiles: List[str]
    hardware: Dict[str, HardwareStatus]
    backends: List[BackendStatus]
    mentor: MentorStatus
    online: bool
    summary: str

PROMETHEUS_URL = "http://prometheus:9090"
PROBE_TIMEOUT_S = 2
CAPABILITIES_CACHE_S = 10

# Known model backends; which ones are up depends on the active compose profiles.
# The Ollama tier is the device it runs on (nvidia or cpu profile).
BACKENDS = [
    {"name": "ovms-npu", "tier": "npu", "kind": "openai", "url": "http://ovms-npu:8001/v3"},
    {"name": "ovms-gpu", "tier": "intel-gpu", "kind": "openai", "url": "http://ovms-gpu:8002/v3"},
    {"name": "ollama", "tier": "ollama", "kind": "ollama", "url": "http://ollama:11434"},
]

# Hardware presence and current load, from the exporters Prometheus scrapes
HARDWARE_QUERIES = {
    "npu": ("max(npu_up)", "100 * max(rate(npu_busy_time_seconds_total[1m]))"),
    "intel_gpu": ("max(intel_gpu_up)", '100 * (1 - max(rate(intel_gpu_rc6_seconds_total{gt="gt0"}[1m])))'),
    "nvidia_gpu": ("count(DCGM_FI_DEV_GPU_UTIL) > bool 0", "avg(DCGM_FI_DEV_GPU_UTIL)"),
}

_capabilities_cache: Dict[str, Any] = {"at": 0.0, "value": None}
_capabilities_lock = threading.Lock()

def active_profiles() -> List[str]:
    return [p for p in os.environ.get("AIDEN_PROFILES", "").split(",") if p]

def probe_backend(backend: Dict[str, str]) -> BackendStatus:
    tier = backend["tier"]
    if tier == "ollama":
        tier = "nvidia" if "nvidia" in active_profiles() else "cpu"
    path = "/models" if backend["kind"] == "openai" else "/api/tags"
    start = time.time()
    try:
        response = requests.get(backend["url"] + path, timeout=PROBE_TIMEOUT_S)
        response.raise_for_status()
        body = response.json()
        if backend["kind"] == "openai":
            models = [m["id"] for m in body.get("data", [])]
        else:
            models = [m["name"] for m in body.get("models", [])]
        status = BackendStatus(name=backend["name"], tier=tier, url=backend["url"], available=True,
                               models=models, latency_ms=round((time.time() - start) * 1000, 1))
    except (requests.RequestException, ValueError, KeyError) as exc:
        status = BackendStatus(name=backend["name"], tier=tier, url=backend["url"], available=False,
                               error=type(exc).__name__)
    sensed = senses.status.get(backend["name"])
    if sensed:
        status.generating, status.generating_checked_at = sensed["generating"], sensed["checked_at"]
    tested = senses.tool_status.get(backend["name"])
    if tested and tested["model"] in status.models:
        status.tools = tested["tools"]
    return status

def prometheus_value(query: str) -> Optional[float]:
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=PROBE_TIMEOUT_S)
        result = response.json()["data"]["result"]
        return float(result[0]["value"][1]) if result else None
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None

def probe_hardware(name: str) -> HardwareStatus:
    present_query, busy_query = HARDWARE_QUERIES[name]
    present = (prometheus_value(present_query) or 0) >= 1
    busy = prometheus_value(busy_query) if present else None
    return HardwareStatus(present=present, busy_percent=round(busy, 1) if busy is not None else None)

def probe_mentor() -> MentorStatus:
    """The mentor is Claude via the mentor-bridge service (Claude Code CLI). Reachable = the
    bridge answers; configured = it accepts AIden's token, has the CLI and a Claude login token."""
    try:
        response = requests.get(f"{mentor.MENTOR_URL}/health", headers={"X-Mentor-Token": mentor.MENTOR_TOKEN}, timeout=PROBE_TIMEOUT_S)
        body = response.json() if response.status_code == 200 else {}
        return MentorStatus(name="claude", reachable=True,
                            configured=bool(body.get("ok") and body.get("claude") and body.get("authenticated")))
    except (requests.RequestException, ValueError):
        return MentorStatus(name="claude", reachable=False, configured=False)

def join_and(items: List[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"

def describe(hardware: Dict[str, HardwareStatus], backends: List[BackendStatus], mentor: MentorStatus) -> str:
    labels = {"npu": "an Intel NPU", "intel_gpu": "an Intel GPU", "nvidia_gpu": "an NVIDIA GPU"}
    tiers = {"npu": "the NPU", "intel-gpu": "the Intel GPU", "nvidia": "the NVIDIA GPU", "cpu": "the CPU"}
    found = [labels[k] for k, v in hardware.items() if v.present]
    serving = [f"{join_and(b.models)} on {tiers[b.tier]}" for b in backends if b.available and b.models]
    empty = [f"{b.name} ({tiers[b.tier]})" for b in backends if b.available and not b.models]
    down = [b.name for b in backends if not b.available]
    stuck = [tiers[b.tier] for b in backends if b.available and b.generating is False]
    parts = [f"I'm running on a machine with {join_and(found) if found else 'no accelerators I can see'}."]
    parts.append(f"I can answer with {join_and(serving)}." if serving else "None of my local models are available right now.")
    if empty:
        parts.append(f"{join_and(empty)} {'is' if len(empty) == 1 else 'are'} running but {'has' if len(empty) == 1 else 'have'} no models yet.")
    if down:
        parts.append(f"Not running here: {join_and(down)}.")
    if stuck:
        parts.append(f"My model on {join_and(stuck)} is up but couldn't answer at my last check, so my answers may fall back to the next model.")
    if not mentor.reachable:
        parts.append("My mentor bridge isn't running, so I can't ask Claude for help right now.")
    elif not mentor.configured:
        parts.append("I can reach my mentor bridge, but it isn't set up to ask Claude yet.")
    else:
        parts.append("I'm online and can ask Claude for help.")
    return " ".join(parts)

def gather_capabilities() -> CapabilitiesResponse:
    with ThreadPoolExecutor(max_workers=8) as pool:
        backend_futures = [pool.submit(probe_backend, b) for b in BACKENDS]
        hardware_futures = {name: pool.submit(probe_hardware, name) for name in HARDWARE_QUERIES}
        mentor_future = pool.submit(probe_mentor)
        backends = [f.result() for f in backend_futures]
        hardware = {name: f.result() for name, f in hardware_futures.items()}
        mentor_status = mentor_future.result()
    return CapabilitiesResponse(
        checked_at=datetime.now(timezone.utc).isoformat(),
        profiles=active_profiles(),
        hardware=hardware,
        backends=backends,
        mentor=mentor_status,
        online=mentor_status.reachable,
        summary=describe(hardware, backends, mentor_status),
    )

@api.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities():
    with tracer.start_as_current_span("capabilities"):
        with _capabilities_lock:
            if _capabilities_cache["value"] is None or time.time() - _capabilities_cache["at"] > CAPABILITIES_CACHE_S:
                _capabilities_cache["value"] = gather_capabilities()
                _capabilities_cache["at"] = time.time()
            return _capabilities_cache["value"]


def live_self(caps: Optional[CapabilitiesResponse] = None) -> str:
    """AIden's current state in words, for questions about AIden themselves. Notes in the
    vault describe how AIden was built; this says what is true now, and wins."""
    import models
    import toolbox
    caps = caps or get_capabilities()
    by_name = {b.name: b for b in caps.backends}
    roles = {"ovms-npu": ("the NPU", "routing (does a message need the user's notes? yes/no), chat-UI tasks "
                          "(titles, tags, follow-ups) and fallback answers"),
             "ovms-gpu": ("the Intel GPU", "writing answers")}
    lines = ["AIden right now (live state; where a note says otherwise, this is current):"]
    for name, (device, job) in roles.items():
        b = by_name.get(name)
        if not b or not b.available:
            continue
        model = models.active_model(name) or (b.models[0] if b.models else "no model")
        state = "generating" if b.generating else ("not generating at the last check" if b.generating is False else "not checked yet")
        lines.append(f"- {device}: model {model}, used for {job}; {state}; "
                     f"{'can' if toolbox.offered(name) else 'cannot'} use tools.")
    lines += [
        "- The CPU: runs AIden's router, embeds questions and notes for vault search, and runs the tools themselves.",
        "- Tools: the answering model asks for them with TOOL: lines; AIden's router runs them on the CPU. They are "
        "read-only: time, uptime, memory, load, sleeps, the kernel's GPU warnings, model health, containers.",
        "- Models are chosen by AIden: candidates are tried, judged and switched only on evidence (the model steward does the work).",
        "- Memory: the current chat, plus the user's Obsidian vault (read-only). AIden doesn't remember past "
        "conversations yet; something said in this chat is gone in a new one.",
        f"- Mentor: Claude, {'reachable' if caps.mentor.reachable and caps.mentor.configured else 'not reachable right now'}.",
        f"- Summary: {caps.summary}",
    ]
    return "\n".join(lines)

"""AIden's gear check: "how are you doing?" answered from their own senses.

The report is built from measurements, never from a model, so it is accurate and works
even when every model is down:
- right now: which models can generate (senses.py) and how busy the hardware is;
- the last 24 hours: outages found in AIden's own probe log (Loki), container restarts
  and model-server errors (via docker-ro-proxy), the kernel's GPU warnings (journal);
- the machine: uptime, sleeps since boot, memory and load (terminal.py, read-only).
"""
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter

import models
import senses
import terminal
from capabilities import HARDWARE_QUERIES, get_capabilities, prometheus_value

api = APIRouter()

LOKI_URL = "http://loki:3100"
WINDOW_H = 24
DEVICES = {"ovms-gpu": ("GPU", "intel_gpu"), "ovms-npu": ("NPU", "npu"), "ollama": ("CPU (Ollama)", None)}
FAILURE_KINDS = [("crash", r"RemoteDisconnected|Connection aborted|ConnectionReset"),
                 ("hang", r"ReadTimeout|timed out"), ("stuck loading", r"not ready")]

TRIGGER = re.compile(
    r"\b(gear|status|health|self)[- ]?check\b"
    r"|\bhow are you (doing|feeling)\b"
    r"|\bhow(?:'s| is) (?:your|the) (?:gpu|npu|hardware|body|machine)\b"
    r"|\bhow are your (?:models|gpu|npu)\b", re.I)


def wanted(prompt: str) -> bool:
    return bool(TRIGGER.search(prompt or ""))


def local(ts: datetime) -> str:
    """HH:MM in local time, with the day when it isn't today."""
    ts, today = ts.astimezone(), datetime.now().astimezone().date()
    day = "" if ts.date() == today else ("yesterday " if (today - ts.date()).days == 1 else ts.strftime("%a "))
    return f"{day}{ts.strftime('%H:%M')}"


def probe_events(hours: int = WINDOW_H) -> List[Tuple[datetime, str]]:
    """AIden's own probe log lines from Loki, oldest first."""
    now = datetime.now(timezone.utc).timestamp()
    response = requests.get(f"{LOKI_URL}/loki/api/v1/query_range", timeout=10, params={
        "query": '{service_name="aiden-api"} |~ "could not generate|is not ready|generating again"',
        "start": int((now - hours * 3600) * 1e9), "end": int(now * 1e9), "limit": 1000, "direction": "forward"})
    response.raise_for_status()
    rows = [(int(t), line) for stream in response.json()["data"]["result"] for t, line in stream["values"]]
    return [(datetime.fromtimestamp(t / 1e9, timezone.utc), line) for t, line in sorted(rows)]


def outages(events: List[Tuple[datetime, str]]) -> Dict[str, List[Dict[str, Any]]]:
    """Per backend: each run of failed probes, its kind, when it began and when it recovered."""
    found: Dict[str, List[Dict[str, Any]]] = {}
    open_: Dict[str, Dict[str, Any]] = {}
    for at, line in events:
        name = line.split()[0]
        if "generating again" in line:
            if name in open_:
                open_.pop(name)["recovered"] = at
            continue
        if re.search(r"\(1 (?:in a row|probe\(s\) in a row)\)", line) and name in open_:
            # A fresh run of failures (e.g. after AIden restarted): the previous outage ended
            open_.pop(name)["ended_unseen"] = True
        if name not in open_:
            kind = next((k for k, pattern in FAILURE_KINDS if re.search(pattern, line)), "failure")
            open_[name] = {"kind": kind, "began": at, "recovered": None}
            found.setdefault(name, []).append(open_[name])
    return found


def describe_outage(o: Dict[str, Any], generating_now: bool) -> str:
    text = f"{o['kind']} at {local(o['began'])}"
    if o["recovered"]:
        return text + f" (back by {local(o['recovered'])})"
    if o.get("ended_unseen"):
        return text + " (ended later)"
    # No recovery line, e.g. AIden themselves restarted meanwhile: trust the latest probe
    return text + (" (recovered since)" if generating_now else " (not recovered yet)")


def sleeps(lines: List[str]) -> Optional[str]:
    """The last sleep, from the journal's suspend entry / return lines."""
    entered = [l for l in lines if "suspend entry" in l]
    returned = [l for l in lines if "returned from sleep" in l]
    if not entered or not returned:
        return None
    clock = lambda line: datetime.fromisoformat(line.split()[0]).astimezone().strftime("%H:%M")
    return f"last one {clock(entered[-1])}–{clock(returned[-1])}"


def gather() -> Dict[str, Any]:
    facts: Dict[str, Any] = {"checked_at": datetime.now(timezone.utc), "failed_checks": []}

    def look(command, /, **args):
        result = terminal.run(command, **args)
        if not result["ok"]:
            facts["failed_checks"].append(f"{command}{'(' + ', '.join(map(str, args.values())) + ')' if args else ''}: {result['error']}")
        return result.get("output")

    senses.probe_all()  # a gear check looks now, not at the last scheduled probe
    caps = get_capabilities()
    facts["backends"] = {b.name: b for b in caps.backends}
    facts["busy"] = {key: prometheus_value(query) for key, (_, query) in HARDWARE_QUERIES.items()}
    try:
        facts["outages"] = outages(probe_events())
    except (requests.RequestException, ValueError, KeyError) as exc:
        facts["outages"] = None
        facts["failed_checks"].append(f"probe history (Loki): {type(exc).__name__}")
    try:
        facts["model_changes"] = models.recent()
    except (OSError, ValueError):
        facts["model_changes"] = []
    for name in ("uptime", "memory", "load", "suspends", "sleep-log", "gpu-kernel-log"):
        facts[name] = look(name)
    facts["containers"] = {name: (look("container", name=name), look("container-errors", name=name))
                           for name in ("ovms-gpu", "ovms-npu") if name in facts["backends"]}
    return facts


def report(facts: Dict[str, Any]) -> str:
    lines = [f"**How I'm doing** (checked {local(facts['checked_at'])})", "", "**Right now**"]
    stuck = []
    for name, (label, hardware) in DEVICES.items():
        backend = facts["backends"].get(name)
        if not backend or (name == "ollama" and not backend.models):
            continue
        sensed = senses.status.get(name)
        model = backend.models[0] if backend.models else "no model"
        if not backend.available:
            state = "❌ not running"
            stuck.append(label)
        elif sensed is None:
            state = "⏳ up, not probed yet"
        elif sensed.get("error") == "server not ready":
            state = "❌ up but stuck loading its model"
            stuck.append(label)
        elif sensed["generating"]:
            state = "✅ generating"
        else:
            state = f"❌ up but can't generate ({sensed['error']})"
            stuck.append(label)
        busy = facts["busy"].get(hardware) if hardware else None
        tools = {True: " · can use tools", False: " · no tools (can't follow the protocol)"}.get(getattr(backend, "tools", None), "")
        lines.append(f"- {label} ({model}): {state}" + (f" · {busy:.0f}% busy" if busy is not None else "") + tools)
    if facts.get("memory") and facts.get("load"):
        m, l = facts["memory"], facts["load"]
        lines.append(f"- Memory: {m['available_gib']} of {m['total_gib']} GiB free · load {l['load_1m']} on {l['cpus']} CPUs")

    lines += ["", f"**Last {WINDOW_H} hours**"]
    rough = False
    for name, (label, _) in DEVICES.items():
        if name not in facts["backends"] or (name == "ollama" and not facts["backends"][name].models):
            continue
        found = (facts["outages"] or {}).get(name, [])
        parts = []
        if found:
            rough = True
            generating_now = (senses.status.get(name) or {}).get("generating") is True
            parts.append(f"{len(found)} outage{'s' if len(found) > 1 else ''}: "
                         + "; ".join(describe_outage(o, generating_now) for o in found))
        info, errors = facts["containers"].get(name, (None, None))
        if info and info["restarts"]:
            parts.append(f"{name} has restarted {info['restarts']} time{'s' if info['restarts'] > 1 else ''} since it was created")
        if errors:
            oom = sum("CL_OUT_OF_RESOURCES" in e for e in errors)
            parts.append(f"its log shows {len(errors)} error line{'s' if len(errors) > 1 else ''}"
                         + (f", {oom} of them CL_OUT_OF_RESOURCES" if oom else ""))
        if facts["outages"] is None and not parts:
            parts.append("I couldn't read my probe history")
        lines.append(f"- {label}: " + ("; ".join(parts) + "." if parts else "no problems."))

    lines += ["", "**Machine**"]
    up, sus = facts.get("uptime"), facts.get("suspends")
    if up:
        booted = datetime.fromisoformat(up["booted_at"])
        machine = f"Up {up['up_seconds'] // 3600} h (booted {booted.strftime('%a %H:%M')})"
        if sus:
            last = sleeps(facts.get("sleep-log") or [])
            machine += f"; {sus['since_boot']} sleep{'s' if sus['since_boot'] != 1 else ''} since boot" + (f", {last}" if last else "")
        lines.append(f"- {machine}.")
    kernel = facts.get("gpu-kernel-log")
    if kernel is not None:
        if kernel:
            latest = kernel[-1].split("] ", 1)[-1][:90]
            lines.append(f"- Kernel: {len(kernel)} GPU warning{'s' if len(kernel) != 1 else ''} this boot; "
                         f"latest at {datetime.fromisoformat(kernel[-1].split()[0]).strftime('%H:%M')}: \"{latest}\".")
        else:
            lines.append("- Kernel: no GPU warnings this boot.")
    if facts["failed_checks"]:
        lines.append("- Couldn't check: " + "; ".join(facts["failed_checks"]) + ".")

    changes = [r for r in facts.get("model_changes") or []
               if r.get("action") in ("switched", "rolled_back", "rejected", "shadow_started")]
    if changes:
        lines += ["", "**Recent model changes**"]
        for r in changes[-5:]:
            when = local(datetime.fromisoformat(r["at"]))
            if r["action"] == "switched":
                lines.append(f"- {when}: switched my {r['device'].upper()} to {r['name']} ({r['reason']}).")
            elif r["action"] == "shadow_started":
                lines.append(f"- {when}: trying {r['name']} silently on my {r['device'].upper()} before switching ({r['reason']}).")
            elif r["action"] == "rolled_back":
                lines.append(f"- {when}: rolled my {r['device'].upper()} back to {r['back_to']} ({r['reason']}).")
            else:
                lines.append(f"- {when}: tried {r['name']} on my {r['device'].upper()}, kept the current one ({r['reason']}).")

    lines += [""]
    if stuck:
        verdict = f"My {' and '.join(stuck)} can't answer right now, so I'm answering on what's left."
        if "GPU" in stuck and sus and sus["since_boot"]:
            verdict += " This has followed sleep cycles before; a reboot clears it."
    elif rough:
        verdict = "All good now, but I had a rough patch; I recovered each time."
    else:
        verdict = "All good: everything is working."
    lines.append(f"**Verdict:** {verdict}")
    return "\n".join(lines)


def check() -> Tuple[str, Dict[str, Any]]:
    facts = gather()
    return report(facts), facts


@api.get("/selfcheck", summary="AIden's gear check: how their models and machine are doing")
def selfcheck_endpoint():
    text, facts = check()
    return {"report": text, "failed_checks": facts["failed_checks"]}

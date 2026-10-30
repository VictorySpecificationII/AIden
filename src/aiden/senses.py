"""AIden's senses: noticing whether their own models can still think.

A health check only proves a model server is up; the Intel GPU can be up and unable to
generate (after many suspend cycles it fails with CL_OUT_OF_RESOURCES). Every
PROBE_INTERVAL_S AIden asks each local model that is up for a one-token answer and keeps
what they learned in `status`: whether it generated, how long it took, consecutive
failures. /capabilities reports it, and the aiden_backend_generating metric lets
Prometheus alert on it.
"""
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import requests
from opentelemetry import metrics
from opentelemetry.metrics import Observation

PROBE_INTERVAL_S = int(os.environ.get("AIDEN_PROBE_INTERVAL", "900"))
PROBE_TIMEOUT_S = 60
STARTUP_GRACE_S = 120

logger = logging.getLogger("aiden.senses")
status: Dict[str, Dict[str, Any]] = {}
# Whether each backend's model can use AIden's tool protocol (see toolbox.py), tested once per model
tool_status: Dict[str, Dict[str, Any]] = {}
GARBLED_TOOL_LINE = re.compile(r"^[\s`*>]*[A-Z]{2,}:\s*[a-z_]+")
TOOL_TESTS = [  # (question, should it ask for a tool?)
    ("What time is it right now?", True),
    ("What is 2 + 2?", False),
]


def probe(name: str, base_url: str, model: str) -> Dict[str, Any]:
    """Ask one backend for a one-token answer and remember how it went."""
    previous = status.get(name, {})
    start = time.time()
    try:
        response = requests.post(f"{base_url}/chat/completions", timeout=PROBE_TIMEOUT_S,
                                 json={"model": model, "max_tokens": 1,
                                       "messages": [{"role": "user", "content": "Say OK."}]})
        response.raise_for_status()
        response.json()["choices"][0]
        result = {"generating": True, "error": None, "failures": 0,
                  "last_ok": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        result = {"generating": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                  "failures": previous.get("failures", 0) + 1, "last_ok": previous.get("last_ok")}
        logger.warning("%s could not generate (%d in a row): %s", name, result["failures"], result["error"])
    if result["generating"] and previous.get("failures"):
        logger.info("%s is generating again after %d failed probe(s)", name, previous["failures"])
    result.update(model=model, seconds=round(time.time() - start, 2),
                  checked_at=datetime.now(timezone.utc).isoformat())
    status[name] = result
    return result


def ask(base_url: str, model: str, messages) -> str:
    response = requests.post(f"{base_url}/chat/completions", timeout=PROBE_TIMEOUT_S, json={
        "model": model, "messages": messages, "max_tokens": 60, "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False}})
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"] or ""


def follows_tool_protocol(base_url: str, model: str) -> Tuple[bool, str]:
    """Can this model follow AIden's tool protocol? It must ask for a tool when the question
    needs one, and answer plainly when it doesn't (tools mustn't make ordinary answers worse)."""
    from router import build_messages
    import toolbox
    results = []
    try:
        for question, needs_tool in TOOL_TESTS:
            reply = ask(base_url, model, toolbox.with_instruction(build_messages([{"role": "user", "content": question}], [])))
            calls = toolbox.parse(reply)
            asked = bool(calls) and calls[0]["name"] in toolbox.TOOLS
            plain = not GARBLED_TOOL_LINE.match(reply)  # no (garbled) tool line either, e.g. "TOOMANK: suspends {}"
            results.append(asked if needs_tool else (plain and not calls))
        passed = all(results)
        return passed, "follows the tool protocol" if passed else "doesn't follow the tool protocol reliably"
    except Exception as exc:  # untested: no tools until a later probe succeeds
        return False, f"test failed: {type(exc).__name__}"


def test_tools(name: str, base_url: str, model: str) -> Dict[str, Any]:
    passed, detail = follows_tool_protocol(base_url, model)
    tool_status[name] = {"model": model, "tools": passed, "detail": detail,
                         "checked_at": datetime.now(timezone.utc).isoformat()}
    logger.info("%s (%s): %s", name, model, detail)
    return tool_status[name]


def not_ready(name: str):
    """An expected backend that isn't even up (e.g. stuck loading its model) can't generate."""
    previous = status.get(name, {})
    status[name] = {"generating": False, "error": "server not ready", "failures": previous.get("failures", 0) + 1,
                    "last_ok": previous.get("last_ok"), "model": previous.get("model", "unknown"), "seconds": None,
                    "checked_at": datetime.now(timezone.utc).isoformat()}
    logger.warning("%s is not ready (%d probe(s) in a row)", name, status[name]["failures"])


def probe_all():
    from capabilities import active_profiles, get_capabilities
    from router import candidate_backends
    capabilities = get_capabilities()
    ready = {name: (base_url, model) for name, base_url, model in candidate_backends(capabilities)}
    profiles = active_profiles()
    for backend in capabilities.backends:
        if backend.name in ready:
            result = probe(backend.name, *ready[backend.name])
            import models
            models.watch(backend.name, result)  # roll back a freshly switched model that keeps failing
            model = ready[backend.name][1]
            tested = tool_status.get(backend.name, {})
            if result["generating"] and (tested.get("model") != model or tested.get("detail", "").startswith("test failed")):
                test_tools(backend.name, *ready[backend.name])
        elif backend.tier in profiles and (not backend.available or backend.name != "ollama"):
            # Expected here but down, or a model server up without its model (stuck loading).
            # Ollama without models is just empty, not broken.
            not_ready(backend.name)


def observe(options):
    return [Observation(1 if s["generating"] else 0, {"backend": name})
            for name, s in list(status.items())]


metrics.get_meter("aiden").create_observable_gauge(
    name="aiden_backend_generating", callbacks=[observe],
    description="Whether the backend produced a token at AIden's last probe (1) or not (0)", unit="1")


def run_forever():
    time.sleep(STARTUP_GRACE_S)  # let the model servers load first
    while True:
        try:
            probe_all()
        except Exception:  # keep sensing; the next round retries
            logger.exception("Probing the backends failed")
        time.sleep(PROBE_INTERVAL_S)


def start():
    threading.Thread(target=run_forever, daemon=True, name="senses").start()

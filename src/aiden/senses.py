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
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from opentelemetry import metrics
from opentelemetry.metrics import Observation

PROBE_INTERVAL_S = int(os.environ.get("AIDEN_PROBE_INTERVAL", "900"))
PROBE_TIMEOUT_S = 60
STARTUP_GRACE_S = 120

logger = logging.getLogger("aiden.senses")
status: Dict[str, Dict[str, Any]] = {}


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
            probe(backend.name, *ready[backend.name])
        elif backend.tier in profiles and not backend.available:  # expected here, but down
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

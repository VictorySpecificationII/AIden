"""Vault endpoints and metrics (AIden's memory of the user's notes; local only).
The indexing and search logic itself is in vault.py."""
import requests
from fastapi import APIRouter
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.metrics import Observation

import vault
from telemetry import meter, tracer

api = APIRouter()

@api.get("/vault/status")
def vault_status():
    return vault.status

@api.get("/vault/search")
def vault_search(q: str, k: int = 5):
    with tracer.start_as_current_span("vault.search") as span:
        span.set_attribute("vault.k", k)
        return {"query": q, "results": vault.search(q, k)}

def vault_gauge(key: str):
    def callback(_):
        yield Observation(vault.status.get(key) or 0)
    return callback

def vault_chunks(_):
    # Live count from Qdrant, so progress shows during the first (long) scan too
    try:
        with suppress_instrumentation():  # runs every export interval; not worth a trace
            count = vault.count_chunks()
        yield Observation(count)
    except requests.RequestException:
        return

meter.create_observable_gauge(
    name="aiden_vault_chunks",
    callbacks=[vault_chunks],
    description="Chunks in the vault index",
    unit="{chunks}"
)
meter.create_observable_gauge(
    name="aiden_vault_pending_notes",
    callbacks=[vault_gauge("pending_notes")],
    description="Notes still waiting to be (re)indexed in the current scan",
    unit="{notes}"
)

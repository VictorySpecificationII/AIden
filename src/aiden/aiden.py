"""AIden's API service: assembles the app from its parts.

    telemetry.py     OpenTelemetry setup and instrumentation
    capabilities.py  /capabilities: what this machine offers
    chat_api.py      /v1/models, /v1/chat/completions: AIden as a model (router.py, mentor.py)
    vault_api.py     /vault/*: the vault index (vault.py)
    tools.py         /tool/*, /tools: the original date/time tools
"""
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import capabilities
import chat_api
import feedback
import selfcheck
import senses
import tools
import vault
import vault_api
import telemetry
from telemetry import error_counter, latency_histogram, logger, request_counter, tracer

# --- FastAPI Tool Server ---
app = FastAPI(
    title="Aiden Tool Server",
    description="A collection of utility tools exposed via OpenAPI, with integrated telemetry and observability.",
    version="1.0.0",
    contact={
        "name": "IntellectualPlayspace",
        "url": "https://intellectualplay.space",
        "email": "andrew@intellectualplay.space",
    }
)

telemetry.instrument(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    start = time.time()
    response = None
    # The request span itself comes from FastAPIInstrumentor; this middleware does metrics and logs
    logger.info("Handling request %s", request.url)
    try:
        response = await call_next(request)
    except Exception:
        # Don't swallow it (a return in finally did, leaving clients hanging): log, count, re-raise
        error_counter.add(1)
        logger.exception("Unhandled error while handling %s", request.url)
        raise
    finally:
        latency_histogram.record(time.time() - start)
        request_counter.add(1)
    if response.status_code >= 400:
        error_counter.add(1)
        logger.error("Error response from %s: %d", request.url, response.status_code)
    logger.info("Request completed: %s", request.url)
    return response

@app.on_event("startup")
def start_background_work():
    vault.start(tracer)
    feedback.start()
    senses.start()

app.include_router(tools.api)
app.include_router(vault_api.api)
app.include_router(capabilities.api)
app.include_router(chat_api.api)
app.include_router(selfcheck.api)

@app.get("/", include_in_schema=False)
def root():
    return {
        "API Docs": "/docs",
        "Redoc": "/redoc",
        "OpenAPI Spec": "/openapi.json",
        "Tools": "/tools",
        "Capabilities": "/capabilities",
        "Vault status": "/vault/status",
        "Vault search": "/vault/search?q=..."
    }

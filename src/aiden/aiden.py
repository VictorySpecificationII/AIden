import logging
import os
import threading
import time
import psutil
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

import router
import vault

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from urllib.parse import urlparse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.metrics import Observation

# --- Tool Server Models ---
class DateResponse(BaseModel):
    date: str

class TimeSimpleResponse(BaseModel):
    time: str

class TimeISOResponse(BaseModel):
    time_iso: str

class ErrorResponse(BaseModel):
    error: str

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

# --- Tools class ---
class Tools:
    class Valves(BaseModel):
        pass

    class UserValves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()

    def get_current_date(self) -> str:
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        return f"Today's date is {current_date}"

    def get_current_time(self) -> str:
        current_time = datetime.now().strftime("%H:%M:%S")
        return f"Current Time: {current_time}"

# --- OpenTelemetry Setup ---
def configure_telemetry(service_name: str = "aiden-api"):
    resource = Resource.create({"service.name": service_name})

    # Tracing
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()
    trace_exporter = OTLPSpanExporter(endpoint="http://otel-collector:4317")
    tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

    # Logging
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    log_exporter = OTLPLogExporter(endpoint="http://otel-collector:4317", insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)
    # urllib3 logs every outbound HTTP call at DEBUG, burying AIden's own log lines
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Metrics
    metric_exporter = OTLPMetricExporter(endpoint="http://otel-collector:4317")
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=20000)
    # Buckets sized for the router (the defaults start at 0-5 s, too coarse for a 150 ms search)
    views = [
        View(instrument_name="aiden_route_stage_latency", aggregation=ExplicitBucketHistogramAggregation(
            boundaries=[0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60, 120])),
        View(instrument_name="aiden_answer_tokens", aggregation=ExplicitBucketHistogramAggregation(
            boundaries=[1, 2, 4, 6, 8, 10, 12, 15, 20, 30, 50])),
    ]
    meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource, views=views)
    metrics.set_meter_provider(meter_provider)

    return {
        "logger": logging.getLogger(),
        "meter": metrics.get_meter(service_name),
        "tracer": trace.get_tracer(service_name),
    }

def create_metrics(meter):
    latency_histogram = meter.create_histogram(
        name="aiden_service_latency",
        description="Histogram of request latencies in seconds",
        unit="s"
    )
    request_counter = meter.create_counter(
        name="aiden_service_requests",
        description="Total number of handled requests",
        unit="1"
    )
    error_counter = meter.create_counter(
        name="aiden_service_errors",
        description="Total number of errors",
        unit="1"
    )

    def cpu_callback(_):
        for i, p in enumerate(psutil.cpu_percent(percpu=True)):
            yield Observation(p, {"cpu": str(i)})

    def ram_callback(_):
        yield Observation(psutil.virtual_memory().percent)

    meter.create_observable_gauge(
        name="aiden_cpu_percent",
        callbacks=[cpu_callback],
        description="CPU usage percent per core",
        unit="1"
    )
    meter.create_observable_gauge(
        name="aiden_ram_percent",
        callbacks=[ram_callback],
        description="RAM usage percent",
        unit="1"
    )

    return latency_histogram, request_counter, error_counter

# --- Init telemetry ---
telemetry = configure_telemetry()
logger = telemetry["logger"]
meter = telemetry["meter"]
tracer = telemetry["tracer"]
latency_histogram, request_counter, error_counter = create_metrics(meter)

tools = Tools()

# --- Capabilities (AIden's view of the machine they're running on) ---
PROMETHEUS_URL = "http://prometheus:9090"
MENTOR_URL = os.environ.get("AIDEN_MENTOR_URL", "https://api.anthropic.com/v1/models")
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
        return BackendStatus(name=backend["name"], tier=tier, url=backend["url"], available=True,
                             models=models, latency_ms=round((time.time() - start) * 1000, 1))
    except (requests.RequestException, ValueError, KeyError) as exc:
        return BackendStatus(name=backend["name"], tier=tier, url=backend["url"], available=False,
                             error=type(exc).__name__)

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
    # Any HTTP answer (even 401 without a key) proves the network path to Claude works
    try:
        requests.get(MENTOR_URL, timeout=PROBE_TIMEOUT_S)
        reachable = True
    except requests.RequestException:
        reachable = False
    return MentorStatus(name="claude", reachable=reachable, configured=bool(os.environ.get("ANTHROPIC_API_KEY")))

def join_and(items: List[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"

def describe(hardware: Dict[str, HardwareStatus], backends: List[BackendStatus], mentor: MentorStatus) -> str:
    labels = {"npu": "an Intel NPU", "intel_gpu": "an Intel GPU", "nvidia_gpu": "an NVIDIA GPU"}
    tiers = {"npu": "the NPU", "intel-gpu": "the Intel GPU", "nvidia": "the NVIDIA GPU", "cpu": "the CPU"}
    found = [labels[k] for k, v in hardware.items() if v.present]
    serving = [f"{join_and(b.models)} on {tiers[b.tier]}" for b in backends if b.available and b.models]
    empty = [f"{b.name} ({tiers[b.tier]})" for b in backends if b.available and not b.models]
    down = [b.name for b in backends if not b.available]
    parts = [f"I'm running on a machine with {join_and(found) if found else 'no accelerators I can see'}."]
    parts.append(f"I can answer with {join_and(serving)}." if serving else "None of my local models are available right now.")
    if empty:
        parts.append(f"{join_and(empty)} {'is' if len(empty) == 1 else 'are'} running but {'has' if len(empty) == 1 else 'have'} no models yet.")
    if down:
        parts.append(f"Not running here: {join_and(down)}.")
    if not mentor.reachable:
        parts.append("I'm offline, so I can't ask Claude for help.")
    elif not mentor.configured:
        parts.append("I can reach Claude, but no API key is configured yet.")
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
        mentor = mentor_future.result()
    return CapabilitiesResponse(
        checked_at=datetime.now(timezone.utc).isoformat(),
        profiles=active_profiles(),
        hardware=hardware,
        backends=backends,
        mentor=mentor,
        online=mentor.reachable,
        summary=describe(hardware, backends, mentor),
    )

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

FastAPIInstrumentor.instrument_app(app)
# Child spans for every outgoing HTTP call (NPU/GPU/embeddings/Qdrant/Prometheus/mentor)
def name_outgoing_span(span, request):
    # Default span names are just "GET"/"POST"; name them after the destination instead
    url = urlparse(request.url)
    span.update_name(f"{request.method} {url.hostname} {url.path}")

RequestsInstrumentor().instrument(request_hook=name_outgoing_span)
# Carry the trace context into ThreadPoolExecutor workers (/capabilities probes in parallel)
ThreadingInstrumentor().instrument()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth (Allow all bearer tokens) ---
auth_scheme = HTTPBearer()

def allow_all_tokens(auth: HTTPAuthorizationCredentials = Security(auth_scheme)):
    # No validation – accept any bearer token
    return auth.credentials

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

# --- Tool Endpoints ---

@app.get("/tool/get_date", response_model=DateResponse)
def get_date(token: str = Depends(allow_all_tokens)):
    with tracer.start_as_current_span("tool.get_current_date"):
        date_str = tools.get_current_date().replace("Today's date is ", "")
        return {"date": date_str}

@app.get("/tool/get_time_simple", response_model=TimeSimpleResponse)
def get_time_simple(token: str = Depends(allow_all_tokens)):
    with tracer.start_as_current_span("tool.get_current_time_simple"):
        time_str = tools.get_current_time().replace("Current Time: ", "")
        return {"time": time_str}

@app.get("/tool/get_time", response_model=TimeISOResponse)
def get_time(iso: bool = True, token: str = Depends(allow_all_tokens)):
    with tracer.start_as_current_span("tool.get_current_time"):
        if iso:
            now = datetime.now(timezone.utc).astimezone()
            return {"time_iso": now.isoformat()}
        return {"time_iso": datetime.now().isoformat()}

# --- Vault (AIden's memory of the user's notes; local only) ---

@app.on_event("startup")
def start_vault_indexer():
    vault.start(tracer)

@app.get("/vault/status")
def vault_status():
    return vault.status

@app.get("/vault/search")
def vault_search(q: str, k: int = 5):
    with tracer.start_as_current_span("vault.search") as span:
        span.set_attribute("vault.k", k)
        return {"query": q, "results": vault.search(q, k)}

@app.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities():
    with tracer.start_as_current_span("capabilities"):
        with _capabilities_lock:
            if _capabilities_cache["value"] is None or time.time() - _capabilities_cache["at"] > CAPABILITIES_CACHE_S:
                _capabilities_cache["value"] = gather_capabilities()
                _capabilities_cache["at"] = time.time()
            return _capabilities_cache["value"]

# --- Router: AIden as an OpenAI-compatible model (see router.py) ---

route_counter = meter.create_counter(
    name="aiden_route_decisions",
    description="How the router decided whether a request needed the user's notes",
    unit="1"
)
stage_histogram = meter.create_histogram(
    name="aiden_route_stage_latency",
    description="Latency of each routing stage",
    unit="s"
)
# The collector appends the unit, so this is exported as aiden_answer_tokens_per_second
tokens_histogram = meter.create_histogram(
    name="aiden_answer_tokens",
    description="Generation speed of the answering backend",
    unit="1/s"
)

fallback_counter = meter.create_counter(
    name="aiden_route_fallbacks",
    description="Answers that fell back to the next backend tier",
    unit="1"
)

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

@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": "aiden", "object": "model", "owned_by": "aiden"}]}

@app.post("/v1/chat/completions")
def chat_completions(body: Dict[str, Any]):
    messages = body.get("messages", [])
    prompt = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    if isinstance(prompt, list):  # multi-part content: keep the text parts
        prompt = " ".join(p.get("text", "") for p in prompt if isinstance(p, dict))

    # The trace explains each decision; it records the prompt's length, never its text
    trace.get_current_span().set_attribute("router.prompt_chars", len(prompt))

    with tracer.start_as_current_span("router.decide") as span:
        start = time.time()
        wants_notes, decided_by, reason = router.needs_notes(prompt)
        stage_histogram.record(time.time() - start, {"stage": "decide", "decided_by": decided_by})
        route_counter.add(1, {"needs_notes": str(wants_notes).lower(), "decided_by": decided_by})
        span.set_attribute("router.needs_notes", wants_notes)
        span.set_attribute("router.decided_by", decided_by)
        span.set_attribute("router.reason", reason)
        logger.info("Notes %s (%s: %s)", "needed" if wants_notes else "not needed", decided_by, reason)

    notes = []
    if wants_notes:
        with tracer.start_as_current_span("router.retrieve") as span:
            start = time.time()
            notes, matches = router.retrieve(prompt)
            stage_histogram.record(time.time() - start, {"stage": "retrieve"})
            span.set_attribute("router.embed_device", "cpu")
            span.set_attribute("router.min_score", router.MIN_NOTE_SCORE)
            span.set_attribute("router.notes_found", len(notes))
            span.set_attribute("router.notes_below_threshold", len(matches) - len(notes))
            # Note paths and scores only: vault text stays out of traces
            span.set_attribute("router.notes", [f"{n['score']:.3f} {n['path']} › {n['heading']}" for n in matches])
            logger.info("Vault search: %d of %d matches above %.2f", len(notes), len(matches), router.MIN_NOTE_SCORE)

    out_messages = router.build_messages(messages, notes)
    stream = bool(body.get("stream"))
    response, skipped = None, []
    candidates = router.candidate_backends(get_capabilities())
    trace.get_current_span().set_attribute("router.candidates", [c[0] for c in candidates])
    for name, base, model in candidates:
        span = tracer.start_span("router.answer", attributes={"router.backend": name, "router.model": model,
                                                             "router.notes_used": len(notes), "router.stream": stream})
        start = time.time()
        try:
            # Current span, so the outgoing HTTP call shows up as its child
            with trace.use_span(span, end_on_exit=False):
                response = router.backend_request(base, model, out_messages, stream, body, notes)
            break
        except requests.RequestException as exc:
            # Fall back to the next tier (e.g. GPU wedged -> NPU -> CPU)
            skipped.append(name)
            span.set_attribute("router.error", type(exc).__name__)
            span.add_event("fallback", {"from": name, "error": type(exc).__name__})
            span.end()
            fallback_counter.add(1, {"from": name})
            logger.warning("Backend %s failed (%s), falling back", name, type(exc).__name__)
    if response is None:
        logger.error("No backend answered (tried %s)", ", ".join(skipped) or "none available")
        return JSONResponse(status_code=503, content={"error": {
            "message": "None of my local models answered right now.", "type": "unavailable", "tried": skipped}})
    span.set_attribute("router.skipped", ",".join(skipped))
    logger.info("Answering with %s on %s%s", model, name, f" after {', '.join(skipped)} failed" if skipped else "")

    def finished(tokens: int, seconds: float):
        stage_histogram.record(time.time() - start, {"stage": "answer", "backend": name})
        span.set_attribute("router.answer_tokens", tokens)
        if tokens and seconds > 0:
            tokens_histogram.record(tokens / seconds, {"backend": name})
            span.set_attribute("router.tokens_per_second", round(tokens / seconds, 1))
        span.end()

    if stream:
        route = router.route_footer(name, model, router.passed_over(name, candidates, skipped))
        return StreamingResponse(router.stream_answer(response, notes, finished, route), media_type="text/event-stream")

    result = response.json()
    usage = result.get("usage", {})
    finished(usage.get("completion_tokens", 0), time.time() - start)
    result["model"] = "aiden"
    if result.get("choices"):
        answer = result["choices"][0]["message"]["content"]
        result["choices"][0]["message"]["content"] = (answer + router.sources_footer(notes, answer)
                                                     + router.route_footer(name, model, router.passed_over(name, candidates, skipped)))
    result["aiden"] = {"backend": name, "model": model, "skipped": skipped, "needs_notes": wants_notes, "decided_by": decided_by,
                       "notes": [{"path": n["path"], "heading": n["heading"], "score": n["score"]} for n in notes]}
    return result

# --- Tool Discovery ---

@app.get("/tools", response_model=Dict[str, str])
def list_tools():
    return {
        "get_date": "Return today's date",
        "get_time_simple": "Return the current time in HH:MM:SS",
        "get_time": "Return current time in ISO 8601 format",
    }

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

import logging
import time
import psutil
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
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

    # Metrics
    metric_exporter = OTLPMetricExporter(endpoint="http://otel-collector:4317")
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=20000)
    meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
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
    with tracer.start_as_current_span("http_request"):
        logger.info("Handling request %s", request.url)
        try:
            response = await call_next(request)
        finally:
            end = time.time()
            latency_histogram.record(end - start)
            request_counter.add(1)
            if response and response.status_code >= 400:
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
        "Tools": "/tools"
    }

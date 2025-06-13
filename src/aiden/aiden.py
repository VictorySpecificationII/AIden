import logging
import time
import psutil
from datetime import datetime, timezone
from typing import Any, Dict, Callable

# third-party imports
from fastapi import FastAPI, Request, Response
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

# Your Tools class (unchanged except added here for completeness)
from pydantic import BaseModel


class Tools:
    class Valves(BaseModel):
        pass

    class UserValves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()

    def get_current_date(self) -> str:
        """
        Get the current date.
        :return: The current date as a string.
        """
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        return f"Today's date is {current_date}"

    def get_current_time(self) -> str:
        """
        Get the current time.
        :return: The current time as a string.
        """
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


# Initialize telemetry
telemetry = configure_telemetry()
logger = telemetry["logger"]
meter = telemetry["meter"]
tracer = telemetry["tracer"]
latency_histogram, request_counter, error_counter = create_metrics(meter)

# Instantiate your Tools class once
tools = Tools()

# --- Tool wrappers that expose your class methods with tracing and dict output ---
def get_current_date_tool() -> Dict[str, str]:
    with tracer.start_as_current_span("tool.get_current_date"):
        date_str = tools.get_current_date().replace("Today's date is ", "")
        return {"date": date_str}

def get_current_time_tool() -> Dict[str, str]:
    with tracer.start_as_current_span("tool.get_current_time_simple"):
        time_str = tools.get_current_time().replace("Current Time: ", "")
        return {"time": time_str}

# Existing example tool for ISO time
def get_current_time(iso: bool = True) -> Dict[str, str]:
    with tracer.start_as_current_span("tool.get_current_time"):
        if iso:
            now = datetime.now(timezone.utc).astimezone()
            return {"time_iso": now.isoformat()}
        return {"time": time.ctime()}

# Tool registry
TOOL_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {
    "get_date": get_current_date_tool,
    "get_time_simple": get_current_time_tool,
    "get_time": get_current_time,
}

# --- FastAPI app setup ---
app = FastAPI()
FastAPIInstrumentor.instrument_app(app)

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

# Routes
@app.get('/')
def home():
    return {"API": "http://localhost:8000/docs", "Documentation": "http://localhost:8000/redoc"}

@app.get('/tool/{tool_name}')
async def run_tool(tool_name: str, iso: bool = True):
    try:
        # Pass iso only if tool supports it (get_time)
        if tool_name == "get_time":
            result = TOOL_REGISTRY[tool_name](iso=iso)
        else:
            result = TOOL_REGISTRY[tool_name]()
        return result
    except KeyError:
        return {"error": f"Tool '{tool_name}' not found"}


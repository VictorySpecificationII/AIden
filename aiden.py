import logging
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter # use for metrics
from opentelemetry.metrics import Counter, Histogram, ObservableGauge
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry import metrics
from opentelemetry.metrics import Observation, CallbackOptions

import psutil
import time
import random
from starlette.exceptions import HTTPException
import asyncio

api = FastAPI()

def configure_opentelemetry():
    resource = Resource.create({"service.name": "fastapi-service"})
    
    # Configure tracing
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()
    otlp_trace_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
    
    # Configure logging
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    otlp_log_exporter = OTLPLogExporter(endpoint="http://localhost:4317", insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))
    handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)
    
    # Configure metrics
    exporter = OTLPMetricExporter(endpoint="http://localhost:4317")
    metric_reader = PeriodicExportingMetricReader(exporter, export_interval_millis=20000)
    meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
    metrics.set_meter_provider(meter_provider)

    # Return configured meter
    return metrics.get_meter(__name__)

meter = configure_opentelemetry()

latency_histogram = meter.create_histogram(name="aiden_service_latency", description="Histogram of request latencies in seconds", unit="s")
request_counter = meter.create_counter(name="aiden_service_requests", description="Counter for the number of requests handled", unit="1")
error_counter = meter.create_counter(name="aiden_service_errors", description="Counter for the number of errors encountered", unit="1")

def get_cpu_usage_callback(_):
    for (number, percent) in enumerate(psutil.cpu_percent(percpu=True)):
        attributes = {"cpu_number": str(number)}
        yield Observation(percent, attributes)

def get_ram_usage_callback(_):
    ram_percent = psutil.virtual_memory().percent
    yield Observation(ram_percent)

cpu_gauge = meter.create_observable_gauge(callbacks=[get_cpu_usage_callback], name="aiden_cpu_percent", description="per-cpu usage", unit="1")
ram_gauge = meter.create_observable_gauge(callbacks=[get_ram_usage_callback], name="aiden_ram_percent", description="RAM memory usage", unit="1")

@api.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    tracer = trace.get_tracer(__name__)
    logger = logging.getLogger(__name__)
    start_time = time.time()

    with tracer.start_as_current_span("http_request"):
        logger.info("Processing request: %s", request.url)
        try:
            response = await call_next(request)
        finally:
            end_time = time.time()
            latency_histogram.record(end_time - start_time)
            request_counter.add(1)

            if response.status_code >= 400:
                error_counter.add(1)
                logger.error("Request to %s resulted in error %s", request.url, response.status_code)

            logger.info("Completed request: %s", request.url)
            return response

@api.get("/")
async def root():
    logging.debug("Root endpoint hit")
    return {"message": "Welcome to AIden's API server."}

@api.get("/items/{item_id}")
async def read_item(item_id: int):
    logging.debug(f"Item ID: {item_id} requested")
    return {"item_id": item_id}

@api.get("/latency")
async def simulate_latency():
    delay = random.uniform(0.1, 2.0)
    await asyncio.sleep(delay)
    return {"message": f"Simulated latency of {delay:.2f} seconds"}

@api.get("/error")
async def trigger_error():
    raise HTTPException(status_code=500, detail="This is a test error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.debug("Starting up...")
    yield
    logging.debug("Shutting down...")

api.lifespan = lifespan

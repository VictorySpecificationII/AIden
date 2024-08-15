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

import psutil
import time

def configure_opentelemetry():
    # Set up the TracerProvider
    trace.set_tracer_provider(TracerProvider())
    tracer_provider = trace.get_tracer_provider()

    # Set up OTLP exporter for traces
    otlp_trace_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")  # Adjust endpoint as needed

    # Set up BatchSpanProcessor for traces
    span_processor = BatchSpanProcessor(otlp_trace_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Set up LoggerProvider with OTLP log exporter
    logger_provider = LoggerProvider(
        resource=Resource.create(
            {
                "service.name": "fastapi-service",
                "service.instance.id": "instance-1",
            }
        ),
    )
    set_logger_provider(logger_provider)

    otlp_log_exporter = OTLPLogExporter(endpoint="http://localhost:4317", insecure=True)  # Adjust endpoint as needed
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))

    # Set up LoggingHandler with the logger provider

    logging.basicConfig(level=logging.INFO)
    handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)  # Set level to DEBUG
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)  # Set root logger level to DEBUG


def configure_metrics():
    # # Initialize the OTLP metric exporter
    exporter = OTLPMetricExporter(endpoint="http://localhost:4317")  # Adjust endpoint as needed
    metric_reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
    provider = MeterProvider(metric_readers=[metric_reader], resource=Resource.create(
        {"service.name": "fastapi-service"}
    ))

    metrics.set_meter_provider(provider)
    # Creates a meter from the global meter provider
    meter = metrics.get_meter(__name__)

    # Define latency metric
    latency_histogram = meter.create_histogram(
        name="service_latency",
        description="Histogram of request latencies in seconds",
        unit="s"
    )

    return meter, latency_histogram

api = FastAPI()

# Integrate OpenTelemetry with FastAPI
FastAPIInstrumentor.instrument_app(api)

@api.middleware("http")
async def tracing_middleware(request: Request, call_next):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("http_request"):
        logger = logging.getLogger(__name__)
        logger.info("Processing request: %s", request.url)
        response = await call_next(request)
        logger.info("Completed request: %s", request.url)
        return response

# Middleware for metrics
@api.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    end_time = time.time()
    latency = end_time - start_time
    latency_histogram.record(latency)
    return response

@api.get("/")
async def root():
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("root_endpoint"):
        logging.debug("Root endpoint hit")
        return {"message": "Welcome to AIden's API server."}

@api.get("/items/{item_id}")
async def read_item(item_id: int):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("read_item_endpoint") as span:
        span.set_attribute("item_id", item_id)
        logging.debug(f"Item ID: {item_id} requested")
        return {"item_id": item_id}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.debug("Starting up...")
    yield
    logging.debug("Shutting down...")

api.lifespan = lifespan

configure_opentelemetry()
meter, latency_histogram = configure_metrics()

api.add_middleware(OpenTelemetryMiddleware)

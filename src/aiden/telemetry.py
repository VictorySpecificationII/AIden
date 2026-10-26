"""OpenTelemetry setup for the aiden service: traces, logs and metrics to the collector,
plus instrumentation of incoming requests, outgoing HTTP calls and worker threads."""
import logging
from urllib.parse import urlparse

import psutil
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.metrics import Observation
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


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

def name_outgoing_span(span, request):
    # Default span names are just "GET"/"POST"; name them after the destination instead
    url = urlparse(request.url)
    span.update_name(f"{request.method} {url.hostname} {url.path}")

def instrument(app):
    FastAPIInstrumentor.instrument_app(app)
    # Child spans for every outgoing HTTP call (NPU/GPU/embeddings/Qdrant/Prometheus/mentor)
    RequestsInstrumentor().instrument(request_hook=name_outgoing_span)
    # Carry the trace context into ThreadPoolExecutor workers (/capabilities probes in parallel)
    ThreadingInstrumentor().instrument()

# --- Init telemetry (once, on import) ---
telemetry = configure_telemetry()
logger = telemetry["logger"]
meter = telemetry["meter"]
tracer = telemetry["tracer"]
latency_histogram, request_counter, error_counter = create_metrics(meter)

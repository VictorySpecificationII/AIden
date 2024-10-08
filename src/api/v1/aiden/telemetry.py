# telemetry.py

import logging
import os
from opentelemetry import trace, metrics
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
import psutil
from opentelemetry.metrics import Observation

# Initialize and configure OpenTelemetry for a given service name
def configure_telemetry(service_name: str = "fastapi-service"):
    resource = Resource.create({"service.name": service_name})
    
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
    return metrics.get_meter(service_name)

def create_metrics(meter):
    # Create telemetry instruments
    latency_histogram = meter.create_histogram(
        name="aiden_service_latency",
        description="Histogram of request latencies in seconds",
        unit="s"
    )
    request_counter = meter.create_counter(
        name="aiden_service_requests",
        description="Counter for the number of requests handled",
        unit="1"
    )
    error_counter = meter.create_counter(
        name="aiden_service_errors",
        description="Counter for the number of errors encountered",
        unit="1"
    )
    
    def get_cpu_usage_callback(_):
        for (number, percent) in enumerate(psutil.cpu_percent(percpu=True)):
            attributes = {"cpu_number": str(number)}
            yield Observation(percent, attributes)

    def get_ram_usage_callback(_):
        ram_percent = psutil.virtual_memory().percent
        yield Observation(ram_percent)
    
    cpu_gauge = meter.create_observable_gauge(
        callbacks=[get_cpu_usage_callback],
        name="aiden_cpu_percent",
        description="per-cpu usage",
        unit="1"
    )
    ram_gauge = meter.create_observable_gauge(
        callbacks=[get_ram_usage_callback],
        name="aiden_ram_percent",
        description="RAM memory usage",
        unit="1"
    )
    
    return latency_histogram, request_counter, error_counter

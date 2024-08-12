import logging
from typing import Iterable
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.metrics import (
    CallbackOptions,
    Observation,
    get_meter_provider,
    set_meter_provider,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

class OpenTelemetryInstrumentor:
    """
    Sets up tracing, logging, and metrics instrumentation for an application.
    """

    def __init__(self, svc_name: str, instance_id: str):
        """
        Initializes the OpenTelemetryInstrumentor with a service name and instance ID.

        Parameters:
        - svc_name (str): The name of the service to be used in the logger resource.
        - instance_id (str): The unique instance ID for the service resource.
        """
        self.svc_name = svc_name
        self.instance_id = instance_id

        # Initialize TracerProvider and SpanProcessor
        trace.set_tracer_provider(TracerProvider())
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )

        # Initialize LoggerProvider and LoggingHandler
        self.logger_provider = LoggerProvider(
            resource=Resource.create(
                {
                    "service.name": svc_name,
                    "service.instance.id": instance_id,
                }
            ),
        )
        set_logger_provider(self.logger_provider)

        exporter = OTLPLogExporter(insecure=True)
        self.logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=self.logger_provider)

        # Set minimum log level and attach OTLP handler to root logger
        logging.basicConfig(level=logging.INFO)
        logging.getLogger().addHandler(handler)

        # Initialize Metrics Provider
        self.initialize_metrics()

    def initialize_metrics(self):
        """
        Initializes metrics instrumentation with a basic counter.
        """
        exporter = OTLPMetricExporter(insecure=True)
        reader = PeriodicExportingMetricReader(exporter)
        provider = MeterProvider(metric_readers=[reader])
        set_meter_provider(provider)

        self.meter = get_meter_provider().get_meter("application", "0.1.0")

        # Declare Counters here, implement in main middleware function
        self.request_counter = self.meter.create_counter("request_counter")
        self.error_counter = self.meter.create_counter("error_counter")
        self.letency_counter = self.meter.create_histogram("latency_counter")

    def get_logger(self, logging_area: str) -> logging.Logger:
        """
        Creates and returns a namespaced logger.

        Parameters:
        - logging_area (str): The specific area or component name for creating a namespaced logger.
                              The logger name will be prefixed with "aiden." (e.g., "aiden.startup").

        Returns:
        - logger (logging.Logger): The configured logger instance with the specified namespace.
        """
        return logging.getLogger(f"aiden.{logging_area}")

    def get_tracer(self) -> trace.Tracer:
        """
        Returns the initialized tracer instance.

        Returns:
        - tracer (trace.Tracer): The initialized tracer instance.
        """
        tracer = trace.get_tracer(__name__)
        
        # Attach the helper method to the tracer object for easy access
        tracer.set_span_status = self.set_span_status
        return tracer

    def set_span_status(self, span, success: bool, message: str = ""):
        """
        Sets the status of a span based on success or failure.

        Parameters:
        - span (trace.Span): The span to set the status for.
        - success (bool): Whether the operation was successful.
        - message (str, optional): Additional information about the status.
        """
        if success:
            span.set_status(Status(StatusCode.OK, message))
        else:
            span.set_status(Status(StatusCode.ERROR, message))

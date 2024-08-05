import logging

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

def instrumentator(svc_name, instance_id, logging_area):
    """
    Sets up tracing and logging instrumentation for an application.

    This function initializes the OpenTelemetry tracer provider and logger provider,
    configures them with a console exporter and OTLP log exporter respectively, and
    creates a namespaced logger with a fixed prefix. It also sets up a logging handler
    to route log records to the specified logger provider.

    Parameters:
    - svc_name (str): The name of the service to be used in the logger resource.
    - instance_id (str): The unique instance ID for the service resource.
    - logging_area (str): The specific area or component name for creating a namespaced logger. 
                           The logger name will be prefixed with "aiden." (e.g., "aiden.startup").

    Returns:
    - logger (logging.Logger): The configured logger instance with the specified namespace.
    - tracer (trace.Tracer): The initialized tracer instance.

    Notes:
    - The logging level for the root logger is set to `logging.INFO` by default. 
      To change the logging level, manually edit the `logging.basicConfig(level=logging.INFO)` 
      line in this function.
    """
    # Initialize TracerProvider and SpanProcessor
    trace.set_tracer_provider(TracerProvider())
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(ConsoleSpanExporter())
    )
    # Initialize LoggerProvider and LoggingHandler
    logger_provider = LoggerProvider(
        resource=Resource.create(
            {
                "service.name": svc_name,
                "service.instance.id": instance_id,
            }
        ),
    )
    set_logger_provider(logger_provider)

    exporter = OTLPLogExporter(insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)

    # Set minimum log level and attach OTLP handler to root logger
    logging.basicConfig(level=logging.INFO)
    logging.getLogger().addHandler(handler)

    # Create different namespaced loggers
    logger = logging.getLogger(f"aiden.{logging_area}")

    # Initialize tracer
    tracer = trace.get_tracer(__name__)

    return logger, tracer
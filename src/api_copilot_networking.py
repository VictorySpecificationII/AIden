"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- check_internet_connectivity(): Checks for an active internet connection.
"""

import requests
import logging
from fastapi import APIRouter, HTTPException
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Initialize TracerProvider and SpanProcessor
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(ConsoleSpanExporter())
)

# Initialize LoggerProvider and LoggingHandler
logger_provider = LoggerProvider(
    resource=Resource.create(
        {
            "service.name": "startup",
            "service.instance.id": "instance-00",
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
logger1 = logging.getLogger("aiden.startup")

# Initialize a FastAPI router
router = APIRouter()

# Initialize tracer
tracer = trace.get_tracer(__name__)


# API endpoint to check local internet connection
@router.get("/check_internet_connectivity")
def api_check_internet_connectivity():
    """
    Endpoint to check internet connectivity.
    """
    with tracer.start_as_current_span("check_internet_connectivity"):
        try:
            is_connected = (lambda: requests.get("https://www.google.com", timeout=5).status_code == 200)()
            if is_connected:
                logger1.info("Internet connectivity enabled.")
                return {"message": "Internet connectivity enabled."}
            else:
                logger1.error("No internet connection.")
                raise HTTPException(status_code=503, detail="No internet connection.")
        except requests.ConnectionError:
            logger1.error("Failed to connect to the internet.")
            raise HTTPException(status_code=503, detail="Failed to connect to the internet.")

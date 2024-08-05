"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- check_internet_connectivity(): Checks for an active internet connection.
"""

import requests
import logging
from fastapi import APIRouter, HTTPException
import lib_copilot_telemetry

# Initialize LoggerProvider and LoggingHandler
logger_provider = lib_copilot_telemetry.LoggerProvider(
    resource=lib_copilot_telemetry.Resource.create(
        {
            "service.name": "networking",
            "service.instance.id": "instance-01",
        }
    ),
)
lib_copilot_telemetry.set_logger_provider(logger_provider)

exporter = lib_copilot_telemetry.OTLPLogExporter(insecure=True)
logger_provider.add_log_record_processor(lib_copilot_telemetry.BatchLogRecordProcessor(exporter))
handler = lib_copilot_telemetry.LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)

# Set minimum log level and attach OTLP handler to root logger
logging.basicConfig(level=logging.INFO)
logging.getLogger().addHandler(handler)

# Create different namespaced loggers
logger1 = logging.getLogger("aiden.networking")

# Initialize a FastAPI router
router = APIRouter()

# Initialize tracer
tracer = lib_copilot_telemetry.trace.get_tracer(__name__)


# API endpoint to check local internet connection
@router.get("/check_internet_connectivity", tags=["Networking"])
def check_internet_connectivity():
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

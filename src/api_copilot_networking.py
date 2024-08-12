"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- check_internet_connectivity(): Checks for an active internet connection.
"""
import requests
from fastapi import APIRouter, HTTPException
from lib_copilot_telemetry import OpenTelemetryInstrumentor

# Initialize the OpenTelemetryInstrumentor
instrumentor = OpenTelemetryInstrumentor(svc_name="networking", instance_id="instance-00")

# Get logger and tracer from the instrumentor
logger = instrumentor.get_logger(logging_area="networking")
tracer = instrumentor.get_tracer()

# Initialize a FastAPI router
router = APIRouter()

# API endpoint to check local internet connection
@router.get("/check_internet_connectivity", tags=["Networking"])
def check_internet_connectivity():
    """
    Endpoint to check the internet connectivity of the server.

    This endpoint attempts to make an HTTP GET request to "https://www.google.com" 
    to determine if the server has internet access. It uses a timeout of 5 seconds 
    for the request. Based on the success or failure of the request, it logs the 
    result and returns an appropriate response.

    - If the server is connected to the internet, it logs an informational message 
      and returns a JSON response with the message "Internet connectivity enabled."
    - If the server is not connected to the internet or if there is a connection error, 
      it logs an error message and raises an HTTP 503 Service Unavailable exception 
      with a relevant detail message.

    Returns:
        dict: A JSON response with a message indicating the internet connectivity status.

    Raises:
        HTTPException: If there is no internet connection or if the connection attempt fails.
    """
    with tracer.start_as_current_span("check_internet_connectivity") as span:
        try:
            is_connected = (lambda: requests.get("https://www.google.com", timeout=5)
                            .status_code == 200)()
            if is_connected:
                logger.info("Internet connectivity enabled.")
                tracer.set_span_status(span, success=True)
                return {"message": "Internet connectivity enabled."}
        except requests.ConnectionError as e:
            logger.error("Failed to connect to the internet.")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=503, detail="Failed to connect to the internet.")

"""
This module initializes and configures a FastAPI application for AIden's services.

The application includes routers for networking and LLM (language model) text handling,
sets up telemetry and logging with lib_copilot_telemetry, and defines a root endpoint
for health checks or basic information.

Usage:
    Run this script to start the FastAPI server. The server listens on port 8000.
"""

from fastapi import FastAPI, Request
from api_copilot_networking import router as startup_router
from api_copilot_llm import router as llm_router
import lib_copilot_telemetry
app = FastAPI()

# Include the api routers
app.include_router(startup_router, prefix="/networking")
app.include_router(llm_router, prefix="/llm-text")

logger, tracer = lib_copilot_telemetry.instrumentator("main", "instance-00", "main")

# Define a root endpoint for health checks or basic info
@app.get("/", tags=["Application Root"])
async def root(request: Request):
    """
    Root endpoint for AIden's FastAPI server.

    This endpoint can be used for health checks or to provide basic information
    about the server. It logs an informational message when accessed and returns
    a welcome message.

    Args:
        request (Request): The request object representing the client's request.

    Returns:
        dict: A JSON response containing a welcome message.
    """
    with tracer.start_as_current_span("root-endpoint"):
        logger.info("Root endpoint accessed.")
        return {"message": "Welcome to AIden's FastAPI server."}

if __name__ == "__main__":
    import uvicorn
    from lib_copilot_startup_functions import print_banner
    # Run startup checks
    print_banner()

    # Start the FastAPI server
    print("Starting AIden's FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

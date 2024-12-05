#basic fastap stuff
import logging
import time
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import telemetry
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    yield
    # Shutdown logic

# Initialize FastAPI apilication
app = FastAPI(lifespan=lifespan)
# Initialize telemetry
telemetry_setup = telemetry.configure_telemetry(service_name="aiden-api")
meter = telemetry_setup["meter"]
logger = telemetry_setup["logger"]
tracer = telemetry_setup["tracer"]
latency_histogram, request_counter, error_counter = telemetry.create_metrics(meter)

# Instrument the FastAPI api for tracing
FastAPIInstrumentor.instrument_app(app)

@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    start_time = time.time()
    response = None

    with tracer.start_as_current_span("http_request"):
        logger.info("Processing request: %s", request.url)
        try:
            response = await call_next(request)
        finally:
            end_time = time.time()
            latency_histogram.record(end_time - start_time)
            request_counter.add(1)

            if response is not None and response.status_code >= 400:
                error_counter.add(1)
                logger.error("Request to %s resulted in error %s", request.url, response.status_code)

            logger.info("Completed request: %s", request.url)
            return response

# Define additional routes and endpoints
@app.get("/")
async def root():
    return {"message": "Welcome to Aiden's API server."}

@app.get("/long-task")
async def long_task():
    """
    Simulate a long-running task that takes 30 seconds to complete.
    Useful for testing root endpoint responsiveness.
    """
    logger.info("Long task started.")
    await asyncio.sleep(30)  # Simulate a 30-second async operation
    logger.info("Long task completed.")
    return {"status": "completed", "message": "Long-running task finished successfully."}

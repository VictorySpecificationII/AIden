# main.py

import logging
import time
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import telemetry

# Initialize FastAPI apilication
api = FastAPI()

# Initialize telemetry
meter = telemetry.configure_telemetry(service_name="aiden-api")
latency_histogram, request_counter, error_counter = telemetry.create_metrics(meter)

# Instrument the FastAPI api for tracing
FastAPIInstrumentor.instrument_app(api)

@api.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    tracer = trace.get_tracer(__name__)
    logger = logging.getLogger(__name__)
    start_time = time.time()

    with tracer.start_as_current_span("http_request"):
        logger.info("Processing request: %s", request.url)
        try:
            response = await call_next(request)
        finally:
            end_time = time.time()
            latency_histogram.record(end_time - start_time)
            request_counter.add(1)

            if response.status_code >= 400:
                error_counter.add(1)
                logger.error("Request to %s resulted in error %s", request.url, response.status_code)

            logger.info("Completed request: %s", request.url)
            return response

# Define additional routes and endpoints
@api.get("/")
async def root():
    return {"message": "Welcome to Aiden's API server."}

# Other endpoints go here

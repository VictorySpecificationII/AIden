from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
import logging

# Configure OpenTelemetry
def configure_opentelemetry():
    # Set up the TracerProvider
    trace.set_tracer_provider(TracerProvider())
    tracer_provider = trace.get_tracer_provider()

    # Set up OTLP exporter
    otlp_trace_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")  # Adjust endpoint as needed

    # Set up BatchSpanProcessor for traces
    span_processor = BatchSpanProcessor(otlp_trace_exporter)
    tracer_provider.add_span_processor(span_processor)

# Create FastAPI app
api = FastAPI()

# Integrate OpenTelemetry with FastAPI
FastAPIInstrumentor.instrument_app(api)

# Middleware for tracing
@api.middleware("http")
async def custom_middleware(request: Request, call_next):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("http_request"):
        logger = logging.getLogger("fastapi")
        logger.info("Processing request: %s", request.url)
        response = await call_next(request)
        logger.info("Completed request: %s", request.url)
        return response

# Define routes
@api.get("/")
async def root():
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("root_endpoint"):
        return {"message": "Welcome to AIden's API server."}

@api.get("/items/{item_id}")
async def read_item(item_id: int):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("read_item_endpoint") as span:
        span.set_attribute("item_id", item_id)
        return {"item_id": item_id}

# Startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    yield
    print("Shutting down...")

api.lifespan = lifespan

# Configure OpenTelemetry
configure_opentelemetry()

# Optionally add OpenTelemetry Middleware
api.add_middleware(OpenTelemetryMiddleware)

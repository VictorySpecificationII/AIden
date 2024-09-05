import logging
import os
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry import metrics
import psutil
import time
import random
import asyncio
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch
import requests
import httpx
from pydantic import BaseModel
from huggingface_hub import hf_hub_download
import json

api = FastAPI()

# Ensure Hugging Face token is set
HUGGINGFACE_API_KEY = os.getenv('HUGGINGFACE_HUB_TOKEN')

# Initialize global variables for model and tokenizer
tokenizer = None
model = None

def configure_opentelemetry():
    resource = Resource.create({"service.name": "aiden-api"})
    
    # Configure tracing
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()
    otlp_trace_exporter = OTLPSpanExporter(endpoint="http://otel-collector:4317")
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
    
    # Configure logging
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    otlp_log_exporter = OTLPLogExporter(endpoint="http://otel-collector:4317", insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))
    handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)
    
    # Configure metrics
    exporter = OTLPMetricExporter(endpoint="http://otel-collector:4317")
    metric_reader = PeriodicExportingMetricReader(exporter, export_interval_millis=20000)
    meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
    metrics.set_meter_provider(meter_provider)

    # Return configured meter
    return metrics.get_meter(__name__)

meter = configure_opentelemetry()

latency_histogram = meter.create_histogram(name="aiden_service_latency", description="Histogram of request latencies in seconds", unit="s")
request_counter = meter.create_counter(name="aiden_service_requests", description="Counter for the number of requests handled", unit="1")
error_counter = meter.create_counter(name="aiden_service_errors", description="Counter for the number of errors encountered", unit="1")

def get_cpu_usage_callback(_):
    for (number, percent) in enumerate(psutil.cpu_percent(percpu=True)):
        attributes = {"cpu_number": str(number)}
        yield Observation(percent, attributes)

def get_ram_usage_callback(_):
    ram_percent = psutil.virtual_memory().percent
    yield Observation(ram_percent)

cpu_gauge = meter.create_observable_gauge(callbacks=[get_cpu_usage_callback], name="aiden_cpu_percent", description="per-cpu usage", unit="1")
ram_gauge = meter.create_observable_gauge(callbacks=[get_ram_usage_callback], name="aiden_ram_percent", description="RAM memory usage", unit="1")

# Instrument the FastAPI app for tracing
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

@api.get("/")
async def root():
    logging.debug("Root endpoint hit")
    return {"message": "Welcome to AIden's API server."}

@api.get("/items/{item_id}")
async def read_item(item_id: int):
    logging.debug(f"Item ID: {item_id} requested")
    return {"item_id": item_id}

@api.get("/latency")
async def simulate_latency():
    delay = random.uniform(0.1, 2.0)
    await asyncio.sleep(delay)
    return {"message": f"Simulated latency of {delay:.2f} seconds"}

@api.get("/error")
async def trigger_error():
    raise HTTPException(status_code=500, detail="This is a test error")

class ModelDownloadRequest(BaseModel):
    model_name: str

@api.get("/auth")
async def authenticate_huggingface():
    if not HUGGINGFACE_API_KEY:
        raise HTTPException(status_code=400, detail="Hugging Face API key not set")

    try:
        response = requests.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
        )
        if response.status_code == 200:
            return {"message": "Authentication successful"}
        else:
            raise HTTPException(status_code=response.status_code, detail="Authentication failed")
    except requests.RequestException as e:
        logging.error("Error during Hugging Face authentication: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to authenticate with Hugging Face Hub: {str(e)}")



def load_model_paths():
    if os.path.exists(model_paths_file):
        with open(model_paths_file, "r") as file:
            return json.load(file)
    return {}

def save_model_paths(paths):
    with open(model_paths_file, "w") as file:
        json.dump(paths, file)

# Model paths storage
model_paths_file = "model_paths.json"
model_paths = load_model_paths()

class ModelDownloadRequest(BaseModel):
    model_name: str

@api.post("/download-model-tf")
def download_model_tf(request: ModelDownloadRequest):
    model_name = request.model_name

    if not HUGGINGFACE_API_KEY:
        raise HTTPException(status_code=400, detail="Hugging Face API key not set")

    try:
        # Download the model and tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_auth_token=HUGGINGFACE_API_KEY)
        model = AutoModelForCausalLM.from_pretrained(model_name, use_auth_token=HUGGINGFACE_API_KEY)

        # Save the model and tokenizer to local storage
        model_path = f"./models/{model_name.replace('/', '_')}"
        model.save_pretrained(model_path)
        tokenizer.save_pretrained(model_path)

        model_paths[model_name] = model_path
        save_model_paths(model_paths)

        return {"message": "Model downloaded successfully", "model_path": model_path}
    except Exception as e:
        logging.error("Error during model download: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to download model: {str(e)}")

@api.post("/download-model-hf")
def download_model_hf(request: ModelDownloadRequest):
    model_name = request.model_name
    
    if not HUGGINGFACE_API_KEY:
        raise HTTPException(status_code=400, detail="Hugging Face API key not set")

    try:
        # Define the model file name for GGUF models
        if model_name == "TheBloke/Llama-2-7B-Chat-GGUF":
            ll_model_file = "llama-2-7b-chat.Q4_0.gguf"
        else:
            raise HTTPException(status_code=400, detail="Unsupported model for GGUF download")
        
        # Download the model file
        model_path = hf_hub_download(repo_id=model_name, filename=ll_model_file, token=HUGGINGFACE_API_KEY)

        model_paths[model_name] = model_path
        save_model_paths(model_paths)

        return {"message": f"Model downloaded successfully to {model_path}"}
    except Exception as e:
        logging.error(f"Error during model download: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download model: {str(e)}")

@api.post("/load-model")
def load_model(request: ModelDownloadRequest):
    model_name = request.model_name

    if model_name not in model_paths:
        raise HTTPException(status_code=400, detail="Model not downloaded. Call /download-model first.")

    model_path = model_paths[model_name]
    try:
        # Load the model based on its type
        if model_name.startswith("TheBloke/"):
            # Handle GGUF models
            # Load GGUF models if necessary, e.g., using a custom loader
            pass
        else:
            # Handle transformer models
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            model = AutoModelForCausalLM.from_pretrained(model_path)

        return {"message": f"Model {model_name} loaded successfully from {model_path}"}
    except Exception as e:
        logging.error(f"Error loading model {model_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.debug("Starting up...")
    yield
    logging.debug("Shutting down...")

api.lifespan = lifespan

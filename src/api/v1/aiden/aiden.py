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

api = FastAPI()

# Ensure Hugging Face token is set
HUGGINGFACE_API_KEY = os.getenv('HUGGINGFACE_HUB_TOKEN')

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

@api.post("/download-model")
def download_model(request: ModelDownloadRequest):
    if not HUGGINGFACE_API_KEY:
        raise HTTPException(status_code=400, detail="Hugging Face API key not set")
    
    model_name = request.model_name
    
    # Validate the model name
    if model_name != "meta-llama/Meta-Llama-3-8B":
        raise HTTPException(status_code=400, detail="Invalid model name")

    try:
        # Download the model and tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_auth_token=HUGGINGFACE_API_KEY)
        model = AutoModelForCausalLM.from_pretrained(model_name, use_auth_token=HUGGINGFACE_API_KEY)

        # Save the model and tokenizer to local storage
        model_path = f"./{model_name.replace('/', '_')}"
        model.save_pretrained(model_path)
        tokenizer.save_pretrained(model_path)

        return {"message": "Model downloaded successfully"}
    except Exception as e:
        logging.error("Error during model download: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to download model: {str(e)}")



# @api.get("/download")
# async def download_model():
#     model_name = "meta-llama/Meta-Llama-3-8B"
#     try:
#         logging.debug("Starting download of model: %s", model_name)
        
#         # Download and save model
#         model_dir = "./models/" + model_name.split("/")[-1]
#         os.makedirs(model_dir, exist_ok=True)
        
#         # Download and cache the model
#         model = AutoModelForCausalLM.from_pretrained(model_name, cache_dir="./models")
#         tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir="./models")
        
#         # Save the model and tokenizer
#         model.save_pretrained(model_dir)
#         tokenizer.save_pretrained(model_dir)

#         logging.debug("Model downloaded and saved successfully.")
#         return {"message": "Model downloaded and saved successfully"}
#     except Exception as e:
#         logging.error("Error downloading the model: %s", e)
#         raise HTTPException(status_code=500, detail=f"Failed to download the model: {str(e)}")

# @api.get("/generate")
# async def generate_data(prompt: str):
#     try:
#         logging.debug("Generate endpoint hit with prompt: %s", prompt)
        
#         model_dir = "./models/meta-llama-Meta-Llama-3-8B"
#         if not os.path.exists(model_dir):
#             raise HTTPException(status_code=500, detail="Model not found. Please download the model first.")

#         # Load the model and tokenizer from the saved directory
#         model = AutoModelForCausalLM.from_pretrained(model_dir)
#         tokenizer = AutoTokenizer.from_pretrained(model_dir)
        
#         generator = pipeline("text-generation", model=model, tokenizer=tokenizer, device=0 if torch.cuda.is_available() else -1)
#         result = generator(prompt, max_length=50)

#         logging.debug("Generated response: %s", result)
#         return {"message": "Data generated successfully", "generated_text": result[0]['generated_text']}
#     except Exception as e:
#         logging.error("Error generating data: %s", e)
#         raise HTTPException(status_code=500, detail=f"Failed to generate data: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.debug("Starting up...")
    yield
    logging.debug("Shutting down...")

api.lifespan = lifespan

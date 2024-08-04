"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- print_banner(): Prints a welcome banner at startup.
- check_local_llm_availability(): Checks if the necessary LLM models are available locally, downloads them if not.
- check_local_internet_connection(): Checks for an active internet connection.
"""

import os
import requests
import logging

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

import mistral_onboard_llm
import llama2_onboard_llm

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

# Initialize tracer
tracer = trace.get_tracer(__name__)

def print_banner():
    '''
    Prints a banner at startup.
    '''
    ascii_art = """
        _    ___    _            
       / \  |_ _|__| | ___ _ __  
      / _ \  | |/ _` |/ _ \ '_ \ 
     / ___ \ | | (_| |  __/ | | |
    /_/   \_\___\__,_|\___|_| |_|
    
   Artificial Intelligence Co-Pilot
    """
    print(ascii_art)

def check_local_llm_availability():
    '''
    Checks whether the LLM models are available locally, and if not - downloads them.
    '''
    logger1.info("Checking LLM models in ~/.cache/huggingface/hub...")

    # Start a new span for checking LLM availability
    with tracer.start_as_current_span("check_local_llm_availability"):
        # Get the paths to the model files
        mistral_path = mistral_onboard_llm.load_llm()
        llama2_path = llama2_onboard_llm.load_llm()

        # Check if the model files exist
        if not os.path.isfile(mistral_path):
            logger1.warning("Mistral model file not found at %s.", mistral_path)
            mistral_found = False
        else:
            logger1.info("Mistral model file found at %s.", mistral_path)
            mistral_found = True

        if not os.path.isfile(llama2_path):
            logger1.warning("Llama2 model file not found at %s.", llama2_path)
            llama2_found = False
        else:
            logger1.info("Llama2 model file found at %s.", llama2_path)
            llama2_found = True

        if (llama2_found or mistral_found):
            logger1.info("At least one LLM found in ~/.cache/huggingface/hub directory.")
            return True
        else:
            logger1.error("LLM's not found in ~/.cache/huggingface/hub directory.")
            return False

def check_local_internet_connection():
    '''
    Checks for internet connectivity.
    '''
    logger1.info("Checking Internet connectivity on host...")
    
    # Start a new span for checking internet connectivity
    with tracer.start_as_current_span("check_local_internet_connection"):
        try:
            requests.get("https://www.google.com", timeout=5)
            logger1.info("Internet connectivity enabled.")
            return True
        except requests.ConnectionError:
            logger1.warning("No internet connection.")
            return False

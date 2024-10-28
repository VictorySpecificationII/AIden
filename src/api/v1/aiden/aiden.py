#basic fastap stuff
import logging
import time
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import telemetry

# llm stuff
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.llms.llama_cpp import LlamaCPP
from llama_index.llms.llama_cpp.llama_utils import (
    messages_to_prompt,
    completion_to_prompt,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

def print_banner():
    """
    Prints a banner at startup.
    """

    ascii_art = """
            _    ___    _            
           / \  |_ _|__| | ___ _ __  
          / _ \  | |/ _` |/ _ \ '_ \ 
         / ___ \ | | (_| |  __/ | | |
        /_/   \_\___\__,_|\___|_| |_|
        
    Artificial Intelligence Co-Pilot
        """
    print(ascii_art)

# Initialize FastAPI apilication
api = FastAPI()
print_banner()
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

@api.get("/generate")
async def generate():
    # # loads BAAI/bge-small-en-v1.5
    # local_embedding_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

    # data = SimpleDirectoryReader(input_dir="./data/paul_graham/").load_data()
    # index = VectorStoreIndex.from_documents(data, embed_model = local_embedding_model, show_progress = True)

    # model_url = "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q2_K.gguf"

    # llm = LlamaCPP(
    #     # You can pass in the URL to a GGML model to download it automatically
    #     model_url=model_url,
    #     # optionally, you can set the path to a pre-downloaded model instead of model_url
    #     model_path=None,
    #     temperature=0.1,
    #     max_new_tokens=256,
    #     # llama2 has a context window of 4096 tokens, but we set it lower to allow for some wiggle room
    #     context_window=3900,
    #     # kwargs to pass to __call__()
    #     generate_kwargs={},
    #     # kwargs to pass to __init__()
    #     # set to at least 1 to use GPU
    #     model_kwargs={"n_gpu_layers": 0},
    #     # transform inputs into Llama2 format
    #     messages_to_prompt=messages_to_prompt,
    #     completion_to_prompt=completion_to_prompt,
    #     verbose=True,
    # )

    # # response = llm.complete("Hello! Can you tell me a poem about cats and dogs?")
    # # print(response.text)

    # response_iter = llm.stream_complete("What is the meaning of life?")
    # for response in response_iter:
    #     print(response.delta, end="", flush=True)
    print("done")
    return "ok"
    #return response
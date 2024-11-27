#basic fastap stuff
import logging
import time
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import telemetry
import boot_process

# llm stuff
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.llms.llama_cpp import LlamaCPP
from llama_index.llms.llama_cpp.llama_utils import (
    messages_to_prompt,
    completion_to_prompt,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding


@asynccontextmanager
async def lifespan(app: FastAPI):
    boot_process.print_banner()
    app.state.llm_power = "default_model"#boot_process.boot_checks()
    yield
    # Shutdown logic
    app.state.llm_power = None  # Clear or reset the state if needed

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

# @api.get("/embedding")
# async def embed():
#     # loads BAAI/bge-small-en-v1.5
#     local_embedding_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

#     data = SimpleDirectoryReader(input_dir="./data/paul_graham/").load_data()
#     index = VectorStoreIndex.from_documents(data, embed_model = local_embedding_model, show_progress = True)

@app.get("/generate")
async def generate():

    # Determine the model URL based on the app's state
    if app.state.llm_power == "default_model":
        model_url = "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q2_K.gguf"
    elif app.state.llm_power == "edge_device_model":
        model_url = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q2_K.gguf"
    else:
        raise HTTPException(status_code=400, detail="Invalid model selection")

    llm = LlamaCPP(
        # You can pass in the URL to a GGML model to download it automatically
        model_url=model_url,
        # optionally, you can set the path to a pre-downloaded model instead of model_url
        model_path=None,
        temperature=0.1,
        max_new_tokens=256,
        # llama2 has a context window of 4096 tokens, but we set it lower to allow for some wiggle room
        context_window=3900,
        # kwargs to pass to __call__()
        generate_kwargs={},
        # kwargs to pass to __init__()
        # set to at least 1 to use GPU
        model_kwargs={"n_gpu_layers": 0},
        # transform inputs into Llama2 format
        messages_to_prompt=messages_to_prompt,
        completion_to_prompt=completion_to_prompt,
        verbose=True,
    )

    # response = llm.complete("Hello! Can you tell me a poem about cats and dogs?")
    # print(response.text)

    response_iter = llm.stream_complete("What is the meaning of life?")
    for response in response_iter:
        print(response.delta, end="", flush=True)
    print("done")
    return response
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from huggingface_hub import hf_hub_download
import os
import json

import lib_copilot_telemetry



# Global variables to store model paths, LLM instance, and LLM chain
model_paths = {"mistral": None, "llama2": None}
llm = None
llm_chain = None
current_model_name = None
model_paths_file = "model_paths.json"

logger, tracer = lib_copilot_telemetry.instrumentator("llm", "instance-00", "llm")

router = APIRouter()

class Question(BaseModel):
    question: str

def load_model_paths():
    """
    Load model paths from a file if it exists.
    """
    global model_paths
    if os.path.exists(model_paths_file):
        with open(model_paths_file, "r") as file:
            model_paths = json.load(file)

def save_model_paths():
    """
    Save model paths to a file.
    """
    global model_paths
    with open(model_paths_file, "w") as file:
        json.dump(model_paths, file)

@router.on_event("startup")
async def startup_event():
    """
    Load model paths when the application starts.
    """
    load_model_paths()

@router.get("/download-models", tags=["LLM Management | Text Models"])
def download_models():
    """
    Download the model files from the Hugging Face hub.
    """
    global model_paths
    global current_model_name

    with tracer.start_as_current_span("download_models") as span:
        try:
            # Download Mistral model
            mistral_model_name = "TheBloke/Mistral-7B-OpenOrca-GGUF"
            mistral_model_file = "mistral-7b-openorca.Q4_K_M.gguf"
            model_paths["mistral"] = hf_hub_download(mistral_model_name, filename=mistral_model_file)

            # Download Llama-2 model
            llama2_model_name = "TheBloke/Llama-2-7B-Chat-GGUF"
            llama2_model_file = "llama-2-7b-chat.Q4_0.gguf"
            model_paths["llama2"] = hf_hub_download(llama2_model_name, filename=llama2_model_file)

            # Save model paths to file
            save_model_paths()

            logger.info("LLM models downloaded.")
            tracer.set_span_status(span, success=True)
            return {"model_paths": model_paths}
        except Exception as e:
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/check-downloaded-models", tags=["LLM Management | Text Models"])
def check_downloaded_models(model_name: str):
    """
    Check if the model file has been downloaded.

    Args:
        model_name (str): The name of the model to check. It should be 'mistral' or 'llama2'.
    """
    with tracer.start_as_current_span("check_downloaded_models") as span:
        if model_name not in model_paths:
            logger.info("Invalid model name. Use 'mistral' or 'llama2'.")
            tracer.set_span_status(span, success=False, message = "Invalid model name. Use 'mistral' or 'llama2'.")
            raise HTTPException(status_code=400, detail="Invalid model name. Use 'mistral' or 'llama2'.")

        model_path = model_paths.get(model_name)
        if model_path and os.path.exists(model_path):
            logger.info("LLM model exists locally.")
            tracer.set_span_status(span, success=True)
            return {"model_path": model_path, "status": "model downloaded"}
        else:
            logger.info("LLM model does not exist locally.")
            tracer.set_span_status(span, success=True)
            raise HTTPException(status_code=404, detail="Model not downloaded.")

@router.get("/load-llm", tags=["LLM Management | Text Models"])
def load_llm(model_name: str):
    """
    Load and return the path to the LLM model.

    Args:
        model_name (str): The name of the model to load. It should be 'mistral' or 'llama2'.
    """
    global model_paths
    global current_model_name
    with tracer.start_as_current_span("load_llm") as span:
        if model_name not in model_paths:
            logger.info("Invalid model name. Use 'mistral' or 'llama2'.")
            tracer.set_span_status(span, success=False, message = "Invalid model name. Use 'mistral' or 'llama2'.")
            raise HTTPException(status_code=400, detail="Invalid model name. Use 'mistral' or 'llama2'.")

        model_path = model_paths.get(model_name)
        if model_path is None:
            logger.info("Model not downloaded. Call /download-model first.")
            tracer.set_span_status(span, success=False, message = "Model not downloaded. Call /download-model first.")
            raise HTTPException(status_code=404, detail="Model not downloaded. Call /download-model first.")

        try:
            current_model_name = model_name
            logger.info("LLM model load successful.")
            tracer.set_span_status(span, success=True)
            return {"model_path": model_path}
        except Exception as e:
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/switch-model", tags=["LLM Management | Text Models"])
def switch_model(model_name: str):
    """
    Switch the current active model to the specified model.

    Args:
        model_name (str): The name of the model to switch to. It should be 'mistral' or 'llama2'.
    """
    global llm
    global llm_chain
    global current_model_name
    global model_paths
    with tracer.start_as_current_span("switch_model") as span:
        if model_name not in model_paths:
            logger.info("Invalid model name. Use 'mistral' or 'llama2'.")
            tracer.set_span_status(span, success=False, message = "Invalid model name. Use 'mistral' or 'llama2'.")
            raise HTTPException(status_code=400, detail="Invalid model name. Use 'mistral' or 'llama2'.")

        model_path = model_paths.get(model_name)
        if model_path is None or not os.path.exists(model_path):
            logger.info("Model path not found. Call /load-llm first.")
            tracer.set_span_status(span, success=False, message = "Model not downloaded. Call /download-model first.")
            raise HTTPException(status_code=404, detail="Model not downloaded. Call /download-model first.")

        # Reset the LLM and LLMChain instances
        llm = LlamaCpp(
            model_path=model_path,
            n_gpu_layers=0,
            n_batch=512,
            verbose=False,
        )
        llm_chain = None  # LLMChain will need to be recreated

        current_model_name = model_name
        logger.info("LLM model switch successful.")
        tracer.set_span_status(span, success=True)
        return {"status": f"Switched to model {model_name}", "model_path": model_path}

@router.get("/get_current_model_in_memory", tags=["LLM Management | Text Models"])
def get_current_model_in_memory():
    """
    Endpoint to get the current status of the loaded model.
    """
    current_model = current_model_name
    with tracer.start_as_current_span("get_current_model_in_memory") as span:
        if current_model:
            logger.info("LLM model returned.")
            tracer.set_span_status(span, success=True)
            return {"model": current_model, "status": "loaded"}
        else:
            logger.info("No LLM model to return.")
            tracer.set_span_status(span, success=True)
            return {"model": None, "status": "no model loaded"}

@router.post("/instantiate-llm", tags=["LLM Communication | Text Models"])
def instantiate_llm():
    """
    Instantiate the LLM with the path loaded from /load-llm.
    """
    global llm
    global model_paths
    global current_model_name

    with tracer.start_as_current_span("instantiate_llm_chain") as span:
        if current_model_name is None:
            logger.info("No model loaded. Call /load-llm first.")
            tracer.set_span_status(span, success=False, message = "No model loaded. Call /load-llm first.")
            raise HTTPException(status_code=400, detail="No model loaded. Call /load-llm first.")

        model_path = model_paths.get(current_model_name)
        if model_path is None:
            logger.info("Model path not found. Call /load-llm first.")
            tracer.set_span_status(span, success=False, message = "Model path not found. Call /load-llm first.")
            raise HTTPException(status_code=400, detail="Model path not found. Call /load-llm first.")
        
        try:
            llm = LlamaCpp(
                model_path=model_path,
                n_gpu_layers=0,
                n_batch=512,
                verbose=False,
            )
            logger.info("LLM instantiated.")
            tracer.set_span_status(span, success=True)
            return {"status": "LLM instantiated"}
        except Exception as e:
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-llm-chain", tags=["LLM Communication | Text Models"])
def create_llm_chain():
    """
    Create an LLMChain using the instantiated LLM.
    """
    global llm_chain
    with tracer.start_as_current_span("create_llm_chain") as span:
        if llm is None:
            logger.info("LLM not instantiated. Call /instantiate-llm first.")
            tracer.set_span_status(span, success=False, message = "LLM not instantiated. Call /instantiate-llm first.")
            raise HTTPException(status_code=400, detail="LLM not instantiated. Call /instantiate-llm first.")
        
        try:
            template = """
            You are AIden, a co-pilot and digital companion. You are witty, gentlemanly, and inquisitive with an engineering-oriented mindset. Please reflect these qualities in your response.

            Question: {question}

            Answer:
            """
            prompt = PromptTemplate(template=template, input_variables=["question"])
            llm_chain = LLMChain(prompt=prompt, llm=llm)
            logger.info("LLMChain LLMChain created.")
            tracer.set_span_status(span, success=True)
            return {"status": "LLMChain created"}
        except Exception as e:
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/ask", tags=["LLM Communication | Text Models"])
async def ask_question(data: Question):
    """
    Handle the POST request to answer a question using the LLM.
    
    Args:
        data (Question): The question to ask the LLM.
    
    Returns:
        dict: The answer from the LLM.
    """
    global llm_chain
    with tracer.start_as_current_span("ask_llm") as span:
        if llm_chain is None:
            logger.info("LLMChain not created. Call /create-llm-chain first.")
            tracer.set_span_status(span, success=False, message = "LLMChain not created. Call /create-llm-chain first.")
            raise HTTPException(status_code=400, detail="LLMChain not created. Call /create-llm-chain first.")
        
        try:
            answer = llm_chain.run(data.question)
            logger.info("Query successful. Returning answer from LLM.")
            tracer.set_span_status(span, success=True)
            return {"answer": answer}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))



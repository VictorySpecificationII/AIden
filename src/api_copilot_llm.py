from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from huggingface_hub import hf_hub_download
import os
import json

# Global variables to store model paths, LLM instance, and LLM chain
model_paths = {"mistral": None, "llama2": None}
llm = None
llm_chain = None
current_model_name = None
model_paths_file = "model_paths.json"

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

        return {"model_paths": model_paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/check-downloaded-models", tags=["LLM Management | Text Models"])
def check_downloaded_models(model_name: str):
    """
    Check if the model file has been downloaded.

    Args:
        model_name (str): The name of the model to check. It should be 'mistral' or 'llama2'.
    """
    if model_name not in model_paths:
        raise HTTPException(status_code=400, detail="Invalid model name. Use 'mistral' or 'llama2'.")

    model_path = model_paths.get(model_name)
    if model_path and os.path.exists(model_path):
        return {"model_path": model_path, "status": "model downloaded"}
    else:
        return {"status": "model not downloaded"}

@router.get("/load-llm", tags=["LLM Management | Text Models"])
def load_llm(model_name: str):
    """
    Load and return the path to the LLM model.

    Args:
        model_name (str): The name of the model to load. It should be 'mistral' or 'llama2'.
    """
    global model_paths
    global current_model_name

    if model_name not in model_paths:
        raise HTTPException(status_code=400, detail="Invalid model name. Use 'mistral' or 'llama2'.")

    model_path = model_paths.get(model_name)
    if model_path is None:
        raise HTTPException(status_code=400, detail="Model not downloaded. Call /download-model first.")

    try:
        current_model_name = model_name
        return {"model_path": model_path}
    except Exception as e:
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

    if model_name not in model_paths:
        raise HTTPException(status_code=400, detail="Invalid model name. Use 'mistral' or 'llama2'.")

    model_path = model_paths.get(model_name)
    if model_path is None or not os.path.exists(model_path):
        raise HTTPException(status_code=400, detail="Model not downloaded. Call /download-model first.")

    # Reset the LLM and LLMChain instances
    llm = LlamaCpp(
        model_path=model_path,
        n_gpu_layers=0,
        n_batch=512,
        verbose=False,
    )
    llm_chain = None  # LLMChain will need to be recreated

    current_model_name = model_name
    return {"status": f"Switched to model {model_name}", "model_path": model_path}

@router.post("/instantiate-llm", tags=["LLM Management | Text Models"])
def instantiate_llm():
    """
    Instantiate the LLM with the path loaded from /load-llm.
    """
    global llm
    global model_paths
    global current_model_name

    if current_model_name is None:
        raise HTTPException(status_code=400, detail="No model loaded. Call /load-llm first.")

    model_path = model_paths.get(current_model_name)
    if model_path is None:
        raise HTTPException(status_code=400, detail="Model path not found. Call /load-llm first.")
    
    try:
        llm = LlamaCpp(
            model_path=model_path,
            n_gpu_layers=0,
            n_batch=512,
            verbose=False,
        )
        return {"status": "LLM instantiated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-llm-chain", tags=["LLM Management | Text Models"])
def create_llm_chain():
    """
    Create an LLMChain using the instantiated LLM.
    """
    global llm_chain
    if llm is None:
        raise HTTPException(status_code=400, detail="LLM not instantiated. Call /instantiate-llm first.")
    
    try:
        template = """
        You are AIden, a co-pilot and digital companion. You are witty, gentlemanly, and inquisitive with an engineering-oriented mindset. Please reflect these qualities in your response.

        Question: {question}

        Answer:
        """
        prompt = PromptTemplate(template=template, input_variables=["question"])
        llm_chain = LLMChain(prompt=prompt, llm=llm)
        return {"status": "LLMChain created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ask", tags=["LLM Management | Text Models"])
async def ask_question(data: Question):
    """
    Handle the POST request to answer a question using the LLM.
    
    Args:
        data (Question): The question to ask the LLM.
    
    Returns:
        dict: The answer from the LLM.
    """
    global llm_chain
    if llm_chain is None:
        raise HTTPException(status_code=400, detail="LLMChain not created. Call /create-llm-chain first.")
    
    try:
        answer = llm_chain.run(data.question)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_current_model_in_memory", tags=["LLM Management | Text Models"])
def get_current_model_in_memory():
    """
    Endpoint to get the current status of the loaded model.
    """
    current_model = current_model_name
    if current_model:
        return {"model": current_model, "status": "loaded"}
    else:
        return {"model": None, "status": "no model loaded"}

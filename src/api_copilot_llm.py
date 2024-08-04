from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from huggingface_hub import hf_hub_download

# Global variables to store model path, LLM instance, and LLM chain
global current_model, current_llm_chain
model_path = None
llm = None
llm_chain = None

router = APIRouter()

class Question(BaseModel):
    question: str

@router.get("/load-llm")
def load_llm():
    """
    Load and return the path to the LLM model.
    """
    global model_path
    try:
        llm_model_name = "TheBloke/Mistral-7B-OpenOrca-GGUF"
        model_file = "mistral-7b-openorca.Q4_K_M.gguf"
        model_path = hf_hub_download(llm_model_name, filename=model_file)
        return {"model_path": model_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/instantiate-llm")
def instantiate_llm():
    """
    Instantiate the LLM with the path loaded from /load-llm.
    """
    global llm
    if model_path is None:
        raise HTTPException(status_code=400, detail="Model path not loaded. Call /load-llm first.")
    
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

@router.post("/create-llm-chain")
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

@router.post("/ask")
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

# Optional: An endpoint to check the status of the loaded model
@router.get("/status")
def get_status():
    """
    Endpoint to get the current status of the loaded model.
    """
    if current_model:
        return {"model": current_model, "status": "loaded"}
    else:
        return {"model": None, "status": "no model loaded"}
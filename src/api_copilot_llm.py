from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from svc_copilot_llm import LLMService
import lib_copilot_telemetry

# Initialize logger and tracer
logger, tracer = lib_copilot_telemetry.instrumentator("llm", "instance-00", "llm")

# Singleton LLMService instance with logger and tracer
svc_copilot_llm_instance = LLMService(logger, tracer)

def get_svc_copilot_llm():
    return svc_copilot_llm_instance

router = APIRouter()

class Question(BaseModel):
    question: str

@router.get("/download-models", tags=["LLM Management | Text Models"])
def download_models(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    return svc_copilot_llm.download_models()

@router.get("/load-llm", tags=["LLM Management | Text Models"])
def load_llm(model_name: str, svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    return svc_copilot_llm.load_llm(model_name)

@router.post("/switch-model", tags=["LLM Management | Text Models"])
def switch_model(model_name: str, svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    return svc_copilot_llm.switch_model(model_name)

@router.get("/get_current_model_in_memory", tags=["LLM Management | Text Models"])
def get_current_model_in_memory(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    return svc_copilot_llm.get_current_model_in_memory()

@router.post("/instantiate-llm", tags=["LLM Communication | Text Models"])
def instantiate_llm(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    return svc_copilot_llm.instantiate_llm()

@router.post("/create-llm-chain", tags=["LLM Communication | Text Models"])
def create_llm_chain(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    return svc_copilot_llm.create_llm_chain()

@router.post("/ask", tags=["LLM Communication | Text Models"])
def ask_question(data: Question, svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    return svc_copilot_llm.ask_question(data.question)

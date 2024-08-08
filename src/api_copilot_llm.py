from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from llm_service import LLMService
import lib_copilot_telemetry

# Initialize logger and tracer
logger, tracer = lib_copilot_telemetry.instrumentator("llm", "instance-00", "llm")

# Singleton LLMService instance with logger and tracer
llm_service_instance = LLMService(logger, tracer)

def get_llm_service():
    return llm_service_instance

router = APIRouter()

class Question(BaseModel):
    question: str

@router.get("/download-models", tags=["LLM Management | Text Models"])
def download_models(llm_service: LLMService = Depends(get_llm_service)):
    return llm_service.download_models()

@router.get("/load-llm", tags=["LLM Management | Text Models"])
def load_llm(model_name: str, llm_service: LLMService = Depends(get_llm_service)):
    return llm_service.load_llm(model_name)

@router.post("/switch-model", tags=["LLM Management | Text Models"])
def switch_model(model_name: str, llm_service: LLMService = Depends(get_llm_service)):
    return llm_service.switch_model(model_name)

@router.get("/get_current_model_in_memory", tags=["LLM Management | Text Models"])
def get_current_model_in_memory(llm_service: LLMService = Depends(get_llm_service)):
    return llm_service.get_current_model_in_memory()

@router.post("/instantiate-llm", tags=["LLM Communication | Text Models"])
def instantiate_llm(llm_service: LLMService = Depends(get_llm_service)):
    return llm_service.instantiate_llm()

@router.post("/create-llm-chain", tags=["LLM Communication | Text Models"])
def create_llm_chain(llm_service: LLMService = Depends(get_llm_service)):
    return llm_service.create_llm_chain()

@router.post("/ask", tags=["LLM Communication | Text Models"])
def ask_question(data: Question, llm_service: LLMService = Depends(get_llm_service)):
    return llm_service.ask_question(data.question)

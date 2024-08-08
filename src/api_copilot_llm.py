from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from llm_service import LLMService

router = APIRouter()

class Question(BaseModel):
    question: str

# Singleton LLMService instance
llm_service_instance = LLMService()

def get_llm_service():
    return llm_service_instance

@router.get("/download-models", tags=["LLM Management | Text Models"])
def download_models(llm_service: LLMService = Depends(get_llm_service)):
    try:
        return llm_service.download_models()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/load-llm", tags=["LLM Management | Text Models"])
def load_llm(model_name: str, llm_service: LLMService = Depends(get_llm_service)):
    try:
        return llm_service.load_llm(model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/switch-model", tags=["LLM Management | Text Models"])
def switch_model(model_name: str, llm_service: LLMService = Depends(get_llm_service)):
    try:
        return llm_service.switch_model(model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_current_model_in_memory", tags=["LLM Management | Text Models"])
def get_current_model_in_memory(llm_service: LLMService = Depends(get_llm_service)):
    try:
        return llm_service.get_current_model_in_memory()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/instantiate-llm", tags=["LLM Communication | Text Models"])
def instantiate_llm(llm_service: LLMService = Depends(get_llm_service)):
    try:
        return llm_service.instantiate_llm()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-llm-chain", tags=["LLM Communication | Text Models"])
def create_llm_chain(llm_service: LLMService = Depends(get_llm_service)):
    try:
        return llm_service.create_llm_chain()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ask", tags=["LLM Communication | Text Models"])
async def ask_question(data: Question, llm_service: LLMService = Depends(get_llm_service)):
    try:
        answer = llm_service.ask_question(data.question)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

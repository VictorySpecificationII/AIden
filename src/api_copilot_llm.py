from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from svc_copilot_llm import LLMService
from lib_copilot_telemetry import OpenTelemetryInstrumentor

# Initialize the OpenTelemetryInstrumentor
instrumentor = OpenTelemetryInstrumentor(svc_name="llm", instance_id="instance-00")

# Get logger and tracer from the instrumentor
logger = instrumentor.get_logger(logging_area="llm_service")
tracer = instrumentor.get_tracer()

# Singleton LLMService instance with logger and tracer
svc_copilot_llm_instance = LLMService()

def get_svc_copilot_llm():
    return svc_copilot_llm_instance

router = APIRouter()

class Question(BaseModel):
    question: str

@router.get("/download-models", tags=["LLM Management | Text Models"])
def download_models(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    with tracer.start_as_current_span("api_download_models") as span:
        try:
            return svc_copilot_llm.download_models()
        except Exception as e:
            logger.error(f"Error in /download-models API call: {str(e)}")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/load-llm", tags=["LLM Management | Text Models"])
def load_llm(model_name: str, svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    with tracer.start_as_current_span("api_load_llm") as span:
        try:
            return svc_copilot_llm.load_llm(model_name)
        except Exception as e:
            logger.error(f"Error in /load-llm API call: {str(e)}")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/switch-model", tags=["LLM Management | Text Models"])
def switch_model(model_name: str, svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    with tracer.start_as_current_span("api_switch_model") as span:
        try:
            return svc_copilot_llm.switch_model(model_name)
        except Exception as e:
            logger.error(f"Error in /switch-model API call: {str(e)}")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_current_model_in_memory", tags=["LLM Management | Text Models"])
def get_current_model_in_memory(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    with tracer.start_as_current_span("api_get_current_model_in_memory") as span:
        try:
            return svc_copilot_llm.get_current_model_in_memory()
        except Exception as e:
            logger.error(f"Error in /get_current_model_in_memory API call: {str(e)}")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/instantiate-llm", tags=["LLM Communication | Text Models"])
def instantiate_llm(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    with tracer.start_as_current_span("api_instantiate_llm") as span:
        try:
            return svc_copilot_llm.instantiate_llm()
        except Exception as e:
            logger.error(f"Error in /instantiate_llm API call: {str(e)}")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-llm-chain", tags=["LLM Communication | Text Models"])
def create_llm_chain(svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    with tracer.start_as_current_span("api_create_llm_chain") as span:
        try:
            return svc_copilot_llm.create_llm_chain()
        except Exception as e:
            logger.error(f"Error in /create_llm_chain API call: {str(e)}")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/ask", tags=["LLM Communication | Text Models"])
def ask_question(data: Question, svc_copilot_llm: LLMService = Depends(get_svc_copilot_llm)):
    with tracer.start_as_current_span("api_ask") as span:
        try:
            return svc_copilot_llm.ask_question(data.question)
        except Exception as e:
            logger.error(f"Error in /ask API call: {str(e)}")
            tracer.set_span_status(span, success=False, message=str(e))
            raise HTTPException(status_code=500, detail=str(e))

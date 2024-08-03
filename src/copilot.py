from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import mistral_onboard_llm
import llama2_onboard_llm

app = FastAPI()

# Global variables to store the current model and LLMChain
current_model = None
current_llm_chain = None

# Request model for asking questions
class QuestionRequest(BaseModel):
    question: str

# Request model for loading models
class LoadModelRequest(BaseModel):
    llm_model_name: Optional[str] = None

@app.post("/load_model")
def load_model(request: LoadModelRequest):
    """
    Endpoint to load or reload models.
    """
    global current_model, current_llm_chain

    try:
        if request.llm_model_name == "mistral":
            model_path = mistral_onboard_llm.load_llm()
            llm = mistral_onboard_llm.instantiate_llm(model_path)
            current_llm_chain = mistral_onboard_llm.create_llm_chain(llm)
            current_model = "mistral"
            return {"message": "Mistral model loaded successfully"}
        elif request.llm_model_name == "llama2":
            model_path = llama2_onboard_llm.load_llm()
            llm = llama2_onboard_llm.instantiate_llm(model_path)
            current_llm_chain = llama2_onboard_llm.create_llm_chain(llm)
            current_model = "llama2"
            return {"message": "Llama2 model loaded successfully"}
        else:
            raise HTTPException(status_code=400, detail="Invalid model name specified")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")

@app.post("/ask")
def ask_question(request: QuestionRequest):
    """
    Endpoint to ask questions to the currently loaded model.
    """
    global current_llm_chain

    if current_llm_chain is None:
        raise HTTPException(status_code=503, detail="No model is currently loaded")

    question = request.question
    if not question:
        raise HTTPException(status_code=400, detail="No question provided")

    try:
        answer = current_llm_chain.run(question)
        return {"question": question, "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

# Optional: An endpoint to check the status of the loaded model
@app.get("/status")
def get_status():
    """
    Endpoint to get the current status of the loaded model.
    """
    if current_model:
        return {"model": current_model, "status": "loaded"}
    else:
        return {"model": None, "status": "no model loaded"}

if __name__ == "__main__":
    import uvicorn
    from startup_functions import print_banner, check_local_llm_availability, check_local_internet_connection

    # Run startup checks
    print_banner()
    check_local_llm_availability()
    check_local_internet_connection()

    # Start the FastAPI server
    print("Starting the FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

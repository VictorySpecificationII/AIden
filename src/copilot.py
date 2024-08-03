from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import startup_functions
import mistral_onboard_llm
import llama2_onboard_llm

# Define request model
class QuestionRequest(BaseModel):
    question: str

# Initialize FastAPI app
app = FastAPI()

# Define the /ask route
@app.post("/ask/mistral")
def ask_question(request: QuestionRequest):
    question = request.question

    if not question:
        raise HTTPException(status_code=400, detail="No question provided")

    model_path = mistral_onboard_llm.load_llm()
    llm = mistral_onboard_llm.instantiate_llm(model_path)
    llm_chain = mistral_onboard_llm.create_llm_chain(llm)
    answer = llm_chain.run(question)

    return {"question": question, "answer": answer}

# Define the /ask route
@app.post("/ask/llama2")
def ask_question(request: QuestionRequest):
    question = request.question

    if not question:
        raise HTTPException(status_code=400, detail="No question provided")

    model_path = llama2_onboard_llm.load_llm()
    llm = llama2_onboard_llm.instantiate_llm(model_path)
    llm_chain = llama2_onboard_llm.create_llm_chain(llm)
    answer = llm_chain.run(question)

    return {"question": question, "answer": answer}

if __name__ == "__main__":
    import uvicorn

    # Startup functions
    startup_functions.print_banner()
    startup_functions.check_local_llm_availability()
    startup_functions.check_local_internet_connection()

    # Start FastAPI app with Uvicorn
    print("Starting the FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

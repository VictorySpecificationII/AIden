from fastapi import FastAPI, Request
from api_copilot_llm import router as llm_router
import logging

app = FastAPI()

# Include the LLM router
app.include_router(llm_router, prefix="/llm-text")

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@app.get("/", tags=["Application Root"])
async def root(request: Request):
    logger.info("Root endpoint accessed.")
    return {"message": "Welcome to AIden's FastAPI server."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

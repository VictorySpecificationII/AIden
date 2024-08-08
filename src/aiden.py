from fastapi import FastAPI, Request
from api_copilot_llm import router as llm_router
import lib_copilot_telemetry

app = FastAPI()

# Include the api routers
app.include_router(llm_router, prefix="/llm-text")

# Initialize logger and tracer
logger, tracer = lib_copilot_telemetry.instrumentator("main", "instance-00", "main")

@app.get("/", tags=["Application Root"])
async def root(request: Request):
    with tracer.start_as_current_span("root-endpoint"):
        logger.info("Root endpoint accessed.")
        return {"message": "Welcome to AIden's FastAPI server."}

if __name__ == "__main__":
    import uvicorn
    from lib_copilot_startup_functions import print_banner
    print_banner()
    print("Starting AIden's FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

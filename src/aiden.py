from fastapi import FastAPI
from api_copilot_networking import router as startup_router
from api_copilot_llm import router as llm_router

app = FastAPI()

# Include the api routers
app.include_router(startup_router, prefix="/networking")
app.include_router(llm_router, prefix="/llm-text")

if __name__ == "__main__":
    import uvicorn
    from startup_functions import print_banner
    # Run startup checks
    print_banner()

    # Start the FastAPI server
    print("Starting AIden's FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code
    print("Starting up...")
    yield
    # Shutdown code
    print("Shutting down...")

api = FastAPI(lifespan=lifespan)

@api.middleware("http")
async def custom_middleware(request: Request, call_next):
    # This is a stub for a middleware function.
    # Example: You can process the request, add headers, etc.
    response = await call_next(request)
    return response

@api.get("/")
async def root():
    return {"message": "Welcome to AIden's API server."}

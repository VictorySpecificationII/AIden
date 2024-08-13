from fastapi import FastAPI
import logging

api = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@api.get("/")
async def root():
    logger.info("root point accessed")
    return {"message": "Welcome to AIden's API server."}
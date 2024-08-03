import pytest
from fastapi.testclient import TestClient
from src.copilot import app  # Import your FastAPI app

client = TestClient(app)

def test_ask_question_mistral():
    response = client.post(
        "/ask/mistral",
        json={"question": "What is AI?"}
    )
    assert response.status_code == 200
    assert "question" in response.json()
    assert "answer" in response.json()

def test_ask_question_llama2():
    response = client.post(
        "/ask/llama2",
        json={"question": "What is AI?"}
    )
    assert response.status_code == 200
    assert "question" in response.json()
    assert "answer" in response.json()

def test_ask_question_missing():
    response = client.post(
        "/ask/mistral",
        json={}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "No question provided"}

import pytest
from fastapi.testclient import TestClient
from src.aiden import app  # Replace 'your_module_name' with the actual module name

# Initialize the TestClient with your FastAPI app
client = TestClient(app)

def test_load_mistral_model():
    """
    Test loading the Mistral model.
    """
    response = client.post("/load_model", json={"llm_model_name": "mistral"})
    assert response.status_code == 200
    assert response.json() == {"message": "Mistral model loaded successfully"}

def test_load_llama2_model():
    """
    Test loading the Llama2 model.
    """
    response = client.post("/load_model", json={"llm_model_name": "llama2"})
    assert response.status_code == 200
    assert response.json() == {"message": "Llama2 model loaded successfully"}

def test_load_invalid_model():
    """
    Test loading an invalid model.
    """
    response = client.post("/load_model", json={"llm_model_name": "invalid_model"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid model name specified"}

def test_ask_question_no_model_loaded():
    """
    Test asking a question when no model is loaded.
    """
    # First, ensure no model is loaded
    global current_llm_chain
    current_llm_chain = None  # Manually set to None for testing

    response = client.post("/ask", json={"question": "What is AI?"})
    assert response.status_code == 503
    assert response.json() == {"detail": "No model is currently loaded"}

def test_ask_question_mistral():
    """
    Test asking a question with the Mistral model loaded.
    """
    # Load the Mistral model first
    client.post("/load_model", json={"llm_model_name": "mistral"})

    response = client.post("/ask", json={"question": "What is AI?"})
    assert response.status_code == 200
    assert "question" in response.json()
    assert "answer" in response.json()

def test_ask_question_llama2():
    """
    Test asking a question with the Llama2 model loaded.
    """
    # Load the Llama2 model first
    client.post("/load_model", json={"llm_model_name": "llama2"})

    response = client.post("/ask", json={"question": "What is the capital of France?"})
    assert response.status_code == 200
    assert "question" in response.json()
    assert "answer" in response.json()

def test_status_no_model_loaded():
    """
    Test status endpoint when no model is loaded.
    """
    global current_model
    current_model = None  # Ensure no model is set

    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {"model": None, "status": "no model loaded"}

def test_status_with_model_loaded():
    """
    Test status endpoint with a model loaded.
    """
    # Load the Llama2 model for this test
    client.post("/load_model", json={"llm_model_name": "llama2"})

    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {"model": "llama2", "status": "loaded"}

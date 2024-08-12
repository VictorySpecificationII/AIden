import pytest
from fastapi.testclient import TestClient
from src.aiden import app  # Adjust the import based on your application structure

client = TestClient(app)

@pytest.fixture(scope="module")
def setup():
    # Setup actions before tests
    # You might want to set up some data or configurations
    yield
    # Teardown actions after tests
    # Clean up resources, if needed

def test_download_models(setup):
    response = client.get("/download-models")
    assert response.status_code == 200
    data = response.json()
    assert "model_paths" in data
    assert data["model_paths"]["mistral"] is not None
    assert data["model_paths"]["llama2"] is not None

def test_check_downloaded_models(setup):
    # Assuming models have been downloaded
    response = client.get("/check-downloaded-models?model_name=mistral")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "model downloaded"

def test_load_llm(setup):
    response = client.get("/load-llm?model_name=mistral")
    assert response.status_code == 200
    data = response.json()
    assert "model_path" in data

def test_instantiate_llm(setup):
    response = client.post("/instantiate-llm")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "LLM instantiated"

def test_create_llm_chain(setup):
    response = client.post("/create-llm-chain")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "LLMChain created"

def test_ask_question(setup):
    response = client.post("/ask", json={"question": "What is the capital of France?"})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data

def test_get_current_model_in_memory(setup):
    response = client.get("/get_current_model_in_memory")
    assert response.status_code == 200
    data = response.json()
    assert "model" in data

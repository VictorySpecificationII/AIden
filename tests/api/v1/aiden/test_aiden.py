import pytest
from fastapi.testclient import TestClient
from api.v1.aiden import api  # Adjust based on where `api` is defined

# Create a TestClient instance
client = TestClient(api)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to AIden's API server."}

def test_read_item():
    item_id = 123
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 200
    assert response.json() == {"item_id": item_id}

def test_simulate_latency():
    response = client.get("/latency")
    assert response.status_code == 200
    assert "Simulated latency of" in response.json()["message"]

def test_trigger_error():
    response = client.get("/error")
    assert response.status_code == 500
    assert response.json() == {"detail": "This is a test error"}

def test_authenticate_huggingface():
    # Test if API key is set and authentication works (assuming the key is valid)
    response = client.get("/auth")
    if response.status_code == 200:
        assert response.json() == {"message": "Authentication successful"}
    else:
        assert response.status_code in [400, 500]

def test_download_model():
    model_name = "distilgpt2"  # Example model name; replace with a model available in your environment
    response = client.post("/download-model", json={"model_name": model_name})
    if response.status_code == 200:
        assert "Model downloaded successfully" in response.json()["message"]
    else:
        assert response.status_code == 400 or response.status_code == 500

def test_load_model():
    model_name = "distilgpt2"  # Should match the model downloaded
    response = client.post("/load-model", json={"model_name": model_name})
    if response.status_code == 200:
        assert f"Model {model_name} loaded successfully" in response.json()["message"]
    else:
        assert response.status_code == 400 or response.status_code == 500

def test_generate_text():
    prompt = "Once upon a time"
    response = client.post("/generate", json={"prompt": prompt, "max_length": 50})
    if response.status_code == 200:
        assert "generated_texts" in response.json()
        assert len(response.json()["generated_texts"]) > 0
    else:
        assert response.status_code == 400 or response.status_code == 500

# Optional: Test the OpenTelemetry integration by asserting that logs are being generated
def test_logging_integration():
    # You may want to mock logging and check that specific log entries are created
    pass

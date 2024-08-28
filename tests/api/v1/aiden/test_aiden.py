# /home/antreas/Desktop/AIden/src/tests/test_aiden.py

import pytest
from fastapi.testclient import TestClient
from src.api.v1.aiden import api  # Adjust import based on the package location

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

# Optional: Test the OpenTelemetry integration by asserting that logs are being generated
def test_logging_integration():
    # You may want to mock logging and check that specific log entries are created
    pass

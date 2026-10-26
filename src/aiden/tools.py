"""The original tool server: date/time tools exposed over OpenAPI for OpenWebUI."""
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from telemetry import tracer

api = APIRouter()

# --- Tool Server Models ---
class DateResponse(BaseModel):
    date: str

class TimeSimpleResponse(BaseModel):
    time: str

class TimeISOResponse(BaseModel):
    time_iso: str

class ErrorResponse(BaseModel):
    error: str

# --- Tools class ---
class Tools:
    class Valves(BaseModel):
        pass

    class UserValves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()

    def get_current_date(self) -> str:
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        return f"Today's date is {current_date}"

    def get_current_time(self) -> str:
        current_time = datetime.now().strftime("%H:%M:%S")
        return f"Current Time: {current_time}"

tools = Tools()

# --- Auth (Allow all bearer tokens) ---
auth_scheme = HTTPBearer()

def allow_all_tokens(auth: HTTPAuthorizationCredentials = Security(auth_scheme)):
    # No validation – accept any bearer token
    return auth.credentials

# --- Tool Endpoints ---

@api.get("/tool/get_date", response_model=DateResponse)
def get_date(token: str = Depends(allow_all_tokens)):
    with tracer.start_as_current_span("tool.get_current_date"):
        date_str = tools.get_current_date().replace("Today's date is ", "")
        return {"date": date_str}

@api.get("/tool/get_time_simple", response_model=TimeSimpleResponse)
def get_time_simple(token: str = Depends(allow_all_tokens)):
    with tracer.start_as_current_span("tool.get_current_time_simple"):
        time_str = tools.get_current_time().replace("Current Time: ", "")
        return {"time": time_str}

@api.get("/tool/get_time", response_model=TimeISOResponse)
def get_time(iso: bool = True, token: str = Depends(allow_all_tokens)):
    with tracer.start_as_current_span("tool.get_current_time"):
        if iso:
            now = datetime.now(timezone.utc).astimezone()
            return {"time_iso": now.isoformat()}
        return {"time_iso": datetime.now().isoformat()}

# --- Tool Discovery ---

@api.get("/tools", response_model=Dict[str, str])
def list_tools():
    return {
        "get_date": "Return today's date",
        "get_time_simple": "Return the current time in HH:MM:SS",
        "get_time": "Return current time in ISO 8601 format",
    }

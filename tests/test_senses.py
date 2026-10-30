"""Senses: AIden noticing whether their models can still generate."""
from types import SimpleNamespace

import pytest

import senses


class Reply:
    def __init__(self, ok=True):
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise senses.requests.HTTPError("500 Server Error")

    def json(self):
        return {"choices": [{"message": {"content": "OK"}}]}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(senses, "status", {})


def test_a_model_that_answers_is_generating(monkeypatch):
    sent = {}
    monkeypatch.setattr(senses.requests, "post", lambda url, json, timeout: sent.update(url=url, **json) or Reply())
    result = senses.probe("ovms-gpu", "http://ovms-gpu:8002/v3", "qwen")
    assert result["generating"] is True and result["failures"] == 0
    assert sent["url"].endswith("/v3/chat/completions") and sent["max_tokens"] == 1


def test_failures_are_counted_and_cleared_on_recovery(monkeypatch):
    monkeypatch.setattr(senses.requests, "post", lambda *a, **k: Reply(ok=False))
    senses.probe("ovms-gpu", "http://g", "qwen")
    assert senses.probe("ovms-gpu", "http://g", "qwen")["failures"] == 2
    assert senses.status["ovms-gpu"]["generating"] is False and "HTTPError" in senses.status["ovms-gpu"]["error"]
    monkeypatch.setattr(senses.requests, "post", lambda *a, **k: Reply())
    assert senses.probe("ovms-gpu", "http://g", "qwen")["failures"] == 0


def test_an_expected_backend_that_is_down_counts_as_not_generating(monkeypatch):
    backend = lambda name, tier, available, models: SimpleNamespace(
        name=name, tier=tier, url=f"http://{name}", available=available, models=models)
    capabilities = SimpleNamespace(backends=[
        backend("ovms-gpu", "intel-gpu", True, []),    # up, but stuck loading its model
        backend("ovms-npu", "npu", True, ["phi"]),
        backend("ollama", "cpu", True, []),             # up, no models pulled: not a fault
    ])
    monkeypatch.setattr("capabilities.get_capabilities", lambda: capabilities)
    monkeypatch.setattr("capabilities.active_profiles", lambda: ["cpu", "npu", "intel-gpu"])
    monkeypatch.setattr(senses.requests, "post", lambda *a, **k: Reply())
    senses.probe_all()
    assert senses.status["ovms-gpu"]["generating"] is False and senses.status["ovms-gpu"]["error"] == "server not ready"
    assert senses.status["ovms-npu"]["generating"] is True
    assert "ollama" not in senses.status


def test_metric_reports_each_backend():
    senses.status.update({"ovms-gpu": {"generating": False}, "ovms-npu": {"generating": True}})
    assert {(o.attributes["backend"], o.value) for o in senses.observe(None)} == {("ovms-gpu", 0), ("ovms-npu", 1)}


@pytest.mark.parametrize("replies, expected", [
    (["TOOL: current_time {}", "4"], True),                       # asks when needed, plain otherwise
    (["TOOMANK: current_time {}", "4"], False),                   # garbled protocol (Phi)
    (["TOOL: current_time {}", "TOWN: current_time {}"], False),  # reaches for tools when it shouldn't
    (["It is noon.", "4"], False),                                # never asks
    (["TOOL: current_time {}", "To answer that: 2 + 2 = 4."], True),  # plain answers may start with "To"
])
def test_tool_protocol_test(monkeypatch, replies, expected):
    answers = iter(replies)
    monkeypatch.setattr(senses, "ask", lambda base, model, messages: next(answers))
    monkeypatch.setattr(senses, "tool_status", {})
    assert senses.test_tools("ovms-x", "http://x", "m")["tools"] is expected
    assert senses.tool_status["ovms-x"]["model"] == "m"


def test_a_model_is_tested_once_and_again_when_it_changes(monkeypatch):
    backend = SimpleNamespace(name="ovms-gpu", tier="intel-gpu", url="http://g", available=True, models=["qwen"])
    capabilities = SimpleNamespace(backends=[backend])
    monkeypatch.setattr("capabilities.get_capabilities", lambda: capabilities)
    monkeypatch.setattr("capabilities.active_profiles", lambda: ["intel-gpu"])
    monkeypatch.setattr(senses.requests, "post", lambda *a, **k: Reply())
    monkeypatch.setattr(senses, "tool_status", {})
    tested = []
    monkeypatch.setattr(senses, "test_tools", lambda name, url, model: tested.append(model) or senses.tool_status.update(
        {name: {"model": model, "tools": True, "detail": "ok"}}))
    senses.probe_all(); senses.probe_all()
    backend.models = ["llama"]
    senses.probe_all()
    assert tested == ["qwen", "llama"]

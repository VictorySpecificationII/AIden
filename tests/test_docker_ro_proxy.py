"""docker-ro-proxy: only a few GET requests reach Docker, and never container secrets."""
import importlib.util
import json
import pathlib

import pytest

spec = importlib.util.spec_from_file_location(
    "docker_ro_proxy", pathlib.Path(__file__).parent.parent / "tools/sre/docker-ro-proxy/docker_ro_proxy.py")
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.fixture
def docker(monkeypatch):
    calls = []

    def fake(path):
        calls.append(path)
        if path.endswith("/json") and "/containers/" in path and not path.startswith("/containers/json"):
            return 200, json.dumps({"Config": {"Env": ["MENTOR_TOKEN=secret"], "Image": "x"}, "RestartCount": 2}).encode()
        return 200, b"[]"

    monkeypatch.setattr(proxy, "docker_get", fake)
    monkeypatch.setattr(proxy, "LOG_CONTAINERS", {"ovms-gpu"})
    return calls


def test_inspect_never_reveals_environment_variables(docker):
    status, body = proxy.route("/containers/ovms-gpu/json")
    data = json.loads(body)
    assert status == 200 and "Env" not in data["Config"] and data["RestartCount"] == 2
    assert b"secret" not in body


def test_logs_only_for_listed_containers_and_tail_is_capped(docker):
    assert proxy.route("/containers/mentor-bridge/logs") is None
    proxy.route("/containers/ovms-gpu/logs?tail=999999&since=123")
    assert "tail=5000" in docker[-1] and "since=123" in docker[-1]


@pytest.mark.parametrize("path", [
    "/containers/ovms-gpu/start", "/containers/ovms-gpu/exec", "/images/json", "/v1.43/containers/json",
    "/containers/../json", "/containers/a%2Fb/json", "/volumes", "/containers/ovms-gpu/archive?path=/",
])
def test_everything_else_is_refused(docker, path):
    assert proxy.route(path) is None and docker == []

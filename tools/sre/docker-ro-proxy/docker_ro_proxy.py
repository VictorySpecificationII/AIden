"""Read-only window onto Docker for AIden.

The Docker socket can't be mounted read-only in any meaningful way: anyone who can
reach it can create, stop or delete containers. So AIden never gets it. This proxy holds
the socket and answers only a few GET requests:

    GET /containers/json                 list containers (state, status)
    GET /containers/{name}/json          inspect, with Config.Env removed (it holds secrets)
    GET /containers/{name}/logs          logs, for LOG_CONTAINERS only, tail capped

Everything else gets 403. Standard library only.
"""
import http.client
import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
PORT = int(os.environ.get("PROXY_PORT", "2375"))
LOG_CONTAINERS = set(filter(None, os.environ.get("LOG_CONTAINERS", "").split(",")))
MAX_TAIL = 5000
NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]*"


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(SOCKET)


def docker_get(path: str):
    conn = UnixConnection("docker")
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def without_env(body: bytes) -> bytes:
    data = json.loads(body)
    (data.get("Config") or {}).pop("Env", None)
    return json.dumps(data).encode()


def route(raw_path: str):
    """(status, body) for an allowed request, or None when it isn't allowed."""
    url = urlparse(raw_path)
    query = parse_qs(url.query)
    if url.path == "/containers/json":
        return docker_get("/containers/json?" + urlencode({"all": "1"}))
    match = re.fullmatch(rf"/containers/({NAME})/json", url.path)
    if match:
        status, body = docker_get(f"/containers/{match[1]}/json")
        return status, without_env(body) if status == 200 else body
    match = re.fullmatch(rf"/containers/({NAME})/logs", url.path)
    if match and match[1] in LOG_CONTAINERS:
        params = {"stdout": "1", "stderr": "1", "timestamps": "1",
                  "tail": str(min(int(query.get("tail", ["500"])[0]), MAX_TAIL))}
        if "since" in query and query["since"][0].isdigit():
            params["since"] = query["since"][0]
        return docker_get(f"/containers/{match[1]}/logs?" + urlencode(params))
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            result = route(self.path)
        except (OSError, ValueError) as exc:
            result = (502, json.dumps({"error": type(exc).__name__}).encode())
        status, body = result or (403, b'{"error": "not allowed: read-only proxy"}')
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def refuse(self):
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = refuse

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

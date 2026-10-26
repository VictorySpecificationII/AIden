"""AIden's mentor bridge: lets AIden ask Claude through the Claude Code CLI on the host.

Runs on the host (where Claude Code is logged in), not in a container, so the user's
credentials never enter the stack. AIden calls POST /ask over the Docker bridge.

Each question runs as:
    claude -p --tools "" --setting-sources project --strict-mcp-config
           --no-session-persistence --output-format json --system-prompt ...
from an empty working directory: no tools (a crafted question can't make Claude Code
act on the host), and none of the user's own CLAUDE.md, memories or MCP servers.

Guard rails: shared token, one call at a time, MENTOR_MAX_PER_HOUR calls per hour,
timeout. Only the question (and AIden's draft, when it didn't use the user's notes)
ever reaches it; AIden's router enforces that before calling.

Configuration (environment, e.g. systemd EnvironmentFile=AIden/.env):
    MENTOR_TOKEN          required, shared with the aiden service
    MENTOR_BIND           default 172.17.0.1 (docker0: containers only, not the LAN)
    MENTOR_PORT           default 8765
    MENTOR_MAX_PER_HOUR   default 10
    MENTOR_MODEL          optional, e.g. a smaller model to save limits
    MENTOR_TIMEOUT_S      default 180
    CLAUDE_BIN            default: claude on PATH
"""
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("MENTOR_TOKEN", "")
BIND = os.environ.get("MENTOR_BIND", "172.17.0.1")
PORT = int(os.environ.get("MENTOR_PORT", "8765"))
MAX_PER_HOUR = int(os.environ.get("MENTOR_MAX_PER_HOUR", "10"))
MODEL = os.environ.get("MENTOR_MODEL", "")
TIMEOUT_S = int(os.environ.get("MENTOR_TIMEOUT_S", "180"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"
# Empty directory: no project CLAUDE.md or settings to pick up
WORKDIR = tempfile.mkdtemp(prefix="aiden-mentor-")

SYSTEM_PROMPT = (
    "You are the mentor of AIden, a small local AI co-pilot running on the user's laptop. "
    "AIden asks you when they, or the user, are unsure. You only see the question (and "
    "sometimes AIden's draft answer), never the user's private notes. Answer the question "
    "directly and concisely for the user. If AIden's draft is included, say what it got "
    "right or wrong. If you're unsure too, say so plainly."
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mentor-bridge")
busy = threading.Lock()
recent_calls: deque = deque()


def calls_left() -> int:
    cutoff = time.time() - 3600
    while recent_calls and recent_calls[0] < cutoff:
        recent_calls.popleft()
    return MAX_PER_HOUR - len(recent_calls)


def ask_claude(question: str, draft: str) -> dict:
    prompt = question if not draft else (
        f"The user asked:\n{question}\n\nAIden's draft answer:\n{draft}\n\n"
        "Give the user your answer, and say briefly whether AIden's draft was right.")
    cmd = [CLAUDE_BIN, "-p", "--tools", "", "--setting-sources", "project", "--strict-mcp-config",
           "--no-session-persistence", "--output-format", "json", "--system-prompt", SYSTEM_PROMPT]
    if MODEL:
        cmd += ["--model", MODEL]
    start = time.time()
    proc = subprocess.run(cmd + [prompt], cwd=WORKDIR, capture_output=True, text=True, timeout=TIMEOUT_S)
    result = json.loads(proc.stdout)
    if result.get("is_error"):
        raise RuntimeError(result.get("result") or "claude returned an error")
    return {"answer": result.get("result", ""), "model": next(iter(result.get("modelUsage") or {}), MODEL or "claude"),
            "duration_ms": round((time.time() - start) * 1000)}


class Handler(BaseHTTPRequestHandler):
    def reply(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorised(self) -> bool:
        return bool(TOKEN) and self.headers.get("X-Mentor-Token") == TOKEN

    def do_GET(self):
        if self.path != "/health":
            return self.reply(404, {"error": "not found"})
        if not self.authorised():
            return self.reply(401, {"error": "unauthorised"})
        self.reply(200, {"ok": True, "calls_left_this_hour": calls_left(), "busy": busy.locked(),
                         "claude": os.path.exists(CLAUDE_BIN) or bool(shutil.which(CLAUDE_BIN))})

    def do_POST(self):
        if self.path != "/ask":
            return self.reply(404, {"error": "not found"})
        if not self.authorised():
            return self.reply(401, {"error": "unauthorised"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            question, draft = str(body["question"]).strip(), str(body.get("draft") or "").strip()
        except (ValueError, KeyError):
            return self.reply(400, {"error": "expected JSON with 'question'"})
        if not question:
            return self.reply(400, {"error": "empty question"})
        if calls_left() <= 0:
            return self.reply(429, {"error": f"mentor limit reached ({MAX_PER_HOUR} per hour)"})
        if not busy.acquire(blocking=False):
            return self.reply(429, {"error": "mentor is busy with another question"})
        try:
            recent_calls.append(time.time())
            log.info("Asking Claude (%d chars, draft %s)", len(question), "yes" if draft else "no")
            answer = ask_claude(question, draft)
            log.info("Claude answered in %d ms", answer["duration_ms"])
            self.reply(200, answer)
        except subprocess.TimeoutExpired:
            self.reply(504, {"error": f"claude took longer than {TIMEOUT_S} s"})
        except (RuntimeError, ValueError, OSError) as exc:
            log.warning("Mentor call failed: %s", exc)
            self.reply(502, {"error": f"claude failed: {exc}"})
        finally:
            busy.release()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("MENTOR_TOKEN is not set")
    log.info("Mentor bridge on %s:%d using %s (max %d/hour)", BIND, PORT, CLAUDE_BIN, MAX_PER_HOUR)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()

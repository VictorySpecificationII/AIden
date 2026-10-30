"""Tools any model can use: AIden's own plain-text protocol, and the loop that runs them.

Tool calling is AIden's, not the model's or the server's: the system prompt lists the
tools and asks for a reply of only lines like

    TOOL: suspends {}
    TOOL: container_errors {"name": "ovms-gpu", "hours": 6}

AIden reads those lines, runs the tools (AIden's read-only terminal plus the clock), adds
the results to the conversation and asks again, at most MAX_ROUNDS times; the last request
has no tools, so the model must answer. Any instruct model can follow this, on any
server, and AIden's own model will learn the same protocol. A reply that doesn't start
with TOOL: is relayed as it streams, so tools cost nothing when they aren't needed.
Unknown tools and bad arguments are answered with an error result, never raised.

Not every model can follow the protocol (Phi-3.5-mini garbles it, and the instructions
make its ordinary answers worse), so by default only models that pass AIden's own test
(senses.test_tools) are offered tools.
"""
import json
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import terminal

# Backends offered tools: "auto" (default) = those whose model passed AIden's protocol test
# (senses.test_tools); or "*" for all, or a comma-separated list of backend names
TOOL_BACKENDS = os.environ.get("AIDEN_TOOL_BACKENDS", "auto")
MAX_ROUNDS = 3
MAX_RESULT_CHARS = 4000
TOOL_LINE = re.compile(r"^[\s`*>]*TOOL:[\s`*]*([A-Za-z_]+)\s*(\{.*\})?[\s`*]*$")
PREFIX = "TOOL:"

CONTAINER_NAMES = "|".join(terminal.CONTAINERS)
# name: (arguments, description)
TOOLS: Dict[str, Tuple[str, str]] = {
    "current_time": ("{}", "the current local date and time"),
    "uptime": ("{}", "how long your machine has been running and when it booted"),
    "memory": ("{}", "total and available memory on your machine"),
    "load": ("{}", "CPU load averages on your machine"),
    "suspends": ("{}", "how many times your machine has slept (suspended) since boot"),
    "sleep_log": ("{}", "when your machine went to sleep and woke up, this boot"),
    "gpu_kernel_log": ("{}", "warnings the kernel logged about the Intel GPU this boot"),
    "model_health": ("{}", "whether each of your model servers could generate at your last check"),
    "containers": ("{}", "your containers and their state"),
    "container": (f'{{"name": "{CONTAINER_NAMES}"}}', "status, health and restart count of one of your containers"),
    "container_errors": (f'{{"name": "{CONTAINER_NAMES}", "hours": 1-72}}', "error lines from one of your containers' logs"),
}

INSTRUCTION = (
    "\n\nYou can look at your own machine with read-only tools. To use tools, reply with only "
    "tool lines, one per tool and nothing else, in exactly this form:\n"
    "TOOL: <name> <JSON arguments>\n"
    "You will then get the results and can answer. Use a tool only when the question needs "
    "facts about your machine, your models or the current time. Available tools:\n"
    + "\n".join(f"- {name} {args}: {desc}" for name, (args, desc) in TOOLS.items())
)
RESULTS_INTRO = "Results from your tools (not from the user). Answer the user's question with them now."


def offered(backend: str) -> bool:
    if TOOL_BACKENDS == "auto":
        import senses
        return senses.tool_status.get(backend, {}).get("tools") is True
    return TOOL_BACKENDS == "*" or backend in TOOL_BACKENDS.split(",")


def execute(name: str, arguments: str) -> Tuple[str, bool]:
    """Run one tool; returns (result text for the model, ok)."""
    if name not in TOOLS:
        return json.dumps({"error": f"no such tool: {name}"}), False
    if TOOLS[name][0] == "{}":
        args = {}  # takes no arguments: whatever a model invented doesn't matter
    else:
        try:
            args = json.loads(arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be an object")
        except ValueError as exc:
            return json.dumps({"error": f"bad arguments: {exc}"}), False
    if name == "current_time":
        result = {"command": name, "ok": True, "output": datetime.now().astimezone().strftime("%A %d %B %Y, %H:%M %Z")}
    elif name == "model_health":
        import senses
        result = {"command": name, "ok": True, "output": {
            backend: {k: s.get(k) for k in ("generating", "error", "failures", "checked_at")}
            for backend, s in senses.status.items()}}
    else:
        result = terminal.run(name.replace("_", "-"), **{k: v for k, v in args.items() if k in ("name", "hours")})
    return json.dumps(result, default=str)[:MAX_RESULT_CHARS], result["ok"]


def parse(text: str) -> List[Dict[str, str]]:
    """The TOOL: lines in a reply, in order."""
    calls = []
    for line in text.splitlines():
        match = TOOL_LINE.match(line)
        if match:
            calls.append({"name": match[1], "arguments": match[2] or "{}"})
    return calls


class Replay:
    """A streamed response whose first lines were already read: replays them, then the rest."""

    def __init__(self, response, seen: List[str], rest: Iterator[str]):
        self.response, self.seen, self.rest = response, seen, rest
        self.encoding = "utf-8"

    def iter_lines(self, decode_unicode=True):
        yield from self.seen
        yield from self.rest


def delta_text(line: str) -> str:
    if not line or not line.startswith("data: ") or line.strip() == "data: [DONE]":
        return ""
    choice = (json.loads(line[6:]).get("choices") or [{}])[0]
    return (choice.get("delta") or {}).get("content") or ""


def peek(response) -> Tuple[Optional[str], Any]:
    """Read a streamed reply until it shows what it is: (its full text, None) when it is a
    tool request, (None, replayable response) when the model is answering."""
    response.encoding = "utf-8"
    lines = response.iter_lines(decode_unicode=True)
    seen, text = [], ""
    for line in lines:
        seen.append(line)
        text += delta_text(line)
        start = text.lstrip(" \n`*>")
        if len(start) >= len(PREFIX) or (start and not PREFIX.startswith(start[:len(PREFIX)])):
            if not start.startswith(PREFIX):
                return None, Replay(response, seen, lines)
            text += "".join(delta_text(l) for l in lines)  # a tool request: read it all
            return text, None
    return (text, None) if text.lstrip(" \n`*>").startswith(PREFIX) else (None, Replay(response, seen, iter(())))


def with_instruction(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if messages and messages[0].get("role") == "system":
        return [{**messages[0], "content": messages[0]["content"] + INSTRUCTION}] + messages[1:]
    return [{"role": "system", "content": INSTRUCTION.strip()}] + messages


def converse(send: Callable[[List[Dict[str, Any]]], Any], messages: List[Dict[str, Any]],
             stream: bool, use_tools: bool) -> Tuple[Any, List[Dict[str, Any]]]:
    """Ask the model, running any tools it asks for. send(messages) makes one request.
    Returns (final response, tool calls made: name, arguments, ok)."""
    made: List[Dict[str, Any]] = []
    exchange: List[Dict[str, Any]] = []
    for round_ in range(MAX_ROUNDS + 1):
        offer = use_tools and round_ < MAX_ROUNDS
        response = send((with_instruction(messages) if offer else messages) + exchange)
        if not offer:
            return response, made
        if stream:
            text, replay = peek(response)
        else:
            content = ((response.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            text, replay = (content, None) if content.lstrip(" \n`*>").startswith(PREFIX) else (None, response)
        calls = parse(text) if text is not None else []
        if not calls:
            # Not a tool request after all (or one AIden can't read): answer without tools
            return (replay if replay is not None else send(messages + exchange)), made
        results = []
        for call in calls:
            result, ok = execute(call["name"], call["arguments"])
            made.append({**call, "ok": ok})
            results.append(f"{call['name']}: {result}")
        exchange += [{"role": "assistant", "content": "\n".join(f"TOOL: {c['name']} {c['arguments']}" for c in calls)},
                     {"role": "user", "content": RESULTS_INTRO + "\n" + "\n".join(results)}]
    return response, made

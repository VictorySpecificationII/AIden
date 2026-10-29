"""AIden's router: answers chat requests by splitting the work across devices.

For each request:
1. Does it need the user's notes? Keyword rules decide the obvious cases; the NPU
   model classifies the unclear ones.
2. If so, search the vault (query embedded on CPU) and keep matches above a score.
3. Answer with the best available chat backend (Intel GPU, then NPU, then Ollama),
   citing the notes used.

Privacy: vault content may only be sent to local backends. check_outbound() is the
gate every backend call goes through; it refuses to send vault text anywhere else
(e.g. to the Claude mentor, once that exists).
"""
import json
import os
import re
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlparse

import requests

import senses
import vault

CLASSIFIER = {"url": "http://ovms-npu:8001/v3", "model": os.environ.get("OVMS_NPU_MODEL_NAME", "")}
# Preferred order for answering; the first available one with a model is used
ANSWER_BACKENDS = ["ovms-gpu", "ovms-npu", "ollama"]
OLLAMA_OPENAI_PATH = "/v1"
MIN_NOTE_SCORE = float(os.environ.get("AIDEN_MIN_NOTE_SCORE", "0.45"))
# The local model ends every reply with "Confidence: high|medium|low"; the router removes
# that line and treats "low" as doubt. (A marker the model should add "only when unsure"
# didn't work: Qwen3-8B added it to every answer, even "12 times 12".)
CONFIDENCE_LINE = re.compile(r"\n?[ \t*_]*confidence[ \t*_]*:[ \t*_]*(high|medium|low)[ \t*_.]*\s*$", re.IGNORECASE)
CONFIDENCE_HOLD = len("**Confidence: medium**") + 4
MENTOR_OFFER = "I'm not confident about this one. Say \"ask Claude\" if you'd like a second opinion."
ANSWER_TIMEOUT_S = 180       # whole non-streamed answer
STREAM_READ_TIMEOUT_S = 60   # first token / gap between streamed chunks
MAX_NOTES = 5
LOCAL_HOSTS = {"ovms-npu", "ovms-gpu", "ollama", "ovms-embed-query", "ovms-embed-index", "qdrant", "localhost"}

SYSTEM_PROMPT = (
    "You are AIden, the user's personal co-pilot running locally on their own machine. "
    "Be direct and concise. You and the user work things out together, and being unsure is "
    "normal and welcome. End every reply with a final line 'Confidence: high', "
    "'Confidence: medium' or 'Confidence: low'. Use high for well-known facts, definitions, "
    "arithmetic and anything you clearly know. Use low when you may well be wrong: events or "
    "releases after your training data, predictions, niche specifics you can't verify, or "
    "guesses; then also say what you're unsure about and why."
)
# Only added when notes are attached, otherwise models invent citations
NOTES_INSTRUCTION = (
    "Base your answer on the notes from the user's Obsidian vault below and cite them inline "
    "as [1], [2] matching their numbers. If the notes don't contain the answer, say so plainly "
    "rather than guessing."
)

# --- Background tasks from the chat UI ---------------------------------------

# OpenWebUI asks the chat model for titles, tags and follow-up suggestions with prompts
# that start like this. They're not the user talking to AIden: no notes, no confidence
# line, no footers (the UI expects clean JSON back), and they're recorded apart.
BACKGROUND_TASK = re.compile(r"^\s*###\s*Task:\s*(.*)")


def background_task(prompt: str) -> Optional[str]:
    """The task's one-line description if this is a UI background task, else None."""
    match = BACKGROUND_TASK.match(prompt or "")
    return (match.group(1).strip()[:80] or "unspecified") if match else None


# --- Step 1: does this request need the user's notes? -------------------------

NOTES_PATTERNS = [
    r"\bmy (notes?|vault|obsidian|knowledge ?base)\b",
    r"\bwhat (did|do|have) i (decide|write|wrote|note|say|plan|think)\b",
    r"\b(did|have) i (decide|write|note|mention|plan)\b",
    r"\b(last|this|previous) (week|month|meeting|call|session)\b",
    r"\bremind me\b",
    r"\b(aiden|hive|legion|client|clients)\b",
    r"\bin my\b.*\b(project|plan|setup|runbook|notes?)\b",
]
NO_NOTES_PATTERNS = [
    r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|cool|great)\b[\s!.]*$",
]
_note_titles: List[str] = []


def note_titles() -> List[str]:
    """Distinctive note and folder names from the vault, so mentioning one routes to notes."""
    if not _note_titles and os.path.isdir(vault.VAULT_DIR):
        names = set()
        for path in vault.notes_on_disk():
            for part in [os.path.splitext(os.path.basename(path))[0]] + path.split(os.sep)[:-1]:
                if len(part) >= 6 and not part.lower().startswith("untitled"):
                    names.add(part.lower())
        _note_titles.extend(sorted(names, key=len, reverse=True))
    return _note_titles


def rules_decide(prompt: str) -> Tuple[Optional[bool], str]:
    """(True/False when a rule settles it, None when it's unclear; which rule)."""
    text = prompt.lower()
    for pattern in NO_NOTES_PATTERNS:
        if re.search(pattern, text):
            return False, f"no-notes pattern {pattern}"
    for pattern in NOTES_PATTERNS:
        if re.search(pattern, text):
            return True, f"notes pattern {pattern}"
    for title in note_titles():
        if title in text:
            return True, f"mentions note or folder '{title}'"
    return None, "no rule matched"


def classify_with_npu(prompt: str) -> Tuple[Optional[bool], str]:
    question = (
        "Does answering the following message require the user's own personal notes "
        "(their projects, decisions, clients, plans or past work)? Reply with only yes or no.\n\n"
        f"Message: {prompt[:1000]}"
    )
    try:
        response = requests.post(f"{CLASSIFIER['url']}/chat/completions", timeout=15, json={
            "model": CLASSIFIER["model"], "max_tokens": 3, "temperature": 0,
            "messages": [{"role": "user", "content": question}]})
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip().lower()
        if answer.startswith("yes"):
            return True, f"classifier said '{answer}'"
        if answer.startswith("no"):
            return False, f"classifier said '{answer}'"
        return None, f"classifier gave an unclear answer '{answer[:40]}'"
    except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
        return None, f"classifier failed: {type(exc).__name__}"


def needs_notes(prompt: str) -> Tuple[bool, str, str]:
    """(decision, how it was decided: rule/npu/fallback, the reason in words)."""
    decision, reason = rules_decide(prompt)
    if decision is not None:
        return decision, "rule", reason
    decision, verdict = classify_with_npu(prompt)
    if decision is not None:
        return decision, "npu", verdict
    # Classifier unavailable: searching is cheap and the score threshold filters noise
    return True, "fallback", f"{verdict}; searching anyway"


# --- Step 2: retrieve ---------------------------------------------------------

def retrieve(prompt: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(notes kept, all matches before the score threshold)."""
    try:
        results = vault.search(prompt, limit=MAX_NOTES)
    except (requests.RequestException, KeyError, ValueError):
        return [], []
    return [r for r in results if r["score"] >= MIN_NOTE_SCORE], results


def notes_context(notes: List[Dict[str, Any]]) -> str:
    blocks = [f"[{i}] {n['path']} — {n['heading'] or '(top)'}\n{n['text']}" for i, n in enumerate(notes, 1)]
    return "Notes from the user's vault:\n\n" + "\n\n".join(blocks)


def sources_footer(notes: List[Dict[str, Any]], answer: str) -> str:
    """Only the notes the answer actually cites, so unused matches don't look like sources."""
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    lines = [f"[{i}] {n['path']}" + (f" › {n['heading']}" if n["heading"] else "")
             for i, n in enumerate(notes, 1) if i in cited]
    return "\n\nSources:\n" + "\n".join(lines) if lines else ""


def split_confidence(text: str) -> Tuple[str, Optional[str]]:
    """Remove the trailing confidence line; (text, "high"/"medium"/"low" or None)."""
    match = CONFIDENCE_LINE.search(text)
    if not match:
        return text, None
    return text[:match.start()].rstrip(), match.group(1).lower()


def split_unsure(text: str) -> Tuple[str, bool]:
    """(text without the confidence line, whether the model said its confidence is low)."""
    stripped, level = split_confidence(text)
    return stripped, level == "low"


# --- Step 3: answer -----------------------------------------------------------

def check_outbound(url: str, payload: Dict[str, Any], notes: List[Dict[str, Any]]):
    """Refuse to send vault content to anything that isn't a local service."""
    if not notes or urlparse(url).hostname in LOCAL_HOSTS:
        return
    body = json.dumps(payload)
    if any(n["text"][:200] in body for n in notes) or "Notes from the user's vault" in body:
        raise PermissionError(f"Refusing to send vault content to non-local host {urlparse(url).hostname}")


def candidate_backends(capabilities) -> List[Tuple[str, str, str]]:
    """(name, base url, model) of the available answering backends, in preference order.
    "Available" only means the server answers health checks. A backend that couldn't
    generate at AIden's last probe (see senses.py) goes to the back of the line rather
    than first; one that wedges mid-request is caught by the request timeout."""
    by_name = {b.name: b for b in capabilities.backends}
    candidates, degraded = [], []
    for name in ANSWER_BACKENDS:
        backend = by_name.get(name)
        if backend and backend.available and backend.models:
            base = backend.url + OLLAMA_OPENAI_PATH if name == "ollama" else backend.url
            (degraded if getattr(backend, "generating", None) is False else candidates).append((name, base, backend.models[0]))
    return candidates + degraded


def build_messages(messages: List[Dict[str, Any]], notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    system = SYSTEM_PROMPT + (f" {NOTES_INSTRUCTION}\n\n{notes_context(notes)}" if notes else "")
    history = [m for m in messages if m.get("role") != "system"]
    return [{"role": "system", "content": system}] + history


def backend_request(base: str, model: str, messages, stream: bool, request: Dict[str, Any], notes) -> requests.Response:
    payload = {"model": model, "messages": messages, "stream": stream,
               "max_tokens": request.get("max_tokens") or 1024,
               "chat_template_kwargs": {"enable_thinking": False}}
    if request.get("temperature") is not None:
        payload["temperature"] = request["temperature"]
    url = f"{base}/chat/completions"
    check_outbound(url, payload, notes)
    # Connect fast; when streaming the read timeout is per chunk, so a stall is caught quickly
    response = requests.post(url, json=payload, stream=stream, timeout=(5, STREAM_READ_TIMEOUT_S if stream else ANSWER_TIMEOUT_S))
    response.raise_for_status()
    return response


SHOW_ROUTE = os.environ.get("AIDEN_SHOW_ROUTE", "true").lower() != "false"
DEVICE_NAMES = {"ovms-gpu": "the Intel GPU", "ovms-npu": "the NPU"}


def route_footer(name: str, model: str, passed_over: List[str]) -> str:
    """One line saying which model answered where, and which preferred tier wasn't
    available, so AIden's choices are visible in chat."""
    if not SHOW_ROUTE:
        return ""
    device = DEVICE_NAMES.get(name) or ("the NVIDIA GPU" if "nvidia" in os.environ.get("AIDEN_PROFILES", "") else "the CPU")
    line = f"answered by {model} on {device}"
    degraded = [s for s in passed_over if senses.status.get(s, {}).get("generating") is False]
    down = [s for s in passed_over if s not in degraded]
    reasons = []
    if down:
        reasons.append(f"{' and '.join(DEVICE_NAMES.get(s, s) for s in down)} {'was' if len(down) == 1 else 'were'} unavailable")
    for s in degraded:
        reasons.append(f"{DEVICE_NAMES.get(s, s)} is up but couldn't generate at my last check"
                       + ("; a reboot usually clears it" if s == "ovms-gpu" else ""))
    if reasons:
        line += f" ({'; '.join(reasons)})"
    return f"\n\n*{line}*"


def passed_over(answered_by: str, candidates: List[Tuple[str, str, str]], skipped: List[str]) -> List[str]:
    """Preferred tiers above the one that answered which were down or didn't respond,
    limited to tiers this machine is meant to have."""
    expected = {"ovms-gpu": "intel-gpu", "ovms-npu": "npu"}
    profiles = os.environ.get("AIDEN_PROFILES", "").split(",")
    names = [c[0] for c in candidates]
    higher = ANSWER_BACKENDS[:ANSWER_BACKENDS.index(answered_by)]
    stepped_around = lambda b: senses.status.get(b, {}).get("generating") is False
    return [b for b in higher if (b in skipped or b not in names or stepped_around(b))
            and expected.get(b, "") in profiles]


def sse_chunk(content: str, finish: Optional[str] = None) -> str:
    chunk = {"id": "aiden", "object": "chat.completion.chunk", "created": int(time.time()), "model": "aiden",
             "choices": [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish}]}
    return f"data: {json.dumps(chunk)}\n\n"


def stream_answer(response: requests.Response, notes, on_done, route: str = "", offer_mentor: bool = False) -> Iterator[str]:
    """Relay the backend's SSE stream, add the sources and route footers before [DONE].

    The last few characters are held back until the end, so the confidence line can be
    removed before it reaches the user."""
    tokens, start, answer, pending = 0, time.time(), [], ""
    hold = CONFIDENCE_HOLD
    # SSE responses carry no charset, and requests would otherwise decode them as Latin-1
    response.encoding = "utf-8"
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            content = chunk["choices"][0].get("delta", {}).get("content") if chunk["choices"] else None
            if not content:
                continue
            tokens += 1
            answer.append(content)
            pending += content
            # Keep back trailing whitespace plus the last few visible characters, so the
            # marker can't be partly sent even when the model adds newlines after it
            cut = len(pending.rstrip()) - hold
            if cut > 0:
                yield sse_chunk(pending[:cut])
                pending = pending[cut:]
        except (ValueError, KeyError, IndexError):
            continue
    text, confidence = split_confidence("".join(answer))
    unsure = confidence == "low"
    pending, _ = split_confidence(pending)
    footer = (pending if text.endswith(pending) else "") + sources_footer(notes, text)
    if unsure and offer_mentor:
        footer += f"\n\n*{MENTOR_OFFER}*"
    footer += route
    if footer:
        yield sse_chunk(footer)
    yield "data: [DONE]\n\n"
    on_done(tokens, time.time() - start, unsure, text, confidence)

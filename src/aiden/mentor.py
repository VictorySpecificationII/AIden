"""The mentor: Claude, asked through the mentor-bridge service (Claude Code CLI).

Only questions without the user's notes go to the mentor; router.check_outbound()
guards every call."""
import os
import re
from typing import Any, Dict, List, Tuple

import requests

import router

MENTOR_URL = os.environ.get("MENTOR_URL", "http://mentor-bridge:8765")
MENTOR_TOKEN = os.environ.get("MENTOR_TOKEN", "")

MENTOR_TRIGGERS = [
    r"\b(ask|check with|ask your|ask the) (claude|mentor)\b",
    r"\bsecond opinion\b",
    r"\bnot sure either\b",
]
FOOTER_START = re.compile(r"\n\n(Sources:|\*answered by |\*I'm not confident)")


def wants_mentor(prompt: str) -> bool:
    return any(re.search(p, prompt.lower()) for p in MENTOR_TRIGGERS)


def strip_footers(text: str) -> str:
    match = FOOTER_START.search(text or "")
    return (text[:match.start()] if match else text or "").strip()


def mentor_question(messages: List[Dict[str, Any]], prompt: str) -> Tuple[str, str, bool]:
    """(question for the mentor, AIden's previous draft or "", whether this follows AIden's offer).

    A bare "ask Claude" refers to the previous question. AIden's previous answer goes along
    as a draft only when it didn't use the user's notes (it has no Sources footer), because a
    paraphrase of a note could otherwise leave the machine.
    """
    remainder = prompt
    for pattern in MENTOR_TRIGGERS:
        remainder = re.sub(pattern, "", remainder, flags=re.IGNORECASE)
    remainder = remainder.strip(" ,.:;!?-\n")
    users = [m for m in messages if m.get("role") == "user"]
    assistants = [m for m in messages if m.get("role") == "assistant"]
    previous_answer = assistants[-1].get("content", "") if assistants else ""
    if isinstance(previous_answer, list):
        previous_answer = " ".join(p.get("text", "") for p in previous_answer if isinstance(p, dict))
    if len(remainder) >= 15 or len(users) < 2:
        question = remainder or prompt
        draft = ""
    else:
        question = users[-2].get("content", "") if isinstance(users[-2].get("content"), str) else ""
        draft = "" if "\n\nSources:" in previous_answer else strip_footers(previous_answer)
    return question, draft, router.MENTOR_OFFER[:30] in previous_answer


def ask_mentor(question: str, draft: str, notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {"question": question, "draft": draft}
    url = f"{MENTOR_URL}/ask"
    router.check_outbound(url, payload, notes)
    response = requests.post(url, json=payload, headers={"X-Mentor-Token": MENTOR_TOKEN}, timeout=(5, 200))
    body = response.json()
    if response.status_code != 200:
        raise RuntimeError(body.get("error", f"mentor returned {response.status_code}"))
    return body

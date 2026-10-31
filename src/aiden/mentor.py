"""The mentor: Claude, asked through the mentor-bridge service (Claude Code CLI).

Only questions without the user's notes go to the mentor; router.check_outbound()
guards every call."""
import os
import re
from typing import Any, Dict, List, Tuple

import requests

import router
import vault

MENTOR_URL = os.environ.get("MENTOR_URL", "http://mentor-bridge:8765")
MENTOR_TOKEN = os.environ.get("MENTOR_TOKEN", "")
# A draft that resembles the user's notes this closely stays local (measured: answers
# drawn from notes score ~0.77 against the vault, general answers ~0.5-0.63)
DRAFT_MAX_NOTE_SCORE = float(os.environ.get("AIDEN_DRAFT_MAX_NOTE_SCORE", "0.65"))
SHINGLE_WORDS = 8

MENTOR_TRIGGERS = [
    r"\b(ask|check with|ask your|ask the) (claude|mentor)\b",
    r"\bsecond opinion\b",
    r"\bnot sure either\b",
]



def wants_mentor(prompt: str) -> bool:
    return any(re.search(p, prompt.lower()) for p in MENTOR_TRIGGERS)


strip_footers = router.strip_footers  # AIden's footers, defined with the replies that carry them


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


def shingles(text: str, size: int = SHINGLE_WORDS) -> set:
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def draft_privacy(draft: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """(safe to send, why, closest notes). Judges the draft itself, not the question, so an
    answer that drew on the user's notes stays local even if the turn that produced it
    can't be reconstructed. Fails closed: if the vault can't be searched, it isn't safe."""
    try:
        matches = vault.search(draft[:2000], limit=5)
    except (requests.RequestException, KeyError, ValueError) as exc:
        return False, f"vault search failed ({type(exc).__name__})", []
    top = max((m["score"] for m in matches), default=0.0)
    if top >= DRAFT_MAX_NOTE_SCORE:
        return False, f"resembles the user's notes (score {top:.2f} >= {DRAFT_MAX_NOTE_SCORE})", matches
    draft_shingles = shingles(draft)
    for match in matches:
        if draft_shingles & shingles(match["text"]):
            return False, f"shares {SHINGLE_WORDS}-word wording with {match['path']}", matches
    return True, f"no close match in the vault (top score {top:.2f})", matches


def ask_mentor(question: str, draft: str, notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {"question": question, "draft": draft}
    url = f"{MENTOR_URL}/ask"
    router.check_outbound(url, payload, notes)
    response = requests.post(url, json=payload, headers={"X-Mentor-Token": MENTOR_TOKEN}, timeout=(5, 200))
    body = response.json()
    if response.status_code != 200:
        raise RuntimeError(body.get("error", f"mentor returned {response.status_code}"))
    return body

"""Your ratings in OpenWebUI (👍/👎, reason, comment), brought into AIden's experience.

Experience records say what AIden did; ratings say whether it was good. That is the
teacher signal for AIden's own model.

Every POLL_INTERVAL_S AIden reads OpenWebUI's feedback export and writes one kind="feedback" record per new or changed rating. Each
rating carries a snapshot of its chat, so the record holds the prompt and the answer as
shown, and the trace_id of the matching turn when AIden answered it (same prompt, closest
in time). Ratings already recorded are remembered in SEEN_FILE, keyed by their updated_at,
so changing your mind is recorded too.

OpenWebUI here runs without login (WEBUI_AUTH=False), so AIden signs in as its built-in
admin, as anyone on the network can; nothing to set up. With login on, put an admin API
key in OPENWEBUI_API_KEY instead. With experience recording off, nothing runs.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from opentelemetry import metrics

import experience

OPENWEBUI_URL = os.environ.get("OPENWEBUI_URL", "http://ollama-webui:8080")
OPENWEBUI_API_KEY = os.environ.get("OPENWEBUI_API_KEY", "")
POLL_INTERVAL_S = int(os.environ.get("AIDEN_FEEDBACK_INTERVAL", "300"))
SEEN_FILE = "feedback-seen.json"
# A turn is recorded when the answer finishes; the chat stamps the message when it starts
MATCH_WINDOW_S = 900

logger = logging.getLogger("aiden.feedback")
rating_counter = metrics.get_meter("aiden").create_counter(
    name="aiden_feedback_ratings",
    description="Ratings given in OpenWebUI, by rating and the model rated",
    unit="1"
)
status: Dict[str, Any] = {"state": "starting", "last_poll": None, "last_error": None, "recorded": 0}


def credential() -> str:
    if OPENWEBUI_API_KEY:
        return OPENWEBUI_API_KEY
    # Without login OpenWebUI accepts its built-in admin (fixed credentials, see auths.py)
    response = requests.post(f"{OPENWEBUI_URL}/api/v1/auths/signin",
                             json={"email": "admin@localhost", "password": "admin"}, timeout=30)
    response.raise_for_status()
    return response.json()["token"]


def fetch() -> List[Dict[str, Any]]:
    response = requests.get(f"{OPENWEBUI_URL}/api/v1/evaluations/feedbacks/all/export",
                            headers={"Authorization": f"Bearer {credential()}"}, timeout=30)
    response.raise_for_status()
    return response.json()


def rating_label(data: Dict[str, Any]) -> Optional[str]:
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        return None
    return "up" if rating > 0 else "down" if rating < 0 else None


def rated_exchange(item: Dict[str, Any]) -> Dict[str, Any]:
    """The rated answer and the prompt before it, from the chat snapshot."""
    chat = (item.get("snapshot") or {}).get("chat") or {}
    chat = chat.get("chat", chat)  # the snapshot is the chat record, its content under "chat"
    messages = (chat.get("history") or {}).get("messages") or {}
    answer = messages.get((item.get("meta") or {}).get("message_id")) or {}
    question = messages.get(answer.get("parentId")) or {}
    return {"prompt": question.get("content"), "answer": answer.get("content"), "timestamp": answer.get("timestamp")}


def find_turn(prompt: Optional[str], timestamp: Optional[float]) -> Optional[Dict[str, Any]]:
    """AIden's own record of the rated answer: same prompt, closest in time."""
    if not prompt or not timestamp:
        return None
    when = datetime.fromtimestamp(timestamp, timezone.utc)
    best, best_gap = None, MATCH_WINDOW_S
    for day in {when.date(), (when + timedelta(seconds=MATCH_WINDOW_S)).date()}:
        path = os.path.join(experience.EXPERIENCE_DIR, f"{day:%Y-%m-%d}.jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("kind") not in ("turn", "mentor") or entry.get("prompt") != prompt:
                    continue
                gap = abs((datetime.fromisoformat(entry["at"]) - when).total_seconds())
                if gap <= best_gap:
                    best, best_gap = entry, gap
    return best


def load_seen() -> Dict[str, Any]:
    try:
        with open(os.path.join(experience.EXPERIENCE_DIR, SEEN_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_seen(seen: Dict[str, Any]):
    path = os.path.join(experience.EXPERIENCE_DIR, SEEN_FILE)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(seen, f)
    os.replace(path + ".tmp", path)


def poll() -> int:
    """Record new or changed ratings; returns how many were recorded."""
    seen = load_seen()
    recorded = 0
    for item in fetch():
        if item.get("type") != "rating" or seen.get(item.get("id")) == item.get("updated_at"):
            continue
        data = item.get("data") or {}
        meta = item.get("meta") or {}
        rating = rating_label(data)
        exchange = rated_exchange(item)
        turn = find_turn(exchange["prompt"], exchange["timestamp"])
        if experience.record("feedback", {
            "feedback_id": item.get("id"), "rating": rating, "reason": data.get("reason"),
            "comment": data.get("comment"), "model": data.get("model_id"),
            "chat_id": meta.get("chat_id"), "message_id": meta.get("message_id"),
            "rated_at": item.get("updated_at"), "prompt": exchange["prompt"], "answer_shown": exchange["answer"],
            # The turn rated, so training can join decision, answer and rating
            "trace_id": turn.get("trace_id") if turn else None,
            "used_notes": ((turn or {}).get("answer") or {}).get("used_notes"),
        }):
            seen[item["id"]] = item.get("updated_at")
            recorded += 1
            rating_counter.add(1, {"rating": rating or "none", "model": data.get("model_id") or "unknown"})
    if recorded:
        save_seen(seen)
    return recorded


def run_forever():
    while True:
        try:
            count = poll()
            status.update(state="ok", last_poll=datetime.now(timezone.utc).isoformat(), last_error=None)
            status["recorded"] += count
            if count:
                logger.info("Recorded %d new rating(s) from OpenWebUI", count)
        except Exception as exc:  # keep polling; OpenWebUI may simply be down
            status.update(state="error", last_error=type(exc).__name__)
            logger.warning("Could not read ratings from OpenWebUI: %s", exc)
        time.sleep(POLL_INTERVAL_S)


def start():
    if not experience.ENABLED:
        status.update(state="disabled", last_error="recording off")
        return
    threading.Thread(target=run_forever, daemon=True, name="feedback-poller").start()

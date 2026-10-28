"""Feedback: your OpenWebUI ratings, matched to AIden's turns and recorded as experience."""
import json
from datetime import datetime, timezone

import pytest

import experience
import feedback

ASKED_AT = datetime(2026, 10, 28, 9, 0, 0, tzinfo=timezone.utc).timestamp()


def rating(id="fb1", rating=1, updated_at=100, prompt="What is the capital of France?",
           answer="Paris.\n\n*answered by qwen3-8b-gpu on the Intel GPU*", wrapped=True):
    chat = {"history": {"messages": {
        "u1": {"id": "u1", "parentId": None, "role": "user", "content": prompt},
        "a1": {"id": "a1", "parentId": "u1", "role": "assistant", "content": answer, "timestamp": ASKED_AT},
    }}}
    return {"id": id, "type": "rating", "updated_at": updated_at,
            "data": {"rating": rating, "model_id": "aiden", "reason": "Accurate information", "comment": "spot on"},
            "meta": {"chat_id": "c1", "message_id": "a1"},
            "snapshot": {"chat": {"id": "c1", "chat": chat} if wrapped else chat}}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", True)
    return tmp_path


def records(store, kind="feedback"):
    lines = [json.loads(l) for f in sorted(store.glob("*.jsonl")) for l in f.read_text(encoding="utf-8").splitlines()]
    return [r for r in lines if r["kind"] == kind]


def write_turn(store, prompt, seconds_after, trace_id):
    at = datetime.fromtimestamp(ASKED_AT + seconds_after, timezone.utc)
    with open(store / f"{at:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "turn", "at": at.isoformat(), "trace_id": trace_id, "prompt": prompt,
                            "answer": {"used_notes": False, "text": "Paris."}}) + "\n")


@pytest.mark.parametrize("value, expected", [(1, "up"), (-1, "down"), ("1", "up"), (0, None), (None, None)])
def test_ratings_become_up_or_down(value, expected):
    assert feedback.rating_label({"rating": value}) == expected


@pytest.mark.parametrize("wrapped", [True, False])
def test_rated_answer_and_its_prompt_come_from_the_snapshot(wrapped):
    exchange = feedback.rated_exchange(rating(wrapped=wrapped))
    assert exchange["prompt"] == "What is the capital of France?"
    assert exchange["answer"].startswith("Paris.") and exchange["timestamp"] == ASKED_AT


def test_a_rating_is_joined_to_the_turn_it_rates(store, monkeypatch):
    write_turn(store, "What is the capital of France?", 600, "far")
    write_turn(store, "What is the capital of France?", 4, "rated")   # closest in time
    write_turn(store, "Something else", 2, "other")
    monkeypatch.setattr(feedback, "fetch", lambda: [rating()])
    assert feedback.poll() == 1
    [entry] = records(store)
    assert entry["trace_id"] == "rated" and entry["rating"] == "up" and entry["used_notes"] is False
    assert entry["comment"] == "spot on" and entry["model"] == "aiden" and entry["message_id"] == "a1"


def test_a_rating_without_a_matching_turn_is_still_kept(store, monkeypatch):
    write_turn(store, "What is the capital of France?", 3600, "too late")
    monkeypatch.setattr(feedback, "fetch", lambda: [rating()])
    feedback.poll()
    assert records(store)[0]["trace_id"] is None


def test_each_rating_is_recorded_once_until_it_changes(store, monkeypatch):
    monkeypatch.setattr(feedback, "fetch", lambda: [rating()])
    assert feedback.poll() == 1
    assert feedback.poll() == 0
    # You changed your mind: thumbs down now
    monkeypatch.setattr(feedback, "fetch", lambda: [rating(rating=-1, updated_at=200)])
    assert feedback.poll() == 1
    assert [r["rating"] for r in records(store)] == ["up", "down"]


def test_only_ratings_are_recorded(store, monkeypatch):
    monkeypatch.setattr(feedback, "fetch", lambda: [{**rating(), "type": "arena"}])
    assert feedback.poll() == 0 and records(store) == []


def test_nothing_runs_with_recording_off(monkeypatch):
    monkeypatch.setattr(experience, "ENABLED", False)
    started = []
    monkeypatch.setattr(feedback.threading, "Thread", lambda **kw: started.append(kw))
    feedback.start()
    assert started == [] and feedback.status["state"] == "disabled"


def test_an_api_key_is_used_when_given_else_the_builtin_admin(monkeypatch):
    monkeypatch.setattr(feedback, "OPENWEBUI_API_KEY", "key")
    assert feedback.credential() == "key"
    monkeypatch.setattr(feedback, "OPENWEBUI_API_KEY", "")
    sent = {}

    class Signin:
        def raise_for_status(self): pass
        def json(self): return {"token": "jwt"}

    monkeypatch.setattr(feedback.requests, "post", lambda url, json, timeout: sent.update(url=url, **json) or Signin())
    assert feedback.credential() == "jwt"
    assert sent["url"].endswith("/api/v1/auths/signin") and sent["email"] == "admin@localhost"

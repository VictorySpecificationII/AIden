"""AIden reflecting on their values: reasons from their own experience, grounded in evidence."""
import json

import pytest

import experience
import reflection


HISTORY = [
    {"kind": "model", "action": "switched", "at": "2026-10-30T15:45:37+00:00", "device": "npu",
     "name": "qwen3-8b-int4-cw-ov", "reason": "can use tools"},
    {"kind": "label_correction", "at": "2026-10-31T20:00:00+00:00", "trace_id": "t1",
     "reason": "narrated creating a directory and file that were never created", "user_rating": "up"},
    {"kind": "model", "action": "judged", "at": "2026-10-30T17:10:15+00:00", "device": "gpu", "name": "x",
     "replays": {"replayed": 10, "shared_with_claude": 8}},
    {"kind": "turn", "at": "2026-10-31T13:30:00+00:00", "prompt": "a private question about my plans",
     "decision": {"decided_by": "fallback"}, "answer": {"confidence": None, "skipped": ["ovms-gpu"], "unbacked_claims": True}},
    {"kind": "feedback", "at": "2026-10-31T13:39:00+00:00", "rating": "up", "prompt": "another private question"},
]


def test_evidence_is_built_from_what_happened_without_the_users_words():
    facts = reflection.evidence(HISTORY)
    text = " ".join(f["fact"] for f in facts)
    assert [f["id"] for f in facts][:2] == ["E1", "E2"]
    assert "switched my NPU model to qwen3-8b-int4-cw-ov" in text
    assert "never created" in text and "found a problem" in text and "rated that answer thumbs-up" in text
    assert "kept 2 of 10 replays" in text
    assert "Since 2026-10-31, when answers started being checked" in text and "1 of 1 answers were flagged" in text
    assert "private question" not in text and "my plans" not in text  # prompts never become evidence


def test_reasons_must_cite_real_evidence():
    facts = [{"id": "E1", "fact": "a"}, {"id": "E2", "fact": "b"}]
    raw = {"values": [{"value": "Honesty", "reason": "I was wrong once", "evidence": ["E2"]},
                      {"value": "Privacy", "reason": "I deeply cherish privacy", "evidence": ["E9"]},
                      {"value": "Helpful", "reason": "Nothing in my experience yet", "evidence": [], "none_found": True}],
           "proposals": [{"change": "add curiosity", "evidence": []}]}
    grounded = reflection.ground(raw, facts)
    honesty, privacy, helpful = grounded["values"]
    assert honesty["grounded"] and honesty["evidence"] == ["E2"]
    assert not privacy["grounded"] and privacy["invented_evidence"] == ["E9"]  # cited evidence that doesn't exist
    mixed = reflection.ground({"values": [{"value": "x", "reason": "r", "evidence": ["E1", "E1美"]}]}, facts)["values"][0]
    assert not mixed["grounded"]  # one real citation doesn't excuse an invented one (seen live)
    assert not helpful["grounded"] and helpful["none_found"]                   # honest "none found" is kept as such
    assert not grounded["proposals"][0]["grounded"]


def test_a_reflection_parses_even_with_text_around_the_json():
    reply = 'Here is my reflection:\n```json\n{"values": [{"value": "Honesty", "reason": "r", "evidence": ["E1"]}]}\n```'
    result = reflection.reflect_with(lambda prompt: reply, ["Honesty"], [{"id": "E1", "fact": "x"}])
    assert result["values"][0]["grounded"] and result["proposals"] == []


def test_the_model_is_told_to_say_when_it_has_no_reason():
    seen = {}
    reflection.reflect_with(lambda prompt: seen.update(prompt=prompt) or "{}", ["Honesty"], [{"id": "E1", "fact": "x"}])
    assert "say so honestly" in seen["prompt"] and "E1: x" in seen["prompt"] and "1. Honesty" in seen["prompt"]


def test_markdown_for_the_note(tmp_path, monkeypatch):
    result = {"model": "qwen", "at": "2026-10-31T21:00:00", "evidence": [{"id": "E1", "fact": "x"}],
              "reflection": {"values": [{"value": "Honesty", "reason": "I was wrong.", "evidence": ["E1"], "grounded": True}],
                             "proposals": [{"change": "add curiosity", "evidence": ["E1"], "grounded": True}]},
              "mentor": {"values": [{"value": "Honesty", "supported": True, "comment": "fair"}], "overall": "honest"}}
    md = reflection.markdown(result)
    assert "**Honesty**: I was wrong. *(grounded; evidence: E1)*" in md and "Mentor: supported: fair" in md
    assert "add curiosity" in md and "E1: x" in md


def test_privacy_guard_stands_between_the_reflection_and_claude(monkeypatch):
    import mentor
    monkeypatch.setattr(mentor, "MENTOR_TOKEN", "t")
    monkeypatch.setattr(mentor, "draft_privacy", lambda text: (False, "resembles the user's notes", []))
    monkeypatch.setattr(mentor, "ask_mentor", lambda *a: pytest.fail("must not ask Claude"))
    review = reflection.mentor_review(["Honesty"], [], {"values": [], "proposals": []})
    assert "not sent to Claude" in review["skipped"]


def test_a_revision_sees_the_review_and_may_push_back():
    previous = {"at": "2026-10-31T21:00:00", "reflection": {"values": [
        {"value": "Being genuinely helpful", "reason": "users rate me well", "evidence": ["E15"], "invented_evidence": [], "grounded": True}],
        "proposals": []},
        "mentor": {"values": [{"value": "Being genuinely helpful", "supported": False, "comment": "3 ratings is thin"}],
                   "overall": "somewhat flattering"}}
    seen = {}
    reflection.reflect_with(lambda prompt: seen.update(prompt=prompt) or "{}", ["Being genuinely helpful"],
                            [{"id": "E15", "fact": "3 ratings"}], previous)
    assert "This is a revision" in seen["prompt"] and "3 ratings is thin" in seen["prompt"]
    assert "Don't simply agree with the mentor" in seen["prompt"] and "somewhat flattering" in seen["prompt"]

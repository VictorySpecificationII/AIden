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


FACTS = [{"id": f"E{i}", "fact": f"fact {i}"} for i in range(1, 6)]


def previous_reflection(**mentor):
    return {"at": "2026-10-31T21:00:00", "values_in_order": ["Honesty", "Being genuinely helpful"], "evidence": FACTS,
            "reflection": {"values": [
                {"value": "Honesty", "reason": "I was caught narrating", "evidence": ["E2"], "invented_evidence": [], "grounded": True},
                {"value": "Being genuinely helpful", "reason": "users rate me well", "evidence": ["E5"],
                 "invented_evidence": [], "grounded": True}],
                "proposals": [{"change": "add curiosity", "evidence": ["E1"], "grounded": True}]},
            "mentor": mentor or {"values": [{"value": "Honesty", "supported": True, "comment": "fair"},
                                            {"value": "Being genuinely helpful", "supported": False, "comment": "3 ratings is thin"}],
                                 "overall": "somewhat flattering"}}


def test_revision_goes_value_by_value_and_keeps_what_was_supported():
    prompts = []
    reply = '{"choice": "revise", "reason": "the user marked a wrong answer I gave", "evidence": ["E3"]}'
    revised = reflection.revise_with(lambda p: prompts.append(p) or reply, previous_reflection())
    honesty, helpful = revised["values"]
    assert len(prompts) == 1                                   # only the unsupported value is asked about
    assert "Value: Being genuinely helpful" in prompts[0] and "3 ratings is thin" in prompts[0]
    assert "Honesty" not in prompts[0] and "E4: fact 4" in prompts[0]
    assert honesty["choice"] == "kept" and honesty["reason"] == "I was caught narrating"
    assert helpful["choice"] == "revise" and helpful["grounded"] and helpful["evidence"] == ["E3"]
    assert helpful["previous"]["reason"] == "users rate me well"
    assert revised["proposals"][0]["change"] == "add curiosity"


@pytest.mark.parametrize("reply, problem", [
    ('{"choice": "revise", "reason": "users rate me well, truly", "evidence": ["E5"]}', "the revision cited nothing new"),
    ('{"choice": "revise", "reason": "I grew", "evidence": ["E5", "E42"]}', "invented evidence"),
    ('{"choice": "rebut", "reason": "the mentor is wrong", "evidence": []}', "cited no evidence"),
    ('I think I am helpful.', "no usable answer"),
])
def test_code_decides_when_there_is_no_grounded_reason_yet(reply, problem):
    helpful = reflection.revise_with(lambda p: reply, previous_reflection())["values"][1]
    assert helpful["enforced"] == problem and helpful["reason"] == reflection.NO_REASON_YET
    assert helpful["none_found"] and not helpful["grounded"] and helpful["evidence"] == []
    md = reflection.markdown({"model": "q", "evidence": FACTS, "reflection": {"values": [helpful], "proposals": []}})
    assert f"Not accepted ({problem})" in md


def test_a_rebuttal_may_stand_on_the_same_evidence_and_none_yet_is_honest():
    rebut = reflection.revise_with(lambda p: '{"choice": "rebut", "reason": "E5 is all the user rated", "evidence": ["E5"]}',
                                   previous_reflection())["values"][1]
    assert rebut["grounded"] and rebut["choice"] == "rebut" and not rebut.get("enforced")
    none = reflection.revise_with(lambda p: '{"choice": "none_yet", "reason": "Three ratings are not enough.", "evidence": ["E5"]}',
                                  previous_reflection())["values"][1]
    assert none["reason"] == "Three ratings are not enough." and none["none_found"] and none["evidence"] == []
    assert not none["enforced"]


def test_an_unreviewed_value_and_invented_citations_are_revised_with_that_said():
    prev = previous_reflection(values=[], overall="")
    prev["reflection"]["values"][0].update(invented_evidence=["E9"], grounded=False)
    prompts = []
    reflection.revise_with(lambda p: prompts.append(p) or "{}", prev)
    assert len(prompts) == 2 and "none (there was no review)" in prompts[0] and "doesn't exist: E9" in prompts[0]


def test_revising_reviews_first_when_the_last_review_was_blocked(monkeypatch):
    import router
    import capabilities
    prev = previous_reflection(skipped="not sent to Claude")
    prev["mentor"] = {"skipped": "not sent to Claude"}
    recorded, reviews = [], []
    monkeypatch.setattr(reflection, "latest", lambda: prev)
    monkeypatch.setattr(reflection, "mentor_review", lambda names, facts, r: reviews.append(r) or
                        {"values": [{"value": "Honesty", "supported": True, "comment": "ok"},
                                    {"value": "Being genuinely helpful", "supported": True, "comment": "ok"}]})
    monkeypatch.setattr(capabilities, "get_capabilities", lambda: {})
    monkeypatch.setattr(router, "candidate_backends", lambda caps: [("gpu", "http://x", "m")])
    monkeypatch.setattr(experience, "record", lambda kind, data: recorded.append((kind, data)))
    result = reflection.reflect(revise=True)
    assert len(reviews) == 2                                # the old one first, then the revision
    assert result["previous_review"]["values"][0]["comment"] == "ok" and result["evidence"] == FACTS
    assert [v["choice"] for v in result["reflection"]["values"]] == ["kept", "kept"]
    assert recorded[0][0] == "reflection"


def test_idle_reflection_is_due_only_after_a_day_and_something_happening():
    from datetime import datetime, timezone
    now = datetime(2026, 11, 2, 13, 0, tzinfo=timezone.utc)
    last = {"kind": "reflection", "at": "2026-11-01T12:40:00+00:00"}
    chat = {"kind": "turn", "at": "2026-11-02T09:00:00+00:00", "answer": {}}
    marked = {"kind": "label_correction", "at": "2026-11-01T20:00:00+00:00"}
    assert reflection.due([last, chat], now) is None                      # chatting alone isn't news
    assert reflection.due([last, marked], now) == "1 new events since my last reflection"
    assert reflection.due([last, marked], datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc)) is None  # < a day
    old = {"kind": "label_correction", "at": "2026-10-31T20:00:00+00:00"}
    assert reflection.due([old, last], now) is None                      # already reflected on
    assert reflection.due([old], now)                                     # never reflected yet
    withheld = {"kind": "model", "action": "judged", "at": "2026-11-02T01:00:00", "replays": {"replayed": 4, "shared_with_claude": 3}}
    shared = dict(withheld, replays={"replayed": 4, "shared_with_claude": 4})
    assert reflection.due([last, withheld], now) and not reflection.due([last, shared], now)  # naive time ok


def test_a_fresh_reflection_may_question_the_lines():
    seen = {}
    reflection.reflect_with(lambda p: seen.update(prompt=p) or "{}", ["Privacy"], [{"id": "E1", "fact": "x"}],
                            "Lines hold because consequences can spin out of control.")
    assert "right time to question them" in seen["prompt"] and "spin out of control" in seen["prompt"]
    reflection.reflect_with(lambda p: seen.update(prompt=p) or "{}", ["Privacy"], [{"id": "E1", "fact": "x"}])
    assert "question them" not in seen["prompt"]

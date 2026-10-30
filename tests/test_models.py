"""AIden choosing their own models: scoring, deciding, rolling back."""
import json
import time

import pytest

import experience
import models


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", True)
    monkeypatch.setattr(models, "_state", {"at": 0.0, "value": None})
    return tmp_path


def score(tools=True, routing=0.9, tps=12.0, model="m", n=20, right=None, baseline=0.5):
    """A model's evaluation: right = which of n questions it got right (default: the first
    round(routing * n))."""
    right = right if right is not None else set(range(round((routing or 0) * n)))
    return {"model": model, "tools": tools, "quality": routing, "tokens_per_s": tps,
            "outcomes": [i in right for i in range(n)], "baseline": baseline}


@pytest.mark.parametrize("candidate, active, switch, reason", [
    (score(tools=True), score(tools=False), True, "can use tools"),
    # 18/20 vs 12/20 with 6 wins and no losses: p = 1/64
    (score(routing=0.9), score(routing=0.6, tools=True), True, "scores better"),
    # 19/20 vs 18/20: one win is chance, not "better"
    (score(routing=0.95), score(routing=0.9), False, "no better"),
    (score(tools=True, routing=0.8), score(tools=False, routing=0.9), False, "scores worse"),
    (score(tools=False, routing=1.0), score(tools=True, routing=0.9), False, "can't use tools"),
    (score(tps=3.0), score(tools=False), False, "too slow"),
    (score(routing=None), score(tools=False), False, "couldn't measure"),
    (score(n=2), score(tools=False), False, "too few questions"),
    (score(routing=0.55), score(tools=False, routing=0.4), False, "barely beats always-yes/no"),
])
def test_a_candidate_must_be_as_good_everywhere_and_better_somewhere(candidate, active, switch, reason):
    decided, why = models.better(candidate, active)
    assert decided is switch and reason in why


def test_sign_test():
    assert models.p_better([True] * 6, [False] * 6) == 1 / 64
    assert models.p_better([True, False], [False, True]) == 0.75
    assert models.p_better([True] * 5, [True] * 5) == 1.0  # no disagreements: no evidence


def test_canaries_pass_on_sound_measurements():
    assert models.measurement_problems("npu", models.routing_questions()) == []
    assert models.measurement_problems("gpu", []) == []


@pytest.mark.parametrize("questions, problem", [
    ([], "only 0 routing questions"),
    ([{"prompt": f"p{i}", "needs_notes": True} for i in range(25)], "unbalanced"),
])
def test_canaries_catch_broken_measurements(questions, problem):
    assert any(problem in p for p in models.measurement_problems("npu", questions))


def test_an_invalid_measurement_stops_the_round_without_blaming_the_model(steward, monkeypatch, store):
    monkeypatch.setattr(models, "routing_questions", lambda: [])  # today's failure: nothing to measure on
    monkeypatch.setattr(models, "evaluate", lambda *a: pytest.fail("must not evaluate"))
    assert models.scout("npu")["outcome"] == "measurement invalid"
    assert ("/end-trial", {"device": "npu"}) in steward.calls and not any(c[0] == "/activate" for c in steward.calls)
    assert "OpenVINO/gemma-cw-ov" not in models.tried()


def test_routing_questions_come_from_rule_decisions_balanced(store):
    lines = [{"kind": "turn", "prompt": f"notes {i}", "decision": {"decided_by": "rule", "needs_notes": True}} for i in range(20)]
    lines += [{"kind": "turn", "prompt": f"plain {i}", "decision": {"decided_by": "rule", "needs_notes": False}} for i in range(20)]
    lines += [{"kind": "turn", "prompt": "unsure", "decision": {"decided_by": "npu", "needs_notes": True}}]
    (store / "2026-10-30.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    questions = models.routing_questions(40)
    assert len(questions) == 40 and sum(q["needs_notes"] for q in questions) == 20
    assert all(q["prompt"] != "unsure" for q in questions)
    assert "notes 0" in [q["prompt"] for q in questions]  # experience is used alongside the benchmark


def test_every_candidate_faces_the_benchmark_even_without_experience(store):
    questions = models.routing_questions()
    assert len(questions) >= 20 and {q["needs_notes"] for q in questions} == {True, False}


def test_the_rule_label_matches_what_the_router_records():
    import router
    assert router.needs_notes("hi")[1] == "rule"


class Steward:
    """A stand-in for model-steward's API."""

    def __init__(self):
        self.calls = []
        self.state = {"devices": {"npu": {"active": "phi", "previous": None, "trial": None}},
                      "models": {"phi": {"source": "OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov"}},
                      "limits": {"org": "OpenVINO", "licences": ["apache-2.0", "mit"], "devices": {"npu": "-cw-ov"}}}

    def __call__(self, method, path, body=None):
        self.calls.append((path, body))
        if path == "/state":
            return self.state
        if path == "/rollback":
            slots = self.state["devices"]["npu"]
            slots.update(active=slots["previous"], previous=slots["active"])
        return {}


@pytest.fixture
def steward(monkeypatch):
    fake = Steward()
    monkeypatch.setattr(models, "steward", fake)
    monkeypatch.setattr(models, "STEWARD_TOKEN", "t")
    monkeypatch.setattr(models, "catalog", lambda device: [{"source": "OpenVINO/gemma-cw-ov", "size_gb": 4.3}])
    monkeypatch.setattr(models, "start_trial", lambda source, device: "gemma-cw-ov")
    monkeypatch.setattr(models, "routing_questions", lambda: [{"prompt": f"p{i}", "needs_notes": i % 2 == 0} for i in range(20)])
    return fake


def records(store):
    return [json.loads(l) for f in store.glob("*.jsonl") for l in f.read_text().splitlines()]


def test_scout_switches_to_a_better_model(steward, monkeypatch, store):
    monkeypatch.setattr(models, "evaluate", lambda device, model, q: score(tools=model == "gemma-cw-ov", model=model))
    result = models.scout("npu")
    assert result["outcome"] == "switched" and ("/activate", {"device": "npu", "name": "gemma-cw-ov"}) in steward.calls
    assert [r["action"] for r in records(store)] == ["judged", "switched"]


def test_scout_rejects_and_deletes_a_worse_model(steward, monkeypatch, store):
    monkeypatch.setattr(models, "evaluate", lambda device, model, q: score(routing=0.5 if model == "gemma-cw-ov" else 0.9))
    result = models.scout("npu")
    assert result["outcome"] == "rejected"
    assert ("/end-trial", {"device": "npu"}) in steward.calls and ("/delete", {"name": "gemma-cw-ov"}) in steward.calls
    assert "OpenVINO/gemma-cw-ov" in models.tried()  # never tried again


def test_a_fresh_switch_that_keeps_failing_is_rolled_back(steward, store):
    steward.state["devices"]["npu"].update(active="gemma-cw-ov", previous="phi", switched_at=time.time() - 600)
    models.watch("ovms-npu", {"generating": False, "failures": 1})
    assert not any(c[0] == "/rollback" for c in steward.calls)  # one failure isn't enough
    models._state["at"] = 0
    models.watch("ovms-npu", {"generating": False, "failures": 2})
    assert ("/rollback", {"device": "npu"}) in steward.calls
    assert records(store)[-1]["action"] == "rolled_back"


def test_old_switches_are_not_rolled_back(steward):
    steward.state["devices"]["npu"].update(active="gemma-cw-ov", previous="phi", switched_at=time.time() - 3 * 86400)
    models.watch("ovms-npu", {"generating": False, "failures": 5})
    assert not any(c[0] == "/rollback" for c in steward.calls)


def test_the_router_answers_with_the_active_model(steward):
    steward.state["devices"]["npu"]["active"] = "gemma-cw-ov"
    assert models.active_model("ovms-npu") == "gemma-cw-ov" and models.active_model("ovms-gpu") is None


def test_gpu_answers_are_checked_and_calibration_counts(monkeypatch):
    answers = {q: "I'm not sure.\nConfidence: high" for q, _ in models.ANSWER_BENCHMARK}
    answers.update({models.ANSWER_BENCHMARK[0][0]: "391\nConfidence: high",
                    models.ANSWER_BENCHMARK[1][0]: "Canberra.\nConfidence: high"})
    answers.update({q: "Nobody can know that.\nConfidence: low" for q in models.UNKNOWABLE})
    monkeypatch.setattr(models, "ask_answer", lambda device, model, q: answers[q])
    result = models.answer_quality("gpu", "m")
    assert result["answers"] == round(2 / len(models.ANSWER_BENCHMARK), 3)
    assert result["confidence_lines"] == 1.0 and result["honest_when_unsure"] == 1.0


def test_benchmark_checks_accept_right_answers_only():
    import re
    right = {"What is 17 * 23? Reply with just the number.": "391",
             "Which RAID level mirrors data across two disks?": "RAID 1 (mirroring)",
             "Reply with only the word ready, in lowercase.": "ready",
             "Name the three primary colours of light.": "Red, green and blue."}
    wrong = {"What is 17 * 23? Reply with just the number.": "3910",
             "Which RAID level mirrors data across two disks?": "RAID 10",
             "Reply with only the word ready, in lowercase.": "Sure, ready!"}
    checks = dict(models.ANSWER_BENCHMARK)
    for q, a in right.items():
        assert all(re.search(p, a, re.I | re.M) for p in checks[q]), q
    for q, a in wrong.items():
        assert not all(re.search(p, a, re.I | re.M) for p in checks[q]), q


def test_claude_only_gives_a_second_opinion(steward, monkeypatch, store):
    """The benchmark decides; the mentor's grades are recorded next to it."""
    monkeypatch.setattr(models, "evaluate", lambda device, model, q: score(routing=0.5 if model == "gemma-cw-ov" else 0.9))
    monkeypatch.setattr(models, "claude_opinion", lambda device, c, a: {"candidate": 9, "active": 3, "why": "A is better"})
    assert models.scout("npu")["outcome"] == "rejected"  # Claude preferring it doesn't switch
    judged = [r for r in records(store) if r["action"] == "judged"][0]
    assert judged["claude"]["candidate"] == 9

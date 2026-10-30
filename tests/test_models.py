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


def score(tools=True, routing=0.9, tps=12.0, model="m"):
    return {"model": model, "tools": tools, "routing": routing, "tokens_per_s": tps}


@pytest.mark.parametrize("candidate, active, switch, reason", [
    (score(tools=True, routing=0.9), score(tools=False, routing=0.9), True, "can use tools"),
    (score(tools=True, routing=0.95), score(tools=True, routing=0.9), True, "routes better"),
    (score(tools=True, routing=0.9), score(tools=True, routing=0.9), False, "no better"),
    (score(tools=True, routing=0.8), score(tools=False, routing=0.9), False, "routes worse"),
    (score(tools=False, routing=1.0), score(tools=True, routing=0.9), False, "can't use tools"),
    (score(tps=3.0), score(tools=False), False, "too slow"),
    (score(routing=None), score(tools=False), False, "couldn't measure"),
])
def test_a_candidate_must_be_as_good_everywhere_and_better_somewhere(candidate, active, switch, reason):
    decided, why = models.better(candidate, active)
    assert decided is switch and reason in why


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
    monkeypatch.setattr(models, "routing_questions", lambda: [])
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

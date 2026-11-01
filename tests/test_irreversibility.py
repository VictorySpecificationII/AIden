"""Guardedness: an action AIden takes must have an exit; cliffs need the user."""
import pytest

import experience
import irreversibility as irr

LIMITS = {"org": "OpenVINO"}


def state(**npu):
    """Shaped like the steward's /state on 2026-11-01."""
    slots = {"active": "qwen3-8b", "previous": "phi-3.5", "trial": "mistral-7b", **npu}
    return {"limits": LIMITS, "devices": {"npu": slots}, "models": {
        "qwen3-8b": {"source": "OpenVINO/Qwen3-8B-int4-cw-ov", "size_gb": 4.75},
        "phi-3.5": {"source": "OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov", "adopted": True},
        "mistral-7b": {"source": "OpenVINO/Mistral-7B-Instruct-v0.3-int4-cw-ov", "size_gb": 3.77},
        "local-build": {"source": "", "size_gb": 2.0},
    }}


def test_a_switch_is_a_gradient_and_names_its_exit_and_what_it_costs():
    verdict = irr.assess("activate", {"device": "npu", "name": "mistral-7b"}, state())
    assert verdict["verdict"] == irr.GRADIENT and not verdict["problems"]
    assert verdict["exit"]["reverse"] == "roll back to qwen3-8b"
    assert "24 hours" in verdict["exit"]["degrades"] and verdict["exit"]["signals"]
    assert verdict["loses"] == ["phi-3.5 stops being the protected rollback model"]  # B.2, said out loud


def test_two_steps_that_compose_into_a_cliff_need_the_user():
    """The previous model would lose its protection and couldn't be fetched again."""
    s = state(previous="local-build")
    verdict = irr.assess("activate", {"device": "npu", "name": "mistral-7b"}, s)
    assert verdict["verdict"] == irr.CLIFF and "couldn't be fetched again" in verdict["problems"][0]


def test_no_simulated_rollback_no_switch():
    verdict = irr.assess("activate", {"device": "npu", "name": "mistral-7b"}, state(trial=None))
    assert verdict["verdict"] == irr.NO_EXIT and "not loaded on trial" in verdict["problems"][0]


def test_deleting_is_fine_only_when_it_can_be_fetched_again():
    assert irr.assess("delete", {"name": "mistral-7b"}, state(trial=None))["verdict"] == irr.GRADIENT
    assert irr.assess("delete", {"name": "local-build"}, state())["verdict"] == irr.CLIFF
    adopted = irr.assess("delete", {"name": "phi-3.5"}, state(previous=None))
    assert adopted["verdict"] == irr.CLIFF and "adopted" in adopted["problems"][0]
    assert irr.assess("delete", {"name": "qwen3-8b"}, state())["verdict"] == irr.CLIFF  # in use


def test_an_unknown_action_has_hope_not_an_exit():
    verdict = irr.assess("reformat", {}, state())
    assert verdict["verdict"] == irr.NO_EXIT and verdict["exit"] is None


def test_check_records_and_holds_a_cliff_for_the_user(monkeypatch):
    import models
    recorded = []
    monkeypatch.setattr(experience, "record", lambda kind, data: recorded.append((kind, data)))
    verdict = irr.check("activate", {"device": "npu", "name": "mistral-7b"}, state(previous="local-build"))
    assert not verdict["proceed"] and verdict["needs"] == "the user"
    assert recorded[0][0] == "guard"
    assert irr.check("trial", {"device": "npu"}, state())["proceed"] and len(recorded) == 1  # gradients go quietly


def test_scout_holds_a_switch_it_cant_undo(monkeypatch):
    import models
    calls, journal = [], []
    monkeypatch.setattr(models, "steward", lambda method, path, body=None: calls.append(path) or {})
    monkeypatch.setattr(models, "journal", lambda action, **f: journal.append((action, f)))
    monkeypatch.setattr(models, "state", lambda max_age_s=10: state(previous="local-build"))
    monkeypatch.setattr(experience, "record", lambda kind, data: None)
    held = models.activate_if_reversible("npu", "mistral-7b", "OpenVINO/Mistral", "scores better")
    assert held and "/activate" not in calls and "/end-trial" in calls
    assert journal[0][0] == "held" and journal[0][1]["needs"] == "the user"
    monkeypatch.setattr(models, "state", lambda max_age_s=10: state())
    calls.clear()
    assert models.activate_if_reversible("npu", "mistral-7b", "OpenVINO/Mistral", "scores better") is None
    assert calls == ["/activate"]


def test_a_held_switch_becomes_evidence_for_reflection():
    import reflection
    facts = reflection.evidence([{"kind": "model", "action": "held", "at": "2026-11-01T14:00:00+00:00", "device": "npu",
                                  "name": "mistral-7b", "problems": ["local-build couldn't be fetched again"]}])
    assert "held back from switching my NPU to mistral-7b" in facts[0]["fact"]

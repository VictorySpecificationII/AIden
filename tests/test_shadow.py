"""Shadow mode: a candidate proves itself silently on real traffic before taking over."""
import json
import time
from datetime import datetime, timezone

import pytest

import evals
import experience
import models
import shadow
from test_models import Steward


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", True)
    monkeypatch.setattr(models, "_state", {"at": 0.0, "value": None})
    fake = Steward()
    fake.state["devices"]["npu"]["trial"] = "cand"
    fake.state["devices"]["gpu"] = {"active": "q8", "previous": None, "trial": "cand"}
    monkeypatch.setattr(models, "steward", fake)
    monkeypatch.setattr(models, "STEWARD_TOKEN", "t")
    monkeypatch.setattr(models, "free_memory_gb", lambda: 12.0)
    monkeypatch.setattr(evals, "shareable", lambda pair: (True, "ok"))
    return fake


def start(device, days_ago):
    at = datetime.fromtimestamp(time.time() - days_ago * 86400, timezone.utc).isoformat()
    record = {"schema": 1, "kind": "model", "at": at, "action": "shadow_started", "device": device,
              "source": "OpenVINO/cand", "name": "cand", "reason": "scores better"}
    with open(f"{experience.EXPERIENCE_DIR}/2026-10-30.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def add_pairs(device, n, **pair):
    for i in range(n):
        shadow.store(device, {"prompt": f"p{i}", **pair})


def test_the_shadow_survives_a_restart_through_the_journal(world):
    start("gpu", days_ago=0.5)
    assert shadow.active("gpu")["name"] == "cand" and shadow.active("npu") is None


def test_no_decision_before_enough_time_and_traffic(world):
    start("gpu", days_ago=0.5)
    add_pairs("gpu", 20, active="a", candidate="c")
    assert shadow.check("gpu") is None  # not old enough
    start("npu", days_ago=3)
    add_pairs("npu", 3, active=True, candidate=True)
    assert shadow.check("npu") is None  # old enough, too few pairs


def test_real_traffic_can_veto_a_gpu_candidate(world, monkeypatch):
    start("gpu", days_ago=3)
    add_pairs("gpu", 12, active="a", candidate="c")
    monkeypatch.setattr(evals, "local_verdicts", lambda judge, pairs, seed: ["active"] * len(pairs))
    monkeypatch.setattr(evals, "claude_verdicts", lambda pairs, seed: ["active"] * len(pairs))
    result = shadow.check("gpu")
    assert result["outcome"] == "rejected" and ("/delete", {"name": "cand"}) in world.calls
    assert shadow.active("gpu") is None and shadow.pairs("gpu") == []  # done, and the pairs are set aside


def test_no_objection_means_the_switch_happens(world, monkeypatch):
    start("gpu", days_ago=3)
    add_pairs("gpu", 12, active="a", candidate="c")
    monkeypatch.setattr(evals, "local_verdicts", lambda judge, pairs, seed: ["candidate"] * len(pairs))
    monkeypatch.setattr(evals, "claude_verdicts", lambda pairs, seed: ["tie"] * len(pairs))
    assert shadow.check("gpu")["outcome"] == "switched" and ("/activate", {"device": "gpu", "name": "cand"}) in world.calls


def test_npu_disagreements_are_settled_by_claude(world, monkeypatch):
    start("npu", days_ago=3)
    add_pairs("npu", 12, active=True, candidate=False)  # they disagree on every request
    monkeypatch.setattr(shadow, "claude_labels", lambda prompts: [True] * len(prompts))  # the current model was right
    result = shadow.check("npu")
    assert result["outcome"] == "rejected" and "routed better" in result["veto"]


def test_low_memory_ends_the_shadow_early(world, monkeypatch):
    start("gpu", days_ago=0.2)
    monkeypatch.setattr(models, "free_memory_gb", lambda: 2.0)
    monkeypatch.setattr(evals, "local_verdicts", lambda judge, pairs, seed: [])
    monkeypatch.setattr(evals, "claude_verdicts", lambda pairs, seed: None)
    result = shadow.check("gpu")
    assert result["outcome"] == "switched"  # no evidence against it: benchmarks stand
    import glob
    lines = [l for f in sorted(glob.glob(f"{experience.EXPERIENCE_DIR}/*.jsonl")) for l in open(f)]
    switched = [json.loads(l) for l in lines if '"switched"' in l][-1]
    assert "shadow inconclusive: 0 pairs" in switched["reason"]


def test_shadow_jobs_never_overlap(monkeypatch):
    ran = []
    shadow._busy.acquire()
    try:
        shadow.in_background(lambda: ran.append(1))
    finally:
        shadow._busy.release()
    assert ran == []

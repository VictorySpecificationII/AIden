"""Layer 2: harder public tests, and the user's own conversations as a veto."""
import json

import pytest

import evals
import experience
import models


@pytest.mark.parametrize("text, expected", [
    ("16 - 3 - 4 = 9, 9 * 2 = 18\nAnswer: 18", 18.0),
    ("Answer: $1,250", 1250.0),
    ("so the total is 42.5 dollars", 42.5),
    ("I can't solve this.", None),
])
def test_gsm8k_answers_are_read(text, expected):
    assert evals.gsm8k_answer(text) == expected


def test_gsm8k_truth():
    assert evals.gsm8k_truth({"answer": "Janet sells 9 eggs...\n#### 1,018"}) == 1018.0


@pytest.mark.parametrize("text, expected", [
    ("C", "C"), ("The answer is J.", "J"), ("**B**", "B"), ("none", None), ("D. Mitochondria", "D"),
    ("I don't know.", None), ("I think it's hard to say", None),  # "I" is a word here, not option I
    ("I", "I"), ("Answer: (E)", "E"),
])
def test_mmlu_letters_are_read(text, expected):
    assert evals.mmlu_answer(text) == expected


def test_mmlu_prompt_lists_lettered_options():
    prompt = evals.mmlu_prompt({"question": "Q?", "options": ["x", "y", "z"]})
    assert "A. x\nB. y\nC. z" in prompt and prompt.endswith("letter of the correct option.")


def test_checked_outcomes():
    questions = {"gsm8k": [{"question": "q1", "answer": "#### 4"}, {"question": "q2", "answer": "#### 5"}],
                 "mmlu_pro": [{"question": "m", "options": ["a", "b"], "answer": "B"}]}
    replies = iter(["Answer: 4", "Answer: 6", "B"])
    assert evals.checked_outcomes(lambda p, t: next(replies), questions) == {"gsm8k": [True, False], "mmlu_pro": [True]}


def test_public_set_canaries_pass_on_real_shaped_rows():
    rows = {"gsm8k": [{"question": f"q{i}", "answer": f"... #### {i}"} for i in range(30)],
            "mmlu_pro": [{"question": f"m{i}", "options": list("abcdefghij"), "answer": "ABCDEFGHIJ"[i % 10]} for i in range(30)]}
    assert models.measurement_problems("gpu", rows) == []
    rows["gsm8k"] = rows["gsm8k"][:5]
    assert any("only 5 gsm8k" in p for p in models.measurement_problems("gpu", rows))


def test_the_local_judge_cant_win_by_always_saying_A():
    pairs = [{"prompt": "p", "candidate": "c", "active": "a"} for _ in range(40)]
    verdicts = evals.local_verdicts(lambda q: "A", pairs, seed=1)
    # Answers are shuffled per pair, so "always A" splits between the two models
    assert 10 < verdicts.count("candidate") < 30 and verdicts.count("tie") == 0


def test_the_local_judge_maps_its_choice_back_to_the_right_model():
    pairs = [{"prompt": "p", "candidate": "GOOD", "active": "bad"} for _ in range(20)]
    judge = lambda q: "A" if q.index("GOOD") < q.index("bad") else "B"
    assert evals.local_verdicts(judge, pairs, seed=3) == ["candidate"] * 20


def test_claude_verdicts_are_mapped_back(monkeypatch):
    import mentor
    pairs = [{"prompt": f"p{i}", "candidate": "GOOD", "active": "bad"} for i in range(6)]

    monkeypatch.setattr(mentor, "MENTOR_TOKEN", "t")
    monkeypatch.setattr(mentor, "ask_mentor", lambda q, d, n: {"answer": json.dumps(
        ["A" if "Answer A: GOOD" in part else "B" for part in q.split("\n\n#")[1:]])})
    verdicts = evals.claude_verdicts(pairs, seed=5)
    assert verdicts == ["candidate"] * 6


def test_replays_skip_notes_and_tasks_and_put_disliked_first(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    turn = lambda p, trace, notes=False: {"kind": "turn", "prompt": p, "trace_id": trace,
                                          "answer": {"source": "local", "used_notes": notes}}
    lines = [turn("plain one", "t1"), turn("from my notes", "t2", notes=True), turn("### Task:\ntitle", "t3"),
             turn("disliked one", "t4"), {"kind": "feedback", "rating": "down", "trace_id": "t4"}]
    (tmp_path / "2026-10-30.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    replays = evals.replay_prompts()
    assert [r["prompt"] for r in replays] == ["disliked one", "plain one"] and replays[0]["disliked"]


def test_nothing_resembling_the_notes_goes_to_claude(monkeypatch):
    import mentor
    monkeypatch.setattr(mentor, "draft_privacy", lambda text: (("burn-in" not in text), "resembles notes", []))
    assert evals.shareable({"prompt": "hi", "candidate": "a", "active": "b"})[0]
    assert not evals.shareable({"prompt": "hi", "candidate": "about the burn-in plan", "active": "b"})[0]


@pytest.fixture
def replay_world(monkeypatch):
    monkeypatch.setattr(evals, "replay_prompts", lambda: [{"prompt": f"p{i}", "disliked": False} for i in range(8)])
    monkeypatch.setattr(models, "ask_answer", lambda device, model, prompt: f"{model} says\nConfidence: high")
    monkeypatch.setattr(evals, "shareable", lambda pair: (True, "ok"))


def test_claude_and_the_local_judge_together_can_veto(replay_world, monkeypatch):
    monkeypatch.setattr(evals, "local_verdicts", lambda judge, pairs, seed: ["active"] * len(pairs))
    monkeypatch.setattr(evals, "claude_verdicts", lambda pairs, seed: ["active"] * len(pairs))
    result = models.judge_replays("gpu", "cand", "act", seed=1)
    assert result["veto"] and "both judges prefer the current model" in result["veto"]


def test_the_biased_local_judge_alone_cannot_veto(replay_world, monkeypatch):
    monkeypatch.setattr(evals, "local_verdicts", lambda judge, pairs, seed: ["active"] * len(pairs))
    monkeypatch.setattr(evals, "claude_verdicts", lambda pairs, seed: None)  # mentor offline
    assert models.judge_replays("gpu", "cand", "act", seed=1)["veto"] is None


def test_a_vetoed_switch_does_not_happen(monkeypatch, tmp_path):
    from test_models import Steward, score
    fake = Steward()
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", True)
    monkeypatch.setattr(models, "_state", {"at": 0.0, "value": None})
    monkeypatch.setattr(models, "steward", fake)
    monkeypatch.setattr(models, "STEWARD_TOKEN", "t")
    fake.state["devices"]["gpu"] = {"active": "qwen8b", "previous": None, "trial": None}
    monkeypatch.setattr(models, "catalog", lambda device: [{"source": "OpenVINO/x-int4-ov", "size_gb": 5}])
    monkeypatch.setattr(models, "start_trial", lambda source, device: "x-int4-ov")
    monkeypatch.setattr(evals, "sample", lambda seed: {})
    monkeypatch.setattr(models, "measurement_problems", lambda device, q: [])
    monkeypatch.setattr(models, "evaluate", lambda d, m, q: score(tools=m == "x-int4-ov"))
    monkeypatch.setattr(models, "claude_opinion", lambda *a: None)
    monkeypatch.setattr(models, "judge_replays", lambda *a: {"veto": "on your conversations both judges prefer the current model"})
    result = models.scout("gpu")
    assert result["outcome"] == "rejected" and "both judges" in result["reason"]
    assert not any(c[0] == "/activate" for c in fake.calls)


def test_candidates_much_smaller_or_too_big_are_skipped(monkeypatch):
    monkeypatch.setattr(models, "STEWARD_TOKEN", "t")
    monkeypatch.setattr(models, "state", lambda max_age_s=10: {
        "devices": {"gpu": {"active": "q8"}}, "models": {"q8": {"source": "OpenVINO/Qwen3-8B-int4-ov", "size_gb": 4.5}},
        "limits": {"org": "OpenVINO", "licences": ["apache-2.0"], "devices": {"gpu": "-int4-ov"}, "min_free_gb": 4}})
    monkeypatch.setattr(models, "tried", lambda: set())
    monkeypatch.setattr(models, "free_memory_gb", lambda: 12.0)  # room: 8 GB, so up to ~6.6 GB on disk
    sizes = {"OpenVINO/tiny-int4-ov": 0.45, "OpenVINO/peer-int4-ov": 4.3, "OpenVINO/huge-int4-ov": 9.0}

    class Reply:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def get(url, params=None, timeout=None):
        if url.endswith("/api/models"):
            return Reply([{"id": s, "downloads": 1} for s in sizes])
        source = url.split("/api/models/")[1]
        return Reply({"cardData": {"license": "apache-2.0"}, "pipeline_tag": "text-generation",
                      "siblings": [{"size": sizes[source] * 1e9}]})

    monkeypatch.setattr(models.requests, "get", get)
    assert [c["source"] for c in models.catalog("gpu")] == ["OpenVINO/peer-int4-ov"]

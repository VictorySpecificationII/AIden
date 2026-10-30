"""model-steward: AIden's hands for models, and the limits it enforces itself."""
import importlib.util
import json
import pathlib

import pytest

spec = importlib.util.spec_from_file_location(
    "steward", pathlib.Path(__file__).parent.parent / "tools/model-steward/steward.py")
steward = importlib.util.module_from_spec(spec)
spec.loader.exec_module(steward)


@pytest.fixture
def models(tmp_path, monkeypatch):
    monkeypatch.setattr(steward, "MODELS", str(tmp_path))
    monkeypatch.setattr(steward, "STATE_FILE", str(tmp_path / "aiden-models.json"))
    monkeypatch.setattr(steward, "ADOPT", {"npu": ("OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov", "phi")})
    monkeypatch.setattr(steward, "free_memory_gb", lambda: 12.0)
    steward.adopt()
    return tmp_path


def add_pulled(name, size_gb=4.0):
    state = steward.load_state()
    state["models"][name] = {"source": f"OpenVINO/{name}", "device": "npu", "path": f"{steward.MODELS}/OpenVINO/{name}",
                             "size_gb": size_gb, "pulled_at": 1}
    steward.save(state)


def served(models):
    return [e["name"] for e in json.loads((models / "config_npu.json").read_text())["mediapipe_config_list"]]


def test_first_start_adopts_the_model_already_served(models):
    assert steward.load_state()["devices"]["npu"]["active"] == "phi" and served(models) == ["phi"]


def test_trial_activate_rollback(models):
    add_pulled("gemma-cw-ov")
    steward.trial("npu", "gemma-cw-ov")
    assert served(models) == ["phi", "gemma-cw-ov"]  # both loaded while on trial
    steward.activate("npu", "gemma-cw-ov")
    assert served(models) == ["gemma-cw-ov"] and steward.load_state()["devices"]["npu"]["previous"] == "phi"
    steward.rollback("npu")
    assert served(models) == ["phi"] and steward.load_state()["devices"]["npu"]["previous"] == "gemma-cw-ov"


def test_a_trial_needs_free_memory(models, monkeypatch):
    add_pulled("big-cw-ov", size_gb=8.0)
    monkeypatch.setattr(steward, "free_memory_gb", lambda: 10.0)  # 10 - 8*1.2 < 4
    with pytest.raises(steward.Refused, match="memory"):
        steward.trial("npu", "big-cw-ov")


def test_one_trial_at_a_time(models):
    add_pulled("a-cw-ov"), add_pulled("b-cw-ov")
    steward.trial("npu", "a-cw-ov")
    with pytest.raises(steward.Refused, match="already on trial"):
        steward.trial("npu", "b-cw-ov")


def test_models_in_use_and_shared_files_are_never_deleted(models):
    with pytest.raises(steward.Refused):
        steward.delete("phi")
    state = steward.load_state()
    state["models"]["phi-again"] = {**state["models"]["phi"], "adopted": False}  # same files, another name
    steward.save(state)
    with pytest.raises(steward.Refused, match="same files"):
        steward.delete("phi-again")


def test_rejected_candidates_are_deleted(models):
    add_pulled("gemma-cw-ov")
    (models / "OpenVINO/gemma-cw-ov").mkdir(parents=True)
    steward.delete("gemma-cw-ov")
    assert not (models / "OpenVINO/gemma-cw-ov").exists() and "gemma-cw-ov" not in steward.load_state()["models"]


def test_disk_budget_counts_candidates_only(models, monkeypatch):
    add_pulled("old-candidate-cw-ov", size_gb=18.0)
    monkeypatch.setattr(steward, "hf_info", lambda source: {
        "cardData": {"license": "apache-2.0"}, "pipeline_tag": "text-generation", "siblings": [{"size": 4e9}]})
    with pytest.raises(steward.Refused, match="candidate budget"):
        steward.check_source("OpenVINO/new-int4-cw-ov", "npu")

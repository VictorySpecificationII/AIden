"""The gear check: triggers, outages from the probe log, and an honest report."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import selfcheck

T0 = datetime(2026, 10, 29, 22, 20, tzinfo=timezone.utc)


@pytest.mark.parametrize("prompt", ["gear check", "Can you run a status check?", "how are you doing, AIden?",
                                    "how's your GPU", "How are your models?", "health-check please"])
def test_explicit_phrases_trigger_it(prompt):
    assert selfcheck.wanted(prompt)


@pytest.mark.parametrize("prompt", ["hi, how are you", "check my notes on Ceph", "how is the weather"])
def test_small_talk_does_not(prompt):
    assert not selfcheck.wanted(prompt)


def test_outages_are_found_and_classified():
    events = [
        (T0, "ovms-gpu could not generate (1 in a row): ConnectionError: ('Connection aborted.', RemoteDisconnected(...))"),
        (T0 + timedelta(minutes=15), "ovms-gpu is generating again after 1 failed probe(s)"),
        (T0 + timedelta(hours=2), "ovms-gpu could not generate (1 in a row): ReadTimeout: Read timed out."),
        (T0 + timedelta(hours=2, minutes=15), "ovms-gpu could not generate (2 in a row): ReadTimeout: Read timed out."),
        (T0 + timedelta(hours=3), "ovms-npu is not ready (1 probe(s) in a row)"),
        # AIden restarted: the count starts over, so this is a new outage
        (T0 + timedelta(hours=5), "ovms-gpu could not generate (1 in a row): ConnectionError: RemoteDisconnected"),
    ]
    found = selfcheck.outages(events)
    assert [(o["kind"], o["recovered"] is not None, o.get("ended_unseen", False)) for o in found["ovms-gpu"]] == [
        ("crash", True, False), ("hang", False, True), ("crash", False, False)]
    assert selfcheck.describe_outage(found["ovms-gpu"][1], generating_now=False).endswith("(ended later)")
    assert found["ovms-npu"][0]["kind"] == "stuck loading"


def facts(**over):
    backend = lambda name, available=True, models=("m",): SimpleNamespace(name=name, available=available, models=list(models))
    base = {
        "checked_at": T0, "failed_checks": [],
        "backends": {"ovms-gpu": backend("ovms-gpu"), "ovms-npu": backend("ovms-npu"), "ollama": backend("ollama", models=())},
        "busy": {"intel_gpu": 3.0, "npu": 0.0},
        "outages": {"ovms-gpu": [{"kind": "crash", "began": T0, "recovered": T0 + timedelta(minutes=15)}]},
        "uptime": {"up_seconds": 13 * 3600, "booted_at": "2026-10-29T21:53:43+01:00"},
        "memory": {"total_gib": 30.3, "available_gib": 11.2, "swap_free_gib": 8.0},
        "load": {"load_1m": 1.2, "load_5m": 1.0, "load_15m": 0.9, "cpus": 16},
        "suspends": {"since_boot": 3, "failed": 0, "last_hw_sleep_s": 84.8},
        "sleep-log": ["2026-10-30T11:11:58+01:00 hive kernel: PM: suspend entry (s2idle)",
                      "2026-10-30T11:18:43+01:00 hive systemd-sleep[1]: System returned from sleep operation 'suspend'."],
        "gpu-kernel-log": [],
        "containers": {"ovms-gpu": ({"restarts": 2}, ["x CL_OUT_OF_RESOURCES", "y CL_OUT_OF_RESOURCES"]),
                       "ovms-npu": ({"restarts": 0}, [])},
    }
    base.update(over)
    return base


def test_report_after_a_rough_night(monkeypatch):
    monkeypatch.setattr(selfcheck.senses, "status", {"ovms-gpu": {"generating": True}, "ovms-npu": {"generating": True}})
    text = selfcheck.report(facts())
    assert "GPU (m): ✅ generating · 3% busy" in text
    assert "1 outage: crash at" in text and "restarted 2 times" in text and "2 of them CL_OUT_OF_RESOURCES" in text
    assert "NPU: no problems." in text and "3 sleeps since boot, last one " in text  # times shown in local time
    assert "no GPU warnings" in text and "I recovered each time" in text
    assert "Ollama" not in text  # up but without models: not part of the body yet


def test_report_when_the_gpu_cannot_generate(monkeypatch):
    monkeypatch.setattr(selfcheck.senses, "status", {"ovms-gpu": {"generating": False, "error": "ReadTimeout"},
                                                     "ovms-npu": {"generating": True}})
    text = selfcheck.report(facts(outages={}))
    assert "❌ up but can't generate (ReadTimeout)" in text and "a reboot clears it" in text


def test_checks_that_fail_are_named(monkeypatch):
    monkeypatch.setattr(selfcheck.senses, "status", {})
    text = selfcheck.report(facts(failed_checks=["gpu-kernel-log: PermissionError"], outages=None))
    assert "Couldn't check: gpu-kernel-log: PermissionError" in text and "not probed yet" in text


def test_gather_runs_every_check_and_collects_failures(monkeypatch):
    backends = [SimpleNamespace(name="ovms-gpu", available=True, models=["q"]),
                SimpleNamespace(name="ovms-npu", available=True, models=["p"])]
    monkeypatch.setattr(selfcheck, "get_capabilities", lambda: SimpleNamespace(backends=backends))
    monkeypatch.setattr(selfcheck, "prometheus_value", lambda query: None)
    monkeypatch.setattr(selfcheck, "probe_events", lambda: [])
    monkeypatch.setattr(selfcheck.senses, "probe_all", lambda: None)
    ran = []

    def fake_run(command, /, **args):
        ran.append((command, args.get("name")))
        return {"command": command, "ok": command != "gpu-kernel-log", "output": None, "error": "PermissionError"}

    monkeypatch.setattr(selfcheck.terminal, "run", fake_run)
    facts = selfcheck.gather()
    assert ("container", "ovms-gpu") in ran and ("container-errors", "ovms-npu") in ran
    assert facts["failed_checks"] == ["gpu-kernel-log: PermissionError"]


def test_a_server_stuck_loading_is_named(monkeypatch):
    monkeypatch.setattr(selfcheck.senses, "status", {"ovms-gpu": {"generating": False, "error": "server not ready"},
                                                     "ovms-npu": {"generating": True}})
    text = selfcheck.report(facts(outages={}))
    assert "❌ up but stuck loading its model" in text and "a reboot clears it" in text


def test_times_from_other_days_say_which_day():
    now = datetime.now(timezone.utc)
    assert ":" in selfcheck.local(now) and " " not in selfcheck.local(now)
    assert selfcheck.local(now - timedelta(days=1)).startswith("yesterday ")

"""AIden's read-only terminal: fixed commands, failures reported, never raised."""
import struct

import pytest

import terminal


def test_unknown_commands_are_refused():
    assert terminal.run("rm", path="/") == {"command": "rm", "ok": False, "error": "unknown command"}


def test_a_failing_command_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(terminal, "HOST_SYS", "/nonexistent")
    result = terminal.run("suspends")
    assert result["ok"] is False and "FileNotFoundError" in result["error"]


def test_suspend_stats_are_read(tmp_path, monkeypatch):
    stats = tmp_path / "power/suspend_stats"
    stats.mkdir(parents=True)
    for name, value in {"success": "3", "fail": "0", "last_hw_sleep": "84798906"}.items():
        (stats / name).write_text(value + "\n")
    monkeypatch.setattr(terminal, "HOST_SYS", str(tmp_path))
    assert terminal.run("suspends")["output"] == {"since_boot": 3, "failed": 0, "last_hw_sleep_s": 84.8}


def test_only_aidens_own_containers_can_be_named():
    result = terminal.run("container-errors", name="mentor-bridge")
    assert result["ok"] is False and "not one of AIden's containers" in result["error"]


def test_docker_log_frames_are_decoded():
    frame = lambda text: struct.pack(">BxxxI", 2, len(text)) + text
    raw = frame(b"2026-10-30T00:50:50Z [GPU] CL_OUT_OF_RESOURCES\n") + frame(b"line two\n")
    assert terminal.demux(raw) == ["2026-10-30T00:50:50Z [GPU] CL_OUT_OF_RESOURCES", "line two"]


def test_journal_runs_without_a_shell(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        # Several journal files: lines can arrive out of order
        return type("R", (), {"returncode": 0, "stderr": "", "stdout":
                              "2026-10-30T10:41:59+01:00 hive kernel: PM: suspend entry (s2idle)\n"
                              "2026-10-29T21:57:34+01:00 hive kernel: PM: suspend entry (s2idle)\n"})()

    monkeypatch.setattr(terminal.subprocess, "run", fake_run)
    assert [l[:10] for l in terminal.run("sleep-log")["output"]] == ["2026-10-29", "2026-10-30"]
    assert seen["argv"][:3] == ["journalctl", "-D", terminal.JOURNAL_DIR] and "shell" not in seen
    assert "--system" in seen["argv"]  # never the user's own session journal

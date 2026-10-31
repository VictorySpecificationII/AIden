"""Experience records: AIden's training data."""
import json

import experience


def test_records_are_appended_as_json_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", True)
    assert experience.record("turn", {"prompt": "Eu conheço a cidade?", "answer": {"text": "Sim."}})
    assert experience.record("mentor", {"question": "q", "source": "claude"})
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1  # one file per day
    first, second = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert first["kind"] == "turn" and first["prompt"] == "Eu conheço a cidade?" and first["schema"] == 1
    assert second["kind"] == "mentor" and second["source"] == "claude"


def test_recording_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", False)
    assert experience.record("turn", {"prompt": "x"}) is False
    assert list(tmp_path.iterdir()) == []


def test_a_failing_disk_never_breaks_a_request(tmp_path, monkeypatch):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("a file where the directory should be")
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(blocked))
    monkeypatch.setattr(experience, "ENABLED", True)
    assert experience.record("turn", {"prompt": "x"}) is False  # logged, not raised


def test_records_are_mirrored_to_loki_under_their_trace(tmp_path, monkeypatch, caplog):
    import logging
    from opentelemetry import trace
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", True)
    monkeypatch.setattr(experience, "TO_LOKI", True)
    seen = {}

    class Grab(logging.Handler):
        def emit(self, record):
            seen.update(message=record.getMessage(), event=record.event, kind=record.kind,
                        trace=format(trace.get_current_span().get_span_context().trace_id, "032x"))

    handler = Grab()
    experience.mirror_logger.addHandler(handler)
    try:
        experience.record("turn", {"prompt": "hi", "trace_id": "0af7651916cd43dd8448eb211c80319c"})
    finally:
        experience.mirror_logger.removeHandler(handler)
    assert json.loads(seen["message"])["prompt"] == "hi"
    assert seen["event"] == "experience" and seen["kind"] == "turn"
    assert seen["trace"] == "0af7651916cd43dd8448eb211c80319c"


def test_the_mirror_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "EXPERIENCE_DIR", str(tmp_path))
    monkeypatch.setattr(experience, "ENABLED", True)
    monkeypatch.setattr(experience, "TO_LOKI", False)
    monkeypatch.setattr(experience, "mirror", lambda *a: (_ for _ in ()).throw(AssertionError("mirrored")))
    assert experience.record("turn", {"prompt": "x"})

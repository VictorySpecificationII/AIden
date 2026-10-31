"""AIden's experience: one JSON line per request, the raw material for AIden's own model.

Records are appended to EXPERIENCE_DIR/YYYY-MM-DD.jsonl (the aiden-experience volume) and
never leave the machine. The training pipeline reads them and registers each dataset
version in MLflow.

Each record keeps the prompt and the answer (the user chose to keep both), the routing
decision and how it was made, and the outcome. Note *text* is never recorded: only paths
and scores. Flags let the training pipeline filter later:
    answer.used_notes   the answer drew on the user's notes (its text may reflect them)
    source == "claude"  a mentor answer; check Anthropic's terms before training on these

Each record is also mirrored to Loki as one JSON log line (attribute event=experience),
linked to its trace, so conversations can be browsed and searched in Grafana. The JSONL
files stay the source of truth (training reads them; Loki keeps 30 days). Switch the
mirror off with AIDEN_EXPERIENCE_TO_LOKI=false.

Recording must never break a request: failures are logged and ignored.
Switch off with AIDEN_RECORD_EXPERIENCE=false.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

EXPERIENCE_DIR = os.environ.get("EXPERIENCE_DIR", "/data/experience")
ENABLED = os.environ.get("AIDEN_RECORD_EXPERIENCE", "true").lower() != "false"
TO_LOKI = os.environ.get("AIDEN_EXPERIENCE_TO_LOKI", "true").lower() != "false"
MAX_LOG_CHARS = 16000  # one log line; the JSONL record keeps everything
SCHEMA_VERSION = 1

logger = logging.getLogger("aiden.experience")
_lock = threading.Lock()


def record(kind: str, fields: Dict[str, Any]) -> bool:
    """Append one record; returns whether it was written."""
    if not ENABLED:
        return False
    now = datetime.now(timezone.utc)
    entry = {"schema": SCHEMA_VERSION, "kind": kind, "at": now.isoformat(), **fields}
    path = os.path.join(EXPERIENCE_DIR, f"{now:%Y-%m-%d}.jsonl")
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with _lock:
            os.makedirs(EXPERIENCE_DIR, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if TO_LOKI:
            mirror(entry, line)
        return True
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Could not record experience: %s", exc)
        return False


def mirror(entry: Dict[str, Any], line: str):
    """Send the record to Loki (via the OpenTelemetry log pipeline), under its own trace.
    Records are often written after their span has ended (a streamed answer finishes
    later), so the trace is re-attached from the record's trace_id."""
    try:
        from opentelemetry import trace
        from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
        trace_id = entry.get("trace_id")
        span = trace.get_current_span()
        if trace_id and len(trace_id) == 32:
            span = NonRecordingSpan(SpanContext(trace_id=int(trace_id, 16), span_id=int.from_bytes(os.urandom(8), "big") or 1,
                                                is_remote=True, trace_flags=TraceFlags(TraceFlags.SAMPLED)))
        with trace.use_span(span, end_on_exit=False):
            mirror_logger.info(line[:MAX_LOG_CHARS], extra={"event": "experience", "kind": entry.get("kind")})
    except Exception as exc:  # the mirror must never affect recording
        logger.debug("Could not mirror experience to Loki: %s", exc)


mirror_logger = logging.getLogger("aiden.experience.mirror")

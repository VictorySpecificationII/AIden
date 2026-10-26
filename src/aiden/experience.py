"""AIden's experience: one JSON line per request, the raw material for AIden's own model.

Records are appended to EXPERIENCE_DIR/YYYY-MM-DD.jsonl (the aiden-experience volume) and
never leave the machine. The training pipeline reads them and registers each dataset
version in MLflow.

Each record keeps the prompt and the answer (the user chose to keep both), the routing
decision and how it was made, and the outcome. Note *text* is never recorded: only paths
and scores. Flags let the training pipeline filter later:
    answer.used_notes   the answer drew on the user's notes (its text may reflect them)
    source == "claude"  a mentor answer; check Anthropic's terms before training on these

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
        return True
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Could not record experience: %s", exc)
        return False

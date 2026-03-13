from __future__ import annotations

import json
from pathlib import Path
from time import time


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "failed"},
    "running": {"completed", "failed", "retry", "queued"},
    "retry": {"running", "failed"},
    "completed": set(),
    "failed": set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition_record(job_id: str, previous: str, current: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "previous_status": previous,
        "status": current,
        "ts": round(time(), 3),
    }


def append_transition_record(record: dict[str, object], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return output_file

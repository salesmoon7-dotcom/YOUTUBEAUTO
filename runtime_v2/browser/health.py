from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time


def build_browser_health_payload(
    sessions: list[dict[str, object]],
    runtime: str = "runtime_v2",
    run_id: str = "",
) -> dict[str, object]:
    total = len(sessions)
    healthy = sum(1 for session in sessions if bool(session.get("healthy", False)))
    unhealthy = total - healthy
    availability = round((healthy / total) * 100, 3) if total else 0.0
    return {
        "schema_version": "1.0",
        "runtime": runtime,
        "run_id": run_id,
        "checked_at": round(time(), 3),
        "session_count": total,
        "healthy_count": healthy,
        "unhealthy_count": unhealthy,
        "availability_percent": availability,
        "sessions": sessions,
    }


def write_browser_health(payload: dict[str, object], output_file: str | Path) -> Path:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(path)
    return path

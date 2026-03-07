from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.browser.manager import BrowserSession


def build_browser_registry_payload(
    sessions: list[dict[str, object]],
    runtime: str = "runtime_v2",
    run_id: str = "",
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "runtime": runtime,
        "run_id": run_id,
        "checked_at": round(time(), 3),
        "session_count": len(sessions),
        "sessions": sessions,
    }


def write_browser_registry(payload: dict[str, object], output_file: str | Path) -> Path:
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


def load_browser_registry(output_file: str | Path) -> list[BrowserSession]:
    path = Path(output_file)
    if not path.exists():
        return []
    raw_payload_obj = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw_payload_obj, dict):
        return []
    raw_payload = cast(dict[object, object], raw_payload_obj)
    sessions_value = raw_payload.get("sessions", [])
    if not isinstance(sessions_value, list):
        return []
    raw_sessions = cast(list[object], sessions_value)
    sessions: list[BrowserSession] = []
    for raw_item in raw_sessions:
        if isinstance(raw_item, dict):
            item = cast(dict[object, object], raw_item)
            session_payload: dict[str, object] = {}
            for raw_key in item:
                session_payload[str(raw_key)] = item[raw_key]
            sessions.append(BrowserSession.from_dict(session_payload))
    return sessions

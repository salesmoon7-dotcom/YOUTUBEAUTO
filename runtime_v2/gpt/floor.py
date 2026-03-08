from __future__ import annotations

from dataclasses import dataclass
import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.recovery.hybrid import should_spawn


@dataclass(slots=True)
class GptEndpoint:
    name: str
    status: str
    last_seen_at: float


def ok_count(endpoints: list[GptEndpoint], fresh_sec: int = 60) -> int:
    now = time()
    return sum(
        1 for e in endpoints if e.status == "OK" and now - e.last_seen_at <= fresh_sec
    )


def build_gpt_status_payload(
    endpoints: list[GptEndpoint],
    *,
    min_ok: int,
    breach_sec: int,
    previous_status: dict[str, object] | None = None,
    pending_boot: int = 0,
    spawn_fail_count: int = 0,
    last_spawn_at: float | None = None,
    cooldown_sec: int = 300,
    runtime: str = "runtime_v2",
) -> dict[str, object]:
    now = round(time(), 3)
    current_ok_count = ok_count(endpoints)
    floor_breached = current_ok_count < min_ok
    previous_spawn_history = _to_float_list(
        [] if previous_status is None else previous_status.get("spawn_history", [])
    )
    previous_breach_started_at = _to_float(
        None if previous_status is None else previous_status.get("breach_started_at")
    )
    previous_pending_boot = _to_int(
        0 if previous_status is None else previous_status.get("pending_boot", 0)
    )
    previous_spawn_fail_count = _to_int(
        0 if previous_status is None else previous_status.get("spawn_fail_count", 0)
    )
    previous_last_spawn_at = _to_float(
        None if previous_status is None else previous_status.get("last_spawn_at")
    )

    breach_started_at = previous_breach_started_at if floor_breached else None
    if floor_breached and breach_started_at is None:
        breach_started_at = now

    effective_breach_sec = 0
    if floor_breached and breach_started_at is not None:
        effective_breach_sec = max(0, int(now - breach_started_at))

    effective_last_spawn_at = (
        last_spawn_at if last_spawn_at is not None else previous_last_spawn_at
    )
    cooldown_elapsed = cooldown_sec
    if effective_last_spawn_at is not None:
        cooldown_elapsed = max(0, int(now - effective_last_spawn_at))

    effective_pending_boot = (
        pending_boot if pending_boot != 0 else previous_pending_boot
    )
    effective_spawn_fail_count = (
        spawn_fail_count if spawn_fail_count != 0 else previous_spawn_fail_count
    )
    recent_spawn_history = [
        entry for entry in previous_spawn_history if now - entry <= 3600
    ]
    spawn_needed = should_spawn(
        current_ok_count, effective_breach_sec, cooldown_elapsed
    )
    return {
        "schema_version": "1.0",
        "runtime": runtime,
        "checked_at": now,
        "ok_count": current_ok_count,
        "min_ok": min_ok,
        "floor_breached": floor_breached,
        "breach_started_at": breach_started_at,
        "breach_sec": effective_breach_sec if floor_breached else breach_sec,
        "pending_boot": effective_pending_boot,
        "last_spawn_at": effective_last_spawn_at,
        "spawn_fail_count": effective_spawn_fail_count,
        "spawn_needed": spawn_needed,
        "warning_active": floor_breached,
        "last_warning_at": now if floor_breached else None,
        "cooldown_sec": cooldown_sec,
        "cooldown_elapsed_sec": cooldown_elapsed,
        "hourly_spawn_count": len(recent_spawn_history),
        "spawn_history": recent_spawn_history,
        "endpoints": [
            {
                "name": endpoint.name,
                "status": endpoint.status,
                "last_seen_at": endpoint.last_seen_at,
            }
            for endpoint in endpoints
        ],
    }


def write_gpt_status(payload: dict[str, object], output_file: str | Path) -> Path:
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


def load_gpt_status(output_file: str | Path) -> dict[str, object] | None:
    path = Path(output_file)
    if not path.exists():
        return None
    try:
        raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    payload = cast(dict[object, object], raw_payload)
    typed_payload: dict[str, object] = {}
    for raw_key in payload:
        typed_payload[str(raw_key)] = payload[raw_key]
    return typed_payload


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float, str)):
        return float(value)
    return None


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return 0


def _to_float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    raw_items = cast(list[object], value)
    items: list[float] = []
    for entry in raw_items:
        if isinstance(entry, bool):
            items.append(float(entry))
        elif isinstance(entry, (int, float)):
            items.append(float(entry))
        elif isinstance(entry, str):
            try:
                items.append(float(entry))
            except ValueError:
                continue
    return items

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.gpt.floor import (
    GptEndpoint,
    build_gpt_status_payload,
    load_gpt_status,
    write_gpt_status,
)


def monitor_gpt_pool(status_file: Path) -> dict[str, object]:
    status = load_gpt_status(status_file)
    if status is None:
        return {"ok": False, "reason": "missing_status"}
    ok_count_value = status.get("ok_count", 0)
    min_ok_value = status.get("min_ok", 1)
    ok_count = _to_int(ok_count_value)
    min_ok = max(1, _to_int(min_ok_value, default=1))
    return {
        "ok": ok_count >= min_ok,
        "ok_count": ok_count,
        "floor_breached": bool(status.get("floor_breached", False)),
        "spawn_needed": bool(status.get("spawn_needed", False)),
    }


def tick_gpt_status(
    status_file: Path, config: RuntimeConfig | None = None
) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
    previous_status = load_gpt_status(status_file)
    endpoints = _endpoints_from_browser_health(runtime_config.browser_health_file)
    payload = build_gpt_status_payload(
        endpoints,
        min_ok=runtime_config.gpt_floor_min_ok,
        breach_sec=runtime_config.gpt_breach_sec,
        previous_status=previous_status,
        cooldown_sec=runtime_config.gpt_spawn_cooldown_sec,
        runtime="runtime_v2",
    )
    _ = write_gpt_status(payload, status_file)
    return payload


def _endpoints_from_browser_health(browser_health_file: Path) -> list[GptEndpoint]:
    payload = _read_json(browser_health_file)
    if payload is None:
        return []
    raw_sessions = payload.get("sessions", [])
    if not isinstance(raw_sessions, list):
        return []
    endpoints: list[GptEndpoint] = []
    for raw_entry in cast(list[object], raw_sessions):
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[object, object], raw_entry)
        if str(entry.get("group", "")).strip().lower() != "llm":
            continue
        endpoints.append(
            GptEndpoint(
                name=str(entry.get("service", "default")),
                status="OK" if bool(entry.get("healthy", False)) else "FAILED",
                last_seen_at=_to_float(entry.get("last_seen_at", 0.0)),
            )
        )
    return endpoints


def _to_float(value: object) -> float:
    if isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else 0.0
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else 0.0
    if isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return 0.0
        return numeric if math.isfinite(numeric) else 0.0
    return 0.0


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            numeric = float(value)
        except ValueError:
            return default
        except OverflowError:
            return default
        if not math.isfinite(numeric):
            return default
        return int(numeric)
    return default


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    return {
        str(raw_key): raw_value
        for raw_key, raw_value in cast(dict[object, object], raw_payload).items()
    }

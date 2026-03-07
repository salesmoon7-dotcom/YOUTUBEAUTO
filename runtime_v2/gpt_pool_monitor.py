from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.gpt.floor import GptEndpoint, build_gpt_status_payload, load_gpt_status, write_gpt_status


def monitor_gpt_pool(status_file: Path) -> dict[str, object]:
    status = load_gpt_status(status_file)
    if status is None:
        return {"ok": False, "reason": "missing_status"}
    ok_count_value = status.get("ok_count", 0)
    min_ok_value = status.get("min_ok", 1)
    ok_count = int(ok_count_value) if isinstance(ok_count_value, (int, float, str)) else 0
    min_ok = int(min_ok_value) if isinstance(min_ok_value, (int, float, str)) else 1
    return {
        "ok": ok_count >= min_ok,
        "ok_count": ok_count,
        "floor_breached": bool(status.get("floor_breached", False)),
        "spawn_needed": bool(status.get("spawn_needed", False)),
    }


def tick_gpt_status(status_file: Path, config: RuntimeConfig | None = None) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
    previous_status = load_gpt_status(status_file)
    endpoints = _endpoints_from_status(previous_status)
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


def _endpoints_from_status(status: dict[str, object] | None) -> list[GptEndpoint]:
    if status is None:
        return []
    raw_endpoints = status.get("endpoints", [])
    if not isinstance(raw_endpoints, list):
        return []
    typed_endpoints: list[GptEndpoint] = []
    for raw_entry in cast(list[object], raw_endpoints):
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[object, object], raw_entry)
        typed_endpoints.append(
            GptEndpoint(
                name=str(entry.get("name", "default")),
                status=str(entry.get("status", "FAILED")),
                last_seen_at=_to_float(entry.get("last_seen_at", 0.0)),
            )
        )
    return typed_endpoints


def _to_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0

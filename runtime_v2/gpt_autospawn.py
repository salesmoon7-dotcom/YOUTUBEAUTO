from __future__ import annotations

import math
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.gpt.floor import load_gpt_status, write_gpt_status


def _coerce_float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    raw_items = cast(list[object], value)
    items: list[float] = []
    for entry in raw_items:
        if isinstance(entry, bool):
            numeric = float(entry)
            if math.isfinite(numeric):
                items.append(numeric)
        elif isinstance(entry, (int, float)):
            numeric = float(entry)
            if math.isfinite(numeric):
                items.append(numeric)
        elif isinstance(entry, str):
            try:
                numeric = float(entry)
            except ValueError:
                continue
            if math.isfinite(numeric):
                items.append(numeric)
    return items


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return None
        return numeric if math.isfinite(numeric) else None
    return None


def _coerce_int(value: object, default: int = 0) -> int:
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


def apply_autospawn_decision(
    status_file: Path,
    config: RuntimeConfig | None = None,
) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
    status = load_gpt_status(status_file)
    if status is None:
        return {"spawned": False, "reason": "missing_status"}
    if not bool(status.get("spawn_needed", False)):
        status["last_spawn_blocked_reason"] = "not_needed"
        _ = write_gpt_status(status, status_file)
        return {"spawned": False, "reason": "not_needed"}
    now = round(time(), 3)
    effective_last_spawn_at = _coerce_float(status.get("last_spawn_at"))
    cooldown_elapsed = runtime_config.gpt_spawn_cooldown_sec
    if effective_last_spawn_at is not None:
        cooldown_elapsed = max(0, int(now - effective_last_spawn_at))
    if cooldown_elapsed < runtime_config.gpt_spawn_cooldown_sec:
        cooldown_remaining = runtime_config.gpt_spawn_cooldown_sec - cooldown_elapsed
        status["cooldown_elapsed_sec"] = cooldown_elapsed
        status["last_spawn_blocked_reason"] = "cooldown"
        _ = write_gpt_status(status, status_file)
        return {
            "spawned": False,
            "reason": "cooldown",
            "cooldown_remaining_sec": cooldown_remaining,
        }
    spawn_history = [
        entry
        for entry in _coerce_float_list(status.get("spawn_history", []))
        if now - entry <= 3600
    ]
    if len(spawn_history) >= runtime_config.gpt_spawn_hourly_limit:
        status["spawn_history"] = spawn_history
        status["hourly_spawn_count"] = len(spawn_history)
        status["last_spawn_blocked_reason"] = "hourly_limit"
        _ = write_gpt_status(status, status_file)
        return {
            "spawned": False,
            "reason": "hourly_limit",
            "hourly_spawn_count": len(spawn_history),
        }
    pending_boot = _coerce_int(status.get("pending_boot", 0))
    status["pending_boot"] = pending_boot + 1
    status["last_spawn_at"] = now
    spawn_history.append(now)
    status["spawn_history"] = spawn_history
    status["hourly_spawn_count"] = len(spawn_history)
    status["cooldown_elapsed_sec"] = 0
    status["last_spawn_blocked_reason"] = ""
    _ = write_gpt_status(status, status_file)
    return {
        "spawned": True,
        "pending_boot": status["pending_boot"],
        "hourly_spawn_count": len(spawn_history),
    }

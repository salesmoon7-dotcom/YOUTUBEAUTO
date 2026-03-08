from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime_v2.browser.health import build_browser_health_payload, write_browser_health
from runtime_v2.browser.manager import default_browser_sessions
from runtime_v2.browser.registry import (
    build_browser_registry_payload,
    write_browser_registry,
)
from runtime_v2.config import GpuWorkload, RuntimeConfig
from runtime_v2.gpt.floor import (
    build_gpt_status_payload,
    load_gpt_status,
    write_gpt_status,
)
from runtime_v2.gpu.lease import (
    Lease,
    build_gpu_health_payload,
    write_gpu_health_payload,
)
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status
from runtime_v2.latest_run import update_latest_run_pointers
from runtime_v2.result_router import write_result_router


def ensure_runtime_bootstrap(
    config: RuntimeConfig,
    *,
    workload: GpuWorkload = "qwen3_tts",
    run_id: str = "runtime-bootstrap",
    mode: str = "local_cli",
) -> None:
    _ensure_runtime_directories(config)
    _ensure_state_files(config)
    _normalize_gpu_health_snapshot(config, workload)
    _normalize_gui_status_snapshot(config)
    default_sessions = [
        session.to_dict(healthy=False) for session in default_browser_sessions()
    ]
    if _read_json(config.browser_health_file) is None:
        _ = write_browser_health(
            build_browser_health_payload(
                default_sessions, runtime="runtime_v2", run_id=run_id
            ),
            config.browser_health_file,
        )
    if _read_json(config.browser_registry_file) is None:
        _ = write_browser_registry(
            build_browser_registry_payload(
                default_sessions, runtime="runtime_v2", run_id=run_id
            ),
            config.browser_registry_file,
        )
    if load_gpt_status(config.gpt_status_file) is None:
        _ = write_gpt_status(
            build_gpt_status_payload(
                [],
                min_ok=config.gpt_floor_min_ok,
                breach_sec=config.gpt_breach_sec,
                cooldown_sec=config.gpt_spawn_cooldown_sec,
                runtime="runtime_v2",
            ),
            config.gpt_status_file,
        )
    if _read_json(config.result_router_file) is None:
        _ = write_result_router(
            [],
            config.artifact_root,
            config.result_router_file,
            metadata={
                "run_id": run_id,
                "mode": mode,
                "status": "idle",
                "code": "BOOTSTRAPPED",
                "exit_code": 0,
                "debug_log": str(config.debug_log_root / f"{run_id}.jsonl"),
            },
        )
    if _read_json(config.gui_status_file) is None:
        _ = write_gui_status(
            build_gui_status_payload(
                {"queue_status": "idle", "seeded_jobs": 0},
                run_id=run_id,
                mode=mode,
                stage="idle",
                exit_code=0,
            ),
            config.gui_status_file,
        )
    if _read_json(config.latest_active_run_file) is None:
        update_latest_run_pointers(
            config,
            run_id=run_id,
            mode=mode,
            status="idle",
            code="BOOTSTRAPPED",
            debug_log=str(config.debug_log_root / f"{run_id}.jsonl"),
            write_completed=_read_json(config.latest_completed_run_file) is None,
        )
    elif _read_json(config.latest_completed_run_file) is None:
        update_latest_run_pointers(
            config,
            run_id=run_id,
            mode=mode,
            status="idle",
            code="BOOTSTRAPPED",
            debug_log=str(config.debug_log_root / f"{run_id}.jsonl"),
            write_completed=True,
        )


def _ensure_runtime_directories(config: RuntimeConfig) -> None:
    roots = [
        config.lock_root,
        config.debug_log_root,
        config.artifact_root,
        config.input_root,
        config.input_root / "accepted",
        config.input_root / "invalid",
        config.input_root / "qwen3_tts",
        config.input_root / "chatgpt",
        config.input_root / "genspark",
        config.input_root / "seaart",
        config.input_root / "geminigen",
        config.input_root / "canva",
        config.input_root / "render",
        config.input_root / "kenburns",
        config.input_root / "rvc",
        config.input_root / "rvc" / "source",
        config.input_root / "rvc" / "audio",
        config.gui_status_file.parent,
        config.browser_health_file.parent,
        config.browser_registry_file.parent,
        config.gpt_status_file.parent,
        config.control_plane_events_file.parent,
        config.queue_store_file.parent,
        config.feeder_state_file.parent,
        config.result_router_file.parent,
        config.latest_active_run_file.parent,
        config.latest_completed_run_file.parent,
        config.failure_summary_file.parent,
        config.worker_registry_file.parent,
    ]
    for root in roots:
        _ = root.mkdir(parents=True, exist_ok=True)
    if not config.control_plane_events_file.exists():
        _ = config.control_plane_events_file.write_text("", encoding="utf-8")


def _ensure_state_files(config: RuntimeConfig) -> None:
    if not config.queue_store_file.exists():
        _ = config.queue_store_file.write_text("[]", encoding="utf-8")
    if not config.feeder_state_file.exists():
        _ = config.feeder_state_file.write_text("{}", encoding="utf-8")


def _normalize_gpu_health_snapshot(
    config: RuntimeConfig, workload: GpuWorkload
) -> None:
    payload = _read_json(config.lease_file)
    if payload is None:
        _ = write_gpu_health_payload(
            build_gpu_health_payload(
                workload, lock_key=f"lock:{workload}", lease=None, event="idle"
            ),
            config.lease_file,
        )
        return
    has_schema = isinstance(payload.get("schema_version"), str) and isinstance(
        payload.get("checked_at"), (int, float)
    )
    if has_schema:
        return
    lease_payload = None
    lock_key = ""
    if all(key in payload for key in ("key", "owner", "expires_at")):
        lease_payload = payload
        lock_key = str(payload.get("key", "")).strip()
    normalized_workload = _workload_from_lock_key(lock_key) or workload
    normalized = build_gpu_health_payload(
        normalized_workload,
        lock_key=lock_key or f"lock:{normalized_workload}",
        lease=None
        if lease_payload is None
        else Lease.from_dict(_lease_like_payload(lease_payload)),
        event="normalized_snapshot" if lease_payload is not None else "idle",
    )
    _ = write_gpu_health_payload(normalized, config.lease_file)


def _normalize_gui_status_snapshot(config: RuntimeConfig) -> None:
    payload = _read_json(config.gui_status_file)
    if payload is None:
        return
    has_schema = isinstance(payload.get("schema_version"), str) and isinstance(
        payload.get("checked_at"), (int, float)
    )
    if has_schema:
        return
    status_payload = _coerce_mapping(payload.get("status", {}))
    normalized = build_gui_status_payload(
        {} if status_payload is None else status_payload,
        run_id=str(payload.get("run_id", "runtime-bootstrap")),
        mode=str(payload.get("mode", "local_cli")),
        stage=str(payload.get("stage", "idle")),
        exit_code=_to_int(payload.get("exit_code", 0)),
    )
    _ = write_gui_status(normalized, config.gui_status_file)


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    raw_payload_dict = cast(dict[object, object], raw_payload)
    payload: dict[str, object] = {}
    for raw_key, raw_value in raw_payload_dict.items():
        payload[str(raw_key)] = raw_value
    return payload


def _coerce_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw_value = cast(dict[object, object], value)
    return {str(key): item for key, item in raw_value.items()}


def _lease_like_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "key": str(payload.get("key", "")),
        "owner": str(payload.get("owner", "")),
        "token": _to_int(payload.get("token", 0)),
        "expires_at": _to_float(payload.get("expires_at", 0.0), 0.0),
        "run_id": str(payload.get("run_id", "unknown")),
        "pid": _to_int(payload.get("pid", 0)),
        "started_at": _to_float(payload.get("started_at", 0.0), 0.0),
        "host": str(payload.get("host", "unknown")),
    }


def _workload_from_lock_key(lock_key: str) -> GpuWorkload | None:
    normalized = lock_key.strip().lower()
    if normalized.endswith("qwen3_tts"):
        return "qwen3_tts"
    if normalized.endswith("rvc"):
        return "rvc"
    if normalized.endswith("kenburns"):
        return "kenburns"
    return None


def _to_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0

from __future__ import annotations

import json
import math
from pathlib import Path
from time import time
from typing import Literal, cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.latest_run import load_joined_latest_run


JsonState = Literal["ok", "missing", "invalid"]


def load_latest_result_metadata(
    result_file: str | Path | None = None,
) -> dict[str, object]:
    path = (
        RuntimeConfig().result_router_file if result_file is None else Path(result_file)
    )
    raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw_payload, dict):
        return {"code": "UNKNOWN"}
    typed_payload = cast(dict[object, object], raw_payload)
    metadata = typed_payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return {"code": str(typed_payload.get("code", "UNKNOWN"))}
    typed_metadata = {
        str(raw_key): raw_value
        for raw_key, raw_value in cast(dict[object, object], metadata).items()
    }
    if "code" not in typed_metadata:
        typed_metadata["code"] = str(typed_payload.get("code", "UNKNOWN"))
    return typed_metadata


def load_runtime_readiness(
    config: RuntimeConfig | None = None, *, completed: bool = True
) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
    pointer_file = (
        runtime_config.latest_completed_run_file
        if completed
        else runtime_config.latest_active_run_file
    )
    latest_join = load_joined_latest_run(runtime_config, completed=completed)
    result_metadata = latest_join.get("result_metadata")
    typed_result_metadata = _dict_from_object(result_metadata, default_code="UNKNOWN")
    snapshot_run_id, snapshot_run_id_source = resolve_snapshot_run_id(
        latest_join, typed_result_metadata
    )
    gpt_status, gpt_status_state = _read_json_dict_with_state(
        runtime_config.gpt_status_file
    )
    browser_health, browser_health_state = _read_json_dict_with_state(
        runtime_config.browser_health_file
    )
    browser_registry, browser_registry_state = _read_json_dict_with_state(
        runtime_config.browser_registry_file
    )
    _, pointer_state = _read_json_dict_with_state(pointer_file)

    blockers: list[dict[str, object]] = []
    stale_sec = max(1, int(runtime_config.running_stale_sec))
    now = round(time(), 3)

    if gpt_status_state == "missing":
        blockers.append(
            {
                "axis": "gpt_floor",
                "code": "GPT_STATUS_MISSING",
                "reason": "gpt_status_missing",
                "trace_path": str(runtime_config.gpt_status_file),
            }
        )
    elif gpt_status_state == "invalid":
        blockers.append(
            {
                "axis": "gpt_floor",
                "code": "GPT_STATUS_INVALID",
                "reason": "gpt_status_invalid",
                "trace_path": str(runtime_config.gpt_status_file),
            }
        )
    else:
        if gpt_status is None:
            blockers.append(
                {
                    "axis": "gpt_floor",
                    "code": "GPT_STATUS_INVALID",
                    "reason": "gpt_status_unreadable",
                    "trace_path": str(runtime_config.gpt_status_file),
                }
            )
            gpt_status = {}
        gpt_checked_at = _to_float(gpt_status.get("checked_at"))
        gpt_status_is_stale = True
        if gpt_checked_at is not None:
            gpt_status_is_stale = now - gpt_checked_at > stale_sec
        if gpt_checked_at is None or gpt_status_is_stale:
            blockers.append(
                {
                    "axis": "gpt_floor",
                    "code": "GPT_STATUS_STALE",
                    "reason": "gpt_status_stale",
                    "checked_at": gpt_checked_at,
                    "stale_sec": stale_sec,
                    "trace_path": str(runtime_config.gpt_status_file),
                }
            )
        ok_count = _to_int(gpt_status.get("ok_count", 0))
        min_ok = max(1, _to_int(gpt_status.get("min_ok", 1), default=1))
        if ok_count < min_ok:
            blockers.append(
                {
                    "axis": "gpt_floor",
                    "code": "GPT_FLOOR_FAIL",
                    "reason": "ok_count_below_min",
                    "ok_count": ok_count,
                    "min_ok": min_ok,
                    "trace_path": str(runtime_config.gpt_status_file),
                }
            )

    if pointer_state == "missing":
        blockers.append(
            {
                "axis": "latest_run",
                "code": "LATEST_RUN_POINTER_MISSING",
                "reason": "latest_pointer_missing",
                "trace_path": str(pointer_file),
            }
        )
    elif pointer_state == "invalid":
        blockers.append(
            {
                "axis": "latest_run",
                "code": "LATEST_RUN_POINTER_INVALID",
                "reason": "latest_pointer_invalid",
                "trace_path": str(pointer_file),
            }
        )
    else:
        pointer_payload = _dict_from_object(latest_join.get("pointer"))
        if not str(pointer_payload.get("run_id", "")).strip():
            blockers.append(
                {
                    "axis": "latest_run",
                    "code": "LATEST_RUN_POINTER_INVALID",
                    "reason": "latest_pointer_run_id_missing",
                    "trace_path": str(pointer_file),
                }
            )

    if bool(latest_join.get("out_of_sync", False)):
        reasons_obj = latest_join.get("reasons", [])
        reasons = _string_list(reasons_obj)
        pointer_run_id = str(
            _dict_from_object(latest_join.get("pointer")).get("run_id", "")
        )
        gui_run_id = str(
            _dict_from_object(latest_join.get("gui_status")).get("run_id", "")
        )
        result_run_id = str(typed_result_metadata.get("run_id", ""))
        blockers.append(
            {
                "axis": "latest_run",
                "code": "LATEST_RUN_DRIFT",
                "reason": "run_id_mismatch",
                "details": [str(reason) for reason in reasons],
                "snapshot_run_id": snapshot_run_id,
                "snapshot_run_id_source": snapshot_run_id_source,
                "expected_run_id": pointer_run_id,
                "gui_run_id": gui_run_id,
                "result_run_id": result_run_id,
                "trace_path": str(pointer_file),
                "related_paths": {
                    "pointer": str(pointer_file),
                    "gui_status": str(runtime_config.gui_status_file),
                    "result": str(runtime_config.result_router_file),
                },
            }
        )

    if browser_health_state == "missing":
        blockers.append(
            {
                "axis": "browser_health",
                "code": "BROWSER_HEALTH_MISSING",
                "reason": "browser_health_missing",
                "trace_path": str(runtime_config.browser_health_file),
            }
        )
    elif browser_health_state == "invalid":
        blockers.append(
            {
                "axis": "browser_health",
                "code": "BROWSER_HEALTH_INVALID",
                "reason": "browser_health_invalid",
                "trace_path": str(runtime_config.browser_health_file),
            }
        )
    else:
        if browser_health is None:
            blockers.append(
                {
                    "axis": "browser_health",
                    "code": "BROWSER_HEALTH_INVALID",
                    "reason": "browser_health_unreadable",
                    "trace_path": str(runtime_config.browser_health_file),
                }
            )
            browser_health = {}
        unhealthy_count = _to_int(browser_health.get("unhealthy_count", 0))
        if unhealthy_count > 0:
            blockers.append(
                {
                    "axis": "browser_health",
                    "code": "BROWSER_UNHEALTHY",
                    "reason": "unhealthy_sessions_present",
                    "unhealthy_count": unhealthy_count,
                    "trace_path": str(runtime_config.browser_health_file),
                }
            )

    if browser_registry_state == "missing":
        blockers.append(
            {
                "axis": "browser_registry",
                "code": "BROWSER_REGISTRY_MISSING",
                "reason": "browser_registry_missing",
                "trace_path": str(runtime_config.browser_registry_file),
            }
        )
    elif browser_registry_state == "invalid":
        blockers.append(
            {
                "axis": "browser_registry",
                "code": "BROWSER_REGISTRY_INVALID",
                "reason": "browser_registry_invalid",
                "trace_path": str(runtime_config.browser_registry_file),
            }
        )

    if browser_health is not None and browser_registry is not None:
        health_run_id = str(browser_health.get("run_id", ""))
        registry_run_id = str(browser_registry.get("run_id", ""))
        if health_run_id and registry_run_id and health_run_id != registry_run_id:
            blockers.append(
                {
                    "axis": "browser_registry",
                    "code": "BROWSER_REGISTRY_DRIFT",
                    "reason": "run_id_mismatch",
                    "health_run_id": health_run_id,
                    "registry_run_id": registry_run_id,
                    "trace_path": str(runtime_config.browser_registry_file),
                }
            )

    latest_code = str(typed_result_metadata.get("code", "UNKNOWN"))
    latest_result_payload = _dict_from_object(latest_join.get("result"))
    latest_result_checked_at = _to_float(latest_result_payload.get("checked_at"))
    latest_result_is_fresh = True
    canonical_handoff = _dict_from_object(
        typed_result_metadata.get("canonical_handoff")
    )
    mismatch_warning = str(
        canonical_handoff.get("warning_worker_error_code_mismatch", "")
    ).strip()
    if latest_result_checked_at is not None:
        latest_result_is_fresh = now - latest_result_checked_at <= stale_sec
    if latest_result_is_fresh and latest_code in {
        "BROWSER_BLOCKED",
        "BROWSER_RESTART_EXHAUSTED",
        "BROWSER_UNHEALTHY",
        "GPT_FLOOR_FAIL",
    }:
        blocker: dict[str, object] = {
            "axis": "latest_result",
            "code": latest_code,
            "reason": "latest_result_blocker",
            "trace_path": str(runtime_config.result_router_file),
        }
        if mismatch_warning:
            blocker["details"] = {"warning_worker_error_code_mismatch": True}
        blockers.append(blocker)

    primary_code = "OK" if not blockers else str(blockers[0].get("code", "CLI_USAGE"))
    return {
        "ready": len(blockers) == 0,
        "code": primary_code,
        "snapshot_run_id": snapshot_run_id,
        "snapshot_run_id_source": snapshot_run_id_source,
        "blockers": blockers,
        "latest": latest_join,
        "result_metadata": typed_result_metadata,
        "gpt_status": gpt_status,
        "browser_health": browser_health,
        "browser_registry": browser_registry,
        "trace_paths": {
            "gpt_status": str(runtime_config.gpt_status_file),
            "browser_health": str(runtime_config.browser_health_file),
            "browser_registry": str(runtime_config.browser_registry_file),
            "result": str(runtime_config.result_router_file),
            "gui_status": str(runtime_config.gui_status_file),
            "control_plane_events": str(runtime_config.control_plane_events_file),
            "latest_pointer": str(
                runtime_config.latest_completed_run_file
                if completed
                else runtime_config.latest_active_run_file
            ),
        },
    }


def resolve_snapshot_run_id(
    latest_join: dict[str, object], result_metadata: dict[str, object]
) -> tuple[str, str]:
    canonical_handoff = _dict_from_object(result_metadata.get("canonical_handoff"))
    evidence_run_id = str(result_metadata.get("run_id", "")).strip()
    handoff_run_id = str(canonical_handoff.get("run_id", "")).strip()
    pointer_run_id = str(
        _dict_from_object(latest_join.get("pointer")).get("run_id", "")
    ).strip()
    gui_run_id = str(
        _dict_from_object(latest_join.get("gui_status")).get("run_id", "")
    ).strip()
    for source, value in (
        ("result_metadata.run_id", evidence_run_id),
        ("canonical_handoff.run_id", handoff_run_id),
        ("latest.pointer.run_id", pointer_run_id),
        ("latest.gui_status.run_id", gui_run_id),
    ):
        if value:
            return value, source
    return "", ""


def _read_json_dict_with_state(
    path_like: str | Path,
) -> tuple[dict[str, object] | None, JsonState]:
    path = Path(path_like)
    if not path.exists():
        return None, "missing"
    try:
        raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None, "invalid"
    if not isinstance(raw_payload, dict):
        return None, "invalid"
    return (
        {
            str(raw_key): raw_value
            for raw_key, raw_value in cast(dict[object, object], raw_payload).items()
        },
        "ok",
    )


def _dict_from_object(
    value: object, *, default_code: str | None = None
) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"code": default_code} if default_code is not None else {}
    typed_value = cast(dict[object, object], value)
    result = {str(raw_key): raw_value for raw_key, raw_value in typed_value.items()}
    if default_code is not None and "code" not in result:
        result["code"] = default_code
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    typed_items = cast(list[object], value)
    return [str(item) for item in typed_items]


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


def _to_float(value: object) -> float | None:
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
        except OverflowError:
            return None
        return numeric if math.isfinite(numeric) else None
    return None

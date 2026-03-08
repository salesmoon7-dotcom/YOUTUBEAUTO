from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.config import RuntimeConfig


def build_latest_run_pointer(
    *,
    run_id: str,
    mode: str,
    status: str,
    code: str,
    debug_log: str,
    result_path: str,
    gui_status_path: str,
    events_path: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "runtime": "runtime_v2",
        "checked_at": round(time(), 3),
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "code": code,
        "debug_log": debug_log,
        "result_path": result_path,
        "gui_status_path": gui_status_path,
        "events_path": events_path,
    }


def write_latest_run_pointer(payload: dict[str, object], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_file.parent,
        prefix=f"{output_file.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(output_file)
    return output_file


def update_latest_run_pointers(
    config: RuntimeConfig,
    *,
    run_id: str,
    mode: str,
    status: str,
    code: str,
    debug_log: str,
    write_completed: bool,
) -> None:
    pointer = build_latest_run_pointer(
        run_id=run_id,
        mode=mode,
        status=status,
        code=code,
        debug_log=debug_log,
        result_path=str(config.result_router_file),
        gui_status_path=str(config.gui_status_file),
        events_path=str(config.control_plane_events_file),
    )
    _ = write_latest_run_pointer(pointer, config.latest_active_run_file)
    if write_completed:
        _ = write_latest_run_pointer(pointer, config.latest_completed_run_file)


def load_joined_latest_run(
    config: RuntimeConfig, *, completed: bool = False
) -> dict[str, object]:
    pointer_file = (
        config.latest_completed_run_file if completed else config.latest_active_run_file
    )
    pointer = _read_json(pointer_file)
    gui_payload = _read_json(
        _path_from_pointer(pointer, "gui_status_path", config.gui_status_file)
    )
    result_payload = _read_json(
        _path_from_pointer(pointer, "result_path", config.result_router_file)
    )
    result_metadata = None
    if result_payload is not None:
        raw_metadata = result_payload.get("metadata")
        if isinstance(raw_metadata, dict):
            typed_metadata = cast(dict[object, object], raw_metadata)
            result_metadata = {
                str(raw_key): raw_value for raw_key, raw_value in typed_metadata.items()
            }

    out_of_sync_reasons: list[str] = []
    expected_run_id = "" if pointer is None else str(pointer.get("run_id", ""))
    if pointer is not None and not expected_run_id:
        out_of_sync_reasons.append("pointer_run_id_missing")
    if expected_run_id:
        if gui_payload is None or str(gui_payload.get("run_id", "")) != expected_run_id:
            out_of_sync_reasons.append("gui_run_id_mismatch")
        if (
            result_metadata is None
            or str(result_metadata.get("run_id", "")) != expected_run_id
        ):
            out_of_sync_reasons.append("result_run_id_mismatch")

    return {
        "pointer": pointer,
        "gui_status": gui_payload,
        "result": result_payload,
        "result_metadata": result_metadata,
        "out_of_sync": len(out_of_sync_reasons) > 0,
        "reasons": out_of_sync_reasons,
    }


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    typed_payload = cast(dict[object, object], raw_payload)
    return {str(raw_key): raw_value for raw_key, raw_value in typed_payload.items()}


def _path_from_pointer(
    pointer: dict[str, object] | None, field_name: str, fallback: Path
) -> Path:
    if pointer is None:
        return fallback
    raw_value = str(pointer.get(field_name, "")).strip()
    if not raw_value:
        return fallback
    return Path(raw_value)

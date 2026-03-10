from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.gui_adapter import write_gui_status
from runtime_v2.result_router import write_result_router


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


def write_runtime_snapshot(
    config: RuntimeConfig,
    *,
    run_id: str,
    mode: str,
    status: str,
    code: str,
    debug_log: str,
    gui_payload: dict[str, object],
    artifacts: list[Path],
    metadata: dict[str, object],
    write_completed: bool,
    artifact_root: Path | None = None,
    update_pointers: bool = True,
) -> None:
    normalized_metadata = normalize_runtime_snapshot_metadata(
        metadata,
        run_id=run_id,
        mode=mode,
        status=status,
        code=code,
        debug_log=debug_log,
    )
    _ = write_gui_status(gui_payload, config.gui_status_file)
    _ = write_result_router(
        artifacts,
        config.artifact_root if artifact_root is None else artifact_root,
        config.result_router_file,
        metadata=normalized_metadata,
    )
    if update_pointers:
        update_latest_run_pointers(
            config,
            run_id=run_id,
            mode=mode,
            status=status,
            code=code,
            debug_log=debug_log,
            write_completed=write_completed,
        )


def build_canonical_handoff_payload(
    *,
    run_id: str,
    mode: str,
    status: str,
    code: str,
    debug_log: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "runtime": "runtime_v2",
        "owner_layer": "control_plane" if mode == "control_loop" else mode,
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "code": code,
        "debug_log": debug_log,
        "job_id": str(metadata.get("job_id", "")),
        "workload": str(metadata.get("workload", "")),
        "worker_error_code": str(metadata.get("worker_error_code", "")),
        "completion_state": str(metadata.get("completion_state", "")),
        "final_output": bool(metadata.get("final_output", False)),
        "chain_depth": _to_int(metadata.get("chain_depth", 0)),
        "next_jobs_count": _to_int(metadata.get("next_jobs_count", 0)),
        "guardrails": {
            "single_writer": True,
            "single_failure_contract": True,
            "worker_policy_free": True,
            "single_reference_adapter": True,
        },
        "legacy_contracts_ref": "docs/plans/2026-03-09-legacy-post-gpt-service-contract-survey.md",
        "guardrail_plan_ref": "docs/plans/2026-03-09-runtime-v2-guardrail-drift-remediation-plan.md",
    }


def normalize_runtime_snapshot_metadata(
    metadata: dict[str, object],
    *,
    run_id: str,
    mode: str,
    status: str,
    code: str,
    debug_log: str,
) -> dict[str, object]:
    normalized = dict(metadata)
    handoff = normalized.get("canonical_handoff")
    if not isinstance(handoff, dict):
        normalized["canonical_handoff"] = build_canonical_handoff_payload(
            run_id=run_id,
            mode=mode,
            status=status,
            code=code,
            debug_log=debug_log,
            metadata=normalized,
        )
    return normalized


def ensure_bootstrap_runtime_snapshot(
    config: RuntimeConfig,
    *,
    run_id: str,
    mode: str,
    debug_log: str,
    gui_payload: dict[str, object],
) -> None:
    write_completed = _read_json(config.latest_completed_run_file) is None
    if (
        _read_json(config.result_router_file) is None
        or _read_json(config.gui_status_file) is None
    ):
        write_runtime_snapshot(
            config,
            run_id=run_id,
            mode=mode,
            status="idle",
            code="BOOTSTRAPPED",
            debug_log=debug_log,
            gui_payload=gui_payload,
            artifacts=[],
            metadata={
                "run_id": run_id,
                "mode": mode,
                "status": "idle",
                "code": "BOOTSTRAPPED",
                "exit_code": 0,
                "debug_log": debug_log,
            },
            write_completed=write_completed,
        )
        return
    if _read_json(config.latest_active_run_file) is None:
        update_latest_run_pointers(
            config,
            run_id=run_id,
            mode=mode,
            status="idle",
            code="BOOTSTRAPPED",
            debug_log=debug_log,
            write_completed=write_completed,
        )
        return
    if write_completed:
        update_latest_run_pointers(
            config,
            run_id=run_id,
            mode=mode,
            status="idle",
            code="BOOTSTRAPPED",
            debug_log=debug_log,
            write_completed=True,
        )


def write_control_plane_runtime_snapshot(
    config: RuntimeConfig,
    *,
    run_id: str,
    status: str,
    code: str,
    debug_log: str,
    gui_payload: dict[str, object],
    artifacts: list[Path],
    metadata: dict[str, object],
) -> None:
    write_runtime_snapshot(
        config,
        run_id=run_id,
        mode="control_loop",
        status=status,
        code=code,
        debug_log=debug_log,
        gui_payload=gui_payload,
        artifacts=artifacts,
        metadata=metadata,
        write_completed=True,
    )


def write_cli_runtime_snapshot(
    config: RuntimeConfig,
    *,
    run_id: str,
    mode: str,
    status: str,
    code: str,
    debug_log: str,
    gui_payload: dict[str, object],
    metadata: dict[str, object],
    artifacts: list[Path] | None = None,
) -> None:
    normalized_metadata = normalize_runtime_snapshot_metadata(
        metadata,
        run_id=run_id,
        mode=mode,
        status=status,
        code=code,
        debug_log=debug_log,
    )
    cli_gui_path, cli_result_path = _cli_snapshot_paths(debug_log, run_id=run_id)
    _ = write_gui_status(gui_payload, cli_gui_path)
    _ = write_result_router(
        [] if artifacts is None else artifacts,
        config.artifact_root,
        cli_result_path,
        metadata=normalized_metadata,
    )


def write_excel_sync_runtime_snapshot(
    config: RuntimeConfig,
    *,
    run_id: str,
    status: str,
    code: str,
    debug_log: str,
    gui_payload: dict[str, object],
    artifacts: list[Path],
    metadata: dict[str, object],
    artifact_root: Path,
) -> None:
    write_runtime_snapshot(
        config,
        run_id=run_id,
        mode="excel_sync",
        status=status,
        code=code,
        debug_log=debug_log,
        gui_payload=gui_payload,
        artifacts=artifacts,
        metadata=metadata,
        write_completed=True,
        artifact_root=artifact_root,
        update_pointers=False,
    )


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


def _cli_snapshot_paths(debug_log: str, *, run_id: str) -> tuple[Path, Path]:
    debug_path = Path(debug_log).resolve()
    output_root = debug_path.parent / "cli_snapshots"
    safe_run_id = run_id.strip() or "cli-run"
    return (
        output_root / f"{safe_run_id}.gui_status.json",
        output_root / f"{safe_run_id}.result.json",
    )


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


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default

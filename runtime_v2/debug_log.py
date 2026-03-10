from __future__ import annotations

import json
import traceback
from collections.abc import Mapping
from pathlib import Path
from time import time
from typing import cast


def now_ts() -> float:
    return round(time(), 3)


def append_debug_event(
    log_file: Path,
    *,
    event: str,
    payload: Mapping[str, object] | None = None,
    level: str = "INFO",
) -> Path:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    row: dict[str, object] = {
        "ts": now_ts(),
        "level": level,
        "event": event,
    }
    if payload is not None:
        row.update({str(key): value for key, value in payload.items()})
    with log_file.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    return log_file


def debug_log_path(log_root: Path, run_id: str) -> Path:
    safe_run_id = run_id.strip() or "runtime_v2"
    return log_root / f"{safe_run_id}.jsonl"


def exception_payload(exc: BaseException) -> dict[str, object]:
    return {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "traceback": traceback.format_exc(),
    }


def summarize_runtime_result(result: Mapping[str, object]) -> dict[str, object]:
    """Build a debug-oriented summary for runtime results.

    Consumer contract:
    - `error_code` remains for legacy compatibility in debug summaries.
    - `raw_error_code` is a raw worker-level diagnostic value and is not a stable
      routing key for downstream policy decisions.
    - The canonical worker error code lives in runtime result metadata/canonical
      handoff fields, not in this debug summary.
    """
    resolved = _resolved_result(result)
    worker_result = _mapping(result.get("worker_result"))
    job = _mapping(result.get("job"))
    recovery = _mapping(result.get("recovery"))
    payload: dict[str, object] = {
        "status": str(result.get("status", resolved.get("status", "unknown"))),
        "code": str(result.get("code", resolved.get("code", ""))),
    }
    if job is not None:
        payload["job_id"] = str(job.get("job_id", ""))
        payload["workload"] = str(job.get("workload", ""))
        payload["queue_status"] = str(job.get("status", ""))
    if worker_result is not None:
        payload["worker_status"] = str(worker_result.get("status", ""))
        payload["stage"] = str(worker_result.get("stage", ""))
        raw_error_code = str(worker_result.get("error_code", ""))
        payload["error_code"] = raw_error_code
        payload["raw_error_code"] = raw_error_code  # raw diagnostic only
        payload["error_code_source"] = "worker_result.error_code"
        payload["manifest_path"] = str(worker_result.get("manifest_path", ""))
        payload["result_path"] = str(worker_result.get("result_path", ""))
        completion = _mapping(worker_result.get("completion"))
        if completion is not None:
            payload["completion_state"] = str(completion.get("state", ""))
            payload["final_output"] = bool(completion.get("final_output", False))
            payload["final_artifact"] = str(completion.get("final_artifact", ""))
            payload["final_artifact_path"] = str(
                completion.get("final_artifact_path", "")
            )
    else:
        payload["stage"] = str(resolved.get("stage", result.get("stage", "")))
        raw_error_code = str(
            resolved.get("error_code", result.get("error_code", result.get("code", "")))
        )
        payload["error_code"] = raw_error_code
        payload["raw_error_code"] = raw_error_code  # raw diagnostic only
        payload["error_code_source"] = "resolved_result.error_code"
    if recovery is not None:
        payload["backoff_sec"] = recovery.get("backoff_sec", 0)
        payload["recovery_action"] = str(recovery.get("action", ""))
    return payload


def summarize_cli_report(
    report: Mapping[str, object], debug_log: Path
) -> dict[str, object]:
    result = _mapping(report.get("result"))
    payload: dict[str, object] = {
        "run_id": str(report.get("run_id", "unknown")),
        "event": str(report.get("event", "run_finished")),
        "ts": report.get("ts", now_ts()),
        "mode": str(report.get("mode", "")),
        "status": str(report.get("status", "unknown")),
        "code": str(report.get("code", "")),
        "exit_code": report.get("exit_code", 1),
        "debug_log": str(debug_log),
    }
    if result is not None:
        payload.update(summarize_runtime_result(result))
    return payload


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw = cast(dict[object, object], value)
    return {str(key): raw[key] for key in raw}


def _resolved_result(result: Mapping[str, object]) -> dict[str, object]:
    inner = _mapping(result.get("result"))
    if inner is not None:
        return inner
    return {str(key): value for key, value in result.items()}

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time

from runtime_v2.error_codes import select_worker_error_code


def build_gui_status_payload(
    status: dict[str, object],
    run_id: str,
    mode: str,
    stage: str,
    exit_code: int,
) -> dict[str, object]:
    """Local GUI payload contract for on-machine dashboard."""
    summary_status = str(status.get("status", ""))
    summary_code = str(status.get("code", ""))
    job_id = str(status.get("job_id", ""))
    workload = str(status.get("workload", ""))
    queue_status = str(status.get("queue_status", ""))
    worker_stage = str(status.get("worker_stage", status.get("stage", "")))
    worker_error_code = select_worker_error_code(
        {
            "worker_error_code": status.get("worker_error_code", ""),
            "error_code": status.get("error_code", ""),
        }
    )
    result_path = str(status.get("result_path", ""))
    manifest_path = str(status.get("manifest_path", ""))
    debug_log = str(status.get("debug_log", ""))
    completion_state = str(status.get("completion_state", ""))
    final_output = bool(status.get("final_output", False))
    final_artifact = str(status.get("final_artifact", ""))
    final_artifact_path = str(status.get("final_artifact_path", ""))
    return {
        "schema_version": "1.0",
        "execution_env": "local_gui",
        "runtime": "runtime_v2",
        "checked_at": round(time(), 3),
        "run_id": run_id,
        "mode": mode,
        "stage": stage,
        "exit_code": exit_code,
        "status_text": summary_status,
        "status_code": summary_code,
        "job_id": job_id,
        "workload": workload,
        "queue_status": queue_status,
        "worker_stage": worker_stage,
        "worker_error_code": worker_error_code,
        "result_path": result_path,
        "manifest_path": manifest_path,
        "debug_log": debug_log,
        "completion_state": completion_state,
        "final_output": final_output,
        "final_artifact": final_artifact,
        "final_artifact_path": final_artifact_path,
        "status": status,
    }


def write_gui_status(payload: dict[str, object], output_file: str | Path) -> Path:
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

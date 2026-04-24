from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.n8n_adapter import post_callback
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace


def run_n8n_upload_job(job: JobContract, *, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    callback_url = str(job.payload.get("callback_url", "")).strip()
    artifact_path = str(job.payload.get("artifact_path", "")).strip()
    if not callback_url:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_callback_url",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    if not artifact_path:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_artifact_path",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "execution_env": "remote_n8n",
        "callback_url": callback_url,
        "run_id": str(job.payload.get("run_id", "")),
        "row_ref": str(job.payload.get("row_ref", "")),
        "mode": str(job.payload.get("mode", "closeout")),
        "artifact_path": artifact_path,
        "job_id": job.job_id,
        "workload": job.workload,
    }
    callback_result = post_callback(payload)
    if not bool(callback_result.get("ok")):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="callback",
            artifacts=[],
            error_code="callback_fail",
            retryable=bool(callback_result.get("retryable")),
            details={"callback": callback_result, "artifact_path": artifact_path},
            completion={"state": "failed", "final_output": False},
        )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="n8n_upload",
        artifacts=[],
        details={"callback": callback_result, "artifact_path": artifact_path},
        completion={"state": "succeeded", "final_output": True},
    )

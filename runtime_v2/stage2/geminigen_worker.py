from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.request_builders import build_geminigen_prompt_file
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def run_geminigen_job(
    job: JobContract, artifact_root: Path, registry_file: Path | None = None
) -> dict[str, object]:
    _ = registry_file
    workspace = prepare_workspace(job, artifact_root)
    prompt = str(job.payload.get("prompt", "")).strip()
    if not prompt:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_prompt",
            retryable=False,
            completion={"state": "blocked", "final_output": False},
        )
    request_path = write_native_request(workspace, job.payload)
    prompt_path = build_geminigen_prompt_file(workspace, job.payload)
    return native_not_implemented_result(
        workspace,
        workload="geminigen",
        stage="geminigen",
        artifacts=[request_path, prompt_path],
        details={
            "provider": str(job.payload.get("provider", "google")),
            "model": str(job.payload.get("model", "veo3")),
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )

from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.request_builders import build_image_prompt_file
from runtime_v2.workers.job_runtime import prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def run_seaart_job(
    job: JobContract, artifact_root: Path, registry_file: Path | None = None
) -> dict[str, object]:
    _ = registry_file
    workspace = prepare_workspace(job, artifact_root)
    prompt = str(job.payload.get("prompt", "")).strip()
    if not prompt:
        from runtime_v2.workers.job_runtime import finalize_worker_result

        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_prompt",
            retryable=False,
        )
    request_path = write_native_request(workspace, job.payload)
    prompt_path = build_image_prompt_file(workspace, job.payload, workload="seaart")
    return native_not_implemented_result(
        workspace,
        workload="seaart",
        stage="seaart",
        artifacts=[request_path, prompt_path],
        details={
            "model": str(job.payload.get("model", "FLUX")),
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )

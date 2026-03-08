from __future__ import annotations

from pathlib import Path
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.request_builders import build_image_prompt_file
from runtime_v2.worker_registry import update_worker_state
from runtime_v2.workers.job_runtime import prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def run_seaart_job(
    job: JobContract, artifact_root: Path, registry_file: Path | None = None
) -> dict[str, object]:
    if registry_file is not None:
        _ = update_worker_state(
            registry_file,
            workload="seaart",
            state="busy",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
    workspace = prepare_workspace(job, artifact_root)
    request_path = write_native_request(workspace, job.payload)
    prompt_path = build_image_prompt_file(workspace, job.payload, workload="seaart")
    result = native_not_implemented_result(
        workspace,
        workload="seaart",
        stage="seaart",
        artifacts=[request_path, prompt_path],
        details={
            "model": str(job.payload.get("model", "FLUX")),
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )
    if registry_file is not None:
        _ = update_worker_state(
            registry_file,
            workload="seaart",
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
    return result

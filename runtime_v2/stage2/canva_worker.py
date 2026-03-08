from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.request_builders import (
    build_canva_thumb_file,
    channel_from_payload,
    row_index_from_payload,
)
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def run_canva_job(
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
    thumb_data_path = build_canva_thumb_file(workspace, job.payload)
    ref_img = str(job.payload.get("ref_img", "")).strip()
    return native_not_implemented_result(
        workspace,
        workload="canva",
        stage="canva",
        artifacts=[request_path, thumb_data_path],
        details={
            "channel": channel_from_payload(job.payload),
            "row_index": row_index_from_payload(job.payload),
            "save_path": str((workspace / "thumbnail.png").resolve()),
            "ref_img": ref_img,
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )

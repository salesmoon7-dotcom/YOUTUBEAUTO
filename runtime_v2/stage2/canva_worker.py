from __future__ import annotations

from pathlib import Path
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.request_builders import (
    build_canva_thumb_file,
    channel_from_payload,
    row_index_from_payload,
)
from runtime_v2.worker_registry import update_worker_state
from runtime_v2.workers.job_runtime import prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def run_canva_job(
    job: JobContract, artifact_root: Path, registry_file: Path | None = None
) -> dict[str, object]:
    if registry_file is not None:
        _ = update_worker_state(
            registry_file,
            workload="canva",
            state="busy",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
    workspace = prepare_workspace(job, artifact_root)
    request_path = write_native_request(workspace, job.payload)
    thumb_data_path = build_canva_thumb_file(workspace, job.payload)
    save_path = workspace / "thumbnail.png"
    ref_img = str(job.payload.get("ref_img", "")).strip()
    result = native_not_implemented_result(
        workspace,
        workload="canva",
        stage="canva",
        artifacts=[request_path, thumb_data_path],
        details={
            "channel": channel_from_payload(job.payload),
            "row_index": row_index_from_payload(job.payload),
            "save_path": str(save_path.resolve()),
            "ref_img": ref_img,
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )
    if registry_file is not None:
        _ = update_worker_state(
            registry_file,
            workload="canva",
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
    return result

from __future__ import annotations

import base64
from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.request_builders import build_image_prompt_file
from runtime_v2.worker_registry import update_worker_state
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace
from runtime_v2.workers.native_only import (
    write_native_request,
)


_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


def _service_artifact_path(payload: dict[str, object], workspace: Path) -> Path | None:
    raw_path = str(payload.get("service_artifact_path", "")).strip()
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate.resolve()


def _write_placeholder_png(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = output_path.write_bytes(_MINIMAL_PNG)
    return output_path


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
    try:
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
            )

        output_path = _service_artifact_path(job.payload, workspace)
        if output_path is None:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="validate_input",
                artifacts=[],
                error_code="missing_service_artifact_path",
                retryable=False,
            )

        request_path = write_native_request(workspace, job.payload)
        prompt_path = build_image_prompt_file(workspace, job.payload, workload="seaart")
        artifact_path = _write_placeholder_png(output_path)
        return finalize_worker_result(
            workspace,
            status="ok",
            stage="seaart",
            artifacts=[request_path, prompt_path, artifact_path],
            retryable=False,
            details={
                "model": str(job.payload.get("model", "FLUX")),
                "service_artifact_path": str(artifact_path.resolve()),
            },
            completion={
                "state": "succeeded",
                "final_output": True,
                "final_artifact": artifact_path.name,
                "final_artifact_path": str(artifact_path.resolve()),
            },
        )
    finally:
        if registry_file is not None:
            _ = update_worker_state(
                registry_file,
                workload="seaart",
                state="idle",
                run_id=str(job.payload.get("run_id", job.job_id)),
            )

from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.external_process import run_verified_adapter_command
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
    write_json_atomic,
)
from runtime_v2.workers.native_only import native_not_implemented_result


def run_rvc_job(
    job: JobContract | None = None, artifact_root: Path | None = None
) -> dict[str, object]:
    if job is None:
        return {"worker": "rvc", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    raw_source = job.payload.get("source_path", "")
    source = (
        resolve_local_input(str(raw_source))
        if isinstance(raw_source, str) and raw_source.strip()
        else None
    )
    if source is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_source_path",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    model_name = str(job.payload.get("model_name", "")).strip()
    if not model_name:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_model_name",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )

    project_root = workspace / "project"
    video_folder = project_root / "video"
    voice_folder = project_root / "voice"
    video_folder.mkdir(parents=True, exist_ok=True)
    voice_folder.mkdir(parents=True, exist_ok=True)
    source_copy = stage_local_input(voice_folder, source, target_name="#01.flac")
    request_file = write_json_atomic(
        workspace / "rvc_request.json",
        {
            "job_id": job.job_id,
            "source_path": str(source_copy.resolve()),
            "video_folder": str(video_folder.resolve()),
            "model_name": model_name,
        },
    )
    adapter_command_raw = job.payload.get("adapter_command")
    if isinstance(adapter_command_raw, list) and adapter_command_raw:
        adapter_command_items = cast(list[object], adapter_command_raw)
        adapter_command = [str(item) for item in adapter_command_items]
        adapter_result = run_verified_adapter_command(
            workspace,
            adapter_command=adapter_command,
            service_artifact_path=str(job.payload.get("service_artifact_path", "")),
            adapter_error_code="rvc_adapter_failed",
        )
        stdout_path = Path(str(adapter_result["stdout_path"]))
        stderr_path = Path(str(adapter_result["stderr_path"]))
        if not bool(adapter_result.get("ok", False)):
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="rvc_adapter",
                artifacts=[source_copy, request_file, stdout_path, stderr_path],
                error_code=str(adapter_result.get("error_code", "rvc_adapter_failed")),
                retryable=False,
                details={
                    **cast(dict[str, object], adapter_result.get("details", {})),
                    "model_name": model_name,
                },
                completion={"state": "failed", "final_output": False},
            )
        verified_output = Path(str(adapter_result["output_path"]))

        return finalize_worker_result(
            workspace,
            status="ok",
            stage="rvc",
            artifacts=[
                source_copy,
                request_file,
                stdout_path,
                stderr_path,
                verified_output,
            ],
            retryable=False,
            details={
                "model_name": model_name,
                "image_path": str(job.payload.get("image_path", "")).strip(),
                "duration_sec": job.payload.get("duration_sec", 8),
                "service_artifact_path": str(verified_output.resolve()),
                "adapter_mode": "command",
            },
            completion={
                "state": "succeeded",
                "final_output": True,
                "final_artifact": verified_output.name,
                "final_artifact_path": str(verified_output.resolve()),
            },
        )

    return native_not_implemented_result(
        workspace,
        workload="rvc",
        stage="rvc",
        artifacts=[source_copy, request_file],
        details={
            "model_name": model_name,
            "image_path": str(job.payload.get("image_path", "")).strip(),
            "duration_sec": job.payload.get("duration_sec", 8),
        },
    )

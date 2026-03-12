from __future__ import annotations

import os
import sys
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


REPO_ROOT = Path(__file__).resolve().parents[2]


def _canonical_adapter_env() -> dict[str, str]:
    repo_root = str(REPO_ROOT.resolve())
    current = os.environ.get("PYTHONPATH", "").strip()
    pythonpath = repo_root if not current else f"{repo_root}{os.pathsep}{current}"
    return {"PYTHONPATH": pythonpath}


def run_rvc_job(
    job: JobContract | None = None, artifact_root: Path | None = None
) -> dict[str, object]:
    if job is None:
        return {"worker": "rvc", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    raw_source = job.payload.get("source_path", "")
    raw_audio = job.payload.get("audio_path", "")
    source = (
        resolve_local_input(str(raw_source))
        if isinstance(raw_source, str) and str(raw_source).strip()
        else None
    )
    audio_source = (
        resolve_local_input(str(raw_audio))
        if isinstance(raw_audio, str) and str(raw_audio).strip()
        else None
    )
    source_mode = "gemi-video-source" if audio_source is not None else "tts-source"
    selected_source = audio_source if audio_source is not None else source
    if selected_source is None:
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
    source_suffix = selected_source.suffix.lower() or ".flac"
    source_copy = stage_local_input(
        voice_folder, selected_source, target_name=f"#01{source_suffix}"
    )
    request_file = write_json_atomic(
        workspace / "rvc_request.json",
        {
            "job_id": job.job_id,
            "source_path": str(source_copy.resolve()),
            "audio_path": "" if audio_source is None else str(source_copy.resolve()),
            "video_folder": str(video_folder.resolve()),
            "model_name": model_name,
            "source_mode": source_mode,
        },
    )
    adapter_command_raw = job.payload.get("adapter_command")
    adapter_extra_env: dict[str, str] | None = None
    if (not isinstance(adapter_command_raw, list) or not adapter_command_raw) and str(
        job.payload.get("service_artifact_path", "")
    ).strip():
        adapter_command_raw = [
            sys.executable,
            "-m",
            "runtime_v2.cli",
            "--rvc-adapter-child",
            "--service-artifact-path",
            str(job.payload.get("service_artifact_path", "")),
        ]
        adapter_extra_env = _canonical_adapter_env()
    if isinstance(adapter_command_raw, list) and adapter_command_raw:
        adapter_command_items = cast(list[object], adapter_command_raw)
        adapter_command = [str(item) for item in adapter_command_items]
        adapter_result = run_verified_adapter_command(
            workspace,
            approved_root=artifact_root or workspace.parent.parent,
            adapter_command=adapter_command,
            service_artifact_path=str(job.payload.get("service_artifact_path", "")),
            adapter_error_code="rvc_adapter_failed",
            extra_env=adapter_extra_env,
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
                    "source_mode": source_mode,
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
                "audio_path": str(job.payload.get("audio_path", "")).strip(),
                "duration_sec": job.payload.get("duration_sec", 8),
                "source_mode": source_mode,
                "service_artifact_path": str(verified_output.resolve()),
                "reused": bool(adapter_result.get("reused", False)),
                "adapter_mode": "command",
            },
            completion={
                "state": "succeeded",
                "final_output": True,
                "final_artifact": verified_output.name,
                "final_artifact_path": str(verified_output.resolve()),
                "reused": bool(adapter_result.get("reused", False)),
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
            "audio_path": str(job.payload.get("audio_path", "")).strip(),
            "duration_sec": job.payload.get("duration_sec", 8),
            "source_mode": source_mode,
        },
    )

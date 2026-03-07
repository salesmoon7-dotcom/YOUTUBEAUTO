from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace, resolve_local_input, stage_local_input


def run_kenburns_job(job: JobContract | None = None, artifact_root: Path | None = None) -> dict[str, object]:
    if job is None:
        return {"worker": "kenburns", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    raw_source = job.payload.get("source_path", "")
    source = resolve_local_input(str(raw_source)) if isinstance(raw_source, str) and raw_source.strip() else None
    if source is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_source_path",
            retryable=False,
        )
    duration_value = job.payload.get("duration_sec", 8)
    duration_sec = int(duration_value) if isinstance(duration_value, (int, float, str)) else 8
    duration_sec = max(1, duration_sec)
    staged_input = stage_local_input(workspace, source, target_name=f"source{source.suffix.lower()}")
    silent_output_path = workspace / "kenburns_silent.mp4"
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(staged_input),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-t",
        str(duration_sec),
        "-r",
        "30",
        str(silent_output_path),
    ]
    process_result = run_external_process(command, cwd=workspace)
    exit_code = process_result.get("exit_code", 1)
    exit_code_int = int(exit_code) if isinstance(exit_code, (int, float, str)) else 1
    if exit_code_int != 0 or not silent_output_path.exists():
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render_video",
            artifacts=[staged_input] if staged_input.exists() else [],
            error_code="ffmpeg_failed",
            retryable=True,
            details={
                "stdout": process_result.get("stdout", ""),
                "stderr": process_result.get("stderr", ""),
            },
            completion={
                "state": "failed",
                "final_output": False,
            },
        )
    output_path = silent_output_path
    raw_audio_path = job.payload.get("audio_path", "")
    if isinstance(raw_audio_path, str) and raw_audio_path.strip():
        audio_source = resolve_local_input(raw_audio_path)
        if audio_source is not None:
            staged_audio = stage_local_input(workspace, audio_source, target_name=f"audio{audio_source.suffix.lower()}")
            muxed_output_path = workspace / "kenburns.mp4"
            mux_result = run_external_process(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(silent_output_path),
                    "-i",
                    str(staged_audio),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(muxed_output_path),
                ],
                cwd=workspace,
            )
            mux_exit_code = mux_result.get("exit_code", 1)
            mux_exit_int = int(mux_exit_code) if isinstance(mux_exit_code, (int, float, str)) else 1
            if mux_exit_int == 0 and muxed_output_path.exists():
                output_path = muxed_output_path
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="render_video",
        artifacts=[path for path in (staged_input, silent_output_path, output_path) if path.exists()],
        retryable=False,
        details={
            "stdout": process_result.get("stdout", ""),
            "stderr": process_result.get("stderr", ""),
        },
        completion={
            "state": "succeeded",
            "final_output": True,
            "final_artifact": output_path.name,
            "final_artifact_path": str(output_path.resolve()),
        },
    )

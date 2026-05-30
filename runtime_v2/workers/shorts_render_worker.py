from __future__ import annotations

from pathlib import Path
import json

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
)

SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_FPS = 30
SHORTS_CRF = 18


def run_shorts_render_job(
    job: JobContract, *, artifact_root: Path
) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    source_path = resolve_local_input(
        str(job.payload.get("source_video_path", "")).strip()
    )
    voice_json_source = resolve_local_input(
        str(job.payload.get("voice_json_path", "")).strip()
    )
    output_path_raw = str(job.payload.get("service_artifact_path", "")).strip()
    if source_path is None or voice_json_source is None or not output_path_raw:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_shorts_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    try:
        staged_voice_json = stage_local_input(
            workspace, voice_json_source, target_name="voice.json"
        )
        voice_payload = json.loads(staged_voice_json.read_text(encoding="utf-8"))
    except OSError:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="shorts_input_io_failed",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    except json.JSONDecodeError:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[staged_voice_json],
            error_code="missing_shorts_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    voice_texts = (
        voice_payload.get("voice_texts", []) if isinstance(voice_payload, dict) else []
    )
    if not isinstance(voice_texts, list) or not voice_texts:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[staged_voice_json],
            error_code="missing_shorts_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    output_path = Path(output_path_raw)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        f"[0:v]split[original][blur];"
        f"[blur]scale={SHORTS_WIDTH}:{SHORTS_HEIGHT},boxblur=20:20[blurred];"
        f"[original]scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}:force_original_aspect_ratio=decrease,setsar=1[scaled];"
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path.resolve()),
        "-filter_complex",
        filter_complex,
        "-c:v",
        "libx264",
        "-crf",
        str(SHORTS_CRF),
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-r",
        str(SHORTS_FPS),
        str(output_path.resolve()),
    ]
    process = run_external_process(command, cwd=output_path.parent)
    exit_code = process.get("exit_code", 1)
    if not isinstance(exit_code, int):
        exit_code = int(str(exit_code))
    if exit_code != 0 or not output_path.exists():
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="shorts_render",
            artifacts=[staged_voice_json],
            error_code="shorts_render_failed",
            retryable=False,
            details={"process": process},
            completion={"state": "failed", "final_output": False},
        )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="shorts_render",
        artifacts=[staged_voice_json, output_path],
        details={
            "voice_json_path": str(staged_voice_json.resolve()),
            "service_artifact_path": str(output_path.resolve()),
            "process": process,
        },
        completion={
            "state": "succeeded",
            "final_output": True,
            "final_artifact_path": str(output_path.resolve()),
        },
    )

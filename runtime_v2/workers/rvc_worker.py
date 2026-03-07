from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.stage2.legacy_executor import LEGACY_ROOT, int_value, load_legacy_result_json, resolve_output_from_result, script_command, stage_output
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace, resolve_local_input, stage_local_input, write_json_atomic


def _expected_rvc_output(project_root: Path) -> Path | None:
    video_candidate = project_root / "video" / "#01_RVC.mp4"
    if video_candidate.exists() and video_candidate.is_file():
        return video_candidate
    audio_candidate = project_root / "voice" / "#01_GEMINI.flac"
    if audio_candidate.exists() and audio_candidate.is_file():
        return audio_candidate
    return None


def run_rvc_job(job: JobContract | None = None, artifact_root: Path | None = None) -> dict[str, object]:
    if job is None:
        return {"worker": "rvc", "status": "failed", "error_code": "missing_job"}
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
    model_name = str(job.payload.get("model_name", "")).strip()
    if not model_name:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_model_name",
            retryable=False,
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
    result_json_path = workspace / "legacy_result.json"
    command = script_command("rvc_voice_convert.py") + [
        "--video-folder",
        str(video_folder.resolve()),
        "--tts",
        "--model",
        model_name,
        "--result-json",
        str(result_json_path.resolve()),
    ]
    process_result = cast(dict[str, object], run_external_process(command, cwd=LEGACY_ROOT))
    exit_code = int_value(process_result.get("exit_code", 1), 1)
    if exit_code != 0 or not result_json_path.exists():
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="rvc",
            artifacts=[source_copy, request_file],
            error_code="legacy_executor_failed",
            retryable=True,
            details={"process_result": process_result},
            completion={"state": "blocked", "final_output": False},
        )

    parsed_result = load_legacy_result_json(
        workspace,
        stage="rvc",
        result_json_path=result_json_path,
        artifacts=[source_copy, request_file, result_json_path],
        process_result=process_result,
    )
    if parsed_result.get("status") == "failed":
        return parsed_result

    result_payload = cast(dict[str, object], parsed_result)
    output_path = resolve_output_from_result(result_payload)
    if output_path is None:
        output_path = _expected_rvc_output(project_root)
    if output_path is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="rvc",
            artifacts=[source_copy, request_file, result_json_path],
            error_code="missing_legacy_outputs",
            retryable=True,
            details={"legacy_result": result_payload, "process_result": process_result},
            completion={"state": "blocked", "final_output": False},
        )

    staged_output = stage_output(workspace, output_path, fallback_name="converted.flac")
    next_jobs: list[dict[str, object]] = []
    image_path = str(job.payload.get("image_path", "")).strip()
    chain_depth_value = job.payload.get("chain_depth", 0)
    chain_depth = int(chain_depth_value) if isinstance(chain_depth_value, (int, float, str)) else 0
    if image_path and staged_output.suffix.lower() in {".wav", ".mp3", ".flac"}:
        next_jobs.append(
            build_explicit_job_contract(
                job_id=f"kenburns-{job.job_id}",
                workload="kenburns",
                checkpoint_key=f"derived:kenburns:{job.job_id}",
                payload={
                    "source_path": image_path,
                    "audio_path": str(staged_output.resolve()),
                    "duration_sec": int_value(job.payload.get("duration_sec", 8), 8),
                    "chain_depth": chain_depth + 1,
                },
                parent_job_id=job.job_id,
                chain_step=chain_depth + 1,
            )
        )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="rvc",
        artifacts=[source_copy, request_file, result_json_path, staged_output],
        retryable=False,
        details={
            "legacy_result": result_payload,
            "model_name": model_name,
            "processing_backend": "legacy_rvc_tts",
            "service_artifact_path": str(output_path.resolve()),
        },
        next_jobs=next_jobs,
        completion={
            "state": "routed" if next_jobs else "succeeded",
            "final_output": not bool(next_jobs),
            "final_artifact": "" if next_jobs else staged_output.name,
            "final_artifact_path": "" if next_jobs else str(staged_output.resolve()),
        },
    )

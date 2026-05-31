from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
from runtime_v2.contracts.job_contract import build_explicit_job_contract, JobContract
from runtime_v2.config import external_runtime_root
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import (
    REPO_ROOT,
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
)

SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_FPS = 30
SHORTS_CRF = 18
LEGACY_SHORTS_RENDER = Path(r"D:/YOUTUBE_AUTO/scripts/shorts_render.py")


def _resolve_local_directory(raw_path: str) -> Path | None:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    allowed_roots = {REPO_ROOT.resolve(), external_runtime_root().resolve()}
    if not any(
        candidate == root or root in candidate.parents for root in allowed_roots
    ):
        return None
    if not candidate.exists() or not candidate.is_dir():
        return None
    return candidate


def _build_n8n_upload_next_job(
    job: JobContract, output_path: Path
) -> dict[str, object] | None:
    callback_url = str(job.payload.get("callback_url", "")).strip()
    if not callback_url:
        return None
    raw_depth = job.payload.get("chain_depth", 0)
    if isinstance(raw_depth, bool):
        chain_depth = int(raw_depth)
    elif isinstance(raw_depth, int):
        chain_depth = raw_depth
    elif isinstance(raw_depth, float):
        chain_depth = int(raw_depth)
    elif isinstance(raw_depth, str) and raw_depth.strip():
        chain_depth = int(raw_depth.strip())
    else:
        chain_depth = 0
    chain_depth += 1
    return build_explicit_job_contract(
        job_id=f"n8n-{job.job_id}",
        workload="n8n_upload",
        checkpoint_key=f"derived:n8n_upload:{job.job_id}",
        payload={
            "run_id": str(job.payload.get("run_id", "")).strip(),
            "row_ref": str(job.payload.get("row_ref", "")).strip(),
            "row_index": job.payload.get("row_index", 0),
            "channel": job.payload.get("channel", 0),
            "upload_mode": "video",
            "callback_url": callback_url,
            "artifact_path": str(output_path.resolve()),
            "mode": "shorts",
            "chain_depth": chain_depth,
        },
        chain_step=chain_depth,
        parent_job_id=job.job_id,
    )


def run_shorts_render_job(
    job: JobContract, *, artifact_root: Path
) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    render_folder_raw = str(job.payload.get("render_folder_path", "")).strip()
    render_folder = (
        _resolve_local_directory(render_folder_raw) if render_folder_raw else None
    )
    source_path = resolve_local_input(
        str(job.payload.get("source_video_path", "")).strip()
    )
    voice_json_source = resolve_local_input(
        str(job.payload.get("voice_json_path", "")).strip()
    )
    output_path_raw = str(job.payload.get("service_artifact_path", "")).strip()
    if (
        voice_json_source is None
        or not output_path_raw
        or (render_folder is None and source_path is None)
    ):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_shorts_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    staged_voice_json: Path | None = None
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
        decode_artifacts: list[Path] = []
        if staged_voice_json is not None:
            decode_artifacts.append(staged_voice_json)
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=decode_artifacts,
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
    assert staged_voice_json is not None
    output_path = Path(output_path_raw)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_json_path: Path | None = None
    if isinstance(render_folder, Path) and render_folder.is_dir():
        result_json_path = output_path.with_suffix(".json")
        command = [
            sys.executable,
            str(LEGACY_SHORTS_RENDER),
            "--folder",
            str(render_folder.resolve()),
            "--voice-json",
            str(staged_voice_json.resolve()),
            "--result-json",
            str(result_json_path.resolve()),
        ]
    else:
        assert source_path is not None
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
    staged_result_json = result_json_path
    if (
        isinstance(render_folder, Path)
        and render_folder.is_dir()
        and staged_result_json is not None
        and staged_result_json.exists()
    ):
        try:
            result_payload = json.loads(staged_result_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result_payload = {}
        if isinstance(result_payload, dict):
            legacy_output_path = Path(
                str(result_payload.get("output_path", "")).strip()
            )
            if (
                legacy_output_path.exists()
                and legacy_output_path.is_file()
                and legacy_output_path.resolve() != output_path.resolve()
            ):
                try:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    _ = shutil.copy2(legacy_output_path, output_path)
                except OSError:
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
    next_jobs: list[dict[str, object]] = []
    upload_next_job = _build_n8n_upload_next_job(job, output_path)
    if upload_next_job is not None:
        next_jobs.append(upload_next_job)
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
        next_jobs=next_jobs,
        completion={
            "state": "routed" if next_jobs else "succeeded",
            "final_output": True,
            "final_artifact_path": str(output_path.resolve()),
        },
    )

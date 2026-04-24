from __future__ import annotations

from pathlib import Path
import sys

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.config import external_runtime_root
from runtime_v2.workers.job_runtime import REPO_ROOT, finalize_worker_result, prepare_workspace, resolve_local_input

LEGACY_TIMELINE_SCRIPT = Path(r"D:/YOUTUBE_AUTO/scripts/timeline_generator.py")


def _resolve_local_directory(raw_path: str) -> Path | None:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    allowed_roots = {REPO_ROOT.resolve(), external_runtime_root().resolve()}
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        return None
    if not candidate.exists() or not candidate.is_dir():
        return None
    return candidate


def run_timeline_job(job: JobContract, *, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    voice_json_path = resolve_local_input(str(job.payload.get("voice_json_path", "")).strip())
    video_dir_path = _resolve_local_directory(str(job.payload.get("video_dir_path", "")).strip())
    output_path_raw = str(job.payload.get("service_artifact_path", "")).strip()
    if voice_json_path is None or video_dir_path is None or not output_path_raw:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_timeline_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    output_path = Path(output_path_raw)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(LEGACY_TIMELINE_SCRIPT),
        "--voice-json",
        str(voice_json_path.resolve()),
        "--video-dir",
        str(video_dir_path.resolve()),
    ]
    process = run_external_process(command, cwd=workspace)
    exit_code = process.get("exit_code", 1)
    if not isinstance(exit_code, int):
        exit_code = int(str(exit_code))
    timeline_text = str(process.get("stdout", "")).strip()
    if exit_code != 0 or not timeline_text:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="timeline",
            artifacts=[],
            error_code="timeline_generation_failed",
            retryable=False,
            details={"process": process},
            completion={"state": "failed", "final_output": False},
        )
    output_path.write_text(timeline_text, encoding="utf-8")
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="timeline",
        artifacts=[output_path],
        details={"service_artifact_path": str(output_path.resolve()), "process": process},
        completion={"state": "succeeded", "final_output": True, "final_artifact_path": str(output_path.resolve())},
    )

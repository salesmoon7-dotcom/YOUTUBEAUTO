from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.n8n_adapter import post_callback
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import (
    REPO_ROOT,
    finalize_worker_result,
    prepare_workspace,
)

LEGACY_N8N_MYBOX_UPLOAD = Path(r"D:/YOUTUBE_AUTO/scripts/n8n_mybox_upload.py")
LEGACY_APP_CONFIG = Path(r"D:/YOUTUBE_AUTO/system/config/app_config.json")


def _resolve_legacy_topic_folder(channel: int, row_index: int) -> Path | None:
    try:
        config = json.loads(LEGACY_APP_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(config, dict):
        return None
    channels = config.get("channels", {})
    paths = config.get("paths", {})
    if not isinstance(channels, dict) or not isinstance(paths, dict):
        return None
    channel_config = channels.get(str(channel), {})
    if not isinstance(channel_config, dict):
        return None
    channel_name = str(channel_config.get("name", "")).strip()
    download_base = str(paths.get("download_base", "")).strip()
    if not channel_name or not download_base:
        return None
    channel_dir = Path(download_base).expanduser() / channel_name
    if not channel_dir.exists() or not channel_dir.is_dir():
        return None
    topic_folders = sorted([entry for entry in channel_dir.iterdir() if entry.is_dir()])
    if row_index < 0 or row_index >= len(topic_folders):
        return None
    return topic_folders[row_index]


def run_n8n_upload_job(job: JobContract, *, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    callback_url = str(job.payload.get("callback_url", "")).strip()
    artifact_path = str(job.payload.get("artifact_path", "")).strip()
    upload_mode = str(job.payload.get("upload_mode", "")).strip()
    channel_value = job.payload.get("channel")
    row_value = job.payload.get("row_index")
    if upload_mode in {"images", "video"} and isinstance(channel_value, int):
        if upload_mode == "video" and artifact_path and isinstance(row_value, int):
            topic_folder = _resolve_legacy_topic_folder(channel_value, row_value)
            if topic_folder is None:
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="validate_input",
                    artifacts=[],
                    error_code="missing_artifact_path",
                    retryable=False,
                    completion={"state": "failed", "final_output": False},
                )
            source_artifact = Path(artifact_path)
            if not source_artifact.exists() or not source_artifact.is_file():
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="validate_input",
                    artifacts=[],
                    error_code="missing_artifact_path",
                    retryable=False,
                    completion={"state": "failed", "final_output": False},
                )
            try:
                target_render_dir = topic_folder / "render"
                target_render_dir.mkdir(parents=True, exist_ok=True)
                _ = shutil.copy2(
                    source_artifact, target_render_dir / source_artifact.name
                )
                os.utime(target_render_dir / source_artifact.name, None)
            except OSError:
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="validate_input",
                    artifacts=[],
                    error_code="missing_artifact_path",
                    retryable=False,
                    completion={"state": "failed", "final_output": False},
                )
        command = [
            sys.executable,
            str(LEGACY_N8N_MYBOX_UPLOAD),
            "--mode",
            upload_mode,
            "--channel",
            str(channel_value),
            "--require-uploaded-min",
            "1",
        ]
        if isinstance(row_value, int):
            command.extend(["--row", str(row_value), "--row-base", "0"])
        if callback_url:
            command.extend(["--n8n-callback", callback_url])
        process = run_external_process(command=command, cwd=REPO_ROOT)
        exit_code = process.get("exit_code", 1)
        if not isinstance(exit_code, int):
            exit_code = int(str(exit_code))
        if exit_code != 0:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="n8n_upload",
                artifacts=[],
                error_code="callback_fail",
                retryable=False,
                details={"process": process, "artifact_path": artifact_path},
                completion={"state": "failed", "final_output": False},
            )
        return finalize_worker_result(
            workspace,
            status="ok",
            stage="n8n_upload",
            artifacts=[],
            details={"process": process, "artifact_path": artifact_path},
            completion={"state": "succeeded", "final_output": True},
        )
    if not callback_url:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_callback_url",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    if not artifact_path:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_artifact_path",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    artifact_file = Path(artifact_path)
    if not artifact_file.exists() or not artifact_file.is_file():
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_artifact_path",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "execution_env": "remote_n8n",
        "callback_url": callback_url,
        "run_id": str(job.payload.get("run_id", "")),
        "row_ref": str(job.payload.get("row_ref", "")),
        "channel": job.payload.get("channel", 0),
        "row_index": job.payload.get("row_index", 0),
        "upload_mode": upload_mode,
        "mode": str(job.payload.get("mode", "closeout")),
        "artifact_path": artifact_path,
        "job_id": job.job_id,
        "workload": job.workload,
    }
    callback_result = post_callback(payload)
    if not bool(callback_result.get("ok")):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="callback",
            artifacts=[],
            error_code="callback_fail",
            retryable=bool(callback_result.get("retryable")),
            details={"callback": callback_result, "artifact_path": artifact_path},
            completion={"state": "failed", "final_output": False},
        )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="n8n_upload",
        artifacts=[],
        details={"callback": callback_result, "artifact_path": artifact_path},
        completion={"state": "succeeded", "final_output": True},
    )

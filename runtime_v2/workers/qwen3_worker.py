from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    write_json_atomic,
)
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def _int_value(raw_value: object, default: int) -> int:
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if text:
            try:
                return int(text)
            except ValueError:
                return default
    return default


def run_qwen3_job(
    job: JobContract | None = None, artifact_root: Path | None = None
) -> dict[str, object]:
    if job is None:
        return {"worker": "qwen3_tts", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    raw_text = job.payload.get("script_text", "")
    script_text = str(raw_text).strip() if isinstance(raw_text, str) else ""
    if not script_text:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_script_text",
            retryable=False,
        )

    project_root = workspace / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    prompt_payload = {
        "channel": _int_value(job.payload.get("channel", 0), 0),
        "rows": [
            {
                "row_index": 0,
                "channel": _int_value(job.payload.get("channel", 0), 0),
                "topic": str(job.payload.get("topic", job.job_id)),
                "no": str(job.payload.get("episode_no", "1")),
                "folder_path": str(project_root.resolve()),
                "voice_texts": [{"col": "#01", "text": script_text}],
            }
        ],
    }
    request_file = write_native_request(workspace, job.payload)
    prompt_file = write_json_atomic(workspace / "qwen_prompt.json", prompt_payload)
    adapter_command_raw = job.payload.get("adapter_command")
    if isinstance(adapter_command_raw, list) and adapter_command_raw:
        adapter_command_items = cast(list[object], adapter_command_raw)
        adapter_command = [str(item) for item in adapter_command_items]
        completed = subprocess.run(
            adapter_command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )
        stdout_path = workspace / "adapter_stdout.log"
        stderr_path = workspace / "adapter_stderr.log"
        _ = stdout_path.write_text(completed.stdout, encoding="utf-8")
        _ = stderr_path.write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="qwen3_tts_adapter",
                artifacts=[request_file, prompt_file, stdout_path, stderr_path],
                error_code="qwen3_tts_adapter_failed",
                retryable=False,
                details={"returncode": completed.returncode},
                completion={"state": "blocked", "final_output": False},
            )

        service_artifact_path = str(
            job.payload.get("service_artifact_path", "")
        ).strip()
        verified_output = resolve_local_input(service_artifact_path)
        if verified_output is None:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="qwen3_tts_verify_output",
                artifacts=[request_file, prompt_file, stdout_path, stderr_path],
                error_code="missing_service_artifact_path",
                retryable=False,
                completion={"state": "blocked", "final_output": False},
            )

        return finalize_worker_result(
            workspace,
            status="ok",
            stage="qwen3_tts",
            artifacts=[
                request_file,
                prompt_file,
                stdout_path,
                stderr_path,
                verified_output,
            ],
            retryable=False,
            details={
                "script_text_present": True,
                "image_path": str(job.payload.get("image_path", "")).strip(),
                "model_name": str(job.payload.get("model_name", "")).strip(),
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
        workload="qwen3_tts",
        stage="qwen3_tts",
        artifacts=[request_file, prompt_file],
        details={
            "script_text_present": True,
            "image_path": str(job.payload.get("image_path", "")).strip(),
            "model_name": str(job.payload.get("model_name", "")).strip(),
        },
    )

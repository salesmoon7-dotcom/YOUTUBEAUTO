from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
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

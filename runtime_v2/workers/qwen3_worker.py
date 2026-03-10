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
    write_json_atomic,
)
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _voice_texts_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_voice_texts = payload.get("voice_texts", [])
    if isinstance(raw_voice_texts, list):
        normalized: list[dict[str, object]] = []
        for entry in cast(list[object], raw_voice_texts):
            if not isinstance(entry, dict):
                continue
            typed = cast(dict[str, object], entry)
            text = str(typed.get("text", "")).strip()
            col = str(typed.get("col", "")).strip()
            if text and col:
                normalized.append(
                    {
                        "col": col,
                        "text": text,
                        "original_voices": typed.get("original_voices", []),
                    }
                )
        if normalized:
            return normalized
    raw_text = payload.get("script_text", "")
    script_text = str(raw_text).strip() if isinstance(raw_text, str) else ""
    if not script_text:
        return []
    return [{"col": "#01", "text": script_text, "original_voices": [1]}]


def _canonical_adapter_env() -> dict[str, str]:
    repo_root = str(REPO_ROOT.resolve())
    current = os.environ.get("PYTHONPATH", "").strip()
    pythonpath = repo_root if not current else f"{repo_root}{os.pathsep}{current}"
    return {"PYTHONPATH": pythonpath}


def run_qwen3_job(
    job: JobContract | None = None, artifact_root: Path | None = None
) -> dict[str, object]:
    if job is None:
        return {"worker": "qwen3_tts", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    voice_texts = _voice_texts_payload(job.payload)
    if not voice_texts:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_voice_texts",
            retryable=False,
            completion={"state": "failed", "final_output": False},
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
                "voice_texts": voice_texts,
            }
        ],
    }
    request_file = write_native_request(workspace, job.payload)
    prompt_file = write_json_atomic(workspace / "qwen_prompt.json", prompt_payload)
    adapter_command_raw = job.payload.get("adapter_command")
    adapter_extra_env: dict[str, str] | None = None
    if (not isinstance(adapter_command_raw, list) or not adapter_command_raw) and str(
        job.payload.get("service_artifact_path", "")
    ).strip():
        adapter_command_raw = [
            sys.executable,
            "-m",
            "runtime_v2.cli",
            "--qwen3-adapter-child",
            "--workspace-root",
            str(workspace.resolve()),
            "--service-artifact-path",
            str(job.payload.get("service_artifact_path", "")),
        ]
        adapter_extra_env = _canonical_adapter_env()
    if isinstance(adapter_command_raw, list) and adapter_command_raw:
        adapter_command_items = cast(list[object], adapter_command_raw)
        adapter_command = [str(item) for item in adapter_command_items]
        adapter_result = run_verified_adapter_command(
            workspace,
            adapter_command=adapter_command,
            service_artifact_path=str(job.payload.get("service_artifact_path", "")),
            adapter_error_code="qwen3_tts_adapter_failed",
            extra_env=adapter_extra_env,
        )
        stdout_path = Path(str(adapter_result["stdout_path"]))
        stderr_path = Path(str(adapter_result["stderr_path"]))
        if not bool(adapter_result.get("ok", False)):
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="qwen3_tts_adapter",
                artifacts=[request_file, prompt_file, stdout_path, stderr_path],
                error_code=str(
                    adapter_result.get("error_code", "qwen3_tts_adapter_failed")
                ),
                retryable=False,
                details=cast(dict[str, object], adapter_result.get("details", {})),
                completion={"state": "failed", "final_output": False},
            )
        verified_output = Path(str(adapter_result["output_path"]))

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
                "script_text_present": bool(voice_texts),
                "voice_text_count": len(voice_texts),
                "image_path": str(job.payload.get("image_path", "")).strip(),
                "model_name": str(job.payload.get("model_name", "")).strip(),
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
        workload="qwen3_tts",
        stage="qwen3_tts",
        artifacts=[request_file, prompt_file],
        details={
            "script_text_present": bool(voice_texts),
            "voice_text_count": len(voice_texts),
            "image_path": str(job.payload.get("image_path", "")).strip(),
            "model_name": str(job.payload.get("model_name", "")).strip(),
        },
    )

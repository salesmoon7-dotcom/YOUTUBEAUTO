from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import build_explicit_job_contract
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
LEGACY_QWEN3_CONFIG = Path(r"D:/YOUTUBE_AUTO/system/config/qwen3_tts_config.json")


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


def _load_legacy_qwen3_config() -> dict[str, object]:
    if not LEGACY_QWEN3_CONFIG.exists():
        return {}
    try:
        raw_payload = json.loads(LEGACY_QWEN3_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], raw_payload) if isinstance(raw_payload, dict) else {}


def _resolve_reference_audio(job: JobContract, config: dict[str, object]) -> str:
    by_channel = config.get("reference_audio_by_channel", {})
    if isinstance(by_channel, dict):
        channel_value = job.payload.get("channel")
        channel_key = str(channel_value).strip() if channel_value is not None else ""
        if channel_key:
            ref = str(by_channel.get(channel_key, "")).strip()
            if ref:
                return ref
    return str(config.get("reference_audio_default", "")).strip()


def _normalize_output_format(config: dict[str, object]) -> str:
    raw_format = str(config.get("output_format", "")).strip().lower()
    if raw_format in {"wav", "flac"}:
        return raw_format
    return "flac"


def _build_rvc_next_job(
    job: JobContract, verified_output: Path
) -> dict[str, object] | None:
    model_name = str(job.payload.get("model_name", "")).strip()
    if not model_name:
        return None
    rvc_output_path = verified_output.with_name(f"{verified_output.stem}_rvc.wav")
    payload: dict[str, object] = {
        "source_path": str(verified_output.resolve()),
        "model_name": model_name,
        "service_artifact_path": str(rvc_output_path.resolve()),
        "chain_depth": _int_value(job.payload.get("chain_depth", 0), 0) + 1,
    }
    image_path = str(job.payload.get("image_path", "")).strip()
    if image_path:
        payload["image_path"] = image_path
    duration_sec = job.payload.get("duration_sec")
    if isinstance(duration_sec, (int, float, str)) and str(duration_sec).strip():
        payload["duration_sec"] = duration_sec
    for key in ("run_id", "row_ref", "topic", "episode_no", "channel"):
        value = job.payload.get(key)
        if isinstance(value, str) and value.strip():
            payload[key] = value.strip()
        elif isinstance(value, (int, float)):
            payload[key] = value
    return build_explicit_job_contract(
        job_id=f"rvc-{job.job_id}",
        workload="rvc",
        checkpoint_key=f"derived:rvc:{job.job_id}",
        payload=payload,
        chain_step=_int_value(job.payload.get("chain_depth", 0), 0) + 1,
        parent_job_id=job.job_id,
    )


def run_qwen3_job(
    job: JobContract | None = None, artifact_root: Path | None = None
) -> dict[str, object]:
    if job is None:
        return {"worker": "qwen3_tts", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    legacy_config = _load_legacy_qwen3_config()
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
    reference_audio = _resolve_reference_audio(job, legacy_config)
    output_format = _normalize_output_format(legacy_config)
    if reference_audio:
        ref_audio_path = Path(reference_audio)
        if not ref_audio_path.exists() or not ref_audio_path.is_file():
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="validate_input",
                artifacts=[],
                error_code="missing_reference_audio",
                retryable=False,
                details={"reference_audio": reference_audio},
                completion={"state": "failed", "final_output": False},
            )
    prompt_payload = {
        "channel": _int_value(job.payload.get("channel", 0), 0),
        "reference_audio": reference_audio,
        "output_format": output_format,
        "rows": [
            {
                "row_index": 0,
                "channel": _int_value(job.payload.get("channel", 0), 0),
                "topic": str(job.payload.get("topic", job.job_id)),
                "no": str(job.payload.get("episode_no", "1")),
                "folder_path": str(project_root.resolve()),
                "voice_texts": voice_texts,
                "ref_audio_used": reference_audio,
                "output_format": output_format,
            }
        ],
    }
    request_file = write_native_request(workspace, job.payload)
    prompt_file = write_json_atomic(workspace / "qwen_prompt.json", prompt_payload)
    if reference_audio:
        request_payload = cast(
            dict[str, object], json.loads(request_file.read_text(encoding="utf-8"))
        )
        request_payload["reference_audio"] = reference_audio
        request_file = write_json_atomic(request_file, request_payload)

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
            "--service-artifact-path",
            str(job.payload.get("service_artifact_path", "")),
        ]
        if reference_audio:
            adapter_command_raw.extend(["--ref-audio", reference_audio])
        adapter_extra_env = _canonical_adapter_env()
    if isinstance(adapter_command_raw, list) and adapter_command_raw:
        adapter_command_items = cast(list[object], adapter_command_raw)
        adapter_command = [str(item) for item in adapter_command_items]
        adapter_result = run_verified_adapter_command(
            workspace,
            approved_root=artifact_root or workspace.parent.parent,
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
                details={
                    **cast(dict[str, object], adapter_result.get("details", {})),
                    "reference_audio": reference_audio,
                    "ref_audio_used": reference_audio,
                    "output_format": output_format,
                },
                completion={"state": "failed", "final_output": False},
            )
        verified_output = Path(str(adapter_result["output_path"]))
        next_jobs: list[dict[str, object]] = []
        rvc_next_job = _build_rvc_next_job(job, verified_output)
        if rvc_next_job is not None:
            next_jobs.append(rvc_next_job)

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
                "reference_audio": reference_audio,
                "ref_audio_used": reference_audio,
                "output_format": output_format,
            },
            next_jobs=next_jobs,
            completion={
                "state": "routed" if next_jobs else "succeeded",
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
            "reference_audio": reference_audio,
            "ref_audio_used": reference_audio,
            "output_format": output_format,
        },
    )

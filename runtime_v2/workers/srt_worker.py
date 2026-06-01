from __future__ import annotations

import json
from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
)


def _format_srt_timestamp(total_seconds: float) -> str:
    millis = int(round(total_seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def run_srt_job(job: JobContract, *, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    voice_json_path = resolve_local_input(
        str(job.payload.get("voice_json_path", "")).strip()
    )
    render_spec_path = resolve_local_input(
        str(job.payload.get("render_spec_path", "")).strip()
    )
    output_path_raw = str(job.payload.get("service_artifact_path", "")).strip()
    if voice_json_path is None or render_spec_path is None or not output_path_raw:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_srt_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )

    staged_voice_json = stage_local_input(
        workspace, voice_json_path, target_name="voice.json"
    )
    staged_render_spec = stage_local_input(
        workspace, render_spec_path, target_name="render_spec.json"
    )
    try:
        voice_payload = json.loads(staged_voice_json.read_text(encoding="utf-8"))
        render_spec = json.loads(staged_render_spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[staged_voice_json, staged_render_spec],
            error_code="missing_srt_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    voice_texts = voice_payload.get("voice_texts", [])
    timeline = render_spec.get("timeline", [])
    if (
        not isinstance(voice_texts, list)
        or not voice_texts
        or not isinstance(timeline, list)
        or not timeline
    ):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[staged_voice_json, staged_render_spec],
            error_code="missing_srt_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )

    output_path = Path(output_path_raw)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    elapsed = 0.0
    rows: list[str] = []
    for index, entry in enumerate(voice_texts, start=1):
        if isinstance(entry, dict):
            text = str(entry.get("text", "")).strip()
        else:
            text = str(entry).strip()
        if not text:
            continue
        duration = 0.0
        if index - 1 < len(timeline) and isinstance(timeline[index - 1], dict):
            duration = float(timeline[index - 1].get("duration_sec", 0.0) or 0.0)
        if duration <= 0:
            duration = 1.0
        start_ts = _format_srt_timestamp(elapsed)
        end_ts = _format_srt_timestamp(elapsed + duration)
        rows.extend([str(index), f"{start_ts} --> {end_ts}", text, ""])
        elapsed += duration

    output_path.write_text("\n".join(rows), encoding="utf-8")
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="srt",
        artifacts=[staged_voice_json, staged_render_spec, output_path],
        details={"service_artifact_path": str(output_path.resolve())},
        completion={
            "state": "succeeded",
            "final_output": True,
            "final_artifact_path": str(output_path.resolve()),
        },
    )

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.job_runtime import (
    REPO_ROOT,
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
    write_json_atomic,
)
from runtime_v2.workers.native_only import native_not_implemented_result


def _resolve_local_directory(raw_path: str) -> Path | None:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
        return None
    if not candidate.exists() or not candidate.is_dir():
        return None
    return candidate


def _load_render_spec_payload(render_spec_path: Path) -> dict[str, object] | None:
    try:
        raw_payload = cast(
            object, json.loads(render_spec_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    typed_payload = cast(dict[object, object], raw_payload)
    return {str(key): value for key, value in typed_payload.items()}


def _missing_render_paths(render_spec: dict[str, object]) -> list[str]:
    missing_paths: list[str] = []

    def collect_paths(entries: object) -> None:
        if not isinstance(entries, list):
            return
        for entry in cast(list[object], entries):
            if (
                isinstance(entry, str)
                and entry.strip()
                and resolve_local_input(entry) is None
            ):
                missing_paths.append(entry)

    collect_paths(render_spec.get("asset_refs", []))
    collect_paths(render_spec.get("audio_refs", []))
    collect_paths(render_spec.get("thumbnail_refs", []))

    raw_timeline = render_spec.get("timeline", [])
    if isinstance(raw_timeline, list):
        for raw_entry in cast(list[object], raw_timeline):
            if not isinstance(raw_entry, dict):
                continue
            timeline_entry = cast(dict[object, object], raw_entry)
            asset_path = str(timeline_entry.get("asset_path", "")).strip()
            if asset_path and resolve_local_input(asset_path) is None:
                missing_paths.append(asset_path)

    return sorted(set(missing_paths))


def run_render_job(job: JobContract, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    render_spec_path = workspace / "render_spec.json"
    raw_render_spec_path = str(job.payload.get("render_spec_path", "")).strip()
    if raw_render_spec_path:
        source_render_spec = resolve_local_input(raw_render_spec_path)
        if source_render_spec is None:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="render",
                artifacts=[],
                error_code="missing_render_spec",
                retryable=True,
                completion={"state": "blocked", "final_output": False},
            )
        staged_render_spec = stage_local_input(
            workspace, source_render_spec, target_name="render_spec.json"
        )
    else:
        render_spec_payload = job.payload.get("render_spec", {"payload": job.payload})
        typed_render_spec: dict[str, object]
        if isinstance(render_spec_payload, dict):
            typed_render_spec = cast(dict[str, object], render_spec_payload)
        else:
            typed_render_spec = {"payload": job.payload}
        staged_render_spec = write_json_atomic(render_spec_path, typed_render_spec)

    raw_render_folder_path = str(job.payload.get("render_folder_path", "")).strip()
    raw_voice_json_path = str(job.payload.get("voice_json_path", "")).strip()
    render_folder = (
        _resolve_local_directory(raw_render_folder_path)
        if raw_render_folder_path
        else None
    )
    voice_json_path = (
        resolve_local_input(raw_voice_json_path) if raw_voice_json_path else None
    )
    if voice_json_path is None:
        voice_json_payload = job.payload.get("voice_json", {})
        if isinstance(voice_json_payload, dict):
            voice_json_path = write_json_atomic(
                workspace / "voice.json", cast(dict[str, object], voice_json_payload)
            )
    if render_folder is None or voice_json_path is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[staged_render_spec],
            error_code="missing_render_inputs",
            retryable=True,
            completion={"state": "blocked", "final_output": False},
            details={
                "render_folder_path": raw_render_folder_path,
                "voice_json_path": raw_voice_json_path,
            },
        )

    render_spec_payload = _load_render_spec_payload(staged_render_spec)
    if render_spec_payload is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[staged_render_spec, voice_json_path],
            error_code="invalid_render_spec",
            retryable=False,
            completion={"state": "blocked", "final_output": False},
        )

    missing_paths = _missing_render_paths(render_spec_payload)
    if missing_paths:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[staged_render_spec, voice_json_path],
            error_code="render_inputs_not_ready",
            retryable=True,
            completion={"state": "blocked", "final_output": False},
            details={
                "render_folder_path": str(render_folder.resolve()),
                "missing_paths": missing_paths,
            },
        )

    render_stage = str(job.payload.get("render_stage", "")).strip()
    return native_not_implemented_result(
        workspace,
        workload="render",
        stage="render",
        artifacts=[staged_render_spec, voice_json_path],
        details={
            "render_folder_path": str(render_folder.resolve()),
            "voice_json_path": str(voice_json_path.resolve()),
            "render_stage": render_stage,
        },
    )

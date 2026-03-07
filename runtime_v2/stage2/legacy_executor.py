from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import cast

from runtime_v2.workers.job_runtime import REPO_ROOT, finalize_worker_result, resolve_local_input, stage_local_input, write_json_atomic

LEGACY_ROOT = Path("D:/YOUTUBE_AUTO")


def int_value(raw_value: object, default: int) -> int:
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


def row_index_from_payload(payload: dict[str, object]) -> int:
    row_index = int_value(payload.get("row_index", -1), -1)
    if row_index >= 0:
        return row_index
    row_ref = str(payload.get("row_ref", "")).strip()
    token = row_ref.rsplit("row", 1)[-1].strip()
    if token.isdigit():
        parsed = int(token) - 1
        if parsed >= 0:
            return parsed
    return 0


def channel_from_payload(payload: dict[str, object]) -> int:
    return int_value(payload.get("channel", 4), 4)


def build_image_prompt_file(workspace: Path, payload: dict[str, object], *, workload: str) -> Path:
    channel = channel_from_payload(payload)
    row_index = row_index_from_payload(payload)
    scene_index = max(1, int_value(payload.get("scene_index", 1), 1))
    prompt = str(payload.get("prompt", "")).strip()
    prompt_payload = {
        "channel": channel,
        "channel_name": str(payload.get("channel_name", f"channel-{channel}")),
        "rows": [
            {
                "row_index": row_index,
                "topic": str(payload.get("topic", "")),
                "no": str(payload.get("episode_no", row_index + 1)),
                "prompts": [
                    {
                        "col": f"#{scene_index:02d}",
                        "prompt": prompt,
                        "priority": 2,
                        "category": str(payload.get("category", workload)),
                    }
                ],
            }
        ],
    }
    return write_json_atomic(workspace / "legacy_prompt.json", prompt_payload)


def build_geminigen_prompt_file(workspace: Path, payload: dict[str, object]) -> Path:
    channel = channel_from_payload(payload)
    row_index = row_index_from_payload(payload)
    scene_index = max(1, int_value(payload.get("scene_index", 1), 1))
    prompt_payload = {
        "channel": channel,
        "channel_name": str(payload.get("channel_name", f"channel-{channel}")),
        "row_index": row_index,
        "folder_path": str(workspace.resolve()),
        "output_subdir": "video",
        "video_tasks": [
            {
                "scene": f"#{scene_index:02d}",
                "prompt": str(payload.get("prompt", "")).strip(),
                "output_file": f"scene_{scene_index:02d}.mp4",
                "provider": str(payload.get("provider", "google")),
                "model": str(payload.get("model", "veo3")),
            }
        ],
    }
    return write_json_atomic(workspace / "legacy_geminigen.json", prompt_payload)


def build_canva_thumb_file(workspace: Path, payload: dict[str, object]) -> Path:
    thumb_data_raw = payload.get("thumb_data", {})
    thumb_data = cast(dict[object, object], thumb_data_raw) if isinstance(thumb_data_raw, dict) else {}
    prompt = str(payload.get("prompt", "")).strip()
    thumb_payload = {
        "bg_prompt": str(thumb_data.get("bg_prompt", prompt)).strip(),
        "line1": str(thumb_data.get("line1", "")).strip(),
        "line2": str(thumb_data.get("line2", "")).strip(),
    }
    return write_json_atomic(workspace / "thumb_data.json", thumb_payload)


def resolve_output_from_result(result_payload: dict[str, object], *, prefer_thumbnail: bool = False) -> Path | None:
    candidates: list[str] = []
    if prefer_thumbnail:
        thumbnail_path = str(result_payload.get("thumbnail_path", "")).strip()
        if thumbnail_path:
            candidates.append(thumbnail_path)
    outputs_raw = result_payload.get("outputs", [])
    if isinstance(outputs_raw, list):
        for entry in outputs_raw:
            if isinstance(entry, dict):
                typed_entry = cast(dict[object, object], entry)
                path_value = str(typed_entry.get("path", "")).strip()
                if path_value:
                    candidates.append(path_value)
            elif isinstance(entry, str):
                text = entry.strip()
                if text:
                    candidates.append(text)
    for candidate in candidates:
        resolved = resolve_local_input(candidate)
        if resolved is not None:
            return resolved
    return None


def stage_output(workspace: Path, output_path: Path, *, fallback_name: str) -> Path:
    target_name = output_path.name if output_path.suffix else fallback_name
    return stage_local_input(workspace, output_path, target_name=target_name)


def stage_service_artifact(output_path: Path, raw_target_path: str) -> Path | None:
    target_text = raw_target_path.strip()
    if not target_text:
        return None
    target = Path(target_text).expanduser()
    if not target.is_absolute():
        target = (REPO_ROOT / target).resolve()
    else:
        target = target.resolve()
    if REPO_ROOT not in target.parents and target != REPO_ROOT:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(output_path, target)
    return target


def load_legacy_result_json(
    workspace: Path,
    *,
    stage: str,
    result_json_path: Path,
    artifacts: list[Path],
    process_result: dict[str, object],
) -> dict[str, object]:
    try:
        payload_raw = cast(object, json.loads(result_json_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage=stage,
            artifacts=artifacts,
            error_code="invalid_legacy_result_json",
            retryable=True,
            details={"process_result": process_result, "error": str(exc)},
            completion={"state": "blocked", "final_output": False},
        )
    if not isinstance(payload_raw, dict):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage=stage,
            artifacts=artifacts,
            error_code="invalid_legacy_result_json",
            retryable=True,
            details={"process_result": process_result, "error": "legacy_result_json_not_object"},
            completion={"state": "blocked", "final_output": False},
        )
    return cast(dict[str, object], payload_raw)


def script_command(script_name: str) -> list[str]:
    return [sys.executable, str((LEGACY_ROOT / "scripts" / script_name).resolve())]

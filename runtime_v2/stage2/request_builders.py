from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.workers.job_runtime import write_json_atomic


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


def build_image_prompt_file(
    workspace: Path,
    payload: dict[str, object],
    *,
    workload: str,
) -> Path:
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
    return write_json_atomic(workspace / "native_prompt.json", prompt_payload)


def build_geminigen_prompt_file(workspace: Path, payload: dict[str, object]) -> Path:
    channel = channel_from_payload(payload)
    row_index = row_index_from_payload(payload)
    scene_index = max(1, int_value(payload.get("scene_index", 1), 1))
    first_frame_path = str(payload.get("first_frame_path", "")).strip()
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
                "first_frame_path": first_frame_path,
            }
        ],
    }
    return write_json_atomic(workspace / "native_geminigen.json", prompt_payload)


def build_canva_thumb_file(workspace: Path, payload: dict[str, object]) -> Path:
    thumb_data_raw = payload.get("thumb_data", {})
    thumb_data = (
        cast(dict[object, object], thumb_data_raw)
        if isinstance(thumb_data_raw, dict)
        else {}
    )
    prompt = str(payload.get("prompt", "")).strip()
    thumb_payload = {
        "bg_prompt": str(thumb_data.get("bg_prompt", prompt)).strip(),
        "line1": str(thumb_data.get("line1", "")).strip(),
        "line2": str(thumb_data.get("line2", "")).strip(),
    }
    return write_json_atomic(workspace / "thumb_data.json", thumb_payload)

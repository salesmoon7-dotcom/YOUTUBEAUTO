from __future__ import annotations

from typing import cast

STAGE1_HANDOFF_SCHEMA_VERSION = "1.0"

HANDOFF_REQUIRED_FIELDS = [
    "version",
    "run_id",
    "row_ref",
    "topic",
    "title",
    "title_for_thumb",
    "description",
    "keywords",
    "bgm",
    "scene_prompts",
    "voice_groups",
    "reason_code",
]


def normalize_stage1_handoff_contract(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    normalized["version"] = f"stage1_handoff.v{STAGE1_HANDOFF_SCHEMA_VERSION}"
    normalized.setdefault("bgm", "")
    normalized.setdefault("keywords", [])
    normalized.setdefault("url", "")
    normalized.setdefault("scene_map", {})
    normalized.setdefault("scene_prompts", [])
    normalized.setdefault("voice_groups", [])
    normalized.setdefault("voice_lines", _voice_lines_from_voice_groups(normalized))
    normalized.setdefault("voice_texts", _voice_texts_from_voice_groups(normalized))
    normalized.setdefault("ref_img_1", "")
    normalized.setdefault("ref_img_2", "")
    normalized.setdefault("videos", [])
    normalized.setdefault("shorts_description", "")
    normalized.setdefault("shorts_voice", "")
    normalized.setdefault("shorts_clip_mapping", "")
    return normalized


def validate_stage1_handoff_contract(payload: dict[str, object]) -> list[str]:
    missing = [field for field in HANDOFF_REQUIRED_FIELDS if field not in payload]
    if missing:
        return [f"missing_{field}" for field in missing]
    if not str(payload.get("version", "")).startswith("stage1_handoff.v"):
        return ["invalid_version"]
    if not isinstance(payload.get("keywords"), list):
        return ["invalid_keywords"]
    if not isinstance(payload.get("videos"), list):
        return ["invalid_videos"]
    if not isinstance(payload.get("scene_map"), dict):
        return ["invalid_scene_map"]
    if not isinstance(payload.get("scene_prompts"), list) or not cast(
        list[object], payload.get("scene_prompts", [])
    ):
        return ["invalid_scene_prompts"]
    if not isinstance(payload.get("voice_groups"), list):
        return ["invalid_voice_groups"]
    if not isinstance(payload.get("voice_lines"), list):
        return ["invalid_voice_lines"]
    if not isinstance(payload.get("voice_texts"), list):
        return ["invalid_voice_texts"]
    return []


def _voice_lines_from_voice_groups(payload: dict[str, object]) -> list[str]:
    voice_groups = payload.get("voice_groups", [])
    if not isinstance(voice_groups, list):
        return []
    indexed_lines: list[tuple[int, str]] = []
    for entry in cast(list[object], voice_groups):
        if not isinstance(entry, dict):
            continue
        typed_entry = cast(dict[str, object], entry)
        scene_index = typed_entry.get("scene_index")
        voice = str(typed_entry.get("voice", "")).strip()
        if isinstance(scene_index, int) and scene_index > 0 and voice:
            indexed_lines.append((scene_index, voice))
    indexed_lines.sort(key=lambda item: item[0])
    return [voice for _, voice in indexed_lines]


def _voice_texts_from_voice_groups(
    payload: dict[str, object],
) -> list[dict[str, object]]:
    voice_groups = payload.get("voice_groups", [])
    if not isinstance(voice_groups, list):
        return []
    normalized_entries: list[tuple[int, dict[str, object]]] = []
    for entry in cast(list[object], voice_groups):
        if not isinstance(entry, dict):
            continue
        typed_entry = cast(dict[str, object], entry)
        scene_index = typed_entry.get("scene_index")
        voice = str(typed_entry.get("voice", "")).strip()
        if not isinstance(scene_index, int) or scene_index <= 0 or not voice:
            continue
        raw_original_voices = typed_entry.get("original_voices", [])
        original_voices = [
            int(item)
            for item in cast(list[object], raw_original_voices)
            if isinstance(item, int) and item > 0
        ]
        if not original_voices:
            original_voices = [scene_index]
        normalized_entries.append(
            (
                scene_index,
                {
                    "col": f"#{scene_index:02d}",
                    "text": voice,
                    "original_voices": original_voices,
                },
            )
        )
    normalized_entries.sort(key=lambda item: item[0])
    return [entry for _, entry in normalized_entries]

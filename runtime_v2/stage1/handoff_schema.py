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
    normalized.setdefault("scene_prompts", [])
    normalized.setdefault("voice_groups", [])
    normalized.setdefault("voice_texts", _voice_texts_from_scene_prompts(normalized))
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
    if not isinstance(payload.get("scene_prompts"), list) or not cast(
        list[object], payload.get("scene_prompts", [])
    ):
        return ["invalid_scene_prompts"]
    if not isinstance(payload.get("voice_groups"), list):
        return ["invalid_voice_groups"]
    if not isinstance(payload.get("voice_texts"), list):
        return ["invalid_voice_texts"]
    return []


def _voice_texts_from_scene_prompts(
    payload: dict[str, object],
) -> list[dict[str, object]]:
    scene_prompts = payload.get("scene_prompts", [])
    if not isinstance(scene_prompts, list):
        return []
    return [
        {
            "col": f"#{index + 1:02d}",
            "text": str(prompt).strip(),
            "original_voices": [index + 1],
        }
        for index, prompt in enumerate(scene_prompts)
        if str(prompt).strip()
    ]

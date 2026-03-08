from __future__ import annotations

import json
import re
from typing import cast


_JSON_FENCE_PATTERN = re.compile(
    r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL
)


def extract_stage1_gpt_plan_json(response_text: str) -> dict[str, object]:
    match = _JSON_FENCE_PATTERN.search(response_text)
    candidate = response_text
    if match is not None:
        candidate = match.group(1)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end < start:
        raise ValueError("missing_json_object")
    payload_obj = cast(object, json.loads(candidate[start : end + 1]))
    if not isinstance(payload_obj, dict):
        raise ValueError("invalid_stage1_plan_json")
    payload = cast(dict[object, object], payload_obj)
    return {str(key): value for key, value in payload.items()}


def parse_stage1_gpt_plan(payload: dict[str, object]) -> dict[str, object]:
    story_outline = payload.get("story_outline")
    scene_prompts = payload.get("scene_prompts")
    voice_groups = payload.get("voice_groups")

    if not isinstance(story_outline, list) or not story_outline:
        raise ValueError("missing_story_outline")
    if not isinstance(scene_prompts, list) or not scene_prompts:
        raise ValueError("missing_scene_prompts")
    if not isinstance(voice_groups, list) or not voice_groups:
        raise ValueError("missing_voice_groups")

    typed_story_outline = cast(list[object], story_outline)
    typed_scene_prompts = cast(list[object], scene_prompts)
    typed_voice_groups = cast(list[object], voice_groups)

    normalized_outline: list[str] = []
    for item in typed_story_outline:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("invalid_story_outline")
        normalized_outline.append(item.strip())

    normalized_prompts: list[str] = []
    for item in typed_scene_prompts:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("invalid_scene_prompts")
        normalized_prompts.append(item.strip())

    normalized_voice_groups: list[dict[str, object]] = []
    for item_obj in typed_voice_groups:
        if not isinstance(item_obj, dict):
            raise ValueError("invalid_voice_groups")
        item = cast(dict[object, object], item_obj)
        scene_index = item.get("scene_index")
        voice = item.get("voice")
        if not isinstance(scene_index, int) or scene_index <= 0:
            raise ValueError("invalid_voice_groups")
        if not isinstance(voice, str) or not voice.strip():
            raise ValueError("invalid_voice_groups")
        normalized_voice_groups.append(
            {"scene_index": scene_index, "voice": voice.strip()}
        )

    if len(normalized_prompts) != len(normalized_voice_groups):
        raise ValueError("scene_voice_count_mismatch")

    return {
        "story_outline": normalized_outline,
        "scene_prompts": normalized_prompts,
        "voice_groups": normalized_voice_groups,
    }


def map_stage1_plan_to_topic_spec(
    topic_spec: dict[str, object], parsed_plan: dict[str, object]
) -> dict[str, object]:
    mapped = dict(topic_spec)
    mapped["story_outline"] = list(cast(list[object], parsed_plan["story_outline"]))
    mapped["scene_prompts"] = list(cast(list[object], parsed_plan["scene_prompts"]))
    mapped["voice_groups"] = list(cast(list[object], parsed_plan["voice_groups"]))
    return mapped


def build_topic_spec_from_gpt_response(
    topic_spec: dict[str, object], response_text: str
) -> dict[str, object]:
    payload = extract_stage1_gpt_plan_json(response_text)
    parsed_plan = parse_stage1_gpt_plan(payload)
    return map_stage1_plan_to_topic_spec(topic_spec, parsed_plan)

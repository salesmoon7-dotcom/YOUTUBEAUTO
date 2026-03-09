from __future__ import annotations

import json
from typing import cast


def build_stage1_raw_output(topic_spec: dict[str, object]) -> str:
    payload = build_stage1_parsed_payload_from_topic_spec(topic_spec)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_stage1_parsed_payload_from_topic_spec(
    topic_spec: dict[str, object],
) -> dict[str, object]:
    topic = str(topic_spec.get("topic", "")).strip()
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    run_id = str(topic_spec.get("run_id", "")).strip()
    scene_prompts = _scene_prompts(topic_spec)
    voice_groups = [
        {"scene_index": index + 1, "voice": "narration"}
        for index in range(len(scene_prompts))
    ]
    return {
        "version": "stage1.v1",
        "run_id": run_id,
        "row_ref": row_ref,
        "topic": topic,
        "title": topic,
        "title_for_thumb": topic,
        "description": f"{topic} 요약 콘텐츠".strip(),
        "keywords": _keywords(topic),
        "scene_prompts": scene_prompts,
        "voice_groups": voice_groups,
        "reason_code": "ok",
    }


def parse_stage1_output(raw_output: str) -> tuple[dict[str, object] | None, list[str]]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return None, ["invalid_stage1_json"]
    if not isinstance(payload, dict):
        return None, ["invalid_stage1_shape"]
    typed = cast(dict[str, object], payload)
    errors = validate_stage1_parsed_payload(typed)
    if errors:
        return None, errors
    return typed, []


def validate_stage1_parsed_payload(payload: dict[str, object]) -> list[str]:
    required = [
        "version",
        "run_id",
        "row_ref",
        "topic",
        "title",
        "title_for_thumb",
        "description",
        "keywords",
        "scene_prompts",
        "voice_groups",
        "reason_code",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        return [f"missing_{key}" for key in missing]
    if str(payload.get("version", "")).strip() != "stage1.v1":
        return ["invalid_stage1_version"]
    scene_prompts = payload.get("scene_prompts")
    if not isinstance(scene_prompts, list) or not scene_prompts:
        return ["invalid_scene_prompts"]
    keywords = payload.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        return ["invalid_keywords"]
    voice_groups = payload.get("voice_groups")
    if not isinstance(voice_groups, list) or len(voice_groups) != len(scene_prompts):
        return ["invalid_voice_groups"]
    return []


def build_stage1_handoff(
    *,
    raw_output_path: str,
    parsed_payload_path: str,
    parsed_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "raw_output_path": raw_output_path,
        "parsed_payload_path": parsed_payload_path,
        "contract": parsed_payload,
        "meta": {
            "version": str(parsed_payload.get("version", "")),
            "row_ref": str(parsed_payload.get("row_ref", "")),
            "run_id": str(parsed_payload.get("run_id", "")),
        },
    }


def _scene_prompts(topic_spec: dict[str, object]) -> list[str]:
    raw_scene_prompts = topic_spec.get("scene_prompts")
    if isinstance(raw_scene_prompts, list):
        prompts = [str(item).strip() for item in raw_scene_prompts if str(item).strip()]
        if prompts:
            return prompts
    topic = str(topic_spec.get("topic", "")).strip()
    fragments = [
        fragment.strip()
        for fragment in topic.replace("?", ".").replace("!", ".").split(".")
        if fragment.strip()
    ]
    if len(fragments) > 1:
        return fragments
    return [f"{topic} opening".strip(), f"{topic} ending".strip()]


def _keywords(topic: str) -> list[str]:
    parts = [part.strip() for part in topic.replace(",", " ").split() if part.strip()]
    if parts:
        return parts[:5]
    return ["topic"]

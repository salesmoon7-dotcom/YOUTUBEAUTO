from __future__ import annotations

import json
import re
from typing import cast

from runtime_v2.stage1.gpt_plan_parser import build_topic_spec_from_gpt_response

_LABEL_PATTERN = re.compile(
    r"^(Title for Thumb|Title|Description|Keywords|Voice|BGM|Scene\s*\d+|#\d+)\s*:?\s*$",
    re.IGNORECASE,
)


def parse_gpt_response_text(
    topic_spec: dict[str, object], response_text: str
) -> tuple[dict[str, object] | None, list[str]]:
    text = str(response_text).strip()
    if not text:
        return None, ["empty_gpt_response_text"]

    try:
        mapped = build_topic_spec_from_gpt_response(topic_spec, text)
        return _canonical_from_topic_spec(mapped), []
    except ValueError:
        pass

    block_payload = _parse_block_response(topic_spec, text)
    errors = _validate_parsed_result(block_payload)
    if errors:
        return None, errors
    return block_payload, []


def _canonical_from_topic_spec(topic_spec: dict[str, object]) -> dict[str, object]:
    topic = str(topic_spec.get("topic", "")).strip()
    scene_prompts = [
        str(item).strip()
        for item in cast(list[object], topic_spec.get("scene_prompts", []))
        if str(item).strip()
    ]
    voice_groups = [
        cast(dict[str, object], item)
        for item in cast(list[object], topic_spec.get("voice_groups", []))
        if isinstance(item, dict)
    ]
    return {
        "title": topic,
        "title_for_thumb": topic,
        "description": f"{topic} 요약 콘텐츠".strip(),
        "keywords": _keywords(topic),
        "bgm": str(topic_spec.get("bgm", "")).strip(),
        "scene_prompts": scene_prompts,
        "voice_groups": voice_groups,
        "story_outline": [str(item).strip() for item in scene_prompts],
    }


def _parse_block_response(
    topic_spec: dict[str, object], response_text: str
) -> dict[str, object]:
    topic = str(topic_spec.get("topic", "")).strip()
    labels: dict[str, list[str]] = {}
    current_label = ""
    for raw_line in response_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label_match = _LABEL_PATTERN.match(line)
        if label_match:
            current_label = label_match.group(1).strip().lower()
            labels.setdefault(current_label, [])
            continue
        if current_label:
            labels.setdefault(current_label, []).append(line)
    scene_prompts = _collect_scene_prompts(labels)
    voice_text = "\n".join(labels.get("voice", []))
    voice_groups = [
        {"scene_index": index + 1, "voice": voice_text or "narration"}
        for index in range(len(scene_prompts))
    ]
    return {
        "title": _join_label(labels, "title") or topic,
        "title_for_thumb": _join_label(labels, "title for thumb")
        or _join_label(labels, "title")
        or topic,
        "description": _join_label(labels, "description")
        or f"{topic} 요약 콘텐츠".strip(),
        "keywords": _split_keywords(_join_label(labels, "keywords"))
        or _keywords(topic),
        "bgm": _join_label(labels, "bgm"),
        "scene_prompts": scene_prompts or [f"{topic} opening", f"{topic} ending"],
        "voice_groups": voice_groups,
        "story_outline": scene_prompts or [f"{topic} opening", f"{topic} ending"],
    }


def _collect_scene_prompts(labels: dict[str, list[str]]) -> list[str]:
    scene_entries: list[tuple[int, str]] = []
    for key, value in labels.items():
        normalized = key.lower()
        match = re.match(r"^(?:scene\s*(\d+)|#(\d+))$", normalized)
        if match is None:
            continue
        raw_index = match.group(1) or match.group(2) or "0"
        index = int(raw_index)
        joined = "\n".join(value).strip()
        if index > 0 and joined:
            scene_entries.append((index, joined))
    scene_entries.sort(key=lambda item: item[0])
    return [content for _, content in scene_entries]


def _join_label(labels: dict[str, list[str]], key: str) -> str:
    return "\n".join(labels.get(key.lower(), [])).strip()


def _split_keywords(text: str) -> list[str]:
    if not text:
        return []
    return [item.strip() for item in re.split(r"[,\n]", text) if item.strip()]


def _keywords(topic: str) -> list[str]:
    parts = [part.strip() for part in topic.replace(",", " ").split() if part.strip()]
    if parts:
        return parts[:5]
    return ["topic"]


def _validate_parsed_result(payload: dict[str, object]) -> list[str]:
    if not str(payload.get("title", "")).strip():
        return ["missing_title"]
    scene_prompts = payload.get("scene_prompts")
    if not isinstance(scene_prompts, list) or not scene_prompts:
        return ["missing_scene_prompts"]
    voice_groups = payload.get("voice_groups")
    if not isinstance(voice_groups, list) or len(voice_groups) != len(scene_prompts):
        return ["invalid_voice_groups"]
    return []

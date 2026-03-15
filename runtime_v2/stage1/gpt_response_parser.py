from __future__ import annotations

import re
from typing import cast

from runtime_v2.stage1.gpt_plan_parser import build_topic_spec_from_gpt_response

_BLOCK_HEADER_PATTERN = re.compile(
    r"^\[(Title for Thumb|Title|Description|Keywords|Voice|BGM|URL|Ref Img 1|Ref Img 2|Shorts Description|Shorts Voice|Shorts Clip Mapping|Scene\s*\d+|#\d+|Video\d+)(?:[^\]]*)\]\s*(?:[:\-].*)?$",
    re.IGNORECASE,
)
_PLAIN_LABEL_PATTERN = re.compile(
    r"^(Title for Thumb|Title|Description|Keywords|Voice|BGM|URL|Ref Img 1|Ref Img 2|Shorts Description|Shorts Voice|Shorts Clip Mapping|Scene\s*\d+|#\d+|Video\d+)\s*(?:[:\-].*)?$",
    re.IGNORECASE,
)
_INLINE_LABEL_PATTERN = re.compile(
    r"^\[?(Title for Thumb|Title|Description|Keywords|Voice|BGM|URL|Ref Img 1|Ref Img 2|Shorts Description|Shorts Voice|Shorts Clip Mapping|Scene\s*\d+|#\d+|Video\d+)\]?\s*:\s*(.+)$",
    re.IGNORECASE,
)
_NUMBERED_LINE_PATTERN = re.compile(r"^\d+\.\s*(.+)$")
_VOICE_RANGE_PATTERN = re.compile(r"voice\s+(\d+)(?:\s*-\s*(\d+))?", re.IGNORECASE)


def parse_gpt_response_text(
    topic_spec: dict[str, object], response_text: str
) -> tuple[dict[str, object] | None, list[str]]:
    text = str(response_text).strip()
    if not text:
        return None, ["empty_gpt_response_text"]

    structured_errors: list[str] = []
    try:
        mapped = build_topic_spec_from_gpt_response(topic_spec, text)
        return _canonical_from_topic_spec(mapped), []
    except ValueError as exc:
        error_code = str(exc).strip() or "structured_parse_failed"
        if error_code != "missing_json_object":
            structured_errors.append(error_code)

    block_payload = _parse_block_response(topic_spec, text)
    errors = _validate_parsed_result(block_payload)
    if errors:
        return None, structured_errors + errors
    if structured_errors:
        block_payload["parse_mode"] = "block_fallback"
    return block_payload, structured_errors


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
    label_voice_ranges: dict[str, tuple[int, int]] = {}
    current_label = ""
    for raw_line in response_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        inline_match = _INLINE_LABEL_PATTERN.match(line)
        if inline_match:
            current_label = inline_match.group(1).strip().lower()
            labels.setdefault(current_label, []).append(inline_match.group(2).strip())
            continue
        label_match = _BLOCK_HEADER_PATTERN.match(line) or _PLAIN_LABEL_PATTERN.match(
            line
        )
        if label_match:
            current_label = label_match.group(1).strip().lower()
            _ = labels.setdefault(current_label, [])
            voice_range = _parse_voice_range(line)
            if voice_range is not None:
                label_voice_ranges[current_label] = voice_range
            continue
        if current_label:
            labels.setdefault(current_label, []).append(line)
    scene_map = _collect_scene_map(labels)
    ordered_scene_indexes = sorted(scene_map)
    scene_prompts = [scene_map[index] for index in ordered_scene_indexes]
    if not scene_prompts:
        scene_prompts = _collect_voice_numbered_lines(labels)
    voice_lines = _collect_voice_numbered_lines(labels)
    ranged_voice_groups = _voice_groups_from_label_ranges(
        ordered_scene_indexes, label_voice_ranges, voice_lines
    )
    if ranged_voice_groups:
        voice_groups = ranged_voice_groups
    elif voice_lines and len(voice_lines) == len(scene_prompts):
        voice_groups = [
            {
                "scene_index": index + 1,
                "voice": voice_lines[index],
                "original_voices": [index + 1],
            }
            for index in range(len(scene_prompts))
        ]
    else:
        voice_text = "\n".join(voice_lines or labels.get("voice", []))
        voice_groups = [
            {
                "scene_index": index + 1,
                "voice": voice_text or "narration",
                "original_voices": [index + 1],
            }
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
        "url": _join_label(labels, "url"),
        "bgm": _join_label(labels, "bgm"),
        "ref_img_1": _join_label(labels, "ref img 1"),
        "ref_img_2": _join_label(labels, "ref img 2"),
        "scene_map": scene_map,
        "scene_prompts": scene_prompts or [f"{topic} opening", f"{topic} ending"],
        "voice_groups": voice_groups,
        "story_outline": scene_prompts or [f"{topic} opening", f"{topic} ending"],
        "voice_lines": voice_lines,
        "videos": _collect_videos(labels),
        "shorts_description": _join_label(labels, "shorts description"),
        "shorts_voice": _join_label(labels, "shorts voice"),
        "shorts_clip_mapping": _join_label(labels, "shorts clip mapping"),
    }


def _collect_scene_map(labels: dict[str, list[str]]) -> dict[int, str]:
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
    return {index: content for index, content in scene_entries}


def _collect_voice_numbered_lines(labels: dict[str, list[str]]) -> list[str]:
    lines = labels.get("voice", [])
    prompts: list[str] = []
    for line in lines:
        for raw_part in line.splitlines():
            part = raw_part.strip()
            if not part:
                continue
            match = _NUMBERED_LINE_PATTERN.match(part)
            if match is not None:
                prompts.append(match.group(1).strip())
    return prompts


def _collect_videos(labels: dict[str, list[str]]) -> list[str]:
    video_entries: list[tuple[int, str]] = []
    for key, value in labels.items():
        match = re.match(r"^video(\d+)$", key.lower())
        if match is None:
            continue
        index = int(match.group(1))
        joined = "\n".join(value).strip()
        if index > 0 and joined:
            video_entries.append((index, joined))
    video_entries.sort(key=lambda item: item[0])
    return [content for _, content in video_entries]


def _parse_voice_range(line: str) -> tuple[int, int] | None:
    match = _VOICE_RANGE_PATTERN.search(line)
    if match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or match.group(1))
    if start <= 0 or end < start:
        return None
    return start, end


def _voice_groups_from_label_ranges(
    ordered_scene_indexes: list[int],
    label_voice_ranges: dict[str, tuple[int, int]],
    voice_lines: list[str],
) -> list[dict[str, object]]:
    if not ordered_scene_indexes or not voice_lines:
        return []
    voice_groups: list[dict[str, object]] = []
    for scene_index in ordered_scene_indexes:
        voice_range = label_voice_ranges.get(f"#{scene_index:02d}")
        if voice_range is None:
            voice_range = label_voice_ranges.get(f"#{scene_index}")
        if voice_range is None:
            return []
        start, end = voice_range
        selected = [
            line.strip() for line in voice_lines[start - 1 : end] if line.strip()
        ]
        if not selected:
            return []
        voice_groups.append(
            {
                "scene_index": scene_index,
                "voice": "\n".join(selected),
                "original_voices": list(range(start, end + 1)),
            }
        )
    return voice_groups


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
    scene_prompts_obj = payload.get("scene_prompts")
    scene_prompts = (
        cast(list[object], scene_prompts_obj)
        if isinstance(scene_prompts_obj, list)
        else None
    )
    if scene_prompts is None or not scene_prompts:
        return ["missing_scene_prompts"]
    voice_groups_obj = payload.get("voice_groups")
    voice_groups = (
        cast(list[object], voice_groups_obj)
        if isinstance(voice_groups_obj, list)
        else None
    )
    if voice_groups is None or len(voice_groups) != len(scene_prompts):
        return ["invalid_voice_groups"]
    return []

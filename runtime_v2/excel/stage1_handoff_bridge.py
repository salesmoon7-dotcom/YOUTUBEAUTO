from __future__ import annotations

import json
from typing import cast

from runtime_v2.stage1.handoff_schema import (
    normalize_stage1_handoff_contract,
    validate_stage1_handoff_contract,
)

MAX_EXCEL_JSON_CELL_LEN = 30000


def export_stage1_handoff_to_excel_row(payload: dict[str, object]) -> dict[str, str]:
    normalized = normalize_stage1_handoff_contract(payload)
    errors = validate_stage1_handoff_contract(normalized)
    if errors:
        raise ValueError(errors[0])
    scene_prompts = cast(list[object], normalized.get("scene_prompts", []))
    scene_map = cast(dict[object, object], normalized.get("scene_map", {}))
    voice_json = json.dumps(normalized.get("voice_groups", []), ensure_ascii=False)
    voice_lines = cast(list[object], normalized.get("voice_lines", []))
    videos = cast(list[object], normalized.get("videos", []))
    row = {
        "URL": str(normalized.get("url", "")),
        "Title": str(normalized.get("title", "")),
        "Title for Thumb": str(normalized.get("title_for_thumb", "")),
        "Description": str(normalized.get("description", "")),
        "Keywords": ", ".join(
            [
                str(item).strip()
                for item in cast(list[object], normalized.get("keywords", []))
                if str(item).strip()
            ]
        ),
        "Voice": (
            "\n".join(
                [str(item).strip() or "n" for item in voice_lines if str(item).strip()]
            )
            or "n"
        ),
        "BGM": str(normalized.get("bgm", "")),
        "Ref Img 1": str(normalized.get("ref_img_1", "")),
        "Ref Img 2": str(normalized.get("ref_img_2", "")),
        "voice_texts.json": json.dumps(
            normalized.get("voice_texts", []), ensure_ascii=False
        ),
        "Shorts Description": str(normalized.get("shorts_description", "")),
        "Shorts Voice": str(normalized.get("shorts_voice", "")),
        "Shorts Clip Mapping": str(normalized.get("shorts_clip_mapping", "")),
        "Shorts\nStatus": "n",
    }
    for index in range(1, 501):
        row[f"#{index:02d}"] = ""
    if scene_map:
        for raw_key, raw_value in scene_map.items():
            key = str(raw_key).strip()
            value = str(raw_value).strip()
            if not key.isdigit() or not value:
                continue
            index = int(key)
            if 1 <= index <= 500:
                row[f"#{index:02d}"] = value
    else:
        for index, prompt in enumerate(scene_prompts[:500], start=1):
            row[f"#{index:02d}"] = str(prompt).strip()
    for index in range(1, 51):
        row[f"Video{index}"] = ""
    for index, video in enumerate(videos[:50], start=1):
        row[f"Video{index}"] = str(video).strip()
    return row


def import_stage1_handoff_from_excel_row(
    *, base_payload: dict[str, object], row: dict[str, object]
) -> dict[str, object]:
    payload = normalize_stage1_handoff_contract(base_payload)
    payload["url"] = _cell_text(row.get("URL", payload.get("url", "")))
    payload["title"] = _cell_text(row.get("Title", payload.get("title", "")))
    payload["title_for_thumb"] = str(
        row.get("Title for Thumb", payload.get("title_for_thumb", ""))
    ).strip()
    payload["description"] = str(
        row.get("Description", payload.get("description", ""))
    ).strip()
    keywords = _cell_text(row.get("Keywords", ""))
    payload["keywords"] = (
        [item.strip() for item in keywords.split(",") if item.strip()]
        if keywords
        else []
    )
    payload["bgm"] = _cell_text(row.get("BGM", payload.get("bgm", "")))
    payload["ref_img_1"] = str(
        row.get("Ref Img 1", payload.get("ref_img_1", ""))
    ).strip()
    payload["ref_img_2"] = str(
        row.get("Ref Img 2", payload.get("ref_img_2", ""))
    ).strip()
    scene_map = _scene_map_from_row(row)
    payload["scene_map"] = scene_map
    payload["scene_prompts"] = [scene_map[key] for key in sorted(scene_map)]
    payload["videos"] = _videos_from_row(row)
    raw_voice_texts = _cell_text(row.get("voice_texts.json", ""))
    if raw_voice_texts:
        payload["voice_texts"] = cast(list[object], json.loads(raw_voice_texts))
    else:
        payload["voice_texts"] = normalize_stage1_handoff_contract(payload)[
            "voice_texts"
        ]
    raw_voice = _cell_text(row.get("Voice", ""))
    if raw_voice and raw_voice.lower() != "n":
        voice_lines = [line.strip() for line in raw_voice.splitlines() if line.strip()]
        payload["voice_lines"] = voice_lines
        payload["voice_texts"] = [
            {"col": f"#{index + 1:02d}", "text": line, "original_voices": [index + 1]}
            for index, line in enumerate(voice_lines)
        ]
        payload["voice_groups"] = [
            {"scene_index": index + 1, "voice": line}
            for index, line in enumerate(voice_lines)
        ]
    payload["shorts_description"] = _cell_text(
        row.get("Shorts Description", payload.get("shorts_description", ""))
    )
    payload["shorts_voice"] = _cell_text(
        row.get("Shorts Voice", payload.get("shorts_voice", ""))
    )
    payload["shorts_clip_mapping"] = _cell_text(
        row.get("Shorts Clip Mapping", payload.get("shorts_clip_mapping", ""))
    )
    errors = validate_stage1_handoff_contract(payload)
    if errors:
        raise ValueError(errors[0])
    return payload


def _scene_map_from_row(row: dict[str, object]) -> dict[int, str]:
    prompts: dict[int, str] = {}
    index = 1
    while True:
        key = f"#{index:02d}"
        if key not in row:
            break
        value = _cell_text(row.get(key, ""))
        if value:
            prompts[index] = value
        index += 1
    return prompts


def _videos_from_row(row: dict[str, object]) -> list[str]:
    videos: list[str] = []
    index = 1
    while index <= 50:
        key = f"Video{index}"
        value = _cell_text(row.get(key, ""))
        if value:
            videos.append(value)
        index += 1
    return videos


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text == "None" else text

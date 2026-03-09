from __future__ import annotations

import json
from typing import cast

from runtime_v2.stage1.handoff_schema import (
    normalize_stage1_handoff_contract,
    validate_stage1_handoff_contract,
)


def export_stage1_handoff_to_excel_row(payload: dict[str, object]) -> dict[str, str]:
    normalized = normalize_stage1_handoff_contract(payload)
    errors = validate_stage1_handoff_contract(normalized)
    if errors:
        raise ValueError(errors[0])
    scene_prompts = cast(list[object], normalized.get("scene_prompts", []))
    row = {
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
        "Voice": json.dumps(normalized.get("voice_groups", []), ensure_ascii=False),
        "BGM": str(normalized.get("bgm", "")),
        "Ref Img 1": str(normalized.get("ref_img_1", "")),
        "Ref Img 2": str(normalized.get("ref_img_2", "")),
        "voice_texts.json": json.dumps(
            normalized.get("voice_texts", []), ensure_ascii=False
        ),
    }
    for index, prompt in enumerate(scene_prompts, start=1):
        row[f"#{index:02d}"] = str(prompt).strip()
    return row


def import_stage1_handoff_from_excel_row(
    *, base_payload: dict[str, object], row: dict[str, object]
) -> dict[str, object]:
    payload = normalize_stage1_handoff_contract(base_payload)
    payload["title"] = str(row.get("Title", payload.get("title", ""))).strip()
    payload["title_for_thumb"] = str(
        row.get("Title for Thumb", payload.get("title_for_thumb", ""))
    ).strip()
    payload["description"] = str(
        row.get("Description", payload.get("description", ""))
    ).strip()
    keywords = str(row.get("Keywords", "")).strip()
    payload["keywords"] = (
        [item.strip() for item in keywords.split(",") if item.strip()]
        if keywords
        else []
    )
    payload["bgm"] = str(row.get("BGM", payload.get("bgm", ""))).strip()
    payload["ref_img_1"] = str(
        row.get("Ref Img 1", payload.get("ref_img_1", ""))
    ).strip()
    payload["ref_img_2"] = str(
        row.get("Ref Img 2", payload.get("ref_img_2", ""))
    ).strip()
    payload["scene_prompts"] = _scene_prompts_from_row(row)
    raw_voice_texts = str(row.get("voice_texts.json", "")).strip()
    if raw_voice_texts:
        payload["voice_texts"] = cast(list[object], json.loads(raw_voice_texts))
    else:
        payload["voice_texts"] = normalize_stage1_handoff_contract(payload)[
            "voice_texts"
        ]
    raw_voice = str(row.get("Voice", "")).strip()
    if raw_voice:
        payload["voice_groups"] = cast(list[object], json.loads(raw_voice))
    errors = validate_stage1_handoff_contract(payload)
    if errors:
        raise ValueError(errors[0])
    return payload


def _scene_prompts_from_row(row: dict[str, object]) -> list[str]:
    prompts: list[str] = []
    index = 1
    while True:
        key = f"#{index:02d}"
        if key not in row:
            break
        value = str(row.get(key, "")).strip()
        if value:
            prompts.append(value)
        index += 1
    return prompts

from __future__ import annotations

import json
from typing import cast

from runtime_v2.stage1.gpt_response_parser import parse_gpt_response_text
from runtime_v2.stage1.handoff_schema import normalize_stage1_handoff_contract


def build_stage1_raw_output_artifact(
    topic_spec: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "row_ref": str(topic_spec.get("row_ref", "")).strip(),
        "run_id": str(topic_spec.get("run_id", "")).strip(),
    }
    browser_evidence = topic_spec.get("browser_evidence")
    if isinstance(browser_evidence, dict):
        payload["browser_evidence"] = {
            "service": str(browser_evidence.get("service", "")).strip(),
            "port": browser_evidence.get("port"),
            "snapshot_path": str(browser_evidence.get("snapshot_path", "")).strip(),
        }
    gpt_capture = topic_spec.get("gpt_capture")
    if isinstance(gpt_capture, dict):
        payload["gpt_capture"] = cast(dict[str, object], gpt_capture)
    response_text = str(topic_spec.get("gpt_response_text", "")).strip()
    if response_text:
        payload["source"] = "gpt_response_text"
        payload["response_text"] = response_text
        return payload
    if "gpt_capture" in payload:
        payload["source"] = "gpt_capture_only"
        payload["response_text"] = ""
        return payload
    fallback_payload = build_stage1_parsed_payload_from_topic_spec(topic_spec)
    payload["source"] = "topic_spec_fallback"
    payload["response_text"] = json.dumps(
        fallback_payload, ensure_ascii=False, indent=2
    )
    return payload


def build_stage1_raw_output(topic_spec: dict[str, object]) -> str:
    payload = build_stage1_raw_output_artifact(topic_spec)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_stage1_parsed_payload_from_topic_spec(
    topic_spec: dict[str, object],
) -> dict[str, object]:
    response_text = str(topic_spec.get("gpt_response_text", "")).strip()
    if response_text:
        parsed_result, errors = parse_gpt_response_text(topic_spec, response_text)
        if parsed_result is None:
            raise ValueError(errors[0] if errors else "invalid_gpt_response_text")
        return _build_stage1_parsed_payload_from_parsed_result(
            topic_spec, parsed_result
        )
    return _build_stage1_parsed_payload_from_enriched_topic_spec(topic_spec)


def _build_stage1_parsed_payload_from_parsed_result(
    topic_spec: dict[str, object], parsed_result: dict[str, object]
) -> dict[str, object]:
    topic = str(topic_spec.get("topic", "")).strip()
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    run_id = str(topic_spec.get("run_id", "")).strip()
    scene_prompts = [
        str(item).strip()
        for item in cast(list[object], parsed_result.get("scene_prompts", []))
        if str(item).strip()
    ]
    voice_groups = [
        cast(dict[str, object], item)
        for item in cast(list[object], parsed_result.get("voice_groups", []))
        if isinstance(item, dict)
    ]
    story_outline = [
        str(item).strip()
        for item in cast(
            list[object], parsed_result.get("story_outline", scene_prompts)
        )
        if str(item).strip()
    ]
    return {
        "version": "stage1.v1",
        "run_id": run_id,
        "row_ref": row_ref,
        "topic": topic,
        "title": str(parsed_result.get("title", topic)).strip() or topic,
        "title_for_thumb": str(
            parsed_result.get("title_for_thumb", parsed_result.get("title", topic))
        ).strip()
        or topic,
        "description": str(
            parsed_result.get("description", f"{topic} 요약 콘텐츠")
        ).strip(),
        "keywords": [
            str(item).strip()
            for item in cast(list[object], parsed_result.get("keywords", []))
            if str(item).strip()
        ],
        "url": str(parsed_result.get("url", "")).strip(),
        "bgm": str(parsed_result.get("bgm", "")).strip(),
        "scene_prompts": scene_prompts,
        "voice_groups": voice_groups,
        "voice_mapping_source": str(
            parsed_result.get("voice_mapping_source", "stage1_parsed")
        ).strip()
        or "stage1_parsed",
        "story_outline": story_outline,
        "ref_img_1": str(parsed_result.get("ref_img_1", "")).strip(),
        "ref_img_2": str(parsed_result.get("ref_img_2", "")).strip(),
        "videos": [
            str(item).strip()
            for item in cast(list[object], parsed_result.get("videos", []))
            if str(item).strip()
        ],
        "shorts_description": str(parsed_result.get("shorts_description", "")).strip(),
        "shorts_voice": str(parsed_result.get("shorts_voice", "")).strip(),
        "shorts_clip_mapping": str(
            parsed_result.get("shorts_clip_mapping", "")
        ).strip(),
        "reason_code": "ok",
        "excel_snapshot_hash": str(topic_spec.get("excel_snapshot_hash", "")),
    }


def _build_stage1_parsed_payload_from_enriched_topic_spec(
    topic_spec: dict[str, object],
) -> dict[str, object]:
    topic = str(topic_spec.get("topic", "")).strip()
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    run_id = str(topic_spec.get("run_id", "")).strip()
    scene_prompts = _scene_prompts(topic_spec)
    raw_voice_groups = topic_spec.get("voice_groups")
    voice_groups = (
        cast(list[object], raw_voice_groups)
        if isinstance(raw_voice_groups, list)
        else [
            {"scene_index": index + 1, "voice": "narration"}
            for index in range(len(scene_prompts))
        ]
    )
    return {
        "version": "stage1.v1",
        "run_id": run_id,
        "row_ref": row_ref,
        "topic": topic,
        "title": topic,
        "title_for_thumb": topic,
        "description": f"{topic} 요약 콘텐츠".strip(),
        "keywords": _keywords(topic),
        "bgm": str(topic_spec.get("bgm", "default_bgm")).strip() or "default_bgm",
        "scene_prompts": scene_prompts,
        "voice_groups": voice_groups,
        "voice_mapping_source": "excel_scene",
        "reason_code": "ok",
        "excel_snapshot_hash": str(topic_spec.get("excel_snapshot_hash", "")),
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
        "bgm",
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
    if not isinstance(voice_groups, list) or not voice_groups:
        return ["invalid_voice_groups"]
    return []


def build_stage1_handoff(
    *,
    raw_output_path: str,
    parsed_payload_path: str,
    parsed_payload: dict[str, object],
) -> dict[str, object]:
    normalized_payload = normalize_stage1_handoff_contract(parsed_payload)
    return {
        "raw_output_path": raw_output_path,
        "parsed_payload_path": parsed_payload_path,
        "contract": normalized_payload,
        "meta": {
            "version": str(normalized_payload.get("version", "")),
            "row_ref": str(normalized_payload.get("row_ref", "")),
            "run_id": str(normalized_payload.get("run_id", "")),
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

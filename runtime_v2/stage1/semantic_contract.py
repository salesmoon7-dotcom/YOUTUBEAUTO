from __future__ import annotations


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
    semantic_errors = validate_stage1_semantic_contract(payload)
    if semantic_errors:
        return semantic_errors
    return []


def validate_stage1_semantic_contract(payload: dict[str, object]) -> list[str]:
    scene_prompts = payload.get("scene_prompts")
    voice_groups = payload.get("voice_groups")
    if not isinstance(scene_prompts, list) or not isinstance(voice_groups, list):
        return []
    errors: list[str] = []
    if not _voice_groups_cover_scenes(voice_groups, len(scene_prompts)):
        errors.append("invalid_voice_groups")
    return errors


def _voice_groups_cover_scenes(voice_groups: list[object], scene_count: int) -> bool:
    if len(voice_groups) != scene_count:
        return False
    scene_indexes: set[int] = set()
    for entry in voice_groups:
        if not isinstance(entry, dict):
            return False
        scene_index = entry.get("scene_index")
        voice = str(entry.get("voice", "")).strip()
        if not isinstance(scene_index, int) or scene_index <= 0 or not voice:
            return False
        if scene_index in scene_indexes:
            return False
        scene_indexes.add(scene_index)
    return scene_indexes == set(range(1, scene_count + 1))

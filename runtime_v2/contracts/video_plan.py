from __future__ import annotations


def build_video_plan(
    *,
    run_id: str,
    row_ref: str,
    topic: str,
    story_outline: list[str],
    scene_plan: list[dict[str, object]],
    asset_plan: dict[str, object],
    voice_plan: dict[str, object],
    reason_code: str,
    evidence: dict[str, object],
) -> dict[str, object]:
    return {
        "contract": "video_plan",
        "contract_version": "1.0",
        "run_id": run_id,
        "row_ref": row_ref,
        "topic": topic,
        "story_outline": story_outline,
        "scene_plan": scene_plan,
        "asset_plan": asset_plan,
        "voice_plan": voice_plan,
        "reason_code": reason_code,
        "evidence": evidence,
    }


def validate_video_plan(payload: dict[str, object]) -> tuple[bool, list[str]]:
    required = ["run_id", "row_ref", "topic", "scene_plan", "asset_plan", "voice_plan", "reason_code", "evidence"]
    missing = [key for key in required if key not in payload]
    return (len(missing) == 0, missing)

from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.topic_spec import validate_topic_spec
from runtime_v2.contracts.video_plan import build_video_plan
from runtime_v2.stage1.result_contract import stage1_result_payload
from runtime_v2.stage2.router import route_video_plan
from runtime_v2.workers.job_runtime import finalize_worker_result, write_json_atomic


def _scene_count(topic_spec: dict[str, object]) -> int:
    raw_scene_prompts = topic_spec.get("scene_prompts")
    if isinstance(raw_scene_prompts, list) and raw_scene_prompts:
        scene_prompts = cast(list[object], raw_scene_prompts)
        return len(scene_prompts)
    topic = str(topic_spec.get("topic", "")).strip()
    if not topic:
        return 1
    fragments = [
        fragment.strip()
        for fragment in topic.replace("?", ".").replace("!", ".").split(".")
        if fragment.strip()
    ]
    if len(fragments) > 1:
        return len(fragments)
    return 2


def _build_scene_plan(topic_spec: dict[str, object]) -> list[dict[str, object]]:
    topic = str(topic_spec.get("topic", "")).strip()
    raw_scene_prompts = topic_spec.get("scene_prompts")
    scene_prompts = (
        cast(list[object], raw_scene_prompts)
        if isinstance(raw_scene_prompts, list)
        else []
    )
    scene_count = _scene_count(topic_spec)
    scenes: list[dict[str, object]] = []
    for index in range(scene_count):
        prompt = ""
        if index < len(scene_prompts):
            candidate = scene_prompts[index]
            if isinstance(candidate, str):
                prompt = candidate.strip()
        if not prompt:
            role = "opening" if index == 0 else f"beat {index + 1}"
            prompt = f"{topic} {role}".strip()
        scenes.append({"scene_index": index + 1, "prompt": prompt})
    return scenes


def _build_voice_plan(
    topic_spec: dict[str, object], scenes: list[dict[str, object]]
) -> dict[str, object]:
    raw_voice_groups = topic_spec.get("voice_groups")
    if isinstance(raw_voice_groups, list):
        typed_voice_groups: list[dict[str, object]] = []
        for entry in cast(list[object], raw_voice_groups):
            if isinstance(entry, dict):
                typed_voice_groups.append(cast(dict[str, object], entry))
            else:
                raise ValueError("artifact_invalid")
        voice_groups = typed_voice_groups
    else:
        voice_groups = [
            {"scene_index": index + 1, "voice": "narration"}
            for index in range(len(scenes))
        ]
    if len(voice_groups) != len(scenes):
        raise ValueError("artifact_invalid")
    for entry in voice_groups:
        if not str(entry.get("voice", "")).strip():
            raise ValueError("artifact_invalid")
        scene_index = entry.get("scene_index")
        if not isinstance(scene_index, int) or scene_index <= 0:
            raise ValueError("artifact_invalid")
    return {
        "mapping_source": "excel_scene",
        "scene_count": len(scenes),
        "groups": voice_groups,
    }


def build_video_plan_from_topic_spec(
    topic_spec: dict[str, object], workspace: Path
) -> dict[str, object]:
    is_valid, _ = validate_topic_spec(topic_spec)
    if not is_valid:
        raise ValueError("invalid_topic_spec")
    topic = str(topic_spec.get("topic", "")).strip()
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    run_id = str(topic_spec.get("run_id", "")).strip()
    assets_root = workspace / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    scenes = _build_scene_plan(topic_spec)
    video_plan = build_video_plan(
        run_id=run_id,
        row_ref=row_ref,
        topic=topic,
        story_outline=[
            f"{topic} scene {index + 1}".strip() for index in range(len(scenes))
        ],
        scene_plan=scenes,
        asset_plan={
            "asset_root": str(workspace.resolve()),
            "common_asset_folder": str(assets_root.resolve()),
        },
        voice_plan=_build_voice_plan(topic_spec, scenes),
        reason_code="ok",
        evidence={
            "source": "chatgpt_runner",
            "workspace": str(workspace.resolve()),
            "excel_snapshot_hash": str(topic_spec.get("excel_snapshot_hash", "")),
        },
    )
    _ = write_json_atomic(workspace / "video_plan.json", video_plan)
    return video_plan


def _stage1_failed(
    workspace: Path,
    *,
    debug_log: str,
    run_id: str,
    row_ref: str,
    error_code: str,
    reason_code: str,
    evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    stage1_result = stage1_result_payload(
        run_id=run_id,
        row_ref=row_ref,
        video_plan_path="",
        debug_log=debug_log,
        reason_code=reason_code,
        next_jobs=[],
        error_code=error_code,
        status="error",
    )
    details: dict[str, object] = {
        "reason_code": reason_code,
        "stage1_result": stage1_result,
    }
    if evidence:
        details["executor"] = evidence
    return finalize_worker_result(
        workspace,
        status="failed",
        stage="chatgpt",
        artifacts=[],
        error_code=error_code,
        retryable=False,
        details=details,
        completion={"state": "blocked", "final_output": False},
    )


def run_stage1_chatgpt_job(
    topic_spec: dict[str, object], workspace: Path, *, debug_log: str
) -> dict[str, object]:
    run_id = str(topic_spec.get("run_id", "")).strip()
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    try:
        video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)
    except ValueError as exc:
        error_code = str(exc) or "invalid_topic_spec"
        return _stage1_failed(
            workspace,
            debug_log=debug_log,
            run_id=run_id,
            row_ref=row_ref,
            error_code=error_code,
            reason_code=error_code,
        )

    video_plan_path = workspace / "video_plan.json"
    worker_result_path = workspace / "result.json"
    try:
        next_jobs, _ = route_video_plan(video_plan)
    except ValueError as exc:
        error_code = str(exc) or "route_failed"
        return _stage1_failed(
            workspace,
            debug_log=debug_log,
            run_id=run_id,
            row_ref=row_ref,
            error_code=error_code,
            reason_code=error_code,
        )
    stage1_result = stage1_result_payload(
        run_id=str(video_plan.get("run_id", "")),
        row_ref=str(video_plan.get("row_ref", "")),
        video_plan_path=str(video_plan_path.resolve()),
        debug_log=debug_log,
        reason_code=str(video_plan.get("reason_code", "ok")),
        next_jobs=next_jobs,
        result_path=str(worker_result_path.resolve()),
    )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="chatgpt",
        artifacts=[video_plan_path],
        retryable=False,
        details={"video_plan": video_plan, "stage1_result": stage1_result},
        next_jobs=next_jobs,
        completion={"state": "planned", "final_output": False},
    )

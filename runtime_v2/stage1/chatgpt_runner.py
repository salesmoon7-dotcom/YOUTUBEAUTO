from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime_v2.contracts.topic_spec import validate_topic_spec
from runtime_v2.contracts.video_plan import build_video_plan
from runtime_v2.stage1.parsed_payload import (
    build_stage1_handoff,
    build_stage1_parsed_payload_from_topic_spec,
    build_stage1_raw_output_artifact,
    validate_stage1_parsed_payload,
)
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
    parsed_payload = build_stage1_parsed_payload_from_topic_spec(topic_spec)
    return build_video_plan_from_stage1_parsed_payload(parsed_payload, workspace)


def attach_gpt_response_text_from_browser_evidence(
    topic_spec: dict[str, object], browser_evidence: dict[str, object]
) -> dict[str, object]:
    snapshot_path = str(browser_evidence.get("snapshot_path", "")).strip()
    if not snapshot_path:
        return dict(topic_spec)
    snapshot_file = Path(snapshot_path)
    if not snapshot_file.exists():
        return dict(topic_spec)
    enriched = dict(topic_spec)
    enriched["gpt_response_text"] = snapshot_file.read_text(encoding="utf-8")
    enriched["gpt_response_source"] = "agent_browser_snapshot"
    return enriched


def build_video_plan_from_stage1_parsed_payload(
    parsed_payload: dict[str, object], workspace: Path
) -> dict[str, object]:
    topic = str(parsed_payload.get("topic", "")).strip()
    row_ref = str(parsed_payload.get("row_ref", "")).strip()
    run_id = str(parsed_payload.get("run_id", "")).strip()
    assets_root = workspace / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    scene_prompts = cast(list[object], parsed_payload.get("scene_prompts", []))
    raw_voice_groups = cast(list[object], parsed_payload.get("voice_groups", []))
    scenes: list[dict[str, object]] = [
        {"scene_index": index + 1, "prompt": str(prompt).strip()}
        for index, prompt in enumerate(scene_prompts)
        if str(prompt).strip()
    ]
    voice_groups: list[dict[str, object]] = []
    for entry in raw_voice_groups:
        if not isinstance(entry, dict):
            raise ValueError("artifact_invalid")
        scene_index = entry.get("scene_index")
        voice = str(entry.get("voice", "")).strip()
        if not isinstance(scene_index, int) or scene_index <= 0 or not voice:
            raise ValueError("artifact_invalid")
        voice_groups.append({"scene_index": scene_index, "voice": voice})
    if len(voice_groups) != len(scenes):
        raise ValueError("artifact_invalid")
    voice_plan: dict[str, object] = {
        "mapping_source": str(
            parsed_payload.get("voice_mapping_source", "stage1_parsed")
        ).strip()
        or "stage1_parsed",
        "scene_count": len(scenes),
        "groups": voice_groups,
    }
    video_plan = build_video_plan(
        run_id=run_id,
        row_ref=row_ref,
        topic=topic,
        story_outline=[
            str(item).strip() for item in scene_prompts if str(item).strip()
        ],
        scene_plan=scenes,
        asset_plan={
            "asset_root": str(workspace.resolve()),
            "common_asset_folder": str(assets_root.resolve()),
        },
        voice_plan=voice_plan,
        reason_code=str(parsed_payload.get("reason_code", "ok")),
        evidence={
            "source": "chatgpt_runner",
            "workspace": str(workspace.resolve()),
            "excel_snapshot_hash": str(parsed_payload.get("excel_snapshot_hash", "")),
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
    browser_evidence_obj = topic_spec.get("browser_evidence", {})
    browser_evidence = (
        cast(dict[str, object], browser_evidence_obj)
        if isinstance(browser_evidence_obj, dict)
        else {}
    )
    topic_spec = attach_gpt_response_text_from_browser_evidence(
        topic_spec, browser_evidence
    )
    run_id = str(topic_spec.get("run_id", "")).strip()
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    is_valid, _ = validate_topic_spec(topic_spec)
    if not is_valid:
        return _stage1_failed(
            workspace,
            debug_log=debug_log,
            run_id=run_id,
            row_ref=row_ref,
            error_code="invalid_topic_spec",
            reason_code="invalid_topic_spec",
        )
    raw_output_path = workspace / "raw_output.json"
    parsed_payload_path = workspace / "parsed_payload.json"
    handoff_path = workspace / "stage1_handoff.json"
    raw_output = build_stage1_raw_output_artifact(topic_spec)
    _ = write_json_atomic(raw_output_path, raw_output)
    parsed_payload = build_stage1_parsed_payload_from_topic_spec(topic_spec)
    errors = validate_stage1_parsed_payload(parsed_payload)
    if errors:
        return _stage1_failed(
            workspace,
            debug_log=debug_log,
            run_id=run_id,
            row_ref=row_ref,
            error_code=errors[0] if errors else "invalid_stage1_output",
            reason_code=errors[0] if errors else "invalid_stage1_output",
            evidence={"raw_output_path": str(raw_output_path.resolve())},
        )
    _ = write_json_atomic(parsed_payload_path, parsed_payload)
    handoff = build_stage1_handoff(
        raw_output_path=str(raw_output_path.resolve()),
        parsed_payload_path=str(parsed_payload_path.resolve()),
        parsed_payload=parsed_payload,
    )
    _ = write_json_atomic(handoff_path, handoff)
    try:
        video_plan = build_video_plan_from_stage1_parsed_payload(
            parsed_payload, workspace
        )
        video_plan["stage1_handoff"] = handoff
        video_plan["parsed_payload"] = parsed_payload
        _ = write_json_atomic(workspace / "video_plan.json", video_plan)
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
        raw_output_path=str(raw_output_path.resolve()),
        parsed_payload_path=str(parsed_payload_path.resolve()),
        handoff_path=str(handoff_path.resolve()),
    )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="chatgpt",
        artifacts=[video_plan_path, raw_output_path, parsed_payload_path, handoff_path],
        retryable=False,
        details={
            "video_plan": video_plan,
            "stage1_result": stage1_result,
            "stage1_handoff": handoff,
        },
        next_jobs=next_jobs,
        completion={"state": "planned", "final_output": False},
    )

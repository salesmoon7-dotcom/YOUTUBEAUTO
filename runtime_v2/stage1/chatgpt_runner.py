from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

from runtime_v2.contracts.topic_spec import validate_topic_spec
from runtime_v2.contracts.video_plan import build_video_plan
from runtime_v2.stage1.result_contract import stage1_result_payload
from runtime_v2.stage2.router import route_video_plan
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import finalize_worker_result, write_json_atomic


LEGACY_ROOT = Path("D:/YOUTUBE_AUTO")
LEGACY_CHATGPT_SCRIPT = Path("scripts/chatgpt_automation.py")


def _scene_count(topic_spec: dict[str, object]) -> int:
    raw_scene_prompts = topic_spec.get("scene_prompts")
    if isinstance(raw_scene_prompts, list) and raw_scene_prompts:
        scene_prompts = cast(list[object], raw_scene_prompts)
        return len(scene_prompts)
    topic = str(topic_spec.get("topic", "")).strip()
    if not topic:
        return 1
    fragments = [fragment.strip() for fragment in topic.replace("?", ".").replace("!", ".").split(".") if fragment.strip()]
    if len(fragments) > 1:
        return len(fragments)
    return 2


def _build_scene_plan(topic_spec: dict[str, object]) -> list[dict[str, object]]:
    topic = str(topic_spec.get("topic", "")).strip()
    raw_scene_prompts = topic_spec.get("scene_prompts")
    scene_prompts = cast(list[object], raw_scene_prompts) if isinstance(raw_scene_prompts, list) else []
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


def _build_voice_plan(topic_spec: dict[str, object], scenes: list[dict[str, object]]) -> dict[str, object]:
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
        voice_groups = [{"scene_index": index + 1, "voice": "narration"} for index in range(len(scenes))]
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


def build_video_plan_from_topic_spec(topic_spec: dict[str, object], workspace: Path) -> dict[str, object]:
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
        story_outline=[f"{topic} scene {index + 1}".strip() for index in range(len(scenes))],
        scene_plan=scenes,
        asset_plan={"asset_root": str(workspace.resolve()), "common_asset_folder": str(assets_root.resolve())},
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
    details: dict[str, object] = {"reason_code": reason_code, "stage1_result": stage1_result}
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


def _resolve_legacy_channel(topic_spec: dict[str, object]) -> int | None:
    raw_channel = topic_spec.get("channel", os.getenv("RUNTIME_V2_CHATGPT_CHANNEL", ""))
    if isinstance(raw_channel, int):
        return raw_channel if raw_channel > 0 else None
    raw_text = str(raw_channel).strip()
    if not raw_text:
        return None
    try:
        channel = int(raw_text)
    except ValueError:
        return None
    return channel if channel > 0 else None


def _parse_row_number(row_ref: str) -> int | None:
    token = row_ref.rsplit("row", 1)[-1].strip()
    if not token.isdigit():
        return None
    row_number = int(token)
    if row_number <= 0:
        return None
    return row_number - 1


def _legacy_rows_result_path(channel: int) -> Path:
    return LEGACY_ROOT / "system" / "chatgpt_rows" / f"chatgpt_rows_ch{channel}.json"


def _int_value(raw_value: object, default: int) -> int:
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if text:
            try:
                return int(text)
            except ValueError:
                return default
    return default


def _collect_scene_prompts(fields: dict[str, object]) -> list[str]:
    scene_entries: list[tuple[int, str]] = []
    for key, value in fields.items():
        key_text = str(key).strip()
        if not key_text.startswith("#"):
            continue
        try:
            scene_index = int(key_text[1:])
        except ValueError:
            continue
        prompt = str(value).strip()
        if prompt:
            scene_entries.append((scene_index, prompt))
    scene_entries.sort(key=lambda item: item[0])
    return [prompt for _, prompt in scene_entries]


def _build_video_plan_from_legacy_row(
    topic_spec: dict[str, object],
    workspace: Path,
    *,
    channel: int,
    executor_result: dict[str, object],
    row_payload: dict[str, object],
    executor_result_path: Path,
    rows_result_path: Path,
) -> dict[str, object]:
    fields_raw = row_payload.get("fields", {})
    fields = cast(dict[object, object], fields_raw) if isinstance(fields_raw, dict) else {}
    normalized_fields: dict[str, object] = {str(key): value for key, value in fields.items()}
    scene_prompts = _collect_scene_prompts(normalized_fields)
    effective_topic_spec = dict(topic_spec)
    if scene_prompts:
        effective_topic_spec["scene_prompts"] = scene_prompts
    title = str(normalized_fields.get("Title", topic_spec.get("topic", ""))).strip()
    voice_text = str(normalized_fields.get("Voice", "")).strip()
    video_plan = build_video_plan_from_topic_spec(effective_topic_spec, workspace)
    video_plan["topic"] = title or str(topic_spec.get("topic", "")).strip()
    video_plan["story_outline"] = scene_prompts or cast(list[str], video_plan.get("story_outline", []))
    video_plan["evidence"] = {
        "source": "legacy_chatgpt_executor",
        "workspace": str(workspace.resolve()),
        "excel_snapshot_hash": str(topic_spec.get("excel_snapshot_hash", "")),
        "legacy_root": str(LEGACY_ROOT.resolve()),
        "legacy_channel": channel,
        "legacy_status": str(row_payload.get("status", "")),
        "legacy_result_json": str(executor_result_path.resolve()),
        "legacy_rows_json": str(rows_result_path.resolve()),
        "legacy_exit_code": _int_value(executor_result.get("exit_code", 1), 1),
        "voice_text_present": bool(voice_text),
    }
    _ = write_json_atomic(workspace / "video_plan.json", video_plan)
    return video_plan


def _run_legacy_stage1(
    topic_spec: dict[str, object],
    workspace: Path,
) -> tuple[dict[str, object] | None, dict[str, object], Path | None, Path | None]:
    channel = _resolve_legacy_channel(topic_spec)
    if channel is None:
        return None, {"reason": "missing_channel"}, None, None
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    row_index = _parse_row_number(row_ref)
    if row_index is None:
        return None, {"reason": "invalid_row_ref", "row_ref": row_ref}, None, None
    script_path = LEGACY_ROOT / LEGACY_CHATGPT_SCRIPT
    if not script_path.exists() or not script_path.is_file():
        return None, {"reason": "missing_legacy_script", "script_path": str(script_path)}, None, None
    pending_payload = {
        "channels": [
            {
                "channel": channel,
                "rows": [
                    {
                        "row_index": row_index,
                        "topic": str(topic_spec.get("topic", "")),
                        "status": str(topic_spec.get("status_snapshot", "")),
                    }
                ],
            }
        ]
    }
    pending_json_path = write_json_atomic(workspace / "legacy_pending.json", pending_payload)
    executor_result_path = workspace / "legacy_executor_result.json"
    command = [
        sys.executable,
        str(script_path),
        "--auto",
        "--channel",
        str(channel),
        "--row",
        str(row_index),
        "--pending-json",
        str(pending_json_path.resolve()),
        "--manager-owned-excel",
        "--result-json",
        str(executor_result_path.resolve()),
    ]
    process_result = run_external_process(
        command,
        cwd=LEGACY_ROOT,
        extra_env={
            "CHATGPT_CANONICAL_TOKEN": "runtime_v2_stage1",
            "CHATGPT_CANONICAL_RUN_ID": str(topic_spec.get("run_id", "")).strip(),
        },
        timeout_sec=1800,
    )
    exit_code = _int_value(process_result.get("exit_code", 1), 1)
    if exit_code != 0:
        return None, {**process_result, "reason": "legacy_executor_failed"}, executor_result_path, None
    if not executor_result_path.exists():
        return None, {**process_result, "reason": "missing_legacy_executor_result"}, executor_result_path, None
    executor_result_raw = cast(object, json.loads(executor_result_path.read_text(encoding="utf-8")))
    executor_result = cast(dict[str, object], executor_result_raw) if isinstance(executor_result_raw, dict) else {}
    rows_result_path = _legacy_rows_result_path(channel)
    if not rows_result_path.exists():
        return None, {**process_result, "reason": "missing_legacy_rows_result"}, executor_result_path, rows_result_path
    rows_payload_raw = cast(object, json.loads(rows_result_path.read_text(encoding="utf-8")))
    rows_payload = cast(dict[str, object], rows_payload_raw) if isinstance(rows_payload_raw, dict) else {}
    rows_value = rows_payload.get("rows", [])
    rows_raw = cast(list[object], rows_value) if isinstance(rows_value, list) else []
    if not isinstance(rows_value, list):
        return None, {**process_result, "reason": "invalid_legacy_rows_result"}, executor_result_path, rows_result_path
    matching_row: dict[str, object] | None = None
    for item in rows_raw:
        if not isinstance(item, dict):
            continue
        row_index_value = cast(dict[object, object], item).get("row_index", -1)
        if _int_value(row_index_value, -1) == row_index:
            matching_row = cast(dict[str, object], item)
            break
    if matching_row is None:
        return None, {**process_result, "reason": "missing_legacy_row_entry"}, executor_result_path, rows_result_path
    return matching_row, executor_result, executor_result_path, rows_result_path


def run_stage1_chatgpt_job(topic_spec: dict[str, object], workspace: Path, *, debug_log: str) -> dict[str, object]:
    run_id = str(topic_spec.get("run_id", "")).strip()
    row_ref = str(topic_spec.get("row_ref", "")).strip()
    try:
        legacy_channel = _resolve_legacy_channel(topic_spec)
        if legacy_channel is None:
            video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)
        else:
            legacy_row, executor_result, executor_result_path, rows_result_path = _run_legacy_stage1(topic_spec, workspace)
            if legacy_row is None or executor_result_path is None:
                reason_code = str(executor_result.get("reason", "legacy_executor_failed"))
                return _stage1_failed(
                    workspace,
                    debug_log=debug_log,
                    run_id=run_id,
                    row_ref=row_ref,
                    error_code=reason_code,
                    reason_code=reason_code,
                    evidence=executor_result,
                )
            video_plan = _build_video_plan_from_legacy_row(
                topic_spec,
                workspace,
                channel=legacy_channel,
                executor_result=executor_result,
                row_payload=legacy_row,
                executor_result_path=executor_result_path,
                rows_result_path=cast(Path, rows_result_path),
            )
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

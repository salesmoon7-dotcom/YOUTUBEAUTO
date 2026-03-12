from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time

from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.topic_spec import snapshot_hash_for_excel_snapshot
from runtime_v2.contracts.job_contract import build_explicit_job_contract
from runtime_v2.excel.source import read_excel_row
from runtime_v2.excel.selector import select_topic_spec
from runtime_v2.excel.state_store import (
    finalize_excel_status,
    merge_video_plan_to_excel,
    merge_stage1_handoff_to_excel,
    update_excel_status,
)
from runtime_v2.gui_adapter import build_gui_status_payload
from runtime_v2.latest_run import write_excel_sync_runtime_snapshot
from runtime_v2.result_router import attach_failure_summary
from runtime_v2.workers.job_runtime import write_json_atomic


def _safe_sheet_token(sheet_name: str) -> str:
    lowered = sheet_name.strip().lower()
    token = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in lowered
    )
    return token or "sheet"


def seed_excel_row(
    *,
    config: RuntimeConfig,
    run_id: str,
    excel_path: str | Path,
    sheet_name: str,
    row_index: int,
) -> dict[str, object]:
    topic_spec = select_topic_spec(
        excel_path, sheet_name=sheet_name, row_index=row_index, run_id=run_id
    )
    if topic_spec is None:
        return {
            "status": "no_work",
            "code": "NO_WORK",
            "reason_code": "no_work",
            "worker_launched": False,
        }
    row_ref = str(topic_spec["row_ref"])
    snapshot_hash = str(topic_spec.get("excel_snapshot_hash", "")).strip()
    safe_sheet = _safe_sheet_token(sheet_name)
    job_id = f"chatgpt-{safe_sheet}-{row_index + 1}"
    contract = build_explicit_job_contract(
        job_id=job_id,
        workload="chatgpt",
        checkpoint_key=f"topic_spec:{row_ref}:{snapshot_hash}",
        payload={
            "run_id": run_id,
            "row_ref": row_ref,
            "excel_path": str(Path(excel_path).resolve()),
            "sheet_name": sheet_name,
            "row_index": row_index,
            "topic_spec": topic_spec,
        },
    )
    contract_path = config.input_root / "chatgpt" / f"{job_id}.job.json"
    _ = write_json_atomic(contract_path, contract)
    status_updated = update_excel_status(
        excel_path,
        sheet_name=sheet_name,
        row_index=row_index,
        next_status="Seeded",
        reason_code="seeded",
    )
    if not status_updated:
        return {
            "status": "failed",
            "code": "EXCEL_STATUS_UPDATE_FAILED",
            "reason_code": "excel_status_update_failed",
            "worker_launched": False,
            "job_id": job_id,
            "topic_spec": topic_spec,
            "contract": contract,
            "contract_path": str(contract_path.resolve()),
        }
    return {
        "status": "seeded",
        "code": "SEEDED_JOB",
        "reason_code": "seeded",
        "worker_launched": False,
        "job_id": job_id,
        "topic_spec": topic_spec,
        "contract": contract,
        "contract_path": str(contract_path.resolve()),
    }


def mark_excel_row_running(
    *,
    excel_path: str | Path,
    sheet_name: str,
    row_index: int,
) -> bool:
    return update_excel_status(
        excel_path,
        sheet_name=sheet_name,
        row_index=row_index,
        next_status="Running",
        reason_code="running",
    )


def merge_stage1_result(
    *,
    excel_path: str | Path,
    sheet_name: str,
    row_index: int,
    video_plan: dict[str, object],
) -> bool:
    evidence = video_plan.get("evidence", {})
    if isinstance(evidence, dict):
        expected_snapshot_hash = str(evidence.get("excel_snapshot_hash", "")).strip()
        if expected_snapshot_hash:
            row_map = read_excel_row(
                excel_path, sheet_name=sheet_name, row_index=row_index
            )
            current_topic = (
                ""
                if row_map.get("Topic") is None
                else str(row_map.get("Topic", "")).strip()
            )
            current_status = (
                ""
                if row_map.get("Status") is None
                else str(row_map.get("Status", "")).strip()
            )
            current_snapshot_hash = snapshot_hash_for_excel_snapshot(
                f"{current_topic}|{current_status}|{sheet_name}|{row_index}"
            )
            if current_snapshot_hash != expected_snapshot_hash:
                return False
    summary = json.dumps(
        {
            "topic": video_plan.get("topic", ""),
            "story_outline": video_plan.get("story_outline", []),
        },
        ensure_ascii=True,
    )
    merged = merge_video_plan_to_excel(
        excel_path,
        sheet_name=sheet_name,
        row_index=row_index,
        next_status="OK",
        summary=summary,
        reason_code=str(video_plan.get("reason_code", "ok")),
    )
    if not merged:
        return False
    handoff_raw = video_plan.get("stage1_handoff")
    if isinstance(handoff_raw, dict):
        contract = handoff_raw.get("contract")
        if isinstance(contract, dict):
            _ = merge_stage1_handoff_to_excel(
                excel_path,
                sheet_name=sheet_name,
                row_index=row_index,
                parsed_payload=contract,
            )
    return True


def finalize_excel_row(
    *,
    excel_path: str | Path,
    sheet_name: str,
    row_index: int,
    completion_state: str,
    final_output: str,
    reason_code: str,
) -> bool:
    completed_states = {"completed", "succeeded"}
    next_status = (
        "Done"
        if completion_state in completed_states and final_output.strip()
        else "partial"
    )
    return finalize_excel_status(
        excel_path,
        sheet_name=sheet_name,
        row_index=row_index,
        next_status=next_status,
        result_path=final_output,
        reason_code=reason_code,
    )


def sync_final_video_result(
    *,
    config: RuntimeConfig,
    excel_path: str | Path,
    sheet_name: str,
    row_index: int,
    worker_result: dict[str, object],
    run_id: str,
    artifact_root: Path,
    debug_log: str,
) -> bool:
    completion_raw = worker_result.get("completion", {})
    completion = completion_raw if isinstance(completion_raw, dict) else {}
    completion_state = str(completion.get("state", "")).strip()
    hinted_final_output_path = str(completion.get("final_artifact_path", "")).strip()
    final_output_enabled = bool(completion.get("final_output", False)) or bool(
        hinted_final_output_path
    )
    final_output_path = hinted_final_output_path if final_output_enabled else ""
    details_raw = worker_result.get("details", {})
    details = details_raw if isinstance(details_raw, dict) else {}
    raw_reason_code = details.get("reason_code", worker_result.get("error_code", "ok"))
    if raw_reason_code is None:
        reason_code = "ok"
    else:
        reason_code = str(raw_reason_code).strip() or "ok"
    updated = finalize_excel_row(
        excel_path=excel_path,
        sheet_name=sheet_name,
        row_index=row_index,
        completion_state=completion_state,
        final_output=final_output_path,
        reason_code=reason_code,
    )
    artifacts: list[Path] = []
    if final_output_path:
        artifact_path = Path(final_output_path)
        if artifact_path.exists() and artifact_path.is_file():
            artifacts.append(artifact_path)
    gui_payload = build_gui_status_payload(
        {
            "status": "ok" if updated else "failed",
            "code": "OK" if updated else "EXCEL_SYNC_FAILED",
            "queue_status": "completed" if updated else "failed",
            "debug_log": debug_log,
            "completion_state": completion_state,
            "final_output": final_output_enabled,
            "final_artifact": str(completion.get("final_artifact", "")),
            "final_artifact_path": final_output_path,
        },
        run_id=run_id,
        mode="excel_sync",
        stage="final_video_sync",
        exit_code=0 if updated else 1,
    )
    write_excel_sync_runtime_snapshot(
        config,
        run_id=run_id,
        status="ok" if updated else "failed",
        code="OK" if updated else "EXCEL_SYNC_FAILED",
        debug_log=debug_log,
        gui_payload=gui_payload,
        artifacts=artifacts,
        metadata={
            "run_id": run_id,
            "debug_log": debug_log,
            "completion_state": completion_state,
            "final_output": final_output_enabled,
            "final_artifact": str(completion.get("final_artifact", "")),
            "final_artifact_path": final_output_path,
            "reason_code": reason_code,
            "excel_synced": updated,
        },
        artifact_root=artifact_root,
    )
    return updated


def write_failure_summary(
    config: RuntimeConfig,
    *,
    run_id: str,
    reason_code: str,
    summary: str,
    evidence_refs: list[str],
    debug_log: str,
) -> Path:
    payload = {
        "run_id": run_id,
        "reason_code": reason_code,
        "summary": summary,
        "evidence_refs": evidence_refs[:3],
        "debug_log": debug_log,
        "ts": round(time(), 3),
    }
    path = config.failure_summary_file
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, indent=2))
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return path


def sync_failure_result(
    *,
    config: RuntimeConfig,
    run_id: str,
    reason_code: str,
    summary: str,
    evidence_refs: list[str],
    debug_log: str,
    artifact_root: Path,
) -> bool:
    failure_path = write_failure_summary(
        config,
        run_id=run_id,
        reason_code=reason_code,
        summary=summary,
        evidence_refs=evidence_refs,
        debug_log=debug_log,
    )
    metadata = attach_failure_summary(
        {
            "run_id": run_id,
            "reason_code": reason_code,
            "summary": summary,
            "debug_log": debug_log,
            "status": "failed",
        },
        str(failure_path),
    )
    gui_payload = build_gui_status_payload(
        {
            "status": "failed",
            "code": reason_code,
            "queue_status": "failed",
            "debug_log": debug_log,
            "completion_state": "failed",
        },
        run_id=run_id,
        mode="excel_sync",
        stage="failure_summary",
        exit_code=1,
    )
    write_excel_sync_runtime_snapshot(
        config,
        run_id=run_id,
        status="failed",
        code=reason_code,
        debug_log=debug_log,
        gui_payload=gui_payload,
        artifacts=[],
        metadata=metadata,
        artifact_root=artifact_root,
    )
    return failure_path.exists() and config.result_router_file.exists()

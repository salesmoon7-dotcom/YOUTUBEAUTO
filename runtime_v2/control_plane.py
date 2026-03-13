from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import Callable, cast

from runtime_v2.bootstrap import ensure_runtime_bootstrap
from runtime_v2.config import GpuWorkload, RuntimeConfig
from runtime_v2.control_plane_feeder import (
    archived_contract_counts,
    invalid_reason_summary,
    job_from_explicit_payload,
    payload_paths_are_local,
    seed_local_jobs,
)
from runtime_v2.debug_log import append_debug_event, debug_log_path
from runtime_v2.error_codes import normalize_error_code, select_worker_error_code
from runtime_v2.gui_adapter import build_gui_status_payload
from runtime_v2.latest_run import (
    normalize_runtime_snapshot_metadata,
    write_control_plane_runtime_snapshot,
)
from runtime_v2.agent_browser.evidence import build_agent_browser_evidence
from runtime_v2.gpt_autospawn import apply_autospawn_decision
from runtime_v2.gpt_pool_monitor import tick_gpt_status
from runtime_v2.manager import merge_stage1_result, sync_final_video_result
from runtime_v2 import recovery_policy
from runtime_v2.queue_store import QueueStore, QueueStoreError
from runtime_v2.state_machine import (
    append_transition_record,
    can_transition,
    transition_record,
)
from runtime_v2.stage1.chatgpt_runner import run_stage1_chatgpt_job
from runtime_v2.stage2.router import route_video_plan
from runtime_v2.stage2.canva_worker import run_canva_job
from runtime_v2.stage2.geminigen_worker import run_geminigen_job
from runtime_v2.stage2.genspark_worker import run_genspark_job
from runtime_v2.stage2.seaart_worker import run_seaart_job
from runtime_v2.stage3.render_worker import run_render_job
from runtime_v2.worker_registry import update_worker_state
from runtime_v2.workers.agent_browser_worker import (
    run_agent_browser_verify_job,
    run_agent_browser_verify_safe_mode_job,
)
from runtime_v2.workers.dev_implement_worker import run_dev_implement_job
from runtime_v2.workers.dev_plan_worker import run_dev_plan_job
from runtime_v2.workers.dev_replan_worker import run_dev_replan_job
from runtime_v2.workers.kenburns_worker import run_kenburns_job
from runtime_v2.workers.qwen3_worker import run_qwen3_job
from runtime_v2.workers.rvc_worker import run_rvc_job
from runtime_v2.contracts.job_contract import (
    JobContract,
    build_explicit_job_contract,
)
from runtime_v2.supervisor import run_gated

MAX_CHAIN_DEPTH = 4
MAX_NEXT_JOBS = 4
MAX_STAGE1_DECLARED_NEXT_JOBS = 12
PROMOTION_GATE_ORDER = {"": 0, "A": 1, "B": 2, "C": 3, "D": 4}
RVC_SOURCE_MODE_PRIORITY = {"tts-source": 2, "gemi-video-source": 1}


def _row_closeout_context(
    job: JobContract, completion: dict[str, object] | None, control_run_id: str
) -> tuple[str, bool]:
    if (
        job.workload == "render"
        and completion is not None
        and bool(completion.get("final_output", False))
    ):
        row_run_id = str(job.payload.get("run_id", "")).strip()
        if row_run_id:
            return row_run_id, True
    return control_run_id, False


def run_control_loop_once(
    owner: str,
    config: RuntimeConfig | None = None,
    run_id: str = "control_loop",
    *,
    allow_runtime_side_effects: bool = True,
) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
    default_config = RuntimeConfig()
    if allow_runtime_side_effects:
        ensure_runtime_bootstrap(
            runtime_config,
            workload="qwen3_tts",
            run_id="control-bootstrap",
            mode="control_loop",
        )
        _ = tick_gpt_status(runtime_config.gpt_status_file, runtime_config)
        _ = apply_autospawn_decision(runtime_config.gpt_status_file, runtime_config)
    now = time()
    queue_file = getattr(
        runtime_config,
        "queue_store_file",
        default_config.queue_store_file,
    )
    events_file = getattr(
        runtime_config,
        "control_plane_events_file",
        default_config.control_plane_events_file,
    )
    artifact_root = getattr(
        runtime_config, "artifact_root", default_config.artifact_root
    )
    queue_store = QueueStore(queue_file)
    try:
        jobs = _load_jobs(queue_store)
    except QueueStoreError:
        invalid_debug_log = str(debug_log_path(runtime_config.debug_log_root, run_id))
        gui_payload = _build_control_gui_status(
            run_id=run_id,
            stage="queue_store",
            exit_code=1,
            status={
                "queue_status": "failed",
                "error_code": "QUEUE_STORE_INVALID",
            },
        )
        write_control_plane_runtime_snapshot(
            runtime_config,
            run_id=run_id,
            status="failed",
            code="QUEUE_STORE_INVALID",
            debug_log=invalid_debug_log,
            gui_payload=gui_payload,
            artifacts=[],
            metadata={
                "run_id": run_id,
                "mode": "control_loop",
                "status": "failed",
                "code": "QUEUE_STORE_INVALID",
                "queue_status": "failed",
                "worker_error_code": "QUEUE_STORE_INVALID",
                "debug_log": invalid_debug_log,
                "ts": round(time(), 3),
            },
        )
        _ = _append_control_event(
            {
                "event": "queue_store_invalid",
                "queue_file": str(queue_file),
                "code": "QUEUE_STORE_INVALID",
            },
            events_file,
            run_id=run_id,
        )
        return {"status": "failed", "code": "QUEUE_STORE_INVALID"}
    _recover_stale_running_jobs(
        queue_store, jobs, now, runtime_config, events_file, run_id=run_id
    )
    _fail_closed_blocked_rows(queue_store, jobs, events_file, run_id=run_id)
    job = _next_runnable_job(jobs, now)
    if job is None:
        accepted_count, invalid_count = archived_contract_counts(
            runtime_config.input_root
        )
        seeded_jobs = seed_local_jobs(runtime_config)
        if seeded_jobs:
            jobs = _load_jobs(queue_store)
            job = _next_runnable_job(jobs, now)
            if job is not None:
                gui_payload = _build_control_gui_status(
                    run_id=run_id,
                    stage="seeded_queue",
                    exit_code=0,
                    status={
                        "seeded_jobs": len(seeded_jobs),
                        "queue_status": "seeded",
                        "accepted_count": accepted_count,
                        "invalid_count": invalid_count,
                        "invalid_reason": invalid_reason_summary(
                            runtime_config.input_root
                        ),
                    },
                )
                write_control_plane_runtime_snapshot(
                    runtime_config,
                    run_id=run_id,
                    status="seeded",
                    code="SEEDED_JOB",
                    debug_log=str(
                        debug_log_path(runtime_config.debug_log_root, run_id)
                    ),
                    gui_payload=gui_payload,
                    artifacts=[],
                    metadata={
                        "run_id": run_id,
                        "mode": "control_loop",
                        "status": "seeded",
                        "code": "SEEDED_JOB",
                        "job_id": "",
                        "workload": "",
                        "success": True,
                        "exit_code": 0,
                        "debug_log": str(
                            debug_log_path(runtime_config.debug_log_root, run_id)
                        ),
                        "queue_status": "seeded",
                        "seeded_jobs": len(seeded_jobs),
                        "accepted_count": accepted_count,
                        "invalid_count": invalid_count,
                        "invalid_reason": invalid_reason_summary(
                            runtime_config.input_root
                        ),
                        "ts": round(time(), 3),
                    },
                )
                _ = append_debug_event(
                    debug_log_path(runtime_config.debug_log_root, run_id),
                    event="control_loop_seeded",
                    payload={
                        "run_id": run_id,
                        "seeded_jobs": [
                            seeded_job.to_dict() for seeded_job in seeded_jobs
                        ],
                        "accepted_count": accepted_count,
                        "invalid_count": invalid_count,
                        "invalid_reason": invalid_reason_summary(
                            runtime_config.input_root
                        ),
                    },
                )
                return {
                    "status": "seeded",
                    "code": "SEEDED_JOB",
                    "seeded_jobs": [seeded_job.to_dict() for seeded_job in seeded_jobs],
                }
        gui_payload = _build_control_gui_status(
            run_id=run_id,
            stage="idle",
            exit_code=0,
            status={
                "queue_status": "idle",
                "seeded_jobs": 0,
                "accepted_count": accepted_count,
                "invalid_count": invalid_count,
                "invalid_reason": invalid_reason_summary(runtime_config.input_root),
            },
        )
        write_control_plane_runtime_snapshot(
            runtime_config,
            run_id=run_id,
            status="idle",
            code="NO_JOB",
            debug_log=str(debug_log_path(runtime_config.debug_log_root, run_id)),
            gui_payload=gui_payload,
            artifacts=[],
            metadata={
                "run_id": run_id,
                "mode": "control_loop",
                "status": "idle",
                "code": "NO_JOB",
                "job_id": "",
                "workload": "",
                "success": True,
                "exit_code": 0,
                "debug_log": str(debug_log_path(runtime_config.debug_log_root, run_id)),
                "queue_status": "idle",
                "seeded_jobs": 0,
                "accepted_count": accepted_count,
                "invalid_count": invalid_count,
                "invalid_reason": invalid_reason_summary(runtime_config.input_root),
                "ts": round(time(), 3),
            },
        )
        _ = append_debug_event(
            debug_log_path(runtime_config.debug_log_root, run_id),
            event="control_loop_idle",
            payload={
                "run_id": run_id,
                "queue_status": "idle",
                "accepted_count": accepted_count,
                "invalid_count": invalid_count,
                "invalid_reason": invalid_reason_summary(runtime_config.input_root),
            },
        )
        return {"status": "idle", "code": "NO_JOB"}

    previous_status = job.status
    if can_transition(previous_status, "running"):
        job.status = "running"
        _ = _upsert_job(queue_store, job)
        running_record = transition_record(job.job_id, previous_status, job.status)
        running_record["routed_from"] = str(job.payload.get("routed_from", ""))
        running_record["chain_depth"] = _to_int(job.payload.get("chain_depth", 0))
        _ = _append_transition_record(running_record, events_file, run_id=run_id)

    mock_chain = _mock_chain_enabled(
        job, allow_mock_chain=runtime_config.allow_mock_chain
    )
    if mock_chain:
        result: dict[str, object] = {
            "status": "ok",
            "code": "OK",
            "workload": job.workload,
            "worker_result": _run_worker(
                job,
                runtime_config.artifact_root,
                registry_file=runtime_config.worker_registry_file,
                allow_mock_chain=runtime_config.allow_mock_chain,
            ),
        }
    elif (
        job.workload == "agent_browser_verify"
        and not allow_runtime_side_effects
        and bool(job.payload.get("allow_in_safe_mode", False))
    ):
        result = {
            "status": "ok",
            "code": "OK",
            "workload": job.workload,
            "worker_result": run_agent_browser_verify_safe_mode_job(
                job,
                runtime_config.artifact_root,
            ),
        }
    else:
        result = run_gated(
            owner=owner,
            execute=lambda: _run_worker(
                job,
                runtime_config.artifact_root,
                registry_file=runtime_config.worker_registry_file,
                allow_mock_chain=runtime_config.allow_mock_chain,
            ),
            workload=job.workload,
            config=runtime_config,
            run_id=run_id,
            require_browser_healthy=True,
            allow_runtime_side_effects=allow_runtime_side_effects,
        )
    browser_payload = _mapping_from_obj(result.get("browser", {}))
    browser_events_obj: object = (
        [] if browser_payload is None else browser_payload.get("events", [])
    )
    if isinstance(browser_events_obj, list):
        browser_events = cast(list[object], browser_events_obj)
        for raw_event in browser_events:
            browser_event = _mapping_from_obj(raw_event)
            if browser_event is None:
                continue
            browser_event["run_id"] = run_id
            _ = _append_control_event(browser_event, events_file, run_id=run_id)
    worker_result = _worker_result_from_runtime(result)
    artifact_path: Path | None = None
    worker_contract = _worker_result_contract(worker_result)
    runtime_error_code = normalize_error_code(str(result.get("code", "FAILED")).strip())
    if runtime_error_code and runtime_error_code != "OK":
        worker_contract = _normalize_runtime_failure_contract(
            worker_contract,
            runtime_error_code=runtime_error_code,
            workload=job.workload,
        )
    worker_artifacts = _worker_artifact_paths(worker_contract)
    worker_ok = _worker_succeeded(worker_contract)
    worker_manifest_path = str(
        worker_contract.get("manifest_path", worker_result.get("manifest_path", ""))
    )
    worker_result_path = str(
        worker_contract.get("result_path", worker_result.get("result_path", ""))
    )
    next_jobs_entries = _next_jobs_entries(worker_contract)
    next_jobs_count = len(next_jobs_entries)
    completion = _mapping_from_obj(worker_contract.get("completion", {}))
    accepted_count, invalid_count = archived_contract_counts(runtime_config.input_root)
    seeded_downstream: list[JobContract] = []
    success = result.get("status") == "ok" and worker_ok
    if result.get("status") == "ok" and worker_ok:
        if job.workload == "chatgpt":
            details = _mapping_from_obj(worker_contract.get("details", {}))
            video_plan = (
                None
                if details is None
                else _mapping_from_obj(details.get("video_plan", {}))
            )
            excel_path = str(job.payload.get("excel_path", "")).strip()
            sheet_name = str(job.payload.get("sheet_name", "")).strip()
            row_index = _to_int(job.payload.get("row_index", -1))
            if video_plan is not None and excel_path and sheet_name and row_index >= 0:
                _ = merge_stage1_result(
                    excel_path=excel_path,
                    sheet_name=sheet_name,
                    row_index=row_index,
                    video_plan=video_plan,
                )
        seeded_downstream = _seed_declared_next_jobs(
            queue_file,
            jobs,
            worker_contract,
            parent_job=job,
            events_file=events_file,
            run_id=run_id,
            artifact_root=artifact_root,
        )
        if worker_artifacts:
            artifact_path = worker_artifacts[0]
        else:
            artifact_path = _write_worker_artifact(job, worker_result, artifact_root)
        if seeded_downstream:
            for downstream_job in seeded_downstream:
                _ = _append_transition_record(
                    {
                        "job_id": downstream_job.job_id,
                        "previous_status": "declared",
                        "status": "queued",
                        "routed_from": job.job_id,
                        "chain_depth": _to_int(
                            downstream_job.payload.get("chain_depth", 0)
                        ),
                        "ts": round(time(), 3),
                    },
                    events_file,
                )
    elif not success:
        restart_exhausted_terminal_block = bool(
            str(worker_contract.get("error_code", "")) == "BROWSER_RESTART_EXHAUSTED"
            and result.get("status") == "blocked"
        )
        failure_next_jobs = worker_contract.get("next_jobs", [])
        if restart_exhausted_terminal_block:
            failure_next_jobs = []
        elif not isinstance(failure_next_jobs, list) or not failure_next_jobs:
            failure_next_jobs = _agent_browser_failure_next_jobs(job)
        if failure_next_jobs:
            seeded_downstream = _seed_declared_next_jobs(
                queue_file,
                jobs,
                {"next_jobs": failure_next_jobs},
                parent_job=job,
                events_file=events_file,
                run_id=run_id,
                artifact_root=artifact_root,
            )
    worker_retryable = bool(worker_contract.get("retryable", False))
    blocked_failure = bool(
        not success and str(worker_contract.get("status", "")) == "blocked"
    )
    recovery = _evaluate_recovery(
        job,
        success=bool(success),
        blocked=blocked_failure,
        retryable=worker_retryable,
        config=runtime_config,
    )
    next_status = _next_status_for_recovery(recovery)
    backoff_sec = _to_float(recovery.get("backoff_sec", 0), 0.0)
    raw_completion_state = (
        "" if completion is None else str(completion.get("state", ""))
    )
    completion_state = _normalized_completion_state(
        raw_completion_state,
        success=bool(success),
        blocked=blocked_failure,
        retryable=worker_retryable,
    )
    result_status = "ok" if success else "blocked" if blocked_failure else "failed"
    canonical_worker_error_code = select_worker_error_code(
        {
            "worker_error_code": worker_contract.get(
                "error_code", worker_result.get("error_code", "")
            ),
            "error_code": runtime_error_code,
        }
    )
    if (
        not success
        and result_status == "failed"
        and runtime_error_code == "OK"
        and canonical_worker_error_code not in {"", "OK", "FAILED"}
    ):
        runtime_error_code = canonical_worker_error_code

    if can_transition(job.status, next_status):
        previous_status = job.status
        job.status = next_status
        job.attempts += 0 if success or blocked_failure else 1
        if next_status == "retry":
            next_attempt_at = round(
                now + _to_float(recovery.get("backoff_sec", 0), 0.0), 3
            )
            job.payload["next_attempt_at"] = next_attempt_at
        else:
            _ = job.payload.pop("next_attempt_at", None)
        _ = _upsert_job(queue_store, job)
        completed_record = transition_record(job.job_id, previous_status, job.status)
        completed_record["routed_from"] = str(job.payload.get("routed_from", ""))
        completed_record["chain_depth"] = _to_int(job.payload.get("chain_depth", 0))
        _ = _append_transition_record(completed_record, events_file, run_id=run_id)

    control_debug_log = debug_log_path(runtime_config.debug_log_root, run_id)
    gui_status: dict[str, object] = {
        "status": result_status,
        "code": "OK" if success else runtime_error_code,
        "queue_status": job.status,
        "job_id": job.job_id,
        "workload": job.workload,
        "attempts": job.attempts,
        "next_jobs_count": next_jobs_count,
        "routed_count": len(seeded_downstream),
        "chain_depth": _to_int(job.payload.get("chain_depth", 0)),
        "worker_stage": str(
            worker_contract.get("stage", result.get("status", "unknown"))
        ),
        "worker_error_code": canonical_worker_error_code,
        "manifest_path": worker_manifest_path,
        "result_path": worker_result_path,
        "backoff_sec": backoff_sec,
        "completion_state": completion_state,
        "final_output": False
        if completion is None
        else bool(completion.get("final_output", False)),
        "final_artifact": ""
        if completion is None
        else str(completion.get("final_artifact", "")),
        "final_artifact_path": ""
        if completion is None
        else str(completion.get("final_artifact_path", "")),
        "accepted_count": accepted_count,
        "invalid_count": invalid_count,
        "invalid_reason": invalid_reason_summary(runtime_config.input_root),
        "debug_log": str(control_debug_log),
    }
    snapshot_run_id, row_closeout_active = _row_closeout_context(
        job, completion, run_id
    )
    row_ref = str(job.payload.get("row_ref", "")).strip()
    gui_payload = _build_control_gui_status(
        run_id=snapshot_run_id,
        stage=str(worker_contract.get("stage", result.get("status", "unknown"))),
        exit_code=0 if success else 1,
        status=gui_status,
    )
    latest_artifacts: list[Path] = []
    if row_closeout_active and completion is not None:
        final_artifact_path = str(completion.get("final_artifact_path", "")).strip()
        if final_artifact_path:
            latest_artifacts = [Path(final_artifact_path)]
    elif worker_artifacts:
        latest_artifacts = worker_artifacts
    elif artifact_path is not None:
        latest_artifacts = [artifact_path]
    excel_sync_updated = False
    excel_path = str(job.payload.get("excel_path", "")).strip()
    sheet_name = str(job.payload.get("sheet_name", "")).strip()
    row_index = _to_int(job.payload.get("row_index", -1))
    if (
        success
        and job.workload == "render"
        and excel_path
        and sheet_name
        and row_index >= 0
        and completion is not None
        and bool(completion.get("final_output", False))
    ):
        sync_worker_result = dict(worker_contract)
        sync_completion = dict(completion)
        if str(sync_completion.get("state", "")).strip() == "succeeded":
            sync_completion["state"] = "completed"
        sync_worker_result["completion"] = sync_completion
        excel_sync_updated = sync_final_video_result(
            config=runtime_config,
            excel_path=excel_path,
            sheet_name=sheet_name,
            row_index=row_index,
            worker_result=sync_worker_result,
            run_id=snapshot_run_id,
            artifact_root=artifact_root,
            debug_log=str(control_debug_log),
        )
    snapshot_metadata = cast(
        dict[str, object],
        {
            "run_id": snapshot_run_id,
            "mode": "control_loop",
            "status": result_status,
            "code": "OK" if success else runtime_error_code,
            "job_id": job.job_id,
            "workload": job.workload,
            "success": bool(success),
            "exit_code": 0 if success else 1,
            "debug_log": str(control_debug_log),
            "queue_status": job.status,
            "accepted_count": accepted_count,
            "invalid_count": invalid_count,
            "worker_status": str(worker_contract.get("status", "")),
            "worker_stage": str(
                worker_contract.get("stage", result.get("status", "unknown"))
            ),
            "worker_error_code": canonical_worker_error_code,
            "manifest_path": worker_manifest_path,
            "result_path": worker_result_path,
            "attempts": job.attempts,
            "backoff_sec": backoff_sec,
            "chain_depth": _to_int(job.payload.get("chain_depth", 0)),
            "next_jobs_count": next_jobs_count,
            "routed_count": len(seeded_downstream),
            "completion_state": completion_state,
            "final_output": False
            if completion is None
            else bool(completion.get("final_output", False)),
            "final_artifact": ""
            if completion is None
            else str(completion.get("final_artifact", "")),
            "final_artifact_path": ""
            if completion is None
            else str(completion.get("final_artifact_path", "")),
            "excel_sync_updated": excel_sync_updated,
            "excel_path": excel_path,
            "sheet_name": sheet_name,
            "row_index": row_index,
            "row_ref": row_ref,
            "asset_manifest_path": str(
                job.payload.get("asset_manifest_path", "")
            ).strip(),
            "completion": {} if completion is None else completion,
            "legacy_contracts_summary": (
                "post_gpt_immediate=seaart,genspark,tts; "
                "requires_upstream_artifacts=geminigen,canva,kenburns,rvc"
            ),
            "invalid_reason": invalid_reason_summary(runtime_config.input_root),
            "browser_evidence": build_agent_browser_evidence(worker_contract)
            if job.workload == "agent_browser_verify"
            else {},
            "ts": round(time(), 3),
        },
    )
    normalized_snapshot_metadata = normalize_runtime_snapshot_metadata(
        snapshot_metadata,
        run_id=snapshot_run_id,
        mode="control_loop",
        status=result_status,
        code="OK" if success else runtime_error_code,
        debug_log=str(control_debug_log),
    )
    raw_worker_error_code = str(worker_contract.get("error_code", "")).strip()
    mismatch_warning = ""
    if (
        raw_worker_error_code
        and runtime_error_code
        and raw_worker_error_code != runtime_error_code
    ):
        mismatch_warning = (
            f"worker_error_code={raw_worker_error_code} error_code={runtime_error_code}"
        )

    write_control_plane_runtime_snapshot(
        runtime_config,
        run_id=snapshot_run_id,
        status=result_status,
        code="OK" if success else runtime_error_code,
        debug_log=str(control_debug_log),
        gui_payload=gui_payload,
        artifacts=latest_artifacts,
        metadata=normalized_snapshot_metadata,
    )
    _ = append_debug_event(
        control_debug_log,
        event="control_loop_result",
        level="ERROR" if result_status == "failed" else "INFO",
        payload={
            "run_id": run_id,
            "job_id": job.job_id,
            "workload": job.workload,
            "queue_status": job.status,
            "success": bool(success),
            "result_status": result_status,
            "accepted_count": accepted_count,
            "invalid_count": invalid_count,
            "invalid_reason": invalid_reason_summary(runtime_config.input_root),
            "runtime_result": result,
            "worker_result": worker_result,
            "recovery": recovery,
            "artifact_path": None if artifact_path is None else str(artifact_path),
            "seeded_downstream": [item.to_dict() for item in seeded_downstream],
            "warning_worker_error_code_mismatch": mismatch_warning,
        },
    )
    _ = _append_control_event(
        {
            "event": "job_summary",
            "job_id": job.job_id,
            "workload": job.workload,
            "queue_status": job.status,
            "success": bool(success),
            "worker_stage": str(
                worker_contract.get("stage", result.get("status", "unknown"))
            ),
            "worker_error_code": canonical_worker_error_code,
            "attempts": job.attempts,
            "backoff_sec": backoff_sec,
            "artifact_count": len(latest_artifacts),
            "next_jobs_count": next_jobs_count,
            "routed_count": len(seeded_downstream),
            "chain_depth": _to_int(job.payload.get("chain_depth", 0)),
            "routed_from": str(job.payload.get("routed_from", "")),
            "completion_state": completion_state,
            "final_output": False
            if completion is None
            else bool(completion.get("final_output", False)),
            "final_artifact": ""
            if completion is None
            else str(completion.get("final_artifact", "")),
            "final_artifact_path": ""
            if completion is None
            else str(completion.get("final_artifact_path", "")),
            "excel_sync_updated": excel_sync_updated,
            "manifest_path": worker_manifest_path,
            "result_path": worker_result_path,
        },
        events_file,
        run_id=run_id,
    )
    return {
        "status": result_status,
        "code": "OK" if success else runtime_error_code,
        "job": job.to_dict(),
        "result": result,
        "worker_result": worker_result,
        "artifact_path": None if artifact_path is None else str(artifact_path),
        "recovery": recovery,
        "routed_count": len(seeded_downstream),
    }


def seed_control_job(job: JobContract, config: RuntimeConfig | None = None) -> None:
    runtime_config = config or RuntimeConfig()
    default_config = RuntimeConfig()
    queue_file = getattr(
        runtime_config,
        "queue_store_file",
        default_config.queue_store_file,
    )
    queue_store = QueueStore(queue_file)
    _ = _upsert_job(queue_store, job)


def _build_control_gui_status(
    *,
    run_id: str,
    stage: str,
    exit_code: int,
    status: dict[str, object],
) -> dict[str, object]:
    return build_gui_status_payload(
        status=status,
        run_id=run_id,
        mode="control_loop",
        stage=stage,
        exit_code=exit_code,
    )


def _next_status_for_recovery(recovery: dict[str, object]) -> str:
    action = str(recovery.get("action", "failed"))
    if action == "completed":
        return "completed"
    if action == "blocked":
        return "retry"
    if action == "retry":
        return "retry"
    return "failed"


def _mapping_from_obj(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw_value = cast(dict[object, object], value)
    return {str(key): item for key, item in raw_value.items()}


_load_jobs = QueueStore.load


def _promotion_gate(job: JobContract) -> str:
    gate = str(job.payload.get("promotion_gate", "")).strip().upper()
    if gate in PROMOTION_GATE_ORDER:
        return gate
    if job.workload in {"genspark", "seaart"}:
        return "A"
    if job.workload in {"canva", "geminigen"}:
        return "B"
    if job.workload in {"qwen3_tts", "rvc", "kenburns"}:
        return "C"
    if job.workload == "render":
        return "D"
    return ""


def _row_ref(job: JobContract) -> str:
    return str(job.payload.get("row_ref", "")).strip()


def _gate_rank(job: JobContract) -> int:
    return PROMOTION_GATE_ORDER.get(_promotion_gate(job), 0)


def _next_runnable_job(jobs: list[JobContract], now: float) -> JobContract | None:
    row_pending_gate: dict[str, int] = {}
    for entry in jobs:
        if entry.status not in {"queued", "retry", "running"}:
            continue
        row_ref = _row_ref(entry)
        if not row_ref:
            continue
        gate_rank = _gate_rank(entry)
        current = row_pending_gate.get(row_ref)
        if current is None or gate_rank < current:
            row_pending_gate[row_ref] = gate_rank
    for entry in jobs:
        row_ref = _row_ref(entry)
        if row_ref and _gate_rank(entry) > row_pending_gate.get(
            row_ref, _gate_rank(entry)
        ):
            continue
        if entry.status == "queued":
            return entry
        if entry.status == "retry":
            next_attempt_at = _to_float(entry.payload.get("next_attempt_at", 0.0), 0.0)
            if next_attempt_at <= now:
                return entry
    return None


def _fail_closed_blocked_rows(
    queue_store: QueueStore,
    jobs: list[JobContract],
    events_file: Path,
    *,
    run_id: str,
) -> None:
    failed_rows: dict[str, int] = {}
    for entry in jobs:
        if entry.status != "failed":
            continue
        row_ref = _row_ref(entry)
        if not row_ref:
            continue
        gate_rank = _gate_rank(entry)
        current = failed_rows.get(row_ref)
        if current is None or gate_rank < current:
            failed_rows[row_ref] = gate_rank
    if not failed_rows:
        return
    for job in jobs:
        row_ref = _row_ref(job)
        if not row_ref or row_ref not in failed_rows:
            continue
        if job.status not in {"queued", "retry"}:
            continue
        if _gate_rank(job) < failed_rows[row_ref]:
            continue
        previous_status = job.status
        if not can_transition(previous_status, "failed"):
            continue
        job.status = "failed"
        _ = _upsert_job(queue_store, job)
        cancelled_record = transition_record(job.job_id, previous_status, job.status)
        cancelled_record["routed_from"] = str(job.payload.get("routed_from", ""))
        cancelled_record["chain_depth"] = _to_int(job.payload.get("chain_depth", 0))
        cancelled_record["reason"] = "promotion_gate_blocked"
        _ = _append_transition_record(cancelled_record, events_file, run_id=run_id)


def _recover_stale_running_jobs(
    queue_store: QueueStore,
    jobs: list[JobContract],
    now: float,
    config: RuntimeConfig,
    events_file: Path,
    *,
    run_id: str = "",
) -> None:
    stale_sec = max(1, int(config.running_stale_sec))
    changed = False
    for job in jobs:
        if job.status != "running":
            continue
        age_sec = max(0.0, now - _to_float(job.updated_at, now))
        if age_sec < stale_sec:
            continue
        recovery_action = (
            "retry"
            if recovery_policy.within_retry_budget(
                job.attempts, config.max_retry_attempts
            )
            else "failed"
        )
        previous_status = job.status
        job.status = recovery_action
        job.attempts += 1
        if recovery_action == "retry":
            job.payload["next_attempt_at"] = round(
                now + recovery_policy.next_backoff_sec(job.attempts), 3
            )
        else:
            _ = job.payload.pop("next_attempt_at", None)
        changed = True
        _ = _append_control_event(
            {
                "event": "stale_running_recovered",
                "job_id": job.job_id,
                "workload": job.workload,
                "age_sec": round(age_sec, 3),
                "action": recovery_action,
                "attempts": job.attempts,
            },
            events_file,
            run_id=run_id,
        )
        transition = transition_record(job.job_id, previous_status, job.status)
        transition["routed_from"] = str(job.payload.get("routed_from", ""))
        transition["chain_depth"] = _to_int(job.payload.get("chain_depth", 0))
        _ = _append_transition_record(transition, events_file, run_id=run_id)
    if changed:
        _ = _save_jobs(queue_store, jobs)


_save_jobs = QueueStore.save


_upsert_job = QueueStore.upsert


def _append_transition_record(
    record: dict[str, object], output_file: Path, *, run_id: str = ""
) -> Path:
    payload = dict(record)
    if run_id:
        _ = payload.setdefault("run_id", run_id)
    return append_transition_record(payload, output_file)


def _append_control_event(
    record: dict[str, object], output_file: Path, *, run_id: str = ""
) -> Path:
    payload = dict(record)
    _ = payload.setdefault("ts", round(time(), 3))
    return _append_transition_record(payload, output_file, run_id=run_id)


def _evaluate_recovery(
    job: JobContract,
    *,
    success: bool,
    blocked: bool = False,
    retryable: bool = True,
    config: RuntimeConfig,
) -> dict[str, object]:
    circuit = recovery_policy.CircuitState(
        failure_count=_to_int(job.payload.get("failure_count", 0)),
        opened_at=_to_optional_float(job.payload.get("circuit_opened_at")),
    )
    if blocked:
        job.payload["failure_count"] = circuit.failure_count
        job.payload["circuit_opened_at"] = circuit.opened_at
        return {
            "action": "blocked",
            "backoff_sec": max(
                1.0, float(getattr(config, "blocked_backoff_sec", 30.0))
            ),
            "circuit_open": False,
        }
    if not success and not retryable:
        job.payload["failure_count"] = circuit.failure_count
        job.payload["circuit_opened_at"] = circuit.opened_at
        return {"action": "failed", "backoff_sec": 0, "circuit_open": False}
    recovery = recovery_policy.evaluate_recovery(
        job.attempts, success=success, circuit=circuit
    )
    if not success and recovery.get("action") == "retry":
        if not recovery_policy.within_retry_budget(
            job.attempts, config.max_retry_attempts
        ):
            recovery = cast(
                dict[str, object],
                {"action": "failed", "backoff_sec": 0, "circuit_open": False},
            )
        else:
            recovery["backoff_sec"] = recovery_policy.next_backoff_sec(job.attempts)
    job.payload["failure_count"] = circuit.failure_count
    job.payload["circuit_opened_at"] = circuit.opened_at
    return recovery


def _run_worker(
    job: JobContract,
    artifact_root: Path | None = None,
    *,
    registry_file: Path | None = None,
    allow_mock_chain: bool = False,
) -> dict[str, object]:
    default_config = RuntimeConfig()
    if _mock_chain_enabled(job, allow_mock_chain=allow_mock_chain):
        if artifact_root is None:
            artifact_root = default_config.artifact_root
        return _run_mock_chain_worker(job, artifact_root)
    if artifact_root is None:
        artifact_root = default_config.artifact_root
    resolved_registry_file = registry_file or default_config.worker_registry_file
    dispatch = _worker_dispatch_table(
        artifact_root=artifact_root,
        registry_file=resolved_registry_file,
        debug_log_root=default_config.debug_log_root,
    )
    handler = dispatch.get(job.workload)
    if handler is None:
        raise ValueError(f"unsupported_workload:{job.workload}")
    run_id = str(job.payload.get("run_id", job.job_id))
    _ = update_worker_state(
        resolved_registry_file,
        workload=job.workload,
        state="busy",
        run_id=run_id,
    )
    try:
        return handler(job)
    finally:
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=run_id,
        )


def run_worker(
    job: JobContract,
    artifact_root: Path | None = None,
    *,
    registry_file: Path | None = None,
) -> dict[str, object]:
    return _run_worker(job, artifact_root, registry_file=registry_file)


WorkerDispatchHandler = Callable[[JobContract], dict[str, object]]


def _run_chatgpt_worker(
    job: JobContract, artifact_root: Path, debug_log_root: Path
) -> dict[str, object]:
    workspace = artifact_root / job.workload / job.job_id
    workspace.mkdir(parents=True, exist_ok=True)
    topic_spec = _mapping_from_obj(job.payload.get("topic_spec", {})) or {}
    return run_stage1_chatgpt_job(
        topic_spec,
        workspace,
        debug_log=str(
            debug_log_path(
                debug_log_root,
                str(job.payload.get("run_id", job.job_id)),
            )
        ),
    )


def _worker_dispatch_table(
    *, artifact_root: Path, registry_file: Path, debug_log_root: Path
) -> dict[str, WorkerDispatchHandler]:
    return {
        "chatgpt": lambda job: _run_chatgpt_worker(job, artifact_root, debug_log_root),
        "genspark": lambda job: run_genspark_job(
            job, artifact_root, registry_file=registry_file
        ),
        "seaart": lambda job: run_seaart_job(
            job, artifact_root, registry_file=registry_file
        ),
        "geminigen": lambda job: run_geminigen_job(
            job, artifact_root, registry_file=registry_file
        ),
        "canva": lambda job: run_canva_job(
            job, artifact_root, registry_file=registry_file
        ),
        "agent_browser_verify": lambda job: run_agent_browser_verify_job(
            job,
            artifact_root,
            registry_file=registry_file,
        ),
        "render": lambda job: run_render_job(job, artifact_root),
        "rvc": lambda job: run_rvc_job(job, artifact_root=artifact_root),
        "kenburns": lambda job: run_kenburns_job(job, artifact_root=artifact_root),
        "qwen3_tts": lambda job: run_qwen3_job(job, artifact_root=artifact_root),
        "dev_plan": lambda job: run_dev_plan_job(job, artifact_root),
        "dev_implement": lambda job: run_dev_implement_job(
            job,
            artifact_root=artifact_root,
            config=RuntimeConfig.from_root(artifact_root.parent),
        ),
        "dev_replan": lambda job: run_dev_replan_job(job, artifact_root),
    }


def _run_mock_chain_worker(job: JobContract, artifact_root: Path) -> dict[str, object]:
    mock_root = artifact_root / "_mock" / job.workload
    mock_root.mkdir(parents=True, exist_ok=True)
    chain_depth = _to_int(job.payload.get("chain_depth", 0))
    if job.workload == "qwen3_tts":
        audio_path = _write_mock_file(
            mock_root / f"{job.job_id}.wav", f"mock qwen audio for {job.job_id}\n"
        )
        next_jobs = [
            _build_mock_chain_job(
                job_id=f"rvc-{job.job_id}",
                workload="rvc",
                checkpoint_key=f"mock_chain:rvc:{job.job_id}",
                payload={
                    "source_path": str(audio_path),
                    "mock_chain": True,
                    **(
                        {"image_path": str(job.payload.get("image_path", ""))}
                        if isinstance(job.payload.get("image_path"), str)
                        and str(job.payload.get("image_path", "")).strip()
                        else {}
                    ),
                },
                chain_depth=chain_depth + 1,
                parent_job_id=job.job_id,
            )
        ]
        qwen_result: dict[str, object] = {
            "status": "ok",
            "stage": "mock_chain_qwen3_tts",
            "error_code": "",
            "retryable": False,
            "artifacts": [str(audio_path)],
            "next_jobs": next_jobs,
            "completion": {
                "state": "mock_routed",
                "final_output": False,
                "final_artifact": "",
                "final_artifact_path": "",
            },
        }
        result_path = _write_mock_result_file(
            mock_root / f"{job.job_id}.result.json", qwen_result
        )
        qwen_result["result_path"] = str(result_path)
        return qwen_result
    if job.workload == "rvc":
        audio_path = _write_mock_file(
            mock_root / f"{job.job_id}.wav", f"mock rvc audio for {job.job_id}\n"
        )
        next_jobs: list[dict[str, object]] = []
        image_path = job.payload.get("image_path")
        if isinstance(image_path, str) and image_path.strip():
            next_jobs.append(
                _build_mock_chain_job(
                    job_id=f"kenburns-{job.job_id}",
                    workload="kenburns",
                    checkpoint_key=f"mock_chain:kenburns:{job.job_id}",
                    payload={
                        "source_path": image_path,
                        "audio_path": str(audio_path),
                        "mock_chain": True,
                        "duration_sec": 8,
                    },
                    chain_depth=chain_depth + 1,
                    parent_job_id=job.job_id,
                )
            )
        rvc_result: dict[str, object] = {
            "status": "ok",
            "stage": "mock_chain_rvc",
            "error_code": "",
            "retryable": False,
            "artifacts": [str(audio_path)],
            "next_jobs": next_jobs,
            "completion": {
                "state": "mock_routed" if next_jobs else "mock_audio_ready",
                "final_output": False,
                "final_artifact": "",
                "final_artifact_path": "",
            },
        }
        result_path = _write_mock_result_file(
            mock_root / f"{job.job_id}.result.json", rvc_result
        )
        rvc_result["result_path"] = str(result_path)
        return rvc_result
    video_path = _write_mock_file(
        mock_root / f"{job.job_id}.mp4", f"mock kenburns video for {job.job_id}\n"
    )
    kenburns_result: dict[str, object] = {
        "status": "ok",
        "stage": "mock_chain_kenburns",
        "error_code": "",
        "retryable": False,
        "artifacts": [str(video_path)],
        "next_jobs": [],
        "completion": {
            "state": "completed",
            "final_output": True,
            "final_artifact": video_path.name,
            "final_artifact_path": str(video_path),
        },
    }
    result_path = _write_mock_result_file(
        mock_root / f"{job.job_id}.result.json", kenburns_result
    )
    kenburns_result["result_path"] = str(result_path)
    return kenburns_result


def _mock_chain_enabled(job: JobContract, *, allow_mock_chain: bool) -> bool:
    return allow_mock_chain and bool(job.payload.get("mock_chain", False))


def _build_mock_chain_job(
    *,
    job_id: str,
    workload: GpuWorkload,
    checkpoint_key: str,
    payload: dict[str, object],
    chain_depth: int,
    parent_job_id: str,
) -> dict[str, object]:
    return build_explicit_job_contract(
        job_id=job_id,
        workload=workload,
        checkpoint_key=checkpoint_key,
        payload=payload,
        chain_step=chain_depth,
        parent_job_id=parent_job_id,
    )


def _write_mock_result_file(path: Path, worker_result: dict[str, object]) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(worker_result, ensure_ascii=True, indent=2))
        temp_path = Path(handle.name)
    _ = temp_path.replace(path)
    return path


def _write_mock_file(path: Path, content: str) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(content)
        temp_path = Path(handle.name)
    _ = temp_path.replace(path)
    return path


def _seed_declared_next_jobs(
    queue_file: Path,
    jobs: list[JobContract],
    worker_result: dict[str, object],
    parent_job: JobContract,
    events_file: Path,
    *,
    run_id: str,
    artifact_root: Path,
) -> list[JobContract]:
    queue_store = QueueStore(queue_file)
    typed_next_jobs = _next_jobs_entries(worker_result)
    next_job_limit = MAX_NEXT_JOBS
    if not typed_next_jobs and parent_job.workload == "chatgpt":
        typed_next_jobs = _declared_stage1_next_jobs(
            worker_result, parent_job, artifact_root
        )
        next_job_limit = MAX_STAGE1_DECLARED_NEXT_JOBS
    _ = _attach_asset_manifest(
        typed_next_jobs,
        run_id=str(parent_job.payload.get("run_id", "")).strip(),
        row_ref=str(parent_job.payload.get("row_ref", "")).strip(),
    )
    if len(typed_next_jobs) > next_job_limit:
        _ = _append_control_event(
            {
                "event": "next_job_rejected",
                "parent_job_id": parent_job.job_id,
                "reason": "too_many_next_jobs",
                "count": len(typed_next_jobs),
                "max_count": next_job_limit,
            },
            events_file,
            run_id=run_id,
        )
        return []
    seeded: list[JobContract] = []
    known_job_ids = {current.job_id for current in jobs}
    for entry in typed_next_jobs:
        if not isinstance(entry, dict):
            continue
        raw_entry = cast(dict[object, object], entry)
        typed_entry: dict[str, object] = {
            str(key): value for key, value in raw_entry.items()
        }
        next_job = _job_from_declared_next_entry(typed_entry)
        if next_job is None:
            _ = _append_control_event(
                {
                    "event": "next_job_rejected",
                    "parent_job_id": parent_job.job_id,
                    "reason": "invalid_next_job_contract",
                    "entry": typed_entry,
                },
                events_file,
                run_id=run_id,
            )
            continue
        next_depth = _to_int(
            next_job.payload.get(
                "chain_depth", _to_int(parent_job.payload.get("chain_depth", 0)) + 1
            )
        )
        if next_depth > MAX_CHAIN_DEPTH:
            _ = _append_control_event(
                {
                    "event": "next_job_rejected",
                    "parent_job_id": parent_job.job_id,
                    "job_id": next_job.job_id,
                    "reason": "chain_depth_exceeded",
                    "chain_depth": next_depth,
                    "max_depth": MAX_CHAIN_DEPTH,
                },
                events_file,
                run_id=run_id,
            )
            continue
        expected_run_id = str(parent_job.payload.get("run_id", "")).strip()
        current_run_id = str(next_job.payload.get("run_id", "")).strip()
        if expected_run_id:
            if current_run_id and current_run_id != expected_run_id:
                _ = _append_control_event(
                    {
                        "event": "next_job_rejected",
                        "parent_job_id": parent_job.job_id,
                        "job_id": next_job.job_id,
                        "reason": "run_id_mismatch",
                        "expected_run_id": expected_run_id,
                        "current_run_id": current_run_id,
                    },
                    events_file,
                    run_id=run_id,
                )
                continue
            next_job.payload["run_id"] = expected_run_id
        expected_row_ref = str(parent_job.payload.get("row_ref", "")).strip()
        current_row_ref = str(next_job.payload.get("row_ref", "")).strip()
        if expected_row_ref:
            if current_row_ref and current_row_ref != expected_row_ref:
                _ = _append_control_event(
                    {
                        "event": "next_job_rejected",
                        "parent_job_id": parent_job.job_id,
                        "job_id": next_job.job_id,
                        "reason": "row_ref_mismatch",
                        "expected_row_ref": expected_row_ref,
                        "current_row_ref": current_row_ref,
                    },
                    events_file,
                    run_id=run_id,
                )
                continue
            next_job.payload["row_ref"] = expected_row_ref
        replaced_job_id = ""
        if next_job.workload == "rvc":
            replaced_job_id = _normalize_rvc_next_job(
                next_job, artifact_root=artifact_root
            )
            if (
                replaced_job_id
                and replaced_job_id != next_job.job_id
                and replaced_job_id in known_job_ids
            ):
                known_job_ids.remove(replaced_job_id)
            duplicate_rvc = _existing_rvc_job_for_run(jobs, next_job)
            if duplicate_rvc is not None:
                existing_priority = _rvc_source_mode_priority(
                    _rvc_source_mode(duplicate_rvc.payload)
                )
                next_priority = _rvc_source_mode_priority(
                    str(next_job.payload.get("source_mode", "")).strip()
                )
                if (
                    next_priority > existing_priority
                    and duplicate_rvc.status == "queued"
                ):
                    jobs.remove(duplicate_rvc)
                    known_job_ids.discard(duplicate_rvc.job_id)
                    _ = _append_control_event(
                        {
                            "event": "next_job_replaced",
                            "parent_job_id": parent_job.job_id,
                            "job_id": next_job.job_id,
                            "replaced_job_id": duplicate_rvc.job_id,
                            "reason": "higher_priority_rvc_source_mode",
                            "source_mode": str(next_job.payload.get("source_mode", "")),
                        },
                        events_file,
                        run_id=run_id,
                    )
                else:
                    _ = _append_control_event(
                        {
                            "event": "next_job_rejected",
                            "parent_job_id": parent_job.job_id,
                            "job_id": next_job.job_id,
                            "reason": "duplicate_rvc_run",
                            "existing_job_id": duplicate_rvc.job_id,
                            "source_mode": str(next_job.payload.get("source_mode", "")),
                        },
                        events_file,
                        run_id=run_id,
                    )
                    continue
        next_job.payload["chain_depth"] = next_depth
        next_job.payload["routed_from"] = parent_job.job_id
        excel_path = str(parent_job.payload.get("excel_path", "")).strip()
        sheet_name = str(parent_job.payload.get("sheet_name", "")).strip()
        row_index = _to_int(parent_job.payload.get("row_index", -1))
        if excel_path:
            next_job.payload["excel_path"] = excel_path
        if sheet_name:
            next_job.payload["sheet_name"] = sheet_name
        if row_index >= 0:
            next_job.payload["row_index"] = row_index
        if not payload_paths_are_local(next_job.payload):
            _ = _append_control_event(
                {
                    "event": "next_job_rejected",
                    "parent_job_id": parent_job.job_id,
                    "job_id": next_job.job_id,
                    "reason": "non_local_payload",
                },
                events_file,
                run_id=run_id,
            )
            continue
        if next_job.job_id in known_job_ids:
            _ = _append_control_event(
                {
                    "event": "next_job_rejected",
                    "parent_job_id": parent_job.job_id,
                    "job_id": next_job.job_id,
                    "reason": "duplicate_job_id",
                },
                events_file,
                run_id=run_id,
            )
            continue
        jobs.append(next_job)
        _ = _save_jobs(queue_store, jobs)
        known_job_ids.add(next_job.job_id)
        seeded.append(next_job)
    return seeded


def _rvc_source_mode(payload: dict[str, object]) -> str:
    declared_mode = str(payload.get("source_mode", "")).strip()
    if declared_mode in RVC_SOURCE_MODE_PRIORITY:
        return declared_mode
    audio_path = str(payload.get("audio_path", "")).strip()
    return "gemi-video-source" if audio_path else "tts-source"


def _rvc_source_mode_priority(source_mode: str) -> int:
    return RVC_SOURCE_MODE_PRIORITY.get(source_mode, 0)


def _normalize_rvc_next_job(next_job: JobContract, *, artifact_root: Path) -> str:
    run_id = str(next_job.payload.get("run_id", "")).strip()
    if not run_id:
        source_mode = _rvc_source_mode(next_job.payload)
        next_job.payload["source_mode"] = source_mode
        return ""
    source_mode = _rvc_source_mode(next_job.payload)
    next_job.payload["source_mode"] = source_mode
    previous_job_id = next_job.job_id
    if source_mode == "tts-source":
        canonical_job_id = f"rvc-qwen3-{run_id}"
    else:
        canonical_job_id = f"rvc-geminigen-{run_id}"
    next_job.job_id = canonical_job_id
    next_job.checkpoint_key = f"derived:rvc:{source_mode}:{run_id}"
    next_job.payload["service_artifact_path"] = str(
        (artifact_root / "rvc" / canonical_job_id / "speech_rvc.wav").resolve()
    )
    return previous_job_id


def _existing_rvc_job_for_run(
    jobs: list[JobContract], next_job: JobContract
) -> JobContract | None:
    expected_run_id = str(next_job.payload.get("run_id", "")).strip()
    if not expected_run_id:
        return None
    for current in jobs:
        if current.workload != "rvc":
            continue
        current_run_id = str(current.payload.get("run_id", "")).strip()
        if current_run_id != expected_run_id:
            continue
        if current.job_id == next_job.job_id:
            continue
        return current
    return None


def _attach_asset_manifest(
    typed_next_jobs: list[object], *, run_id: str, row_ref: str
) -> Path | None:
    manifest_context = _asset_manifest_context(typed_next_jobs)
    if manifest_context is None:
        return None
    asset_root, roles = manifest_context
    manifest_path = _write_asset_manifest(
        asset_root, run_id=run_id, row_ref=row_ref, roles=roles
    )
    for raw_entry in typed_next_jobs:
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[object, object], raw_entry)
        job_raw = entry.get("job")
        if not isinstance(job_raw, dict):
            continue
        job_block = cast(dict[object, object], job_raw)
        if str(job_block.get("worker", "")) != "render":
            continue
        payload_raw = job_block.get("payload")
        if not isinstance(payload_raw, dict):
            continue
        payload = cast(dict[object, object], payload_raw)
        payload["asset_manifest_path"] = str(manifest_path.resolve())
    return manifest_path


def _asset_manifest_context(
    typed_next_jobs: list[object],
) -> tuple[Path, dict[str, str]] | None:
    asset_root: Path | None = None
    roles: dict[str, str] = {}
    for raw_entry in typed_next_jobs:
        entry = _mapping_from_obj(raw_entry)
        if entry is None:
            continue
        job_block = _mapping_from_obj(entry.get("job", {}))
        if job_block is None:
            continue
        worker = str(job_block.get("worker", "")).strip()
        payload = _mapping_from_obj(job_block.get("payload", {}))
        if payload is None:
            continue
        if worker == "render":
            render_root = str(payload.get("render_folder_path", "")).strip()
            if render_root:
                asset_root = Path(render_root).resolve()
            voice_json_path = str(payload.get("voice_json_path", "")).strip()
            if voice_json_path and "voice_json" not in roles:
                roles["voice_json"] = voice_json_path
            continue
        artifact_path = str(payload.get("service_artifact_path", "")).strip()
        if not artifact_path:
            continue
        scene_index = _to_int(payload.get("scene_index", 0))
        if worker == "canva":
            roles[f"thumb.scene_{scene_index:02d}.canva"] = artifact_path
            if "thumb_primary" not in roles:
                roles["thumb_primary"] = artifact_path
        elif worker == "geminigen":
            roles[f"stage2.scene_{scene_index:02d}.geminigen"] = artifact_path
        else:
            roles[f"stage2.scene_{scene_index:02d}.{worker}"] = artifact_path
            if worker == "genspark" and "image_primary" not in roles:
                roles["image_primary"] = artifact_path
            elif worker == "seaart" and "image_primary" not in roles:
                roles["image_primary"] = artifact_path
            if worker == "geminigen" and "video_primary" not in roles:
                roles["video_primary"] = artifact_path
    if asset_root is None or not roles:
        return None
    return asset_root, roles


def _write_asset_manifest(
    asset_root: Path, *, run_id: str, row_ref: str, roles: dict[str, str]
) -> Path:
    manifest_path = asset_root / "asset_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "runtime": "runtime_v2",
        "checked_at": round(time(), 3),
        "run_id": run_id,
        "row_ref": row_ref,
        "asset_root": str(asset_root.resolve()),
        "roles": roles,
    }
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=manifest_path.parent,
        prefix=f"{manifest_path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True, indent=2))
        temp_path = Path(handle.name)
    _ = temp_path.replace(manifest_path)
    return manifest_path


def _declared_stage1_next_jobs(
    worker_result: dict[str, object],
    parent_job: JobContract,
    artifact_root: Path,
) -> list[object]:
    details = _mapping_from_obj(worker_result.get("details", {}))
    if details is None:
        return []
    video_plan = _mapping_from_obj(details.get("video_plan", {}))
    if video_plan is None:
        return []
    try:
        next_jobs, _ = route_video_plan(video_plan)
    except ValueError:
        return []
    qwen_job = _declared_stage1_qwen_job(details, parent_job, artifact_root)
    typed_jobs = [cast(object, item) for item in next_jobs]
    if qwen_job is not None:
        typed_jobs.append(cast(object, qwen_job))
    return typed_jobs


def _declared_stage1_qwen_job(
    details: dict[str, object],
    parent_job: JobContract,
    artifact_root: Path,
) -> dict[str, object] | None:
    stage1_handoff = _mapping_from_obj(details.get("stage1_handoff", {}))
    if stage1_handoff is None:
        return None
    handoff_contract = _mapping_from_obj(stage1_handoff.get("contract", {}))
    if handoff_contract is None:
        return None
    raw_voice_texts = handoff_contract.get("voice_texts", [])
    if not isinstance(raw_voice_texts, list):
        return None
    voice_texts: list[dict[str, object]] = []
    for entry in cast(list[object], raw_voice_texts):
        if not isinstance(entry, dict):
            continue
        typed_entry = _mapping_from_obj(entry)
        if typed_entry is None:
            continue
        text = str(typed_entry.get("text", "")).strip()
        col = str(typed_entry.get("col", "")).strip()
        if not text or not col:
            continue
        voice_texts.append(
            {
                "col": col,
                "text": text,
                "original_voices": typed_entry.get("original_voices", []),
            }
        )
    if not voice_texts:
        return None
    run_id = str(parent_job.payload.get("run_id", "")).strip()
    row_ref = str(parent_job.payload.get("row_ref", "")).strip()
    excel_path = str(parent_job.payload.get("excel_path", "")).strip()
    sheet_name = str(parent_job.payload.get("sheet_name", "")).strip()
    row_index = _to_int(parent_job.payload.get("row_index", -1))
    topic = str(
        handoff_contract.get("topic", parent_job.payload.get("topic", ""))
    ).strip()
    model_name = str(parent_job.payload.get("model_name", "voice-model-a")).strip()
    job_id = f"qwen3-{run_id or parent_job.job_id}"
    service_artifact_path = (
        artifact_root / "qwen3_tts" / job_id / "speech.wav"
    ).resolve()
    return build_explicit_job_contract(
        job_id=job_id,
        workload="qwen3_tts",
        checkpoint_key=f"declared:qwen3_tts:{row_ref or parent_job.job_id}",
        payload={
            "run_id": run_id,
            "row_ref": row_ref,
            "topic": topic,
            "voice_texts": voice_texts,
            "model_name": model_name or "voice-model-a",
            "service_artifact_path": str(service_artifact_path),
            "chain_depth": 0,
            "excel_path": excel_path,
            "sheet_name": sheet_name,
            "row_index": row_index,
        },
        chain_step=1,
        parent_job_id=parent_job.job_id,
    )


def _job_from_declared_next_entry(entry: dict[str, object]) -> JobContract | None:
    parsed_job, _ = job_from_explicit_payload(
        entry, source_hint=f"declared:{entry.get('job', {})}"
    )
    return parsed_job


def _worker_result_contract(worker_result: dict[str, object]) -> dict[str, object]:
    result_path_raw = worker_result.get("result_path")
    if isinstance(result_path_raw, str) and result_path_raw.strip():
        result_path = Path(result_path_raw)
        if not result_path.exists() or not result_path.is_file():
            return {
                "status": "failed",
                "stage": str(worker_result.get("stage", "worker_result_contract")),
                "error_code": "missing_worker_result_json",
                "retryable": False,
                "result_path": str(result_path.resolve()),
                "next_jobs": [],
                "completion": {"state": "failed", "final_output": False},
                "details": {"debug_log": str(worker_result.get("debug_log", ""))},
            }
        try:
            raw_payload = cast(
                object, json.loads(result_path.read_text(encoding="utf-8"))
            )
        except OSError:
            return {
                "status": "failed",
                "stage": str(worker_result.get("stage", "worker_result_contract")),
                "error_code": "unreadable_worker_result_json",
                "retryable": False,
                "result_path": str(result_path.resolve()),
                "next_jobs": [],
                "completion": {"state": "failed", "final_output": False},
                "details": {"debug_log": str(worker_result.get("debug_log", ""))},
            }
        except json.JSONDecodeError:
            return {
                "status": "failed",
                "stage": str(worker_result.get("stage", "worker_result_contract")),
                "error_code": "invalid_worker_result_json",
                "retryable": False,
                "result_path": str(result_path.resolve()),
                "next_jobs": [],
                "completion": {"state": "failed", "final_output": False},
                "details": {"debug_log": str(worker_result.get("debug_log", ""))},
            }
        payload = _mapping_from_obj(raw_payload)
        if payload is not None:
            return payload
        return {
            "status": "failed",
            "stage": str(worker_result.get("stage", "worker_result_contract")),
            "error_code": "invalid_worker_result_contract",
            "retryable": False,
            "result_path": str(result_path.resolve()),
            "next_jobs": [],
            "completion": {"state": "failed", "final_output": False},
            "details": {"debug_log": str(worker_result.get("debug_log", ""))},
        }
    return worker_result


def _worker_result_from_runtime(runtime_result: dict[str, object]) -> dict[str, object]:
    worker_result = _mapping_from_obj(runtime_result.get("worker_result"))
    if worker_result is not None:
        return worker_result
    runtime_code = str(runtime_result.get("code", "RUNTIME_PRECHECK_FAILED"))
    completion_state, retryable, worker_status = _runtime_preflight_contract(
        runtime_code
    )
    return {
        "status": worker_status,
        "stage": "runtime_preflight",
        "error_code": runtime_code,
        "retryable": retryable,
        "next_jobs": [],
        "completion": {
            "state": completion_state,
            "final_output": False,
        },
    }


def _runtime_preflight_contract(
    runtime_code: str, *, workload: str = ""
) -> tuple[str, bool, str]:
    normalized_code = normalize_error_code(runtime_code)
    if normalized_code == "BROWSER_RESTART_EXHAUSTED":
        return ("failed", False, "failed")
    if workload == "agent_browser_verify" and normalized_code == "BROWSER_BLOCKED":
        return ("failed", False, "failed")
    if normalized_code in {
        "BROWSER_BLOCKED",
        "GPU_LEASE_BUSY",
        "GPT_FLOOR_FAIL",
    }:
        return ("blocked", True, "blocked")
    return ("failed", True, "failed")


def _normalize_runtime_failure_contract(
    worker_result: dict[str, object], *, runtime_error_code: str, workload: str
) -> dict[str, object]:
    normalized_runtime_error_code = normalize_error_code(runtime_error_code)
    canonical_error_code = select_worker_error_code(
        {
            "worker_error_code": worker_result.get("error_code", ""),
            "error_code": normalized_runtime_error_code,
        }
    )
    completion_state, retryable, worker_status = _runtime_preflight_contract(
        canonical_error_code or normalized_runtime_error_code,
        workload=workload,
    )
    normalized = dict(worker_result)
    normalized["status"] = worker_status
    normalized["error_code"] = canonical_error_code or normalized_runtime_error_code
    normalized["retryable"] = retryable
    normalized["next_jobs"] = []
    completion = _mapping_from_obj(normalized.get("completion", {})) or {}
    completion["state"] = completion_state
    _ = completion.setdefault("final_output", False)
    normalized["completion"] = completion
    return normalized


def _normalized_completion_state(
    raw_state: str, *, success: bool, blocked: bool, retryable: bool
) -> str:
    if success:
        return raw_state
    if blocked:
        return "blocked"
    if not retryable:
        return "failed"
    return raw_state or "failed"


def _next_jobs_entries(worker_result: dict[str, object]) -> list[object]:
    raw_next_jobs = worker_result.get("next_jobs", [])
    if not isinstance(raw_next_jobs, list):
        return []
    return cast(list[object], raw_next_jobs)


def _worker_succeeded(worker_result: dict[str, object]) -> bool:
    status = str(worker_result.get("status", "unknown"))
    return status in {"ok", "prepared", "ready", "no_work"}


def _worker_artifact_paths(worker_result: dict[str, object]) -> list[Path]:
    raw_artifacts = worker_result.get("artifacts", [])
    if not isinstance(raw_artifacts, list):
        return []
    typed_artifacts = cast(list[object], raw_artifacts)
    artifact_paths: list[Path] = []
    for entry in typed_artifacts:
        if isinstance(entry, str) and entry.strip():
            artifact_paths.append(Path(entry))
    return artifact_paths


def _agent_browser_failure_next_jobs(
    parent_job: JobContract,
) -> list[dict[str, object]]:
    if parent_job.workload != "agent_browser_verify":
        return []
    if not bool(parent_job.payload.get("replan_on_failure", False)):
        return []
    raw_verification = parent_job.payload.get("verification", [])
    verification = (
        cast(list[object], raw_verification)
        if isinstance(raw_verification, list)
        else []
    )
    raw_browser_checks = parent_job.payload.get("browser_checks", [])
    browser_checks = (
        cast(list[object], raw_browser_checks)
        if isinstance(raw_browser_checks, list)
        else []
    )
    return [
        build_explicit_job_contract(
            job_id=f"dev-replan-{parent_job.job_id}",
            workload="dev_replan",
            checkpoint_key=f"derived:dev_replan:{parent_job.job_id}",
            payload={
                "run_id": str(parent_job.payload.get("run_id", "")).strip(),
                "verification": verification,
                "browser_checks": browser_checks,
                "replan_payload": parent_job.payload.get("replan_payload", {}),
            },
            chain_step=_to_int(parent_job.payload.get("chain_depth", 0)) + 1,
            parent_job_id=parent_job.job_id,
        )
    ]


def _write_worker_artifact(
    job: JobContract,
    worker_result: dict[str, object],
    artifact_root: Path,
) -> Path:
    artifact_dir = artifact_root / job.workload
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{job.job_id}.json"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=artifact_dir,
        prefix=f"{job.job_id}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(worker_result, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(artifact_path)
    return artifact_path


def _to_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _to_float(value, 0.0)

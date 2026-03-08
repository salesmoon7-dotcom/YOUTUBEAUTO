from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.bootstrap import ensure_runtime_bootstrap
from runtime_v2.config import GpuWorkload, RuntimeConfig, allowed_workloads
from runtime_v2.debug_log import append_debug_event, debug_log_path
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status
from runtime_v2.gpt_autospawn import apply_autospawn_decision
from runtime_v2.gpt_pool_monitor import tick_gpt_status
from runtime_v2.recovery_policy import CircuitState, evaluate_recovery
from runtime_v2.result_router import write_result_router
from runtime_v2.retry_budget import next_backoff_sec, within_retry_budget
from runtime_v2.queue_store import QueueStore
from runtime_v2.state_machine import (
    append_transition_record,
    can_transition,
    transition_record,
)
from runtime_v2.stage1.chatgpt_runner import run_stage1_chatgpt_job
from runtime_v2.stage2.canva_worker import run_canva_job
from runtime_v2.stage2.geminigen_worker import run_geminigen_job
from runtime_v2.stage2.genspark_worker import run_genspark_job
from runtime_v2.stage2.seaart_worker import run_seaart_job
from runtime_v2.stage3.render_worker import run_render_job
from runtime_v2.worker_registry import update_worker_state
from runtime_v2.workers.kenburns_worker import run_kenburns_job
from runtime_v2.workers.qwen3_worker import run_qwen3_job
from runtime_v2.workers.rvc_worker import run_rvc_job
from runtime_v2.contracts.job_contract import (
    EXPLICIT_CONTRACT_NAME,
    EXPLICIT_CONTRACT_VERSION,
    JobContract,
    build_explicit_job_contract,
    workload_from_value,
)
from runtime_v2.supervisor import run_gated

ALLOWED_WORKLOADS = set(allowed_workloads())
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_EXTENSIONS = {".wav", ".mp3", ".flac", ".mp4", ".mov", ".mkv", ".avi"}
MAX_CHAIN_DEPTH = 4
MAX_NEXT_JOBS = 4
MAX_CONTRACT_BYTES = 262144
REPO_ROOT = Path(__file__).resolve().parents[1]


def run_control_loop_once(
    owner: str,
    config: RuntimeConfig | None = None,
    run_id: str = "control_loop",
    *,
    allow_runtime_side_effects: bool = True,
) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
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
        Path("system/runtime_v2/state/job_queue.json"),
    )
    events_file = getattr(
        runtime_config,
        "control_plane_events_file",
        Path("system/runtime_v2/evidence/control_plane_events.jsonl"),
    )
    artifact_root = getattr(
        runtime_config, "artifact_root", Path("system/runtime_v2/artifacts")
    )
    result_router_file = getattr(
        runtime_config,
        "result_router_file",
        Path("system/runtime_v2/evidence/result.json"),
    )
    jobs = _load_jobs(queue_file)
    _recover_stale_running_jobs(queue_file, jobs, now, runtime_config, events_file)
    job = _next_runnable_job(jobs, now)
    if job is None:
        accepted_count, invalid_count = _archived_contract_counts(
            runtime_config.input_root
        )
        seeded_jobs = seed_local_jobs(runtime_config)
        if seeded_jobs:
            jobs = _load_jobs(queue_file)
            job = _next_runnable_job(jobs, now)
            if job is not None:
                _ = _write_control_gui_status(
                    runtime_config,
                    run_id=run_id,
                    stage="seeded_queue",
                    exit_code=0,
                    status={
                        "seeded_jobs": len(seeded_jobs),
                        "queue_status": "seeded",
                        "accepted_count": accepted_count,
                        "invalid_count": invalid_count,
                        "invalid_reason": _invalid_reason_summary(
                            runtime_config.input_root
                        ),
                    },
                )
                _ = write_result_router(
                    [],
                    artifact_root,
                    result_router_file,
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
                        "invalid_reason": _invalid_reason_summary(
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
                        "invalid_reason": _invalid_reason_summary(
                            runtime_config.input_root
                        ),
                    },
                )
                return {
                    "status": "seeded",
                    "code": "SEEDED_JOB",
                    "seeded_jobs": [seeded_job.to_dict() for seeded_job in seeded_jobs],
                }
        _ = _write_control_gui_status(
            runtime_config,
            run_id=run_id,
            stage="idle",
            exit_code=0,
            status={
                "queue_status": "idle",
                "seeded_jobs": 0,
                "accepted_count": accepted_count,
                "invalid_count": invalid_count,
                "invalid_reason": _invalid_reason_summary(runtime_config.input_root),
            },
        )
        _ = write_result_router(
            [],
            artifact_root,
            result_router_file,
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
                "invalid_reason": _invalid_reason_summary(runtime_config.input_root),
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
                "invalid_reason": _invalid_reason_summary(runtime_config.input_root),
            },
        )
        return {"status": "idle", "code": "NO_JOB"}

    previous_status = job.status
    if can_transition(previous_status, "running"):
        job.status = "running"
        _ = _upsert_job(queue_file, jobs, job)
        running_record = transition_record(job.job_id, previous_status, job.status)
        running_record["routed_from"] = str(job.payload.get("routed_from", ""))
        running_record["chain_depth"] = _to_int(job.payload.get("chain_depth", 0))
        _ = append_transition_record(running_record, events_file)

    mock_chain = _mock_chain_enabled(job)
    if mock_chain:
        result: dict[str, object] = {
            "status": "ok",
            "code": "OK",
            "workload": job.workload,
            "worker_result": _run_worker(
                job,
                runtime_config.artifact_root,
                registry_file=runtime_config.worker_registry_file,
            ),
        }
    else:
        result = run_gated(
            owner=owner,
            execute=lambda: _run_worker(
                job,
                runtime_config.artifact_root,
                registry_file=runtime_config.worker_registry_file,
            ),
            workload=job.workload,
            config=runtime_config,
            run_id=run_id,
            require_browser_healthy=True,
            allow_runtime_side_effects=allow_runtime_side_effects,
        )
    worker_result = _worker_result_from_runtime(result)
    artifact_path: Path | None = None
    worker_contract = _worker_result_contract(worker_result)
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
    accepted_count, invalid_count = _archived_contract_counts(runtime_config.input_root)
    seeded_downstream: list[JobContract] = []
    if result.get("status") == "ok" and worker_ok:
        seeded_downstream = _seed_declared_next_jobs(
            queue_file,
            jobs,
            worker_contract,
            parent_job=job,
            events_file=events_file,
        )
        if worker_artifacts:
            _ = write_result_router(
                worker_artifacts,
                artifact_root,
                result_router_file,
                metadata={
                    "job_id": job.job_id,
                    "workload": job.workload,
                    "chain_depth": _to_int(job.payload.get("chain_depth", 0)),
                    "routed_from": str(job.payload.get("routed_from", "")),
                    "next_jobs_count": next_jobs_count,
                    "routed_count": len(seeded_downstream),
                    "worker_status": str(worker_contract.get("status", "")),
                    "worker_stage": str(worker_contract.get("stage", "")),
                    "worker_error_code": str(worker_contract.get("error_code", "")),
                    "completion_state": ""
                    if completion is None
                    else str(completion.get("state", "")),
                    "final_output": False
                    if completion is None
                    else bool(completion.get("final_output", False)),
                    "final_artifact": ""
                    if completion is None
                    else str(completion.get("final_artifact", "")),
                    "final_artifact_path": ""
                    if completion is None
                    else str(completion.get("final_artifact_path", "")),
                    "completion": {} if completion is None else completion,
                    "ts": round(time(), 3),
                },
            )
            artifact_path = worker_artifacts[0]
        else:
            artifact_path = _write_worker_artifact(job, worker_result, artifact_root)
            _ = write_result_router(
                [artifact_path],
                artifact_root,
                result_router_file,
                metadata={
                    "job_id": job.job_id,
                    "workload": job.workload,
                    "chain_depth": _to_int(job.payload.get("chain_depth", 0)),
                    "routed_from": str(job.payload.get("routed_from", "")),
                    "next_jobs_count": next_jobs_count,
                    "routed_count": len(seeded_downstream),
                    "worker_status": str(worker_contract.get("status", "")),
                    "worker_stage": str(worker_contract.get("stage", "")),
                    "worker_error_code": str(worker_contract.get("error_code", "")),
                    "completion_state": ""
                    if completion is None
                    else str(completion.get("state", "")),
                    "final_output": False
                    if completion is None
                    else bool(completion.get("final_output", False)),
                    "final_artifact": ""
                    if completion is None
                    else str(completion.get("final_artifact", "")),
                    "final_artifact_path": ""
                    if completion is None
                    else str(completion.get("final_artifact_path", "")),
                    "completion": {} if completion is None else completion,
                    "ts": round(time(), 3),
                },
            )
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
    success = result.get("status") == "ok" and worker_ok
    blocked_failure = bool(
        not success
        and (
            result.get("status") == "blocked"
            or (
                completion is not None and str(completion.get("state", "")) == "blocked"
            )
        )
    )
    recovery = _evaluate_recovery(
        job, success=bool(success), blocked=blocked_failure, config=runtime_config
    )
    next_status = _next_status_for_recovery(recovery)
    backoff_sec = _to_float(recovery.get("backoff_sec", 0), 0.0)

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
        _ = _upsert_job(queue_file, jobs, job)
        completed_record = transition_record(job.job_id, previous_status, job.status)
        completed_record["routed_from"] = str(job.payload.get("routed_from", ""))
        completed_record["chain_depth"] = _to_int(job.payload.get("chain_depth", 0))
        _ = append_transition_record(completed_record, events_file)

    control_debug_log = debug_log_path(runtime_config.debug_log_root, run_id)
    gui_status: dict[str, object] = {
        "status": "ok" if success else "failed",
        "code": "OK"
        if success
        else str(worker_contract.get("error_code", result.get("code", "FAILED"))),
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
        "worker_error_code": str(worker_contract.get("error_code", "")),
        "manifest_path": worker_manifest_path,
        "result_path": worker_result_path,
        "backoff_sec": backoff_sec,
        "completion_state": ""
        if completion is None
        else str(completion.get("state", "")),
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
        "invalid_reason": _invalid_reason_summary(runtime_config.input_root),
        "debug_log": str(control_debug_log),
    }
    _ = _write_control_gui_status(
        runtime_config,
        run_id=run_id,
        stage=str(worker_contract.get("stage", result.get("status", "unknown"))),
        exit_code=0 if success else 1,
        status=gui_status,
    )
    latest_artifacts: list[Path] = []
    if worker_artifacts:
        latest_artifacts = worker_artifacts
    elif artifact_path is not None:
        latest_artifacts = [artifact_path]
    _ = write_result_router(
        latest_artifacts,
        artifact_root,
        result_router_file,
        metadata={
            "run_id": run_id,
            "mode": "control_loop",
            "status": "ok" if success else "failed",
            "code": "OK"
            if success
            else str(worker_contract.get("error_code", result.get("code", "FAILED"))),
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
            "worker_error_code": str(worker_contract.get("error_code", "")),
            "manifest_path": worker_manifest_path,
            "result_path": worker_result_path,
            "attempts": job.attempts,
            "backoff_sec": backoff_sec,
            "chain_depth": _to_int(job.payload.get("chain_depth", 0)),
            "next_jobs_count": next_jobs_count,
            "routed_count": len(seeded_downstream),
            "completion_state": ""
            if completion is None
            else str(completion.get("state", "")),
            "final_output": False
            if completion is None
            else bool(completion.get("final_output", False)),
            "final_artifact": ""
            if completion is None
            else str(completion.get("final_artifact", "")),
            "final_artifact_path": ""
            if completion is None
            else str(completion.get("final_artifact_path", "")),
            "completion": {} if completion is None else completion,
            "invalid_reason": _invalid_reason_summary(runtime_config.input_root),
            "ts": round(time(), 3),
        },
    )
    _ = append_debug_event(
        control_debug_log,
        event="control_loop_result",
        level="ERROR" if not success else "INFO",
        payload={
            "run_id": run_id,
            "job_id": job.job_id,
            "workload": job.workload,
            "queue_status": job.status,
            "success": bool(success),
            "accepted_count": accepted_count,
            "invalid_count": invalid_count,
            "invalid_reason": _invalid_reason_summary(runtime_config.input_root),
            "runtime_result": result,
            "worker_result": worker_result,
            "recovery": recovery,
            "artifact_path": None if artifact_path is None else str(artifact_path),
            "seeded_downstream": [item.to_dict() for item in seeded_downstream],
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
            "worker_error_code": str(worker_contract.get("error_code", "")),
            "attempts": job.attempts,
            "backoff_sec": backoff_sec,
            "artifact_count": len(latest_artifacts),
            "next_jobs_count": next_jobs_count,
            "routed_count": len(seeded_downstream),
            "chain_depth": _to_int(job.payload.get("chain_depth", 0)),
            "routed_from": str(job.payload.get("routed_from", "")),
            "completion_state": ""
            if completion is None
            else str(completion.get("state", "")),
            "final_output": False
            if completion is None
            else bool(completion.get("final_output", False)),
            "final_artifact": ""
            if completion is None
            else str(completion.get("final_artifact", "")),
            "final_artifact_path": ""
            if completion is None
            else str(completion.get("final_artifact_path", "")),
            "manifest_path": worker_manifest_path,
            "result_path": worker_result_path,
        },
        events_file,
    )
    return {
        "status": "ok" if success else "failed",
        "code": "OK"
        if success
        else str(worker_contract.get("error_code", result.get("code", "FAILED"))),
        "job": job.to_dict(),
        "result": result,
        "worker_result": worker_result,
        "artifact_path": None if artifact_path is None else str(artifact_path),
        "recovery": recovery,
        "routed_count": len(seeded_downstream),
    }


def seed_control_job(job: JobContract, config: RuntimeConfig | None = None) -> None:
    runtime_config = config or RuntimeConfig()
    queue_file = getattr(
        runtime_config,
        "queue_store_file",
        Path("system/runtime_v2/state/job_queue.json"),
    )
    jobs = _load_jobs(queue_file)
    _ = _upsert_job(queue_file, jobs, job)


def seed_local_jobs(config: RuntimeConfig | None = None) -> list[JobContract]:
    runtime_config = config or RuntimeConfig()
    queue_store = QueueStore(runtime_config.queue_store_file)
    existing_jobs = queue_store.load()
    known_keys = {job.checkpoint_key for job in existing_jobs if job.checkpoint_key}
    feeder_state = _load_feeder_state(runtime_config.feeder_state_file)
    known_keys.update(feeder_state)
    seeded: list[JobContract] = []
    for job in _discover_explicit_contract_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    for job in _discover_qwen_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    for job in _discover_kenburns_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    for job in _discover_rvc_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    _ = _save_feeder_state(runtime_config.feeder_state_file, feeder_state)
    return seeded


def _write_control_gui_status(
    config: RuntimeConfig,
    *,
    run_id: str,
    stage: str,
    exit_code: int,
    status: dict[str, object],
) -> None:
    payload = build_gui_status_payload(
        status=status,
        run_id=run_id,
        mode="control_loop",
        stage=stage,
        exit_code=exit_code,
    )
    _ = write_gui_status(payload, config.gui_status_file)


def _archived_contract_counts(inbox_root: Path) -> tuple[int, int]:
    accepted_root = inbox_root / "accepted"
    invalid_root = inbox_root / "invalid"
    accepted_count = _archived_contract_count(accepted_root)
    invalid_count = _archived_contract_count(invalid_root)
    return accepted_count, invalid_count


def _archived_contract_count(root: Path) -> int:
    if not root.exists():
        return 0
    exact = list(root.glob("*.job.json"))
    legacy = [
        path
        for path in root.glob("*.job.*.json")
        if not path.name.endswith(".reason.json")
    ]
    return len(exact) + len(legacy)


def _invalid_reason_summary(inbox_root: Path) -> str:
    invalid_root = inbox_root / "invalid"
    if not invalid_root.exists():
        return ""
    reason_files = sorted(
        invalid_root.glob("*.reason.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reason_files:
        return ""
    latest = reason_files[0]
    try:
        raw_payload = cast(object, json.loads(latest.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return latest.name
    if not isinstance(raw_payload, dict):
        return latest.name
    payload = cast(dict[object, object], raw_payload)
    code = str(payload.get("code", "invalid"))
    message = str(payload.get("message", ""))
    return f"{code}:{message}" if message else code


def _discover_explicit_contract_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    inbox_root = config.input_root
    if not inbox_root.exists():
        return []
    jobs: list[JobContract] = []
    for contract_file in sorted(inbox_root.rglob("*.job.json")):
        if not contract_file.is_file() or not _is_stable_file(
            contract_file, age_sec=config.stable_file_age_sec
        ):
            continue
        if _is_explicit_contract_archived(inbox_root, contract_file):
            continue
        if not _is_allowed_explicit_contract_path(inbox_root, contract_file):
            _ = _archive_explicit_contract(
                inbox_root,
                contract_file,
                accepted=False,
                invalid_reason={
                    "code": "invalid_contract_path",
                    "message": "explicit contract must stay inside allowed inbox subdirectories",
                },
            )
            continue
        explicit_job, invalid_reason = _job_from_explicit_contract(contract_file)
        if explicit_job is None:
            _ = _archive_explicit_contract(
                inbox_root, contract_file, accepted=False, invalid_reason=invalid_reason
            )
            continue
        if explicit_job.checkpoint_key in known_keys:
            _ = _archive_explicit_contract(inbox_root, contract_file, accepted=True)
            continue
        jobs.append(explicit_job)
        _ = _archive_explicit_contract(inbox_root, contract_file, accepted=True)
    return jobs


def _job_from_explicit_contract(
    contract_file: Path,
) -> tuple[JobContract | None, dict[str, object] | None]:
    try:
        if contract_file.stat().st_size > MAX_CONTRACT_BYTES:
            return None, {
                "code": "contract_too_large",
                "message": "explicit contract exceeds size limit",
            }
        raw_payload = cast(
            object, json.loads(contract_file.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError):
        return None, {
            "code": "invalid_json",
            "message": "explicit contract is not valid JSON",
        }
    payload = _mapping_from_obj(raw_payload)
    if payload is None:
        return None, {
            "code": "invalid_contract",
            "message": "explicit contract root must be object",
        }
    return _job_from_explicit_payload(payload, source_hint=str(contract_file))


def _job_from_explicit_payload(
    payload: dict[str, object],
    *,
    source_hint: str,
) -> tuple[JobContract | None, dict[str, object] | None]:
    if str(payload.get("contract", "")) != EXPLICIT_CONTRACT_NAME:
        return None, {"code": "invalid_contract", "message": "contract name mismatch"}
    if str(payload.get("contract_version", "")) != EXPLICIT_CONTRACT_VERSION:
        return None, {
            "code": "invalid_contract_version",
            "message": "unsupported contract_version",
        }
    if bool(payload.get("local_only", False)) is not True:
        return None, {"code": "not_local_only", "message": "local_only must be true"}
    raw_job = payload.get("job")
    job_block = _mapping_from_obj(raw_job)
    if job_block is None:
        return None, {"code": "missing_job", "message": "job block missing"}
    job_id = str(job_block.get("job_id", "")).strip()
    workload = workload_from_value(
        job_block.get("worker", job_block.get("workload", ""))
    )
    if not job_id or workload is None or workload not in ALLOWED_WORKLOADS:
        return None, {"code": "invalid_job", "message": "job_id or workload invalid"}
    typed_payload: dict[str, object] = {}
    raw_payload_block = job_block.get("payload", {})
    raw_payload_dict = _mapping_from_obj(raw_payload_block)
    if raw_payload_dict is not None:
        for raw_key, raw_value in raw_payload_dict.items():
            typed_payload[str(raw_key)] = raw_value
    raw_args_block = job_block.get("args", {})
    raw_args_dict = _mapping_from_obj(raw_args_block)
    if raw_args_dict is not None:
        for raw_key, raw_value in raw_args_dict.items():
            typed_payload[str(raw_key)] = raw_value
    raw_inputs = job_block.get("inputs", [])
    if isinstance(raw_inputs, list):
        for raw_entry in cast(list[object], raw_inputs):
            entry = _mapping_from_obj(raw_entry)
            if entry is None:
                continue
            name = str(entry.get("name", "")).strip()
            path_value = str(entry.get("path", "")).strip()
            if name and path_value:
                typed_payload[name] = path_value
    raw_chain = payload.get("chain")
    chain_block = _mapping_from_obj(raw_chain)
    if chain_block is not None:
        typed_payload["chain_depth"] = _to_int(
            chain_block.get("step", chain_block.get("chain_depth", 0))
        )
        parent_job_id = str(chain_block.get("parent_job_id", "")).strip()
        if parent_job_id:
            typed_payload["routed_from"] = parent_job_id
    if not _payload_paths_are_local(typed_payload):
        return None, {
            "code": "non_local_path",
            "message": "payload paths must stay inside workspace",
        }
    checkpoint_key = str(job_block.get("checkpoint_key", f"explicit:{source_hint}"))
    return JobContract(
        job_id=job_id,
        workload=workload,
        checkpoint_key=checkpoint_key,
        payload=typed_payload,
    ), None


def _is_explicit_contract_archived(inbox_root: Path, contract_file: Path) -> bool:
    archived_roots = {inbox_root / "accepted", inbox_root / "invalid"}
    return any(
        root == contract_file.parent or root in contract_file.parents
        for root in archived_roots
    )


def _is_allowed_explicit_contract_path(inbox_root: Path, contract_file: Path) -> bool:
    allowed_roots = {
        (inbox_root / "qwen3_tts").resolve(),
        (inbox_root / "chatgpt").resolve(),
        (inbox_root / "genspark").resolve(),
        (inbox_root / "seaart").resolve(),
        (inbox_root / "geminigen").resolve(),
        (inbox_root / "canva").resolve(),
        (inbox_root / "render").resolve(),
        (inbox_root / "kenburns").resolve(),
        (inbox_root / "rvc" / "source").resolve(),
        (inbox_root / "rvc" / "audio").resolve(),
    }
    contract_parent = contract_file.resolve().parent
    return contract_parent in allowed_roots


def _archive_explicit_contract(
    inbox_root: Path,
    contract_file: Path,
    *,
    accepted: bool,
    invalid_reason: dict[str, object] | None = None,
) -> Path:
    archive_root = inbox_root / ("accepted" if accepted else "invalid")
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / contract_file.name
    if target.exists():
        target = (
            archive_root
            / f"{contract_file.name.removesuffix('.job.json')}.{int(time())}.job.json"
        )
    _ = contract_file.replace(target)
    if invalid_reason is not None:
        reason_file = target.with_suffix(target.suffix + ".reason.json")
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=reason_file.parent,
            prefix=f"{reason_file.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            _ = handle.write(json.dumps(invalid_reason, ensure_ascii=True, indent=2))
            temp_path = Path(handle.name)
        _ = temp_path.replace(reason_file)
    return target


def _next_status_for_recovery(recovery: dict[str, object]) -> str:
    action = str(recovery.get("action", "failed"))
    if action == "completed":
        return "completed"
    if action == "blocked":
        return "queued"
    if action == "retry":
        return "retry"
    return "failed"


def _discover_qwen_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    inbox = config.input_root / "qwen3_tts"
    image_inbox = config.input_root / "kenburns"
    if not inbox.exists():
        return []
    jobs: list[JobContract] = []
    for text_file in sorted(inbox.glob("*.txt")):
        if not _is_stable_file(text_file, age_sec=config.stable_file_age_sec):
            continue
        checkpoint_key = f"qwen3_tts:{text_file.resolve()}"
        if checkpoint_key in known_keys:
            continue
        script_text = text_file.read_text(encoding="utf-8").strip()
        if not script_text:
            continue
        payload: dict[str, object] = {"script_text": script_text}
        image_path = _matching_image_path(
            image_inbox, text_file.stem, age_sec=config.stable_file_age_sec
        )
        if image_path is not None:
            payload["image_path"] = str(image_path.resolve())
        if not _payload_paths_are_local(payload):
            continue
        jobs.append(
            JobContract(
                job_id=f"qwen3_tts-{text_file.stem}",
                workload="qwen3_tts",
                checkpoint_key=checkpoint_key,
                payload=payload,
            )
        )
    return jobs


def _discover_kenburns_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    inbox = config.input_root / "kenburns"
    if not inbox.exists():
        return []
    jobs: list[JobContract] = []
    for source_file in sorted(inbox.iterdir()):
        if (
            not source_file.is_file()
            or source_file.suffix.lower() not in IMAGE_EXTENSIONS
        ):
            continue
        if not _is_stable_file(source_file, age_sec=config.stable_file_age_sec):
            continue
        checkpoint_key = f"kenburns:{source_file.resolve()}"
        if checkpoint_key in known_keys:
            continue
        jobs.append(
            JobContract(
                job_id=f"kenburns-{source_file.stem}",
                workload="kenburns",
                checkpoint_key=checkpoint_key,
                payload={
                    "source_path": str(source_file.resolve()),
                    "duration_sec": 8,
                    "chain_depth": 0,
                },
            )
        )
    return jobs


def _discover_rvc_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    source_root = config.input_root / "rvc" / "source"
    audio_root = config.input_root / "rvc" / "audio"
    if not source_root.exists():
        return []
    jobs: list[JobContract] = []
    audio_candidates = _audio_map(audio_root)
    for source_file in sorted(source_root.iterdir()):
        if (
            not source_file.is_file()
            or source_file.suffix.lower() not in MEDIA_EXTENSIONS
        ):
            continue
        if not _is_stable_file(source_file, age_sec=config.stable_file_age_sec):
            continue
        checkpoint_key = f"rvc:{source_file.resolve()}"
        if checkpoint_key in known_keys:
            continue
        payload: dict[str, object] = {"source_path": str(source_file.resolve())}
        audio_match = audio_candidates.get(source_file.stem)
        if audio_match is not None:
            payload["audio_path"] = str(audio_match.resolve())
        if not _payload_paths_are_local(payload):
            continue
        jobs.append(
            JobContract(
                job_id=f"rvc-{source_file.stem}",
                workload="rvc",
                checkpoint_key=checkpoint_key,
                payload=payload,
            )
        )
    return jobs


def _audio_map(audio_root: Path) -> dict[str, Path]:
    if not audio_root.exists():
        return {}
    mapping: dict[str, Path] = {}
    for audio_file in sorted(audio_root.iterdir()):
        if (
            not audio_file.is_file()
            or audio_file.suffix.lower() not in MEDIA_EXTENSIONS
        ):
            continue
        mapping[audio_file.stem] = audio_file
    return mapping


def _matching_image_path(image_root: Path, stem: str, *, age_sec: int) -> Path | None:
    if not image_root.exists():
        return None
    for extension in sorted(IMAGE_EXTENSIONS):
        candidate = image_root / f"{stem}{extension}"
        if (
            candidate.exists()
            and candidate.is_file()
            and _is_stable_file(candidate, age_sec=age_sec)
        ):
            return candidate
    return None


def _is_stable_file(path: Path, age_sec: int = 3) -> bool:
    try:
        modified_age = time() - path.stat().st_mtime
    except OSError:
        return False
    return modified_age >= age_sec


def _load_feeder_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_payload, dict):
        return {}
    source_payload = cast(dict[object, object], raw_payload)
    state: dict[str, dict[str, object]] = {}
    for raw_key, raw_value in source_payload.items():
        if isinstance(raw_key, str) and isinstance(raw_value, dict):
            raw_mapping = cast(dict[object, object], raw_value)
            state[raw_key] = {str(key): value for key, value in raw_mapping.items()}
    return state


def _save_feeder_state(path: Path, payload: dict[str, dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True, indent=2))
        temp_path = Path(handle.name)
    _ = temp_path.replace(path)
    return path


def _mapping_from_obj(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw_value = cast(dict[object, object], value)
    return {str(key): item for key, item in raw_value.items()}


def _payload_paths_are_local(payload: dict[str, object]) -> bool:
    for key in ("source_path", "audio_path", "image_path"):
        raw_value = payload.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            if _normalize_local_path(raw_value) is None:
                return False
    return True


def _normalize_local_path(raw_path: str) -> Path | None:
    if "://" in raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
        return None
    return candidate


def _load_jobs(queue_file: Path) -> list[JobContract]:
    if not queue_file.exists():
        return []
    raw_payload_obj = cast(object, json.loads(queue_file.read_text(encoding="utf-8")))
    if not isinstance(raw_payload_obj, list):
        return []
    raw_payload = cast(list[object], raw_payload_obj)
    jobs: list[JobContract] = []
    for raw_item in raw_payload:
        if isinstance(raw_item, dict):
            item = cast(dict[object, object], raw_item)
            typed_item: dict[str, object] = {}
            for raw_key in item:
                typed_item[str(raw_key)] = item[raw_key]
            jobs.append(JobContract.from_dict(typed_item))
    return jobs


def _next_runnable_job(jobs: list[JobContract], now: float) -> JobContract | None:
    for entry in jobs:
        if entry.status == "queued":
            return entry
        if entry.status == "retry":
            next_attempt_at = _to_float(entry.payload.get("next_attempt_at", 0.0), 0.0)
            if next_attempt_at <= now:
                return entry
    return None


def _recover_stale_running_jobs(
    queue_file: Path,
    jobs: list[JobContract],
    now: float,
    config: RuntimeConfig,
    events_file: Path,
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
            if within_retry_budget(job.attempts, config.max_retry_attempts)
            else "failed"
        )
        previous_status = job.status
        job.status = recovery_action
        job.attempts += 1
        if recovery_action == "retry":
            job.payload["next_attempt_at"] = round(
                now + next_backoff_sec(job.attempts), 3
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
        )
        transition = transition_record(job.job_id, previous_status, job.status)
        transition["routed_from"] = str(job.payload.get("routed_from", ""))
        transition["chain_depth"] = _to_int(job.payload.get("chain_depth", 0))
        _ = append_transition_record(transition, events_file)
    if changed:
        _ = _save_jobs(queue_file, jobs)


def _save_jobs(queue_file: Path, jobs: list[JobContract]) -> Path:
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    payload = [job.to_dict() for job in jobs]
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=queue_file.parent,
        prefix=f"{queue_file.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(queue_file)
    return queue_file


def _upsert_job(queue_file: Path, jobs: list[JobContract], job: JobContract) -> Path:
    for index, current in enumerate(jobs):
        if current.job_id == job.job_id:
            job.updated_at = time()
            jobs[index] = job
            return _save_jobs(queue_file, jobs)
    jobs.append(job)
    return _save_jobs(queue_file, jobs)


def _append_transition_record(record: dict[str, object], output_file: Path) -> Path:
    return append_transition_record(record, output_file)


def _append_control_event(record: dict[str, object], output_file: Path) -> Path:
    payload = dict(record)
    _ = payload.setdefault("ts", round(time(), 3))
    return _append_transition_record(payload, output_file)


def _evaluate_recovery(
    job: JobContract,
    *,
    success: bool,
    blocked: bool = False,
    config: RuntimeConfig,
) -> dict[str, object]:
    circuit = CircuitState(
        failure_count=_to_int(job.payload.get("failure_count", 0)),
        opened_at=_to_optional_float(job.payload.get("circuit_opened_at")),
    )
    if blocked:
        job.payload["failure_count"] = circuit.failure_count
        job.payload["circuit_opened_at"] = circuit.opened_at
        return {"action": "blocked", "backoff_sec": 0, "circuit_open": False}
    recovery = evaluate_recovery(job.attempts, success=success, circuit=circuit)
    if not success and recovery.get("action") == "retry":
        if not within_retry_budget(job.attempts, config.max_retry_attempts):
            recovery = cast(
                dict[str, object],
                {"action": "failed", "backoff_sec": 0, "circuit_open": False},
            )
        else:
            recovery["backoff_sec"] = next_backoff_sec(job.attempts)
    job.payload["failure_count"] = circuit.failure_count
    job.payload["circuit_opened_at"] = circuit.opened_at
    return recovery


def _run_worker(
    job: JobContract,
    artifact_root: Path | None = None,
    *,
    registry_file: Path | None = None,
) -> dict[str, object]:
    if _mock_chain_enabled(job):
        if artifact_root is None:
            artifact_root = Path("system/runtime_v2/artifacts")
        return _run_mock_chain_worker(job, artifact_root)
    if artifact_root is None:
        artifact_root = Path("system/runtime_v2/artifacts")
    resolved_registry_file = registry_file or Path(
        "system/runtime_v2/health/worker_registry.json"
    )
    _ = update_worker_state(
        resolved_registry_file,
        workload=job.workload,
        state="busy",
        run_id=str(job.payload.get("run_id", job.job_id)),
    )
    if job.workload == "chatgpt":
        workspace = artifact_root / job.workload / job.job_id
        workspace.mkdir(parents=True, exist_ok=True)
        topic_spec = _mapping_from_obj(job.payload.get("topic_spec", {})) or {}
        result = run_stage1_chatgpt_job(
            topic_spec,
            workspace,
            debug_log=str(
                debug_log_path(
                    Path("system/runtime_v2/logs"),
                    str(job.payload.get("run_id", job.job_id)),
                )
            ),
        )
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    if job.workload == "genspark":
        result = run_genspark_job(
            job, artifact_root, registry_file=resolved_registry_file
        )
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    if job.workload == "seaart":
        result = run_seaart_job(
            job, artifact_root, registry_file=resolved_registry_file
        )
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    if job.workload == "geminigen":
        result = run_geminigen_job(
            job, artifact_root, registry_file=resolved_registry_file
        )
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    if job.workload == "canva":
        result = run_canva_job(job, artifact_root, registry_file=resolved_registry_file)
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    if job.workload == "render":
        result = run_render_job(job, artifact_root)
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    if job.workload == "rvc":
        result = run_rvc_job(job, artifact_root=artifact_root)
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    if job.workload == "kenburns":
        result = run_kenburns_job(job, artifact_root=artifact_root)
        _ = update_worker_state(
            resolved_registry_file,
            workload=job.workload,
            state="idle",
            run_id=str(job.payload.get("run_id", job.job_id)),
        )
        return result
    result = run_qwen3_job(job, artifact_root=artifact_root)
    _ = update_worker_state(
        resolved_registry_file,
        workload=job.workload,
        state="idle",
        run_id=str(job.payload.get("run_id", job.job_id)),
    )
    return result


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


def _mock_chain_enabled(job: JobContract) -> bool:
    return bool(job.payload.get("mock_chain", False))


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
) -> list[JobContract]:
    typed_next_jobs = _next_jobs_entries(worker_result)
    if len(typed_next_jobs) > MAX_NEXT_JOBS:
        _ = _append_control_event(
            {
                "event": "next_job_rejected",
                "parent_job_id": parent_job.job_id,
                "reason": "too_many_next_jobs",
                "count": len(typed_next_jobs),
                "max_count": MAX_NEXT_JOBS,
            },
            events_file,
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
                )
                continue
            next_job.payload["row_ref"] = expected_row_ref
        next_job.payload["chain_depth"] = next_depth
        next_job.payload["routed_from"] = parent_job.job_id
        if not _payload_paths_are_local(next_job.payload):
            _ = _append_control_event(
                {
                    "event": "next_job_rejected",
                    "parent_job_id": parent_job.job_id,
                    "job_id": next_job.job_id,
                    "reason": "non_local_payload",
                },
                events_file,
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
            )
            continue
        jobs.append(next_job)
        _ = _save_jobs(queue_file, jobs)
        known_job_ids.add(next_job.job_id)
        seeded.append(next_job)
    return seeded


def _job_from_declared_next_entry(entry: dict[str, object]) -> JobContract | None:
    parsed_job, _ = _job_from_explicit_payload(
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
                "completion": {"state": "blocked", "final_output": False},
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
                "completion": {"state": "blocked", "final_output": False},
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
                "completion": {"state": "blocked", "final_output": False},
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
            "completion": {"state": "blocked", "final_output": False},
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


def _runtime_preflight_contract(runtime_code: str) -> tuple[str, bool, str]:
    if runtime_code in {"BROWSER_BLOCKED", "GPU_LEASE_BUSY", "GPT_FLOOR_FAIL"}:
        return ("blocked", True, "blocked")
    return ("failed", True, "failed")


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

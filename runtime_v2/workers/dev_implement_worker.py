from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.dev_writer_lock import (
    acquire_repo_writer_lock,
    release_repo_writer_lock,
)
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    write_json_atomic,
)


def run_dev_implement_job(
    job: JobContract,
    artifact_root: Path,
    *,
    config: RuntimeConfig | None = None,
) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
    workspace = prepare_workspace(job, artifact_root)
    lock = acquire_repo_writer_lock(runtime_config.lock_root, owner=job.job_id)
    if not bool(lock.get("locked", False)):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="dev_implement",
            artifacts=[],
            error_code="repo_writer_lock_busy",
            retryable=True,
            details={"lock_file": str(lock.get("lock_file", ""))},
            completion={"state": "blocked", "final_output": False},
        )
    try:
        raw_tasks = job.payload.get("tasks", [])
        tasks = cast(list[object], raw_tasks) if isinstance(raw_tasks, list) else []
        implement_artifact = write_json_atomic(
            workspace / "implementation.json",
            {
                "run_id": str(job.payload.get("run_id", "")).strip(),
                "tasks": tasks,
            },
        )
        browser_checks = job.payload.get("browser_checks", [])
        check = (
            browser_checks[0]
            if isinstance(browser_checks, list) and browser_checks
            else {}
        )
        if not isinstance(check, dict):
            check = {}
        raw_verification = job.payload.get("verification", [])
        verification = (
            cast(list[object], raw_verification)
            if isinstance(raw_verification, list)
            else []
        )
        typed_browser_checks = (
            cast(list[object], browser_checks)
            if isinstance(browser_checks, list)
            else []
        )
        next_job = build_explicit_job_contract(
            job_id=f"agent-browser-verify-{job.job_id}",
            workload="agent_browser_verify",
            checkpoint_key=f"derived:agent_browser_verify:{job.job_id}",
            payload={
                "run_id": str(job.payload.get("run_id", "")).strip(),
                **{str(key): value for key, value in check.items()},
                "verification": verification,
                "browser_checks": typed_browser_checks,
                "replan_on_failure": bool(job.payload.get("replan_on_failure", False)),
                "replan_payload": job.payload.get("replan_payload", {}),
            },
            chain_step=2,
            parent_job_id=job.job_id,
        )
        return finalize_worker_result(
            workspace,
            status="ok",
            stage="dev_implement",
            artifacts=[implement_artifact],
            retryable=False,
            next_jobs=[next_job],
            completion={"state": "implemented", "final_output": False},
        )
    finally:
        release_repo_writer_lock(runtime_config.lock_root, owner=job.job_id)

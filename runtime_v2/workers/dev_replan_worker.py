from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace


def run_dev_replan_job(job: JobContract, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    replan_payload = job.payload.get("replan_payload", {})
    typed_replan_payload: dict[str, object] = {}
    if isinstance(replan_payload, dict):
        raw_replan_payload = cast(dict[object, object], replan_payload)
        typed_replan_payload = {
            str(key): value for key, value in raw_replan_payload.items()
        }
    browser_checks = typed_replan_payload.get(
        "browser_checks", job.payload.get("browser_checks", [])
    )
    tasks = typed_replan_payload.get("tasks", job.payload.get("tasks", []))
    raw_verification = job.payload.get("verification", [])
    verification = (
        cast(list[object], raw_verification)
        if isinstance(raw_verification, list)
        else []
    )
    typed_tasks = cast(list[object], tasks) if isinstance(tasks, list) else []
    typed_browser_checks = (
        cast(list[object], browser_checks) if isinstance(browser_checks, list) else []
    )
    next_job = build_explicit_job_contract(
        job_id=f"dev-implement-{job.job_id}",
        workload="dev_implement",
        checkpoint_key=f"derived:dev_implement:{job.job_id}",
        payload={
            "run_id": str(job.payload.get("run_id", "")).strip(),
            "tasks": typed_tasks,
            "verification": verification,
            "browser_checks": typed_browser_checks,
            "replan_on_failure": False,
        },
        chain_step=4,
        parent_job_id=job.job_id,
    )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="dev_replan",
        artifacts=[],
        retryable=False,
        next_jobs=[next_job],
        completion={"state": "replanned", "final_output": False},
    )

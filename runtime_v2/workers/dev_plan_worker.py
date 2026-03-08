from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.dev_loop_plan import parse_dev_loop_plan
from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace


def run_dev_plan_job(job: JobContract, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    raw_plan = job.payload.get("plan", {})
    typed_plan: dict[str, object] = {}
    if isinstance(raw_plan, dict):
        raw_plan_dict = cast(dict[object, object], raw_plan)
        typed_plan = {str(key): value for key, value in raw_plan_dict.items()}
    parsed_plan = parse_dev_loop_plan(typed_plan)
    next_job = build_explicit_job_contract(
        job_id=f"dev-implement-{job.job_id}",
        workload="dev_implement",
        checkpoint_key=f"derived:dev_implement:{job.job_id}",
        payload={
            "run_id": str(job.payload.get("run_id", "")).strip(),
            "tasks": parsed_plan["tasks"],
            "verification": parsed_plan["verification"],
            "browser_checks": parsed_plan["browser_checks"],
            "replan_on_failure": parsed_plan["replan_on_failure"],
            "replan_payload": parsed_plan.get("replan_payload", {}),
        },
        chain_step=1,
        parent_job_id=job.job_id,
    )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="dev_plan",
        artifacts=[],
        retryable=False,
        next_jobs=[next_job],
        completion={"state": "planned", "final_output": False},
        details={"goal": parsed_plan["goal"]},
    )

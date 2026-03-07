from __future__ import annotations


def stage1_result_payload(
    *,
    run_id: str,
    row_ref: str,
    video_plan_path: str,
    debug_log: str,
    reason_code: str = "ok",
    next_jobs: list[dict[str, object]] | None = None,
    error_code: str = "",
    result_path: str = "",
    status: str = "ok",
) -> dict[str, object]:
    return {
        "contract": "stage1_result",
        "contract_version": "1.0",
        "run_id": run_id,
        "row_ref": row_ref,
        "status": status,
        "reason_code": reason_code,
        "video_plan_path": video_plan_path,
        "debug_log": debug_log,
        "next_jobs": next_jobs or [],
        "error_code": error_code,
        "result_path": result_path,
    }

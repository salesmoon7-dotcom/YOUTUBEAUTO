from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.contracts.job_contract import _to_int
from runtime_v2.excel.source import read_excel_row
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace


def sync_google_sheets_row(payload: dict[str, object]) -> dict[str, object]:
    return {"ok": False, "status_code": 0, "error": "google_sheets_sync_not_configured"}


def run_google_sheets_sync_job(job: JobContract, *, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    excel_path = str(job.payload.get("excel_path", "")).strip()
    sheet_name = str(job.payload.get("sheet_name", "")).strip()
    row_index = _to_int(job.payload.get("row_index", 0))
    row_ref = str(job.payload.get("row_ref", "")).strip()
    if not excel_path or not sheet_name:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_google_sheets_sync_inputs",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    row_map = read_excel_row(excel_path, sheet_name=sheet_name, row_index=row_index)
    values = [value for value in row_map.values()]
    payload: dict[str, object] = {
        "excel_path": excel_path,
        "sheet_name": sheet_name,
        "row_index": row_index,
        "row_ref": row_ref,
        "values": values,
        "row_data": cast(dict[str, object], row_map),
        "job_id": job.job_id,
        "workload": job.workload,
    }
    result = sync_google_sheets_row(payload)
    if not bool(result.get("ok")):
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="google_sheets_sync",
            artifacts=[],
            error_code="google_sheets_sync_failed",
            retryable=False,
            details={"sync": result},
            completion={"state": "failed", "final_output": False},
        )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="google_sheets_sync",
        artifacts=[],
        details={"sync": result},
        completion={"state": "succeeded", "final_output": True},
    )

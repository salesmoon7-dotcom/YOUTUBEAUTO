from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.legacy_executor import LEGACY_ROOT, build_canva_thumb_file, channel_from_payload, int_value, load_legacy_result_json, resolve_output_from_result, row_index_from_payload, script_command, stage_output, stage_service_artifact
from runtime_v2.worker_registry import update_worker_state
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace, write_json_atomic


def run_canva_job(job: JobContract, artifact_root: Path, registry_file: Path | None = None) -> dict[str, object]:
    if registry_file is not None:
        _ = update_worker_state(registry_file, workload="canva", state="busy", run_id=str(job.payload.get("run_id", job.job_id)))
    workspace = prepare_workspace(job, artifact_root)
    request_path = write_json_atomic(workspace / "request.json", {"payload": job.payload})
    thumb_data_path = build_canva_thumb_file(workspace, job.payload)
    result_json_path = workspace / "legacy_result.json"
    save_path = workspace / "thumbnail.png"
    command = script_command("canva_automation.py") + [
        "--channel",
        str(channel_from_payload(job.payload)),
        "--row",
        str(row_index_from_payload(job.payload)),
        "--thumb-data-file",
        str(thumb_data_path.resolve()),
        "--save-path",
        str(save_path.resolve()),
        "--result-json",
        str(result_json_path.resolve()),
    ]
    ref_img = str(job.payload.get("ref_img", "")).strip()
    if ref_img:
        command.extend(["--ref-img", ref_img])
    process_result = cast(dict[str, object], run_external_process(command, cwd=LEGACY_ROOT))
    exit_code = int_value(process_result.get("exit_code", 1), 1)
    if exit_code != 0 or not result_json_path.exists():
        result = finalize_worker_result(
            workspace,
            status="failed",
            stage="canva",
            artifacts=[request_path, thumb_data_path],
            error_code="legacy_executor_failed",
            retryable=True,
            details={"process_result": process_result},
            completion={"state": "blocked", "final_output": False},
        )
    else:
        parsed_result = load_legacy_result_json(
            workspace,
            stage="canva",
            result_json_path=result_json_path,
            artifacts=[request_path, thumb_data_path, result_json_path],
            process_result=process_result,
        )
        if parsed_result.get("status") == "failed":
            result = parsed_result
        else:
            result_payload = cast(dict[str, object], parsed_result)
            output_path = resolve_output_from_result(result_payload, prefer_thumbnail=True)
            if output_path is None:
                result = finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="canva",
                    artifacts=[request_path, thumb_data_path, result_json_path],
                    error_code="missing_legacy_outputs",
                    retryable=True,
                    details={"legacy_result": result_payload, "process_result": process_result},
                    completion={"state": "blocked", "final_output": False},
                )
            else:
                staged_output = stage_output(workspace, output_path, fallback_name="canva_thumb.png")
                shared_output = stage_service_artifact(staged_output, str(job.payload.get("service_artifact_path", "")))
                result = finalize_worker_result(
                    workspace,
                    status="ok",
                    stage="canva",
                    artifacts=[staged_output, request_path, thumb_data_path, result_json_path],
                    retryable=False,
                    details={
                        "legacy_result": result_payload,
                        "service_artifact_path": str(output_path.resolve()),
                        "shared_service_artifact_path": "" if shared_output is None else str(shared_output.resolve()),
                    },
                    completion={"state": "routed", "final_output": False},
                )
    if registry_file is not None:
        _ = update_worker_state(registry_file, workload="canva", state="idle", run_id=str(job.payload.get("run_id", job.job_id)))
    return result

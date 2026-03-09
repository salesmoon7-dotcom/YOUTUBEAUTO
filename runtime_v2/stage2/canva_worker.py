from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.agent_browser_adapter import (
    attach_evidence_path,
    build_stage2_agent_browser_adapter_command,
)
from runtime_v2.stage2.request_builders import (
    build_canva_thumb_file,
    channel_from_payload,
    row_index_from_payload,
)
from runtime_v2.workers.external_process import run_verified_adapter_command
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def run_canva_job(
    job: JobContract, artifact_root: Path, registry_file: Path | None = None
) -> dict[str, object]:
    _ = registry_file
    workspace = prepare_workspace(job, artifact_root)
    prompt = str(job.payload.get("prompt", "")).strip()
    if not prompt:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_prompt",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    request_path = write_native_request(workspace, job.payload)
    thumb_data_path = build_canva_thumb_file(workspace, job.payload)
    ref_img = str(job.payload.get("ref_img", "")).strip()
    adapter_command_raw = job.payload.get("adapter_command")
    if (not isinstance(adapter_command_raw, list) or not adapter_command_raw) and bool(
        job.payload.get("use_agent_browser", False)
    ):
        adapter_command_raw = build_stage2_agent_browser_adapter_command(
            service="canva",
            service_artifact_path=str(job.payload.get("service_artifact_path", "")),
            expected_url_substring=str(job.payload.get("expected_url_substring", "")),
            expected_title_substring=str(
                job.payload.get("expected_title_substring", "")
            ),
        )
    if isinstance(adapter_command_raw, list) and adapter_command_raw:
        adapter_command_items = cast(list[object], adapter_command_raw)
        adapter_command = [str(item) for item in adapter_command_items]
        adapter_result = run_verified_adapter_command(
            workspace,
            adapter_command=adapter_command,
            service_artifact_path=str(job.payload.get("service_artifact_path", "")),
            adapter_error_code="canva_adapter_failed",
        )
        stdout_path = Path(str(adapter_result["stdout_path"]))
        stderr_path = Path(str(adapter_result["stderr_path"]))
        attach_evidence = attach_evidence_path(workspace)
        if not bool(adapter_result.get("ok", False)):
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="canva_adapter",
                artifacts=[
                    request_path,
                    thumb_data_path,
                    stdout_path,
                    stderr_path,
                    *([attach_evidence] if attach_evidence.exists() else []),
                ],
                error_code=str(
                    adapter_result.get("error_code", "canva_adapter_failed")
                ),
                retryable=False,
                details=cast(dict[str, object], adapter_result.get("details", {})),
                completion={"state": "failed", "final_output": False},
            )
        verified_output = Path(str(adapter_result["output_path"]))

        return finalize_worker_result(
            workspace,
            status="ok",
            stage="canva",
            artifacts=[
                request_path,
                thumb_data_path,
                stdout_path,
                stderr_path,
                *([attach_evidence] if attach_evidence.exists() else []),
                verified_output,
            ],
            retryable=False,
            details={
                "channel": channel_from_payload(job.payload),
                "row_index": row_index_from_payload(job.payload),
                "save_path": str(verified_output.resolve()),
                "ref_img": ref_img,
                "service_artifact_path": str(verified_output.resolve()),
                "adapter_mode": (
                    "agent_browser"
                    if bool(job.payload.get("use_agent_browser", False))
                    and "--agent-browser-stage2-adapter-child" in adapter_command
                    else "command"
                ),
                "attach_evidence_path": (
                    str(attach_evidence.resolve()) if attach_evidence.exists() else ""
                ),
            },
            completion={
                "state": "succeeded",
                "final_output": True,
                "final_artifact": verified_output.name,
                "final_artifact_path": str(verified_output.resolve()),
            },
        )

    return native_not_implemented_result(
        workspace,
        workload="canva",
        stage="canva",
        artifacts=[request_path, thumb_data_path],
        details={
            "channel": channel_from_payload(job.payload),
            "row_index": row_index_from_payload(job.payload),
            "save_path": str((workspace / "thumbnail.png").resolve()),
            "ref_img": ref_img,
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )

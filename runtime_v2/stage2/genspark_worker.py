from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.agent_browser_adapter import (
    attach_evidence_path,
    build_stage2_agent_browser_adapter_command,
    canonical_stage2_adapter_env,
    load_stage2_attach_evidence,
)
from runtime_v2.stage2.request_builders import build_image_prompt_file
from runtime_v2.workers.external_process import run_verified_adapter_command
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


_RETRYABLE_BROWSER_ERROR_CODES = {
    "BROWSER_UNHEALTHY",
    "BROWSER_BLOCKED",
    "AGENT_BROWSER_COMMAND_FAILED",
    "AGENT_BROWSER_VERIFY_FAILED",
    "AGENT_BROWSER_TIMEOUT",
}


def run_genspark_job(
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
    prompt_path = build_image_prompt_file(workspace, job.payload, workload="genspark")
    adapter_command_raw = job.payload.get("adapter_command")
    if (not isinstance(adapter_command_raw, list) or not adapter_command_raw) and bool(
        job.payload.get("use_agent_browser", False)
    ):
        adapter_command_raw = build_stage2_agent_browser_adapter_command(
            service="genspark",
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
            approved_root=artifact_root,
            adapter_command=adapter_command,
            service_artifact_path=str(job.payload.get("service_artifact_path", "")),
            adapter_error_code="genspark_adapter_failed",
            extra_env=canonical_stage2_adapter_env(),
        )
        stdout_path = Path(str(adapter_result["stdout_path"]))
        stderr_path = Path(str(adapter_result["stderr_path"]))
        attach_evidence = attach_evidence_path(workspace)
        attach_evidence_payload = load_stage2_attach_evidence(workspace)
        if not bool(adapter_result.get("ok", False)):
            adapter_error_code = str(
                adapter_result.get("error_code", "genspark_adapter_failed")
            )
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="genspark_adapter",
                artifacts=[
                    request_path,
                    prompt_path,
                    stdout_path,
                    stderr_path,
                    *([attach_evidence] if attach_evidence.exists() else []),
                ],
                error_code=adapter_error_code,
                retryable=adapter_error_code in _RETRYABLE_BROWSER_ERROR_CODES,
                details=cast(dict[str, object], adapter_result.get("details", {})),
                completion={"state": "failed", "final_output": False},
            )
        verified_output = Path(str(adapter_result["output_path"]))

        return finalize_worker_result(
            workspace,
            status="ok",
            stage="genspark",
            artifacts=[
                request_path,
                prompt_path,
                stdout_path,
                stderr_path,
                *([attach_evidence] if attach_evidence.exists() else []),
                verified_output,
            ],
            retryable=False,
            details={
                "model": str(job.payload.get("model", "stage2")),
                "service_artifact_path": str(verified_output.resolve()),
                "reused": bool(adapter_result.get("reused", False)),
                "ref_img_1": str(job.payload.get("ref_img_1", "")).strip(),
                "ref_img_2": str(job.payload.get("ref_img_2", "")).strip(),
                "adapter_mode": (
                    "agent_browser"
                    if bool(job.payload.get("use_agent_browser", False))
                    and "--agent-browser-stage2-adapter-child" in adapter_command
                    else "command"
                ),
                "attach_evidence_path": (
                    str(attach_evidence.resolve()) if attach_evidence.exists() else ""
                ),
                "ref_images_requested": cast(
                    list[object],
                    attach_evidence_payload.get("ref_images_requested", []),
                )
                if isinstance(
                    attach_evidence_payload.get("ref_images_requested", []), list
                )
                else [],
                "ref_images_resolved": cast(
                    list[object], attach_evidence_payload.get("ref_images_resolved", [])
                )
                if isinstance(
                    attach_evidence_payload.get("ref_images_resolved", []), list
                )
                else [],
                "ref_images_attach_attempted": bool(
                    attach_evidence_payload.get("ref_images_attach_attempted", False)
                ),
                "ref_upload_error_code": str(
                    attach_evidence_payload.get("ref_upload_error_code", "")
                ),
            },
            completion={
                "state": "succeeded",
                "final_output": True,
                "final_artifact": verified_output.name,
                "final_artifact_path": str(verified_output.resolve()),
                "reused": bool(adapter_result.get("reused", False)),
            },
        )

    return native_not_implemented_result(
        workspace,
        workload="genspark",
        stage="genspark",
        artifacts=[request_path, prompt_path],
        details={
            "model": str(job.payload.get("model", "stage2")),
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )

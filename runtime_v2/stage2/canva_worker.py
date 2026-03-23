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


_RETRYABLE_BROWSER_ERROR_CODES = {
    "BROWSER_UNHEALTHY",
    "BROWSER_BLOCKED",
    "AGENT_BROWSER_COMMAND_FAILED",
    "AGENT_BROWSER_VERIFY_FAILED",
    "AGENT_BROWSER_TIMEOUT",
}


def _int_detail(details: dict[str, object], key: str) -> int:
    raw_value = details.get(key, 0)
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if text:
            return int(text)
    return 0


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
        stale_attach_evidence = attach_evidence_path(workspace)
        if stale_attach_evidence.exists():
            stale_attach_evidence.unlink()
        adapter_result = run_verified_adapter_command(
            workspace,
            approved_root=artifact_root,
            adapter_command=adapter_command,
            service_artifact_path=str(job.payload.get("service_artifact_path", "")),
            adapter_error_code="canva_adapter_failed",
            extra_env=canonical_stage2_adapter_env(),
        )
        stdout_path = Path(str(adapter_result["stdout_path"]))
        stderr_path = Path(str(adapter_result["stderr_path"]))
        attach_evidence = attach_evidence_path(workspace)
        attach_evidence_payload = load_stage2_attach_evidence(workspace)
        attach_details_raw = attach_evidence_payload.get("details", {})
        attach_details = (
            cast(dict[str, object], attach_details_raw)
            if isinstance(attach_details_raw, dict)
            else {}
        )
        if not bool(adapter_result.get("ok", False)):
            adapter_error_code = str(
                adapter_result.get("error_code", "canva_adapter_failed")
            )
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
                error_code=adapter_error_code,
                retryable=adapter_error_code in _RETRYABLE_BROWSER_ERROR_CODES,
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
                "reused": bool(adapter_result.get("reused", False)),
                "adapter_mode": (
                    "agent_browser"
                    if bool(job.payload.get("use_agent_browser", False))
                    and "--agent-browser-stage2-adapter-child" in adapter_command
                    else "command"
                ),
                "attach_evidence_path": (
                    str(attach_evidence.resolve()) if attach_evidence.exists() else ""
                ),
                "attach_status": str(attach_evidence_payload.get("status", "")),
                "attach_error_code": str(attach_evidence_payload.get("error_code", "")),
                "placeholder_artifact": bool(
                    attach_evidence_payload.get("placeholder_artifact", False)
                ),
                "current_url": str(attach_evidence_payload.get("current_url", "")),
                "current_title": str(attach_evidence_payload.get("current_title", "")),
                "page_count_before": _int_detail(attach_details, "page_count_before"),
                "page_count_after": _int_detail(attach_details, "page_count_after"),
                "clone_ok": bool(attach_details.get("clone_ok", False)),
                "background_generate_ok": bool(
                    attach_details.get("background_generate_ok", False)
                ),
                "upload_tab_ok": bool(attach_details.get("upload_tab_ok", False)),
                "ref_image_requested": str(
                    attach_details.get("ref_image_requested", "")
                ),
                "ref_image_upload_ok": bool(
                    attach_details.get("ref_image_upload_ok", False)
                ),
                "remove_background_ok": bool(
                    attach_details.get("remove_background_ok", False)
                ),
                "position_ok": bool(attach_details.get("position_ok", False)),
                "text_edit_ok": bool(attach_details.get("text_edit_ok", False)),
                "current_page_selection_ok": bool(
                    attach_details.get("current_page_selection_ok", False)
                ),
                "download_options_ok": bool(
                    attach_details.get("download_options_ok", False)
                ),
                "download_sequence_ok": bool(
                    attach_details.get("download_sequence_ok", False)
                ),
                "cleanup_ok": bool(attach_details.get("cleanup_ok", False)),
                "bg_prompt": str(attach_details.get("bg_prompt", "")),
                "line1": str(attach_details.get("line1", "")),
                "line2": str(attach_details.get("line2", "")),
                "transcript_path": str(attach_details.get("transcript_path", "")),
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

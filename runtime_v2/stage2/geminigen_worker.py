from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.contracts.job_contract import build_explicit_job_contract
from runtime_v2.stage2.agent_browser_adapter import (
    attach_evidence_path,
    build_stage2_agent_browser_adapter_command,
    canonical_stage2_adapter_env,
)
from runtime_v2.stage2.request_builders import build_geminigen_prompt_file
from runtime_v2.workers.external_process import run_verified_adapter_command
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def _int_value(raw_value: object, default: int) -> int:
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, int):
        return int(str(raw_value))
    if isinstance(raw_value, float):
        return int(str(raw_value))
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if text:
            return int(text)
    return default


def run_geminigen_job(
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
    prompt_path = build_geminigen_prompt_file(workspace, job.payload)
    adapter_command_raw = job.payload.get("adapter_command")
    if (not isinstance(adapter_command_raw, list) or not adapter_command_raw) and bool(
        job.payload.get("use_agent_browser", False)
    ):
        adapter_command_raw = build_stage2_agent_browser_adapter_command(
            service="geminigen",
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
            adapter_error_code="geminigen_adapter_failed",
            extra_env=canonical_stage2_adapter_env(),
        )
        stdout_path = Path(str(adapter_result["stdout_path"]))
        stderr_path = Path(str(adapter_result["stderr_path"]))
        attach_evidence = attach_evidence_path(workspace)
        if not bool(adapter_result.get("ok", False)):
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="geminigen_adapter",
                artifacts=[
                    request_path,
                    prompt_path,
                    stdout_path,
                    stderr_path,
                    *([attach_evidence] if attach_evidence.exists() else []),
                ],
                error_code=str(
                    adapter_result.get("error_code", "geminigen_adapter_failed")
                ),
                retryable=False,
                details=cast(dict[str, object], adapter_result.get("details", {})),
                completion={"state": "failed", "final_output": False},
            )
        verified_output = Path(str(adapter_result["output_path"]))

        next_jobs: list[dict[str, object]] = []
        model_name = str(job.payload.get("model_name", "")).strip()
        chain_step = _int_value(job.payload.get("chain_depth", 0), 0) + 1
        if model_name:
            next_jobs.append(
                build_explicit_job_contract(
                    job_id=f"rvc-{job.job_id}",
                    workload="rvc",
                    checkpoint_key=f"derived:rvc:{job.job_id}",
                    payload={
                        "audio_path": str(verified_output.resolve()),
                        "model_name": model_name,
                        "service_artifact_path": str(
                            verified_output.with_name(
                                f"{verified_output.stem}_rvc.wav"
                            ).resolve()
                        ),
                        "chain_depth": chain_step,
                        "run_id": str(job.payload.get("run_id", "")).strip(),
                        "row_ref": str(job.payload.get("row_ref", "")).strip(),
                        "topic": str(job.payload.get("topic", "")).strip(),
                    },
                    chain_step=chain_step,
                    parent_job_id=job.job_id,
                )
            )

        return finalize_worker_result(
            workspace,
            status="ok",
            stage="geminigen",
            artifacts=[
                request_path,
                prompt_path,
                stdout_path,
                stderr_path,
                *([attach_evidence] if attach_evidence.exists() else []),
                verified_output,
            ],
            retryable=False,
            next_jobs=next_jobs,
            details={
                "provider": str(job.payload.get("provider", "google")),
                "model": str(job.payload.get("model", "veo3")),
                "generation_mode": str(
                    job.payload.get("generation_mode", "create_new")
                ),
                "orientation": str(job.payload.get("orientation", "landscape")),
                "resolution": str(job.payload.get("resolution", "720p")),
                "duration": str(
                    job.payload.get("duration", job.payload.get("duration_sec", 6))
                ),
                "first_frame_path": str(
                    job.payload.get("first_frame_path", "")
                ).strip(),
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
            },
            completion={
                "state": "routed" if next_jobs else "succeeded",
                "final_output": True,
                "final_artifact": verified_output.name,
                "final_artifact_path": str(verified_output.resolve()),
                "reused": bool(adapter_result.get("reused", False)),
            },
        )

    return native_not_implemented_result(
        workspace,
        workload="geminigen",
        stage="geminigen",
        artifacts=[request_path, prompt_path],
        details={
            "provider": str(job.payload.get("provider", "google")),
            "model": str(job.payload.get("model", "veo3")),
            "generation_mode": str(job.payload.get("generation_mode", "create_new")),
            "orientation": str(job.payload.get("orientation", "landscape")),
            "resolution": str(job.payload.get("resolution", "720p")),
            "duration": str(
                job.payload.get("duration", job.payload.get("duration_sec", 6))
            ),
            "first_frame_path": str(job.payload.get("first_frame_path", "")).strip(),
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )

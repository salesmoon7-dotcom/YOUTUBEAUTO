from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.contracts.job_contract import build_explicit_job_contract
from runtime_v2.stage2.agent_browser_adapter import (
    attach_evidence_path,
    build_stage2_agent_browser_adapter_command,
    canonical_stage2_adapter_env,
    load_stage2_attach_evidence,
)
from runtime_v2.stage2.request_builders import build_geminigen_prompt_file
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

_GEMINIGEN_LOGIN_URL_PATTERNS = (
    "auth/login",
    "/login",
    "signin",
    "sign-in",
    "accounts.google.com",
)


def _transcript_shows_login_redirect(transcript_path: Path) -> bool:
    if not transcript_path.exists():
        return False
    try:
        raw_payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw_payload, dict):
        return False
    steps = raw_payload.get("steps", [])
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        output = str(step.get("output", "")).lower()
        if any(pattern in output for pattern in _GEMINIGEN_LOGIN_URL_PATTERNS):
            return True
    return False


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


def _geminigen_session_proof_failure(
    workspace: Path, *, use_agent_browser: bool
) -> tuple[str, dict[str, object]] | None:
    if not use_agent_browser:
        return None
    attach_evidence = load_stage2_attach_evidence(workspace)
    if not attach_evidence:
        return "GEMINIGEN_LOGIN_UNPROVEN", {
            "reason": "missing_attach_evidence",
        }
    current_url = str(attach_evidence.get("current_url", "")).strip()
    current_title = str(attach_evidence.get("current_title", "")).strip()
    normalized_url = current_url.lower()
    transcript_path = Path(str(attach_evidence.get("transcript_path", "")).strip())
    if _transcript_shows_login_redirect(transcript_path):
        return "GEMINIGEN_LOGIN_REQUIRED", {
            "reason": "login_redirect_detected_in_transcript",
            "current_url": current_url,
            "current_title": current_title,
            "transcript_path": str(transcript_path),
        }
    if any(pattern in normalized_url for pattern in _GEMINIGEN_LOGIN_URL_PATTERNS):
        return "GEMINIGEN_LOGIN_REQUIRED", {
            "reason": "login_url_detected",
            "current_url": current_url,
            "current_title": current_title,
        }
    if not normalized_url or "geminigen.ai" not in normalized_url:
        return "GEMINIGEN_LOGIN_UNPROVEN", {
            "reason": "missing_geminigen_runtime_url",
            "current_url": current_url,
            "current_title": current_title,
        }
    return None


def _resolve_geminigen_image_path(payload: dict[str, object]) -> str:
    image_path = str(payload.get("first_frame_path", "")).strip()
    if image_path:
        return image_path
    manifest_path_raw = str(payload.get("asset_manifest_path", "")).strip()
    if not manifest_path_raw:
        return ""
    manifest_path = Path(manifest_path_raw)
    if not manifest_path.exists() or not manifest_path.is_file():
        return ""
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(raw_manifest, dict):
        return ""
    roles = raw_manifest.get("roles", {})
    if not isinstance(roles, dict):
        return ""
    return str(roles.get("image_primary", "")).strip()


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
        use_agent_browser = bool(job.payload.get("use_agent_browser", False))
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
            adapter_error_code = str(
                adapter_result.get("error_code", "geminigen_adapter_failed")
            )
            session_proof_failure = _geminigen_session_proof_failure(
                workspace, use_agent_browser=use_agent_browser
            )
            if session_proof_failure is not None:
                session_error_code, session_details = session_proof_failure
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="geminigen_session",
                    artifacts=[
                        request_path,
                        prompt_path,
                        stdout_path,
                        stderr_path,
                        *([attach_evidence] if attach_evidence.exists() else []),
                    ],
                    error_code=session_error_code,
                    retryable=False,
                    details=session_details,
                    completion={"state": "failed", "final_output": False},
                )
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
                error_code=adapter_error_code,
                retryable=adapter_error_code in _RETRYABLE_BROWSER_ERROR_CODES,
                details=cast(dict[str, object], adapter_result.get("details", {})),
                completion={"state": "failed", "final_output": False},
            )
        session_proof_failure = _geminigen_session_proof_failure(
            workspace, use_agent_browser=use_agent_browser
        )
        if session_proof_failure is not None:
            session_error_code, session_details = session_proof_failure
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="geminigen_session",
                artifacts=[
                    request_path,
                    prompt_path,
                    stdout_path,
                    stderr_path,
                    *([attach_evidence] if attach_evidence.exists() else []),
                ],
                error_code=session_error_code,
                retryable=False,
                details=session_details,
                completion={"state": "failed", "final_output": False},
            )
        verified_output = Path(str(adapter_result["output_path"]))

        next_jobs: list[dict[str, object]] = []
        model_name = str(job.payload.get("model_name", "")).strip()
        chain_step = _int_value(job.payload.get("chain_depth", 0), 0) + 1
        resolved_image_path = _resolve_geminigen_image_path(job.payload)
        if model_name:
            next_jobs.append(
                build_explicit_job_contract(
                    job_id=f"rvc-{job.job_id}",
                    workload="rvc",
                    checkpoint_key=f"derived:rvc:{job.job_id}",
                    payload={
                        "audio_path": str(verified_output.resolve()),
                        "image_path": resolved_image_path,
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
                "resolved_image_path": resolved_image_path,
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
            "resolved_image_path": _resolve_geminigen_image_path(job.payload),
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

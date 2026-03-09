from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

from runtime_v2.agent_browser.command_builder import (
    build_get_title_command,
    build_get_url_command,
    build_snapshot_command,
    build_tab_list_command,
    build_tab_select_command,
)
from runtime_v2.agent_browser.result_parser import (
    parse_scalar_output,
    parse_tab_list_output,
    select_best_tab,
)
from runtime_v2.browser.manager import BrowserManager
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    write_json_atomic,
)


def _run_agent_browser_command(command: list[str], *, timeout_sec: int = 30) -> str:
    resolved_command = _resolve_agent_browser_command(command)
    completed = subprocess.run(
        resolved_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_sec,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit_code={completed.returncode}"
        raise RuntimeError(detail)
    return completed.stdout


def _resolve_agent_browser_command(command: list[str]) -> list[str]:
    if not command:
        return command
    executable = command[0]
    if executable != "agent-browser":
        return command
    resolved = shutil.which(executable)
    if resolved:
        return [resolved, *command[1:]]
    appdata = os.environ.get("APPDATA", "").strip()
    candidates: list[Path] = []
    if appdata:
        npm_root = Path(appdata) / "npm"
        candidates.extend(
            [
                npm_root / "agent-browser.cmd",
                npm_root / "agent-browser.ps1",
                npm_root
                / "node_modules"
                / "agent-browser"
                / "bin"
                / "agent-browser-win32-x64.exe",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return [str(candidate), *command[1:]]
    return command


def _default_port_for_service(service: str) -> int:
    for session in BrowserManager().sessions:
        if session.service == service:
            return session.port
    raise ValueError(f"unknown_agent_browser_service:{service}")


def _agent_browser_error_code(exc: Exception) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "AGENT_BROWSER_TIMEOUT"
    message = str(exc).strip()
    if message == "agent_browser_target_required":
        return "AGENT_BROWSER_TARGET_REQUIRED"
    if message == "agent_browser_matching_tab_not_found":
        return "AGENT_BROWSER_MATCHING_TAB_NOT_FOUND"
    if isinstance(exc, RuntimeError):
        return "AGENT_BROWSER_COMMAND_FAILED"
    return "AGENT_BROWSER_VERIFY_FAILED"


def run_agent_browser_verify_job(
    job: JobContract,
    artifact_root: Path,
    *,
    registry_file: Path | None = None,
) -> dict[str, object]:
    del registry_file
    workspace = prepare_workspace(job, artifact_root)
    service = str(job.payload.get("service", "chatgpt")).strip() or "chatgpt"
    expected_url = str(job.payload.get("expected_url_substring", "")).strip()
    expected_title = str(job.payload.get("expected_title_substring", "")).strip()
    if not expected_url and not expected_title:
        transcript_path = write_json_atomic(
            workspace / "agent_browser_transcript.json",
            {
                "service": service,
                "error": "agent_browser_target_required",
                "steps": [],
            },
        )
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="agent_browser_verify",
            artifacts=[transcript_path],
            error_code="AGENT_BROWSER_TARGET_REQUIRED",
            retryable=False,
            details={
                "service": service,
                "transcript_path": str(transcript_path.resolve()),
            },
            completion={"state": "blocked", "final_output": False},
        )
    raw_port = job.payload.get("port")
    port = (
        int(raw_port)
        if isinstance(raw_port, int)
        else _default_port_for_service(service)
    )

    transcript: list[dict[str, object]] = []
    try:
        tab_list_command = build_tab_list_command(port=port)
        tab_list_output = _run_agent_browser_command(tab_list_command)
        transcript.append({"command": tab_list_command, "output": tab_list_output})
        tabs = parse_tab_list_output(tab_list_output)

        selected_tab = select_best_tab(
            tabs,
            expected_url_substring=expected_url,
            expected_title_substring=expected_title,
        )
        if selected_tab is None and (expected_url or expected_title):
            raise ValueError("agent_browser_matching_tab_not_found")
        if selected_tab is not None:
            select_command = build_tab_select_command(port=port, index=selected_tab)
            select_output = _run_agent_browser_command(select_command)
            transcript.append({"command": select_command, "output": select_output})

        get_url_command = build_get_url_command(port=port)
        current_url = parse_scalar_output(_run_agent_browser_command(get_url_command))
        transcript.append({"command": get_url_command, "output": current_url})

        get_title_command = build_get_title_command(port=port)
        current_title = parse_scalar_output(
            _run_agent_browser_command(get_title_command)
        )
        transcript.append({"command": get_title_command, "output": current_title})

        snapshot_command = build_snapshot_command(port=port, max_output=1200)
        snapshot_output = _run_agent_browser_command(snapshot_command)
        transcript.append({"command": snapshot_command, "output": snapshot_output})

        transcript_path = write_json_atomic(
            workspace / "agent_browser_transcript.json",
            {"service": service, "port": port, "steps": transcript},
        )
        snapshot_path = workspace / "snapshot.txt"
        _ = snapshot_path.write_text(snapshot_output, encoding="utf-8")

        details: dict[str, object] = {
            "service": service,
            "port": port,
            "selected_tab": selected_tab,
            "current_url": current_url,
            "current_title": current_title,
            "transcript_path": str(transcript_path.resolve()),
            "snapshot_path": str(snapshot_path.resolve()),
        }
        return finalize_worker_result(
            workspace,
            status="ok",
            stage="agent_browser_verify",
            artifacts=[transcript_path, snapshot_path],
            retryable=False,
            details=details,
            completion={"state": "verified", "final_output": False},
        )
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        transcript_path = write_json_atomic(
            workspace / "agent_browser_transcript.json",
            {
                "service": service,
                "port": port,
                "steps": transcript,
                "error": str(exc),
            },
        )
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="agent_browser_verify",
            artifacts=[transcript_path],
            error_code=_agent_browser_error_code(exc),
            retryable=True,
            details={
                "service": service,
                "port": port,
                "transcript_path": str(transcript_path.resolve()),
                "failure_reason": str(exc),
            },
            completion={"state": "blocked", "final_output": False},
        )


def run_agent_browser_verify_safe_mode_job(
    job: JobContract,
    artifact_root: Path,
) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    transcript_path = write_json_atomic(
        workspace / "agent_browser_transcript.json",
        {
            "service": str(job.payload.get("service", "")),
            "safe_mode": True,
            "steps": [],
        },
    )
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="agent_browser_verify",
        artifacts=[transcript_path],
        retryable=False,
        details={
            "service": str(job.payload.get("service", "")),
            "transcript_path": str(transcript_path.resolve()),
            "current_url": str(job.payload.get("expected_url_substring", "")),
            "current_title": str(job.payload.get("expected_title_substring", "")),
            "safe_mode": True,
        },
        completion={"state": "probe_verified", "final_output": False},
    )

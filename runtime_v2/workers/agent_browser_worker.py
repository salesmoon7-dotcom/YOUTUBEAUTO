from __future__ import annotations

import os
import shutil
import subprocess
import json
import time
import urllib.request
from pathlib import Path
from typing import cast

from runtime_v2.agent_browser.command_builder import (
    build_eval_command,
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


def _service_timeout_sec(service: str) -> int:
    if service == "seaart":
        return 60
    if service == "geminigen":
        return 60
    return 30


def _snapshot_required(service: str, payload: dict[str, object]) -> bool:
    raw = payload.get("capture_snapshot")
    if isinstance(raw, bool):
        return raw
    return service == "chatgpt"


def _normalize_agent_browser_actions(raw_actions: object) -> list[dict[str, object]]:
    if not isinstance(raw_actions, list):
        return []
    action_items: list[dict[str, object]] = []
    for item in cast(list[object], raw_actions):
        if isinstance(item, str):
            script = item.strip()
            if script:
                action_items.append({"type": "eval", "script": script})
            continue
        if isinstance(item, dict):
            action_items.append(cast(dict[str, object], item))
    return action_items


def _run_agent_browser_actions(
    *,
    service: str,
    port: int,
    transcript: list[dict[str, object]],
    actions: list[dict[str, object]],
    timeout_sec: int,
) -> None:
    for index, action in enumerate(actions, start=1):
        action_type = str(action.get("type", "eval"))
        if action_type == "eval":
            command = build_eval_command(
                port=port, script=str(action.get("script", ""))
            )
        elif action_type == "upload":
            selector = str(action.get("selector", "input[type=file]"))
            files = [str(item) for item in cast(list[object], action.get("files", []))]
            command = ["agent-browser", "--cdp", str(port), "upload", selector, *files]
        elif action_type == "wait":
            target = str(action.get("target", "1000"))
            command = ["agent-browser", "--cdp", str(port), "wait", target]
        else:
            raise RuntimeError(f"unknown_agent_browser_action:{action_type}")
        output = _run_agent_browser_command(command, timeout_sec=timeout_sec)
        parsed_output = None
        stripped = output.strip()
        if stripped:
            try:
                parsed_output = json.loads(stripped)
            except json.JSONDecodeError:
                parsed_output = None
        if isinstance(parsed_output, str):
            try:
                reparsed = json.loads(parsed_output)
                parsed_output = reparsed
            except json.JSONDecodeError:
                pass
        transcript.append(
            {
                "command": command,
                "output": output,
                "action_index": index,
            }
        )
        if isinstance(parsed_output, dict) and not bool(parsed_output.get("ok", False)):
            raise RuntimeError(f"agent_browser_action_failed:{parsed_output}")
        if isinstance(parsed_output, dict) and str(parsed_output.get("step", "")) in {
            "navigated_image_agent",
            "clicked_generate",
        }:
            if str(parsed_output.get("step", "")) == "clicked_generate":
                time.sleep(5)
            tab_list_command = build_tab_list_command(port=port)
            tab_list_output = _run_agent_browser_command(
                tab_list_command, timeout_sec=timeout_sec
            )
            transcript.append(
                {
                    "command": tab_list_command,
                    "output": tab_list_output,
                    "action_index": index,
                }
            )
            tabs = parse_tab_list_output(tab_list_output)
            selected_tab = select_best_tab(
                tabs,
                expected_url_substring="genspark.ai/agents?type=image_generation_agent",
                expected_title_substring="Genspark",
            )
            if service == "genspark":
                compose_tab = _prefer_genspark_compose_tab(tabs)
                if compose_tab is not None:
                    selected_tab = compose_tab
                elif selected_tab is None:
                    selected_tab = _fallback_single_genspark_tab(
                        tabs, expected_title_substring="Genspark"
                    )
            selected_tab = _prefer_service_specific_tab(service, tabs, selected_tab)
            if selected_tab is not None:
                select_tab_command = build_tab_select_command(
                    port=port, index=selected_tab
                )
                select_tab_output = _run_agent_browser_command(
                    select_tab_command, timeout_sec=timeout_sec
                )
                transcript.append(
                    {
                        "command": select_tab_command,
                        "output": select_tab_output,
                        "action_index": index,
                    }
                )


def _http_cdp_tab_list(port: int) -> list[dict[str, object]]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=10
    ) as response:
        payload = json.loads(response.read().decode("utf-8", "ignore"))
    if not isinstance(payload, list):
        return []
    tabs: list[dict[str, object]] = []
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)
        if str(item.get("type", "")) != "page":
            continue
        tabs.append(
            {
                "index": len(tabs),
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
            }
        )
    return tabs


def _prefer_service_specific_tab(
    service: str, tabs: list[dict[str, object]], selected_tab: int | None
) -> int | None:
    if selected_tab is None or not tabs:
        return selected_tab
    return selected_tab


def _prefer_genspark_compose_tab(tabs: list[dict[str, object]]) -> int | None:
    for item in tabs:
        url = str(item.get("url", ""))
        raw_index = item.get("index")
        if not isinstance(raw_index, int):
            continue
        if url.startswith("https://www.genspark.ai/agents?type=image_generation_agent"):
            return raw_index
    return None


def _fallback_single_genspark_tab(
    tabs: list[dict[str, object]],
    *,
    expected_title_substring: str,
) -> int | None:
    candidates: list[int] = []
    expected_title = expected_title_substring.strip().lower()
    accepted_title_tokens = {
        token for token in {expected_title, "image_generation_agent"} if token
    }
    for item in tabs:
        raw_index = item.get("index")
        if not isinstance(raw_index, int):
            continue
        url = str(item.get("url", "")).strip().lower()
        title = str(item.get("title", "")).strip().lower()
        if not url.startswith("https://www.genspark.ai/agents?id="):
            continue
        if accepted_title_tokens and not any(
            token in title for token in accepted_title_tokens
        ):
            continue
        candidates.append(raw_index)
    if len(candidates) == 1:
        return candidates[0]
    return None


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
    timeout_sec = _service_timeout_sec(service)
    capture_snapshot = _snapshot_required(service, job.payload)
    try:
        tab_list_command = build_tab_list_command(port=port)
        used_http_fallback = False
        try:
            tab_list_output = _run_agent_browser_command(
                tab_list_command, timeout_sec=timeout_sec
            )
            transcript.append({"command": tab_list_command, "output": tab_list_output})
            tabs = parse_tab_list_output(tab_list_output)
        except RuntimeError as exc:
            if service == "chatgpt":
                raise
            try:
                tabs = _http_cdp_tab_list(port)
            except Exception as fallback_exc:
                raise RuntimeError(str(fallback_exc)) from fallback_exc
            used_http_fallback = True
            transcript.append(
                {
                    "command": [f"http://127.0.0.1:{port}/json/list"],
                    "output": json.dumps(tabs, ensure_ascii=False),
                    "fallback": "raw_cdp_http",
                    "agent_browser_error": str(exc),
                }
            )

        selected_tab = select_best_tab(
            tabs,
            expected_url_substring=expected_url,
            expected_title_substring=expected_title,
        )
        if service == "genspark":
            compose_tab = _prefer_genspark_compose_tab(tabs)
            if compose_tab is not None:
                selected_tab = compose_tab
            elif selected_tab is None:
                selected_tab = _fallback_single_genspark_tab(
                    tabs, expected_title_substring=expected_title
                )
        if selected_tab is None and (expected_url or expected_title):
            raise ValueError("agent_browser_matching_tab_not_found")
        current_url = ""
        current_title = ""
        if used_http_fallback and selected_tab is not None:
            selected = tabs[selected_tab]
            current_url = str(selected.get("url", ""))
            current_title = str(selected.get("title", ""))
        elif selected_tab is not None:
            select_command = build_tab_select_command(port=port, index=selected_tab)
            select_output = _run_agent_browser_command(
                select_command, timeout_sec=timeout_sec
            )
            transcript.append({"command": select_command, "output": select_output})
            get_url_command = build_get_url_command(port=port)
            current_url = parse_scalar_output(
                _run_agent_browser_command(get_url_command, timeout_sec=timeout_sec)
            )
            transcript.append({"command": get_url_command, "output": current_url})

            get_title_command = build_get_title_command(port=port)
            current_title = parse_scalar_output(
                _run_agent_browser_command(get_title_command, timeout_sec=timeout_sec)
            )
            transcript.append({"command": get_title_command, "output": current_title})

        action_items = _normalize_agent_browser_actions(job.payload.get("actions", []))
        if action_items:
            _run_agent_browser_actions(
                service=service,
                port=port,
                transcript=transcript,
                actions=action_items,
                timeout_sec=timeout_sec,
            )

        snapshot_path = None
        if capture_snapshot:
            snapshot_command = build_snapshot_command(port=port, max_output=1200)
            snapshot_output = _run_agent_browser_command(
                snapshot_command, timeout_sec=timeout_sec
            )
            transcript.append({"command": snapshot_command, "output": snapshot_output})
            snapshot_path = workspace / "snapshot.txt"
            _ = snapshot_path.write_text(snapshot_output, encoding="utf-8")

        transcript_path = write_json_atomic(
            workspace / "agent_browser_transcript.json",
            {"service": service, "port": port, "steps": transcript},
        )

        details: dict[str, object] = {
            "service": service,
            "port": port,
            "selected_tab": selected_tab,
            "current_url": current_url,
            "current_title": current_title,
            "transcript_path": str(transcript_path.resolve()),
            "snapshot_path": ""
            if snapshot_path is None
            else str(snapshot_path.resolve()),
        }
        artifacts = [transcript_path]
        if snapshot_path is not None:
            artifacts.append(snapshot_path)
        return finalize_worker_result(
            workspace,
            status="ok",
            stage="agent_browser_verify",
            artifacts=artifacts,
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
    except Exception as exc:
        transcript_path = write_json_atomic(
            workspace / "agent_browser_transcript.json",
            {
                "service": service,
                "port": port,
                "steps": transcript,
                "error": str(exc),
                "exception_type": exc.__class__.__name__,
            },
        )
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="agent_browser_verify",
            artifacts=[transcript_path],
            error_code="AGENT_BROWSER_VERIFY_FAILED",
            retryable=True,
            details={
                "service": service,
                "port": port,
                "transcript_path": str(transcript_path.resolve()),
                "failure_reason": str(exc),
                "exception_type": exc.__class__.__name__,
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

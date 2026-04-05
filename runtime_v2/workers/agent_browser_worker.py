from __future__ import annotations

import os
import shutil
import subprocess
import json
import time
import urllib.request
from pathlib import Path
from typing import cast

from playwright.sync_api import sync_playwright

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
from runtime_v2.browser.health import build_browser_health_payload, write_browser_health
from runtime_v2.browser.manager import BrowserManager
from runtime_v2.browser.supervisor import BrowserSupervisor
from runtime_v2.config import RuntimeConfig
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


def _float_value(raw: object, default: float = 0.0) -> float:
    if isinstance(raw, bool):
        return float(int(raw))
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if text:
            return float(text)
    return default


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


def _select_canva_page(port: int):
    browser = (
        sync_playwright().start().chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    )
    page = None
    for context in browser.contexts:
        for candidate in context.pages:
            if "canva.com" in candidate.url:
                page = candidate
                break
        if page is not None:
            break
    if page is None:
        browser.close()
        raise RuntimeError("NO_CANVA_PAGE")
    page.bring_to_front()
    return browser, page


def _last_visible_locator(locator):
    count = locator.count()
    target = None
    for index in range(count):
        candidate = locator.nth(index)
        try:
            box = candidate.bounding_box()
        except Exception:
            box = None
        if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
            target = candidate
    return target


def _playwright_edit_canva_colored_text(
    *, port: int, line1: str, line2: str, timeout_sec: int
) -> dict[str, object]:
    del timeout_sec
    browser, page = _select_canva_page(port)
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        def _edit_by_color(color: str, text: str) -> bool:
            if not text:
                return True
            locator = page.locator(f"span[style*='color: {color}']")
            target = _last_visible_locator(locator)
            if target is None:
                return False
            target.dblclick(timeout=2000)
            page.wait_for_timeout(300)
            page.keyboard.press("Control+A")
            page.wait_for_timeout(100)
            page.keyboard.type(text)
            page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            return True

        result1 = _edit_by_color("rgb(255, 215, 0)", line1)
        result2 = _edit_by_color("rgb(255, 255, 255)", line2)
        body_text = page.evaluate(
            "() => document.body && document.body.innerText ? document.body.innerText : ''"
        )
        body_text_str = str(body_text)
        if not result1 and line1 and line1 in body_text_str:
            result1 = True
        if not result2 and line2 and line2 in body_text_str:
            result2 = True
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return {
            "ok": bool(result1 or result2),
            "step": "edited_thumbnail_text",
            "line1_ok": result1,
            "line2_ok": result2,
        }
    finally:
        browser.close()


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
        elif action_type == "click":
            selector = str(action.get("selector", "")).strip()
            if not selector:
                raise RuntimeError("missing_click_selector")
            command = ["agent-browser", "--cdp", str(port), "click", selector]
        elif action_type == "upload":
            selector = str(action.get("selector", "input[type=file]"))
            files = [str(item) for item in cast(list[object], action.get("files", []))]
            command = ["agent-browser", "--cdp", str(port), "upload", selector, *files]
        elif action_type == "wait":
            target = str(action.get("target", "1000"))
            command = ["agent-browser", "--cdp", str(port), "wait", target]
        elif action_type == "click_box_offset":
            selector = str(action.get("selector", "")).strip()
            if not selector:
                raise RuntimeError("missing_click_box_offset_selector")
            box_command = ["agent-browser", "--cdp", str(port), "get", "box", selector]
            box_output = _run_agent_browser_command(
                box_command, timeout_sec=timeout_sec
            )
            transcript.append(
                {
                    "command": box_command,
                    "output": box_output,
                    "action_index": index,
                }
            )
            box_payload = json.loads(box_output)
            if not isinstance(box_payload, dict):
                raise RuntimeError("invalid_click_box_offset_box")
            x = _float_value(box_payload.get("x", 0.0))
            y = _float_value(box_payload.get("y", 0.0))
            width = _float_value(box_payload.get("width", 0.0))
            height = _float_value(box_payload.get("height", 0.0))
            x_ratio = _float_value(action.get("x_ratio", 0.5), default=0.5)
            y_ratio = _float_value(action.get("y_ratio", 0.5), default=0.5)
            click_x = int(round(x + width * x_ratio))
            click_y = int(round(y + height * y_ratio))
            for mouse_command in (
                [
                    "agent-browser",
                    "--cdp",
                    str(port),
                    "mouse",
                    "move",
                    str(click_x),
                    str(click_y),
                ],
                ["agent-browser", "--cdp", str(port), "mouse", "down"],
                ["agent-browser", "--cdp", str(port), "mouse", "up"],
            ):
                mouse_output = _run_agent_browser_command(
                    mouse_command, timeout_sec=timeout_sec
                )
                transcript.append(
                    {
                        "command": mouse_command,
                        "output": mouse_output,
                        "action_index": index,
                    }
                )
            output = json.dumps(
                {
                    "ok": True,
                    "step": str(action.get("step", "clicked_box_offset")),
                    "selector": selector,
                    "x": click_x,
                    "y": click_y,
                },
                ensure_ascii=True,
            )
            command = [
                "agent-browser",
                "--cdp",
                str(port),
                "mouse",
                "up",
            ]
            parsed_output = json.loads(output)
            transcript.append(
                {
                    "command": command,
                    "output": output,
                    "action_index": index,
                }
            )
            if isinstance(parsed_output, dict) and not bool(
                parsed_output.get("ok", False)
            ):
                raise RuntimeError(
                    f"agent_browser_action_failed:{json.dumps(parsed_output, ensure_ascii=True)}"
                )
            continue
        elif action_type == "drag_box_to_box":
            source_selector = str(action.get("source_selector", "")).strip()
            dest_selector = str(action.get("dest_selector", "")).strip()
            if not source_selector or not dest_selector:
                raise RuntimeError("missing_drag_box_to_box_selector")
            source_box_command = [
                "agent-browser",
                "--cdp",
                str(port),
                "get",
                "box",
                source_selector,
            ]
            source_box_output = _run_agent_browser_command(
                source_box_command, timeout_sec=timeout_sec
            )
            transcript.append(
                {
                    "command": source_box_command,
                    "output": source_box_output,
                    "action_index": index,
                }
            )
            dest_box_command = [
                "agent-browser",
                "--cdp",
                str(port),
                "get",
                "box",
                dest_selector,
            ]
            dest_box_output = _run_agent_browser_command(
                dest_box_command, timeout_sec=timeout_sec
            )
            transcript.append(
                {
                    "command": dest_box_command,
                    "output": dest_box_output,
                    "action_index": index,
                }
            )
            source_box = json.loads(source_box_output)
            dest_box = json.loads(dest_box_output)
            if not isinstance(source_box, dict) or not isinstance(dest_box, dict):
                raise RuntimeError("invalid_drag_box_to_box_box")
            source_x = _float_value(source_box.get("x", 0.0))
            source_y = _float_value(source_box.get("y", 0.0))
            source_w = _float_value(source_box.get("width", 0.0))
            source_h = _float_value(source_box.get("height", 0.0))
            dest_x = _float_value(dest_box.get("x", 0.0))
            dest_y = _float_value(dest_box.get("y", 0.0))
            dest_w = _float_value(dest_box.get("width", 0.0))
            dest_h = _float_value(dest_box.get("height", 0.0))
            dest_x_ratio = _float_value(action.get("dest_x_ratio", 0.5), default=0.5)
            dest_y_ratio = _float_value(action.get("dest_y_ratio", 0.5), default=0.5)
            start_x = int(round(source_x + source_w / 2.0))
            start_y = int(round(source_y + source_h / 2.0))
            end_x = int(round(dest_x + dest_w * dest_x_ratio))
            end_y = int(round(dest_y + dest_h * dest_y_ratio))
            drag_steps = max(int(_float_value(action.get("steps", 20), default=20)), 2)
            mouse_commands: list[list[str]] = [
                [
                    "agent-browser",
                    "--cdp",
                    str(port),
                    "mouse",
                    "move",
                    str(start_x),
                    str(start_y),
                ],
                ["agent-browser", "--cdp", str(port), "mouse", "down"],
            ]
            for step_index in range(1, drag_steps + 1):
                progress = step_index / drag_steps
                current_x = int(round(start_x + (end_x - start_x) * progress))
                current_y = int(round(start_y + (end_y - start_y) * progress))
                mouse_commands.append(
                    [
                        "agent-browser",
                        "--cdp",
                        str(port),
                        "mouse",
                        "move",
                        str(current_x),
                        str(current_y),
                    ]
                )
            mouse_commands.append(["agent-browser", "--cdp", str(port), "mouse", "up"])
            for mouse_command in mouse_commands:
                mouse_output = _run_agent_browser_command(
                    mouse_command, timeout_sec=timeout_sec
                )
                transcript.append(
                    {
                        "command": mouse_command,
                        "output": mouse_output,
                        "action_index": index,
                    }
                )
            output = json.dumps(
                {
                    "ok": True,
                    "step": str(action.get("step", "dragged_box_to_box")),
                    "source_selector": source_selector,
                    "dest_selector": dest_selector,
                    "x": end_x,
                    "y": end_y,
                },
                ensure_ascii=True,
            )
            command = ["agent-browser", "--cdp", str(port), "mouse", "up"]
            parsed_output = json.loads(output)
            transcript.append(
                {
                    "command": command,
                    "output": output,
                    "action_index": index,
                }
            )
            if isinstance(parsed_output, dict) and not bool(
                parsed_output.get("ok", False)
            ):
                raise RuntimeError(
                    f"agent_browser_action_failed:{json.dumps(parsed_output, ensure_ascii=True)}"
                )
            continue
        elif action_type == "playwright_edit_canva_text":
            output_payload = _playwright_edit_canva_colored_text(
                port=port,
                line1=str(action.get("line1", "")),
                line2=str(action.get("line2", "")),
                timeout_sec=timeout_sec,
            )
            output = json.dumps(output_payload, ensure_ascii=True)
            command = ["playwright-edit-canva-text"]
            transcript.append(
                {
                    "command": command,
                    "output": output,
                    "action_index": index,
                }
            )
            if not bool(output_payload.get("ok", False)):
                raise RuntimeError(
                    f"agent_browser_action_failed:{json.dumps(output_payload, ensure_ascii=True)}"
                )
            continue
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
            raise RuntimeError(
                f"agent_browser_action_failed:{json.dumps(parsed_output, ensure_ascii=True)}"
            )
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
    result_tab: int | None = None
    compose_tab: int | None = None
    for item in tabs:
        url = str(item.get("url", ""))
        raw_index = item.get("index")
        if not isinstance(raw_index, int):
            continue
        if url.startswith("https://www.genspark.ai/agents?id="):
            result_tab = raw_index
        if url.startswith("https://www.genspark.ai/agents?type=image_generation_agent"):
            compose_tab = raw_index
    if result_tab is not None:
        return result_tab
    return compose_tab


def _fallback_single_genspark_tab(
    tabs: list[dict[str, object]],
    *,
    expected_title_substring: str,
) -> int | None:
    candidates: list[int] = []
    expected_title = expected_title_substring.strip().lower()
    for item in tabs:
        raw_index = item.get("index")
        if not isinstance(raw_index, int):
            continue
        url = str(item.get("url", "")).strip().lower()
        title = str(item.get("title", "")).strip().lower()
        if not url.startswith("https://www.genspark.ai/agents?id="):
            continue
        if expected_title and expected_title not in title:
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
    if message.startswith("agent_browser_action_failed:"):
        raw_payload = message.split(":", 1)[1].strip()
        try:
            parsed = json.loads(raw_payload)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            explicit_error = str(parsed.get("error", "")).strip()
            if explicit_error:
                return explicit_error
    if isinstance(exc, RuntimeError):
        return "AGENT_BROWSER_COMMAND_FAILED"
    return "AGENT_BROWSER_VERIFY_FAILED"


def _recover_agent_browser_service(service: str) -> None:
    manager = BrowserManager()
    manager.start()
    supervisor = BrowserSupervisor(manager)
    cfg = RuntimeConfig()
    _ = supervisor.tick(
        registry_file=cfg.browser_registry_file,
        health_file=cfg.browser_health_file,
        run_id=f"agent-browser-recover-{service}",
        recover_unhealthy=True,
        restart_threshold=1,
        cooldown_sec=0,
    )


def _mark_probe_browser_unhealthy(
    artifact_root: Path, *, service: str, port: int
) -> None:
    probe_root = (
        artifact_root.parent if artifact_root.name == "artifacts" else artifact_root
    )
    cfg = RuntimeConfig.from_root(probe_root)
    health_file = cfg.browser_health_file
    if not health_file.exists():
        return
    try:
        payload = json.loads(health_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    raw_sessions = payload.get("sessions", [])
    if not isinstance(raw_sessions, list):
        return
    sessions: list[dict[str, object]] = []
    changed = False
    for raw in cast(list[object], raw_sessions):
        if not isinstance(raw, dict):
            continue
        session = {str(key): value for key, value in raw.items()}
        if (
            str(session.get("service", "")) == service
            and int(session.get("port", 0) or 0) == port
        ):
            session["healthy"] = False
            session["status"] = "unhealthy"
            session["cdp_endpoint_ready"] = False
            session["blocked_reason"] = "agent_browser_attach_failed"
            changed = True
        sessions.append(session)
    if not changed:
        return
    _ = write_browser_health(
        build_browser_health_payload(
            sessions,
            runtime=str(payload.get("runtime", "runtime_v2")),
            run_id=str(payload.get("run_id", "")),
        ),
        health_file,
    )


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
    recovery_attempted = False

    def _run_verify_once() -> tuple[
        list[dict[str, object]], int | None, str, str, Path | None
    ]:
        local_transcript: list[dict[str, object]] = []
        tab_list_command = build_tab_list_command(port=port)
        used_http_fallback = False
        try:
            tab_list_output = _run_agent_browser_command(
                tab_list_command, timeout_sec=timeout_sec
            )
            local_transcript.append(
                {"command": tab_list_command, "output": tab_list_output}
            )
            tabs = parse_tab_list_output(tab_list_output)
        except RuntimeError as exc:
            if service in {"genspark", "seaart"} and not recovery_attempted:
                raise RuntimeError(str(exc))
            if service == "chatgpt":
                raise
            try:
                tabs = _http_cdp_tab_list(port)
            except Exception as fallback_exc:
                raise RuntimeError(str(fallback_exc)) from fallback_exc
            used_http_fallback = True
            local_transcript.append(
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
            local_transcript.append(
                {"command": select_command, "output": select_output}
            )
            get_url_command = build_get_url_command(port=port)
            current_url = parse_scalar_output(
                _run_agent_browser_command(get_url_command, timeout_sec=timeout_sec)
            )
            local_transcript.append({"command": get_url_command, "output": current_url})

            get_title_command = build_get_title_command(port=port)
            current_title = parse_scalar_output(
                _run_agent_browser_command(get_title_command, timeout_sec=timeout_sec)
            )
            local_transcript.append(
                {"command": get_title_command, "output": current_title}
            )

        action_items = _normalize_agent_browser_actions(job.payload.get("actions", []))
        if action_items:
            _run_agent_browser_actions(
                service=service,
                port=port,
                transcript=local_transcript,
                actions=action_items,
                timeout_sec=timeout_sec,
            )
            if service == "genspark":
                tab_list_command = build_tab_list_command(port=port)
                tab_list_output = _run_agent_browser_command(
                    tab_list_command, timeout_sec=timeout_sec
                )
                local_transcript.append(
                    {
                        "command": tab_list_command,
                        "output": tab_list_output,
                        "action_index": len(action_items),
                    }
                )
                tabs = parse_tab_list_output(tab_list_output)
                refreshed_tab = _prefer_genspark_compose_tab(tabs)
                if refreshed_tab is not None:
                    selected_tab = refreshed_tab
                    select_command = build_tab_select_command(
                        port=port, index=selected_tab
                    )
                    select_output = _run_agent_browser_command(
                        select_command, timeout_sec=timeout_sec
                    )
                    local_transcript.append(
                        {
                            "command": select_command,
                            "output": select_output,
                            "action_index": len(action_items),
                        }
                    )
                    get_url_command = build_get_url_command(port=port)
                    current_url = parse_scalar_output(
                        _run_agent_browser_command(
                            get_url_command, timeout_sec=timeout_sec
                        )
                    )
                    local_transcript.append(
                        {
                            "command": get_url_command,
                            "output": current_url,
                            "action_index": len(action_items),
                        }
                    )
                    get_title_command = build_get_title_command(port=port)
                    current_title = parse_scalar_output(
                        _run_agent_browser_command(
                            get_title_command, timeout_sec=timeout_sec
                        )
                    )
                    local_transcript.append(
                        {
                            "command": get_title_command,
                            "output": current_title,
                            "action_index": len(action_items),
                        }
                    )

        snapshot_path = None
        if capture_snapshot:
            snapshot_command = build_snapshot_command(port=port, max_output=1200)
            snapshot_output = _run_agent_browser_command(
                snapshot_command, timeout_sec=timeout_sec
            )
            local_transcript.append(
                {"command": snapshot_command, "output": snapshot_output}
            )
            snapshot_path = workspace / "snapshot.txt"
            _ = snapshot_path.write_text(snapshot_output, encoding="utf-8")
        return local_transcript, selected_tab, current_url, current_title, snapshot_path

    try:
        try:
            transcript, selected_tab, current_url, current_title, snapshot_path = (
                _run_verify_once()
            )
        except RuntimeError as exc:
            if service in {"genspark", "seaart"} and not recovery_attempted:
                recovery_attempted = True
                _recover_agent_browser_service(service)
                transcript.append(
                    {
                        "command": ["recovery"],
                        "output": "service_recovered",
                        "recovery_attempted": True,
                        "agent_browser_error": str(exc),
                    }
                )
                transcript, selected_tab, current_url, current_title, snapshot_path = (
                    _run_verify_once()
                )
            else:
                raise

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
        _mark_probe_browser_unhealthy(artifact_root, service=service, port=port)
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

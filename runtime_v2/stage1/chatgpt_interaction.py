from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Callable, cast

from runtime_v2.stage1.chatgpt_backend import AgentBrowserCdpBackend, ChatGPTBackend

CHATGPT_INPUT_SELECTORS = [
    "#prompt-textarea",
    "div.ProseMirror[contenteditable='true']",
    "div[contenteditable='true'][id='prompt-textarea']",
    "div[contenteditable='true']",
    "textarea[name='prompt-textarea']",
    "textarea",
]

CHATGPT_SEND_SELECTORS = [
    "#composer-submit-button",
    "button.composer-submit-btn",
    ".composer-submit-btn",
    "button[data-testid='send-button']",
    "button[aria-label='프롬프트 보내기']",
    "button[aria-label='메시지 보내기']",
    "button[aria-label='Send Message']",
    "button[aria-label*='전송']",
    "button[aria-label*='Send']",
]

CHATGPT_STOP_SELECTORS = [
    "button[data-testid='stop-button']",
    "button[aria-label='스트리밍 중지']",
    "button[aria-label='Stop streaming']",
    "button[aria-label*='중지']",
    "button[aria-label*='Stop']",
]

CHATGPT_RESPONSE_SELECTORS = [
    "[data-testid*='conversation-turn']",
    "div[data-message-author-role='assistant']",
    "[class*='markdown']",
    "article",
]


def generate_gpt_response_text(
    *,
    prompt: str,
    port: int = 9222,
    timeout_sec: int = 180,
    poll_interval_sec: float = 2.0,
    completion_idle_sec: float = 10.0,
    response_start_timeout_sec: float = 30.0,
    command_runner: Callable[[list[str], int], str] | None = None,
    session_probe: Callable[[int], dict[str, object]] | None = None,
    backend: ChatGPTBackend | None = None,
    relaunch_browser: Callable[[], None] | None = None,
) -> dict[str, object]:
    probe = _default_session_probe if session_probe is None else session_probe
    timeline: list[dict[str, object]] = []
    sequence = 0

    def emit(event: str, **fields: object) -> None:
        nonlocal sequence
        sequence += 1
        if "attempt_key" not in fields:
            raw_attempt = fields.get("attempt")
            if not isinstance(raw_attempt, int):
                raw_attempt = fields.get("attempt_from")
            if isinstance(raw_attempt, int):
                fields["attempt_key"] = _attempt_key(raw_attempt)
        timeline.append(
            {
                "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "seq": sequence,
                "event": event,
                **fields,
            }
        )

    interaction_backend = (
        AgentBrowserCdpBackend(
            port=port,
            input_selectors=CHATGPT_INPUT_SELECTORS,
            send_selectors=CHATGPT_SEND_SELECTORS,
            stop_selectors=CHATGPT_STOP_SELECTORS,
            response_selectors=CHATGPT_RESPONSE_SELECTORS,
            command_runner=command_runner,
        )
        if backend is None
        else backend
    )
    for attempt in (1, 2):
        emit("submit_start", attempt=attempt, backend="chatgpt_backend")
        try:
            submit_info = interaction_backend.submit_prompt(prompt)
        except RuntimeError as exc:
            error_code, retry_safe, extra_details = _decode_submit_failure(str(exc))
            submit_evidence = extra_details.get("submit_evidence")
            if isinstance(submit_evidence, dict):
                submit_evidence["attempt_key"] = _attempt_key(attempt)
            emit("submit_failed", attempt=attempt, backend="chatgpt_backend")
            failed = _interaction_failure(
                failure_stage="submit",
                error_code="CHATGPT_BACKEND_UNAVAILABLE",
                backend_error=error_code,
                final_state=probe(port),
                extra_details=extra_details,
            )
            if attempt == 1 and relaunch_browser is not None and retry_safe:
                emit(
                    "retry_decision",
                    attempt=attempt,
                    backend="chatgpt_backend",
                    reason=error_code,
                )
                relaunch_browser()
                continue
            emit(
                "final_state",
                attempt=attempt,
                final_state="failed",
                final_state_code=str(failed.get("error_code", "failed")),
            )
            failed["timeline"] = timeline
            return failed
        emit("submit_ok", attempt=attempt, backend="chatgpt_backend")
        submit_evidence = _decode_submit_success(submit_info, attempt=attempt)
        for fallback in _backend_fallbacks(submit_info):
            emit(
                "fallback_transition",
                attempt_from=attempt,
                backend_from="chatgpt_backend",
                attempt_to=attempt,
                backend_to=fallback,
                reason=fallback,
            )
        started = time.time()
        last_text = ""
        stable_count = 0
        saw_streaming = False
        last_state: dict[str, object] = {}
        last_activity_ts = time.time()
        consecutive_read_failures = 0
        while time.time() - started < timeout_sec:
            try:
                state = interaction_backend.read_response_state()
                consecutive_read_failures = 0
            except RuntimeError as exc:
                backend_error = str(exc)
                emit("read_failed", attempt=attempt, backend="chatgpt_backend")
                if (
                    "timeout" in backend_error.lower()
                    and consecutive_read_failures < 3
                    and time.time() - started < timeout_sec
                ):
                    consecutive_read_failures += 1
                    emit(
                        "read_retry",
                        attempt=attempt,
                        backend="chatgpt_backend",
                        reason=backend_error,
                    )
                    time.sleep(poll_interval_sec)
                    continue
                failed = _interaction_failure(
                    failure_stage="read",
                    error_code="CHATGPT_BACKEND_UNAVAILABLE",
                    backend_error=backend_error,
                    submit_info=submit_info,
                    final_state=probe(port),
                )
                emit(
                    "final_state",
                    attempt=attempt,
                    final_state="failed",
                    final_state_code=str(failed.get("error_code", "failed")),
                )
                failed["timeline"] = timeline
                return failed
            last_state = state
            for fallback in _backend_fallbacks(state):
                emit(
                    "fallback_transition",
                    attempt_from=attempt,
                    backend_from="chatgpt_backend",
                    attempt_to=attempt,
                    backend_to=fallback,
                    reason=fallback,
                )
            text = str(state.get("assistant_text", "")).strip()
            legacy_blocks = state.get("legacy_blocks", [])
            response_text = _response_text_from_state(text, legacy_blocks)
            has_stop = bool(state.get("has_stop", False))
            has_send_button = bool(state.get("has_send_button", False))
            if has_stop:
                if not saw_streaming:
                    emit("streaming_seen", attempt=attempt, backend="chatgpt_backend")
                    emit(
                        "stop_gate",
                        attempt=attempt,
                        gate_state="blocked",
                        reason="streaming_active",
                    )
                saw_streaming = True
                last_activity_ts = time.time()
            if response_text and not has_stop and saw_streaming:
                if response_text == last_text:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_activity_ts = time.time()
                last_text = response_text
                idle_elapsed = time.time() - last_activity_ts
                if stable_count >= 1 and idle_elapsed >= completion_idle_sec:
                    emit(
                        "response_stable",
                        attempt=attempt,
                        backend="chatgpt_backend",
                        final_state_code="ok",
                    )
                    result: dict[str, object] = {
                        "status": "ok",
                        "response_text": response_text,
                        "submit_info": submit_info,
                        "submit_evidence": submit_evidence,
                        "final_state": state,
                    }
                    emit(
                        "final_state",
                        attempt=attempt,
                        final_state="success",
                        final_state_code="ok",
                    )
                    result["timeline"] = timeline
                    return result
            if (
                not saw_streaming
                and not text
                and time.time() - started >= response_start_timeout_sec
            ):
                emit(
                    "response_not_started",
                    attempt=attempt,
                    backend="chatgpt_backend",
                )
                if attempt == 1 and relaunch_browser is not None:
                    emit(
                        "retry_decision",
                        attempt=attempt,
                        backend="chatgpt_backend",
                        reason="response_not_started",
                    )
                    relaunch_browser()
                    break
            time.sleep(poll_interval_sec)
        else:
            emit(
                "final_state",
                attempt=attempt,
                final_state="failed",
                final_state_code="CHATGPT_RESPONSE_TIMEOUT",
            )
            return {
                "status": "failed",
                "error_code": "CHATGPT_RESPONSE_TIMEOUT",
                "failure_stage": "read",
                "submit_info": submit_info,
                "final_state": last_state,
                "timeline": timeline,
            }
    emit(
        "final_state",
        attempt=2,
        final_state="failed",
        final_state_code="CHATGPT_BACKEND_UNAVAILABLE",
    )
    return {
        "status": "failed",
        "error_code": "CHATGPT_BACKEND_UNAVAILABLE",
        "failure_stage": "read",
        "submit_info": {},
        "final_state": probe(port),
        "timeline": timeline,
        "details": {
            "backend_error": "retry_exhausted",
            "backend_fallback": "raw_cdp_http",
        },
    }


def _interaction_failure(
    *,
    failure_stage: str,
    error_code: str,
    backend_error: str,
    submit_info: dict[str, object] | None = None,
    final_state: dict[str, object] | None = None,
    extra_details: dict[str, object] | None = None,
) -> dict[str, object]:
    details: dict[str, object] = {
        "backend_error": backend_error,
        "backend_fallback": "raw_cdp_http",
    }
    if extra_details:
        details.update(extra_details)
    return {
        "status": "failed",
        "error_code": error_code,
        "failure_stage": failure_stage,
        "submit_info": {} if submit_info is None else submit_info,
        "final_state": {} if final_state is None else final_state,
        "details": details,
    }


def _default_session_probe(port: int) -> dict[str, object]:
    tabs = _http_cdp_tab_list(port)
    assistant_tab = _select_chatgpt_tab(tabs)
    return {
        "probe_backend": "raw_cdp_http",
        "port": port,
        "tab_count": len(tabs),
        "selected_tab": assistant_tab,
    }


def _http_cdp_tab_list(port: int) -> list[dict[str, object]]:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=5
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
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
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
            }
        )
    return tabs


def _select_chatgpt_tab(tabs: list[dict[str, object]]) -> dict[str, object]:
    for tab in tabs:
        url = str(tab.get("url", "")).lower()
        title = str(tab.get("title", "")).lower()
        if "chatgpt.com" in url or "chatgpt" in title:
            return tab
    return {}


def _response_text_from_state(text: str, legacy_blocks: object) -> str:
    if isinstance(legacy_blocks, list):
        parts: list[str] = []
        for item in legacy_blocks:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            body = str(item.get("body", "")).strip()
            if label and body:
                if body.startswith("COPY\n"):
                    body = body[len("COPY\n") :]
                parts.append(f"{label}\n{body}")
        if parts:
            return "\n\n".join(parts)
    return text


def _backend_fallbacks(payload: dict[str, object]) -> list[str]:
    raw = payload.get("backend_fallbacks", [])
    if not isinstance(raw, list):
        return []
    fallbacks: list[str] = []
    for item in cast(list[object], raw):
        normalized = str(item).strip()
        if normalized and normalized not in fallbacks:
            fallbacks.append(normalized)
    return fallbacks


def _decode_submit_failure(message: str) -> tuple[str, bool, dict[str, object]]:
    raw = str(message).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw, False, {}
    if not isinstance(parsed, dict):
        return raw, False, {}
    error_code = str(parsed.get("error", raw)).strip() or raw
    extra_details: dict[str, object] = {}
    no_send_evidence = parsed.get("no_send_evidence", {})
    if isinstance(no_send_evidence, dict):
        extra_details["no_send_evidence"] = no_send_evidence
    submit_evidence = parsed.get("submit_evidence", {})
    if isinstance(submit_evidence, dict):
        extra_details["submit_evidence"] = submit_evidence
    extra_details["retry_safe_submit"] = bool(parsed.get("retry_safe", False))
    return error_code, bool(parsed.get("retry_safe", False)), extra_details


def _decode_submit_success(
    payload: dict[str, object], *, attempt: int
) -> dict[str, object]:
    raw = payload.get("submit_evidence", {})
    if isinstance(raw, dict):
        submit_evidence = dict(raw)
        submit_evidence["attempt_key"] = _attempt_key(attempt)
        return submit_evidence
    return {
        "attempt_key": _attempt_key(attempt),
        "classification": "sent",
        "classification_reason": "send_clicked",
        "retry_safe_decision": False,
    }


def _attempt_key(attempt: int) -> str:
    return f"attempt-{attempt}"

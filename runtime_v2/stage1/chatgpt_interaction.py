from __future__ import annotations

import json
import queue
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, cast

from runtime_v2.stage1.chatgpt_backend import (
    AgentBrowserCdpBackend,
    CHATGPT_LONGFORM_URL_SUBSTRING,
    ChatGPTBackend,
)
from runtime_v2.stage1.gpt_plan_parser import (
    extract_stage1_gpt_plan_json,
    parse_stage1_gpt_plan,
)

CHATGPT_INPUT_SELECTORS = [
    "#prompt-textarea",
    ".ProseMirror[contenteditable='true']",
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
    "div[data-message-author-role='assistant']",
    "[data-testid*='conversation-turn'] div[data-message-author-role='assistant']",
]


def generate_gpt_response_text(
    *,
    prompt: str,
    port: int = 9222,
    timeout_sec: int = 1200,
    poll_interval_sec: float = 2.0,
    completion_idle_sec: float = 10.0,
    response_start_timeout_sec: float = 30.0,
    command_runner: Callable[[list[str], int], str] | None = None,
    expected_url_substring: str = CHATGPT_LONGFORM_URL_SUBSTRING,
    session_probe: Callable[[int], dict[str, object]] | None = None,
    backend: ChatGPTBackend | None = None,
    relaunch_browser: Callable[[], None] | None = None,
    timeline_path: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, object]:
    probe = _default_session_probe if session_probe is None else session_probe
    deadline_ts = time.time() + timeout_sec

    def _raw_cdp_timeout(default_timeout: float) -> float:
        remaining = deadline_ts - time.time()
        if remaining <= 0:
            return 1.0
        return min(default_timeout, max(1.0, remaining))

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
        record = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "seq": sequence,
            "event": event,
            **fields,
        }
        timeline.append(record)
        if timeline_path is not None:
            try:
                timeline_path.parent.mkdir(parents=True, exist_ok=True)
                with timeline_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            except OSError:
                pass

    def write_state_snapshot(state: dict[str, object]) -> None:
        if state_path is None:
            return
        raw_block_count = state.get("assistant_block_count", 0)
        assistant_block_count = (
            raw_block_count if isinstance(raw_block_count, int) else 0
        )
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "assistant_text_len": len(str(state.get("assistant_text", "")).strip()),
            "assistant_block_count": assistant_block_count,
            "has_stop": bool(state.get("has_stop", False)),
            "has_send_button": bool(state.get("has_send_button", False)),
            "thinking_stopped": bool(state.get("thinking_stopped", False)),
            "current_url": str(state.get("current_url", "")).strip(),
            "current_title": str(state.get("current_title", "")).strip(),
        }
        tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=True), encoding="utf-8"
            )
            tmp_path.replace(state_path)
        except OSError:
            pass

    interaction_backend = (
        AgentBrowserCdpBackend(
            port=port,
            input_selectors=CHATGPT_INPUT_SELECTORS,
            send_selectors=CHATGPT_SEND_SELECTORS,
            stop_selectors=CHATGPT_STOP_SELECTORS,
            response_selectors=CHATGPT_RESPONSE_SELECTORS,
            expected_url_substring=expected_url_substring,
            command_runner=command_runner,
            raw_cdp_timeout_resolver=_raw_cdp_timeout,
        )
        if backend is None
        else backend
    )
    recovered_after_stream_abort = False
    for attempt in (1, 2):
        emit("submit_start", attempt=attempt, backend="chatgpt_backend")
        try:
            submit_info = _submit_prompt_with_deadline(
                interaction_backend, prompt, deadline_ts=deadline_ts
            )
        except RuntimeError as exc:
            error_code, retry_safe, extra_details = _decode_submit_failure(str(exc))
            submit_evidence = extra_details.get("submit_evidence")
            if isinstance(submit_evidence, dict):
                submit_evidence["attempt_key"] = _attempt_key(attempt)
            else:
                submit_evidence = {
                    "attempt_key": _attempt_key(attempt),
                    "classification": "ambiguous",
                    "classification_reason": error_code,
                    "retry_safe_decision": bool(retry_safe),
                }
                extra_details["submit_evidence"] = submit_evidence
            failed_submit_info: dict[str, object] = {}
            if isinstance(submit_evidence, dict):
                failed_submit_info["submit_evidence"] = dict(submit_evidence)
            no_send_evidence = extra_details.get("no_send_evidence")
            if isinstance(no_send_evidence, dict):
                failed_submit_info["no_send_evidence"] = dict(no_send_evidence)
            emit("submit_failed", attempt=attempt, backend="chatgpt_backend")
            failed = _interaction_failure(
                failure_stage="submit",
                error_code="CHATGPT_BACKEND_UNAVAILABLE",
                backend_error=error_code,
                submit_info=failed_submit_info,
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
        submit_evidence = _decode_submit_success(submit_info, attempt=attempt)
        if isinstance(submit_info, dict):
            submit_info["submit_evidence"] = dict(submit_evidence)
        submit_classification = str(
            submit_evidence.get("classification", "sent")
        ).strip()
        emit(
            "submit_ok" if submit_classification == "sent" else "submit_ambiguous",
            attempt=attempt,
            backend="chatgpt_backend",
        )
        allow_submit_probe = _should_probe_after_ambiguous_submit(
            submit_info, submit_evidence
        )
        ambiguous_submit_probe_only = (
            submit_classification != "sent" and not allow_submit_probe
        )
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
        saw_streaming = recovered_after_stream_abort
        last_state: dict[str, object] = {}
        last_activity_ts = time.time()
        consecutive_read_failures = 0
        response_not_started_emitted = False
        while time.time() - started < timeout_sec:
            try:
                state = interaction_backend.read_response_state()
                consecutive_read_failures = 0
            except RuntimeError as exc:
                backend_error = str(exc)
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
                emit("read_failed", attempt=attempt, backend="chatgpt_backend")
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
            write_state_snapshot(state)
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
            recovery_clicked = bool(state.get("recovery_clicked", False))
            thinking_stopped = bool(state.get("thinking_stopped", False))
            upstream_error_retry_exhausted = bool(
                state.get("upstream_error_retry_exhausted", False)
            )
            if recovery_clicked and not saw_streaming:
                emit("recovery_clicked", attempt=attempt, backend="chatgpt_backend")
                last_activity_ts = time.time()
            if has_stop:
                if not saw_streaming:
                    emit("streaming_seen", attempt=attempt, backend="chatgpt_backend")
                    if isinstance(submit_evidence, dict):
                        submit_evidence["classification"] = "sent"
                        submit_evidence["classification_reason"] = "streaming_observed"
                    emit(
                        "stop_gate",
                        attempt=attempt,
                        gate_state="blocked",
                        reason="streaming_active",
                    )
                saw_streaming = True
            elif has_send_button and _has_structured_stage1_content("", legacy_blocks):
                if not saw_streaming:
                    emit("streaming_seen", attempt=attempt, backend="chatgpt_backend")
                    if isinstance(submit_evidence, dict):
                        submit_evidence["classification"] = "sent"
                        submit_evidence["classification_reason"] = (
                            "legacy_blocks_observed"
                        )
                saw_streaming = True
            structured_stage1_content = _has_structured_stage1_content(
                response_text, legacy_blocks
            )
            response_ready = (
                bool(response_text)
                and saw_streaming
                and (has_send_button or structured_stage1_content)
                and ((not has_stop) or structured_stage1_content)
                and (not (has_stop and has_send_button) or structured_stage1_content)
            )
            if response_ready:
                if response_text == last_text:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_activity_ts = time.time()
                last_text = response_text
                idle_elapsed = time.time() - last_activity_ts
                terminal_stage1_blocks = _has_terminal_stage1_blocks(legacy_blocks)
                if terminal_stage1_blocks or (
                    stable_count >= 1 and idle_elapsed >= completion_idle_sec
                ):
                    emit(
                        "response_stable",
                        attempt=attempt,
                        backend="chatgpt_backend",
                        final_state_code="ok_terminal_blocks"
                        if terminal_stage1_blocks
                        else "ok",
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
                        final_state_code="ok_terminal_blocks"
                        if terminal_stage1_blocks
                        else "ok",
                    )
                    result["timeline"] = timeline
                    return result
            if saw_streaming and thinking_stopped and not response_text:
                emit(
                    "thinking_stopped",
                    attempt=attempt,
                    backend="chatgpt_backend",
                )
                if attempt >= 2 and upstream_error_retry_exhausted:
                    emit(
                        "upstream_error_retry_exhausted",
                        attempt=attempt,
                        backend="chatgpt_backend",
                    )
                    failed: dict[str, object] = {
                        "status": "failed",
                        "error_code": "CHATGPT_UPSTREAM_ERROR_RETRY_EXHAUSTED",
                        "failure_stage": "read",
                        "submit_info": cast(dict[str, object], submit_info),
                        "final_state": cast(dict[str, object], state),
                    }
                    emit(
                        "final_state",
                        attempt=attempt,
                        final_state="failed",
                        final_state_code="CHATGPT_UPSTREAM_ERROR_RETRY_EXHAUSTED",
                    )
                    failed["timeline"] = timeline
                    return failed
                if (
                    attempt == 1
                    and relaunch_browser is not None
                    and submit_classification == "sent"
                ):
                    emit(
                        "retry_decision",
                        attempt=attempt,
                        backend="chatgpt_backend",
                        reason="thinking_stopped_no_output",
                    )
                    relaunch_browser()
                    recovered_after_stream_abort = True
                    break
                failed: dict[str, object] = {
                    "status": "failed",
                    "error_code": "CHATGPT_THINKING_STOPPED_NO_OUTPUT",
                    "failure_stage": "read",
                    "submit_info": cast(dict[str, object], submit_info),
                    "final_state": cast(dict[str, object], state),
                }
                emit(
                    "final_state",
                    attempt=attempt,
                    final_state="failed",
                    final_state_code="CHATGPT_THINKING_STOPPED_NO_OUTPUT",
                )
                failed["timeline"] = timeline
                return failed
            if (
                not saw_streaming
                and not text
                and time.time() - started >= response_start_timeout_sec
            ):
                if ambiguous_submit_probe_only:
                    failed = _interaction_failure(
                        failure_stage="submit",
                        error_code="CHATGPT_BACKEND_UNAVAILABLE",
                        backend_error=str(
                            submit_evidence.get(
                                "classification_reason", "submit_ambiguous"
                            )
                        ),
                        submit_info=submit_info,
                        final_state=cast(dict[str, object], state),
                    )
                    emit(
                        "final_state",
                        attempt=attempt,
                        final_state="failed",
                        final_state_code=str(failed.get("error_code", "failed")),
                    )
                    failed["timeline"] = timeline
                    return failed
                if not response_not_started_emitted:
                    emit(
                        "response_not_started",
                        attempt=attempt,
                        backend="chatgpt_backend",
                    )
                    response_not_started_emitted = True
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


def _submit_prompt_with_deadline(
    backend: ChatGPTBackend, prompt: str, *, deadline_ts: float
) -> dict[str, object]:
    timeout_sec = max(0.05, deadline_ts - time.time())
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def run_submit() -> None:
        try:
            result_queue.put(("ok", backend.submit_prompt(prompt)))
        except RuntimeError as exc:
            result_queue.put(("runtime_error", exc))
        except Exception as exc:
            result_queue.put(("error", exc))

    thread = threading.Thread(target=run_submit, daemon=True)
    thread.start()
    thread.join(timeout_sec)
    if thread.is_alive():
        raise RuntimeError("CHATGPT_SUBMIT_TIMEOUT")
    try:
        status, payload = result_queue.get_nowait()
    except queue.Empty as exc:
        raise RuntimeError("CHATGPT_SUBMIT_TIMEOUT") from exc
    if status == "ok" and isinstance(payload, dict):
        return cast(dict[str, object], payload)
    if isinstance(payload, RuntimeError):
        raise payload
    raise RuntimeError(str(payload))


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
    normalized = text.strip()
    newline = chr(10)
    if isinstance(legacy_blocks, list):
        parts: list[str] = []
        labels: list[str] = []
        for item in legacy_blocks:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            body = str(item.get("body", "")).strip()
            if label:
                labels.append(label)
            if label and body:
                if body.startswith("COPY" + newline):
                    body = body[len("COPY" + newline) :]
                parts.append(label + newline + body)
            elif label and newline in label:
                parts.append(label)
        if parts:
            joined = (newline + newline).join(parts)
            has_voice_or_scene = any(
                label.lower().startswith("[voice")
                or label.lower().startswith("[#")
                or label.lower().startswith("[scene")
                for label in labels
            )
            assistant_has_structure = (
                "[Voice]" in normalized
                or "[#" in normalized
                or "[Scene" in normalized
                or (newline + "1.") in normalized
            )
            if not has_voice_or_scene and assistant_has_structure and normalized:
                return joined + newline + newline + normalized
            return joined
    lowered = normalized.lower()
    status_only = {"생각 중지됨", "stopped thinking", "문서 읽는 중"}
    if lowered in status_only:
        return ""
    if normalized.startswith("롱폼의 말:"):
        body = normalized.split(":", 1)[1].strip() if ":" in normalized else ""
        if body.lower() in status_only or body in {"지금 응답 받기", "다시 시도"}:
            return ""
    return normalized


def _has_terminal_stage1_blocks(legacy_blocks: object) -> bool:
    if not isinstance(legacy_blocks, list):
        return False
    labels = {
        str(item.get("label", "")).strip().lower()
        for item in legacy_blocks
        if isinstance(item, dict)
    }
    has_scene = any(
        label.startswith("[#") or label.startswith("[scene") for label in labels
    )
    has_voice = any(label.startswith("[voice") for label in labels)
    has_terminal = any(
        label.startswith("[shorts voice") or label.startswith("[shorts clip mapping")
        for label in labels
    )
    return has_scene and has_voice and has_terminal


def _has_structured_stage1_content(response_text: str, legacy_blocks: object) -> bool:
    if isinstance(legacy_blocks, list):
        for item in legacy_blocks:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            normalized_label = label.lower()
            if label.startswith("[#") or normalized_label.startswith("[scene"):
                return True
    text = response_text.strip()
    if not text:
        return False
    valid_stage1_json = True
    try:
        _ = parse_stage1_gpt_plan(extract_stage1_gpt_plan_json(text))
    except (json.JSONDecodeError, ValueError):
        valid_stage1_json = False
    if valid_stage1_json:
        return True
    return any(
        marker in text
        for marker in (
            "[#01]",
            "[#02]",
            "[Scene 1]",
            "[Scene 2]",
            "[Voice]",
            chr(10) + "1.",
        )
    )


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
    if isinstance(raw, dict) and raw:
        submit_evidence = dict(raw)
        submit_evidence["attempt_key"] = _attempt_key(attempt)
        return submit_evidence
    return {
        "attempt_key": _attempt_key(attempt),
        "classification": "ambiguous",
        "classification_reason": "submit_evidence_missing",
        "retry_safe_decision": False,
    }


def _should_probe_after_ambiguous_submit(
    submit_info: dict[str, object], submit_evidence: dict[str, object]
) -> bool:
    if str(submit_evidence.get("classification", "")).strip() == "sent":
        return True
    if not bool(submit_info.get("sendClicked", False)):
        return False
    reason = str(submit_evidence.get("classification_reason", "")).strip()
    return reason in {"send_click_unconfirmed", "submit_evidence_missing"}


def _attempt_key(attempt: int) -> str:
    return f"attempt-{attempt}"

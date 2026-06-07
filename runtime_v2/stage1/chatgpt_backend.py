from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Protocol, cast

import websocket

from runtime_v2.agent_browser.result_parser import (
    parse_tab_list_output,
    select_best_tab,
)

CHATGPT_LONGFORM_URL_SUBSTRING = (
    "chatgpt.com/g/g-696a6d74fbd48191a1ffdc5f8ea90a1b-rongpom"
)
CHATGPT_LONGFORM_TITLE_SUBSTRING = "롱폼"
CHATGPT_LONGFORM_URL = f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}"


def _start_new_chat(websocket_url: str, *, timeout_sec: float) -> dict[str, object]:
    expression = (
        "(() => {"
        "const visible = (node) => { if (!node) return false; const rects = typeof node.getClientRects === 'function' ? node.getClientRects() : []; const shown = !!node.isConnected && ((rects && rects.length > 0) || node.offsetParent !== null); if (!shown) return false; const style = window.getComputedStyle ? window.getComputedStyle(node) : null; return !style || (style.visibility !== 'hidden' && style.display !== 'none'); };"
        "const clickIfVisible = (node) => { if (!visible(node)) return false; if (typeof node.click === 'function') node.click(); return true; };"
        'const sidebarToggles = ["button[aria-label*=\"sidebar\" i]", "button[aria-label*=\"사이드바\" i]", "button[data-testid*=\"sidebar\"]"];'
        "for (const selector of sidebarToggles) { try { const node = document.querySelector(selector); if (node && !visible(document.querySelector('nav'))) { clickIfVisible(node); } } catch (_) {} }"
        'const selectors = ["a[href*=\"/g/\"][href$=\"/new\"]", "a[href*=\"/new\"]", "button[data-testid*=\"new-chat\"]", "button[aria-label*=\"New chat\" i]", "button[aria-label*=\"새 채팅\" i]"];'
        "for (const selector of selectors) { try { const node = document.querySelector(selector); if (clickIfVisible(node)) { return JSON.stringify({clicked:true, selector:selector}); } } catch (_) {} }"
        "const labels = ['New chat', '새 채팅', 'New conversation', '새 대화'];"
        "const candidates = Array.from(document.querySelectorAll('button,a')).filter((node) => visible(node));"
        "for (const node of candidates) { const text = String(node.innerText || node.textContent || '').trim(); const aria = node.getAttribute ? String(node.getAttribute('aria-label') || '').trim() : ''; if (labels.some((label) => text.includes(label) || aria.includes(label))) { node.click(); return JSON.stringify({clicked:true, selector:'label_match', label:text || aria}); } }"
        "return JSON.stringify({clicked:false});"
        "})()"
    )
    payload = _run_raw_cdp_method(
        websocket_url,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
        timeout_sec=timeout_sec,
    )
    result = cast(dict[str, object], payload.get("result", {}))
    value = result.get("value", {})
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"clicked": False, "raw": value}
        return (
            cast(dict[str, object], decoded)
            if isinstance(decoded, dict)
            else {"clicked": False}
        )
    return (
        cast(dict[str, object], value)
        if isinstance(value, dict)
        else {"clicked": False}
    )


_SEND_ACK_TIMEOUT_SEC = 5.0
_SEND_ACK_POLL_SEC = 0.2


class ChatGPTBackend(Protocol):
    def submit_prompt(self, prompt: str) -> dict[str, object]: ...

    def read_response_state(self) -> dict[str, object]: ...


class AgentBrowserCdpBackend:
    def __init__(
        self,
        *,
        port: int,
        input_selectors: list[str],
        send_selectors: list[str],
        stop_selectors: list[str],
        response_selectors: list[str],
        expected_url_substring: str = CHATGPT_LONGFORM_URL_SUBSTRING,
        expected_title_substring: str = CHATGPT_LONGFORM_TITLE_SUBSTRING,
        command_runner: Callable[[list[str], int], str] | None = None,
        raw_cdp_timeout_resolver: Callable[[float], float] | None = None,
    ) -> None:
        self._port = port
        self._input_selectors = input_selectors
        self._send_selectors = send_selectors
        self._stop_selectors = stop_selectors
        self._response_selectors = response_selectors
        self._expected_url_substring = expected_url_substring
        self._expected_title_substring = expected_title_substring
        self._runner = _default_runner if command_runner is None else command_runner
        self._raw_cdp_timeout = (
            (lambda default: default)
            if raw_cdp_timeout_resolver is None
            else raw_cdp_timeout_resolver
        )
        self._max_retries = 2
        self._fallback_events: list[str] = []
        self._last_selected_target: dict[str, str] = {}

    def _remember_target(self, target: dict[str, str] | None) -> dict[str, str]:
        if target:
            self._last_selected_target = dict(target)
        return dict(self._last_selected_target)

    def submit_prompt(self, prompt: str) -> dict[str, object]:
        payload = json.dumps(
            {
                "prompt": prompt,
                "inputSelectors": self._input_selectors,
                "sendSelectors": self._send_selectors,
                "stopSelectors": self._stop_selectors,
            },
            ensure_ascii=False,
        )
        parsed: dict[str, object] = {}
        preflight_status: dict[str, object] = {}
        for _attempt in range(10):
            try:
                preflight_status = self._wait_for_input_ready()
            except RuntimeError:
                pass
            try:
                result = self._run_eval_with_retry(_prepare_input_script(payload))
                parsed = _decode_backend_json(result)
            except RuntimeError as exc:
                submit_evidence = cast(
                    dict[str, object],
                    {
                        "attempt_key": "attempt-1",
                        "classification": "ambiguous",
                        "classification_reason": str(exc),
                        "retry_safe_decision": False,
                    },
                )
                if preflight_status:
                    submit_evidence["preflight_status"] = preflight_status
                return {
                    "ok": True,
                    "inputSelector": "",
                    "submit_evidence": submit_evidence,
                }
            raw_submit_evidence = parsed.get("submitEvidence", {})
            submit_transition_observed = False
            if isinstance(raw_submit_evidence, dict):
                typed_submit_evidence = cast(dict[str, object], raw_submit_evidence)
                submit_transition_observed = bool(
                    typed_submit_evidence.get("in_flight_observed", False)
                    or typed_submit_evidence.get("terminal_success_observed", False)
                )
            if (
                bool(parsed.get("ok", False))
                and not bool(parsed.get("inputSuccess", False))
                and not submit_transition_observed
            ):
                parsed["ok"] = False
                parsed["error"] = "NO_INPUT"
            if str(parsed.get("error", "")) != "NO_INPUT":
                break
            if preflight_status:
                parsed.setdefault("preflight_status", preflight_status)
            try:
                self._ensure_custom_gpt_page()
            except RuntimeError:
                pass
            time.sleep(2.0)
        if not bool(parsed.get("ok", False)):
            error = str(parsed.get("error", "chatgpt_submit_failed"))
            no_send_evidence = _normalized_no_send_evidence(parsed)
            submit_evidence = _submit_evidence_record(
                error=error,
                parsed=parsed,
                no_send_evidence=no_send_evidence,
            )
            if preflight_status:
                submit_evidence["preflight_status"] = preflight_status
            if error in {"NO_SEND", "SEND_DISABLED"} and bool(
                no_send_evidence.get("retry_safe", False)
            ):
                raw_target = _select_page_target(
                    self._port, self._expected_url_substring
                )
                self._remember_target(raw_target)
                parsed = _decode_backend_json(
                    _run_raw_cdp_eval(
                        raw_target["webSocketDebuggerUrl"],
                        _prepare_input_script(payload),
                        timeout_sec=self._raw_cdp_timeout(30.0),
                    )
                )
                self._record_fallback("submit_raw_cdp_fallback")
                if bool(parsed.get("ok", False)):
                    parsed.setdefault(
                        "backend_fallbacks", self._fallback_events_payload()
                    )
                    parsed.setdefault("no_send_evidence", no_send_evidence)
                    parsed.setdefault("submit_evidence", submit_evidence)
                    return parsed
            raise RuntimeError(
                json.dumps(
                    {
                        "error": error,
                        "retry_safe": bool(no_send_evidence.get("retry_safe", False)),
                        "no_send_evidence": no_send_evidence,
                        "submit_evidence": submit_evidence,
                    },
                    ensure_ascii=True,
                )
            )
        raw_submit_evidence = parsed.get("submitEvidence", {})
        if isinstance(raw_submit_evidence, dict):
            in_flight_observed = bool(
                raw_submit_evidence.get("in_flight_observed", False)
            )
            terminal_success_observed = bool(
                raw_submit_evidence.get("terminal_success_observed", False)
            )
            if in_flight_observed or terminal_success_observed:
                parsed.setdefault("selected_tab", self._current_selected_tab())
                parsed.setdefault("backend_fallbacks", self._fallback_events_payload())
                parsed.setdefault(
                    "submit_evidence",
                    _submit_evidence_record(
                        error="",
                        parsed=parsed,
                        no_send_evidence=_normalized_no_send_evidence({}),
                    ),
                )
                return parsed
        submit_state = self._wait_for_send_state(payload)
        submit_state.setdefault("selected_tab", self._current_selected_tab())
        submit_state.setdefault("backend_fallbacks", self._fallback_events_payload())
        submit_state.setdefault("inputSelector", str(parsed.get("inputSelector", "")))
        return submit_state

    def _wait_for_send_state(self, payload: str) -> dict[str, object]:
        last_state: dict[str, object] = {}
        for _attempt in range(20):
            state = _decode_backend_json(
                self._run_eval_with_retry(_send_control_state_script(payload))
            )
            last_state = state
            if not bool(state.get("send_found", False)):
                try:
                    self._ensure_chatgpt_target_selected()
                    _wait_for_chatgpt_prompt_ready(
                        self._current_selected_tab().get("webSocketDebuggerUrl", ""),
                        timeout_sec=2.0,
                    )
                except RuntimeError:
                    pass
            if bool(state.get("in_flight_marker", False)):
                submit_evidence = {
                    "attempt_key": "attempt-1",
                    "classification": "sent",
                    "classification_reason": "streaming_or_stop_visible",
                    "retry_safe_decision": False,
                    "pre": state,
                    "post": state,
                    "in_flight_observed": True,
                    "terminal_success_observed": False,
                    "state_transition": True,
                }
                return {
                    "ok": True,
                    "sendClicked": False,
                    "sendTestId": str(state.get("send_test_id", "")),
                    "sendAriaLabel": str(state.get("send_aria_label", "")),
                    "no_send_evidence": state,
                    "submit_evidence": submit_evidence,
                }
            if bool(state.get("send_found", False)) and bool(
                state.get("send_enabled", False)
            ):
                try:
                    click_result = _decode_backend_json(
                        self._run_eval_with_retry(_click_send_script(payload))
                    )
                    post_state = _decode_backend_json(
                        self._run_eval_with_retry(_send_control_state_script(payload))
                    )
                except RuntimeError as exc:
                    try:
                        post_state = _decode_backend_json(
                            self._run_eval_with_retry(
                                _send_control_state_script(payload)
                            )
                        )
                        if (
                            bool(post_state.get("in_flight_marker", False))
                            or not bool(post_state.get("send_found", False))
                            or not bool(post_state.get("send_enabled", False))
                        ):
                            submit_evidence = {
                                "attempt_key": "attempt-1",
                                "classification": "sent",
                                "classification_reason": "send_state_after_click_exception",
                                "retry_safe_decision": False,
                                "pre": state,
                                "post": post_state,
                                "in_flight_observed": bool(
                                    post_state.get("in_flight_marker", False)
                                ),
                                "terminal_success_observed": bool(
                                    post_state.get("terminal_success_observed", False)
                                ),
                                "state_transition": bool(
                                    post_state.get("state_transition", False)
                                )
                                or bool(post_state.get("in_flight_marker", False))
                                or not bool(post_state.get("send_found", False))
                                or not bool(post_state.get("send_enabled", False)),
                            }
                            return {
                                "ok": True,
                                "sendClicked": True,
                                "sendTestId": str(state.get("send_test_id", "")),
                                "sendAriaLabel": str(state.get("send_aria_label", "")),
                                "submit_evidence": submit_evidence,
                            }
                    except RuntimeError:
                        pass
                    submit_evidence = {
                        "attempt_key": "attempt-1",
                        "classification": "ambiguous",
                        "classification_reason": str(exc),
                        "retry_safe_decision": False,
                        "pre": state,
                    }
                    return {
                        "ok": True,
                        "sendClicked": False,
                        "sendTestId": str(state.get("send_test_id", "")),
                        "sendAriaLabel": str(state.get("send_aria_label", "")),
                        "submit_evidence": submit_evidence,
                    }
                deadline = time.time() + _SEND_ACK_TIMEOUT_SEC
                while time.time() < deadline:
                    in_flight_candidate = bool(
                        post_state.get("in_flight_marker", False)
                    )
                    terminal_candidate = bool(
                        post_state.get("terminal_success_observed", False)
                    )
                    state_transition_candidate = (
                        bool(post_state.get("state_transition", False))
                        or in_flight_candidate
                    )
                    send_found_candidate = bool(post_state.get("send_found", False))
                    send_enabled_candidate = bool(post_state.get("send_enabled", False))
                    if (
                        in_flight_candidate
                        or terminal_candidate
                        or state_transition_candidate
                        or not send_found_candidate
                        or not send_enabled_candidate
                    ):
                        break
                    time.sleep(_SEND_ACK_POLL_SEC)
                    post_state = _decode_backend_json(
                        self._run_eval_with_retry(_send_control_state_script(payload))
                    )
                in_flight_observed = bool(post_state.get("in_flight_marker", False))
                terminal_success_observed = bool(
                    post_state.get("terminal_success_observed", False)
                )
                send_found_after_click = bool(post_state.get("send_found", False))
                send_enabled_after_click = bool(post_state.get("send_enabled", False))
                state_transition = (
                    bool(post_state.get("state_transition", False))
                    or in_flight_observed
                    or not send_found_after_click
                    or not send_enabled_after_click
                )
                submit_evidence = {
                    "attempt_key": "attempt-1",
                    "classification": (
                        "sent"
                        if (
                            in_flight_observed
                            or terminal_success_observed
                            or state_transition
                        )
                        else "ambiguous"
                    ),
                    "classification_reason": (
                        "send_button_clicked"
                        if (
                            in_flight_observed
                            or terminal_success_observed
                            or state_transition
                        )
                        else "send_click_unconfirmed"
                    ),
                    "retry_safe_decision": False,
                    "pre": state,
                    "post": post_state,
                    "in_flight_observed": in_flight_observed,
                    "terminal_success_observed": terminal_success_observed,
                    "state_transition": state_transition,
                }
                return {
                    "ok": True,
                    "sendClicked": bool(click_result.get("sendClicked", False)),
                    "sendTestId": str(click_result.get("sendTestId", "")),
                    "sendAriaLabel": str(click_result.get("sendAriaLabel", "")),
                    "submit_evidence": submit_evidence,
                }
            time.sleep(0.5)
        error = (
            "SEND_DISABLED" if bool(last_state.get("send_found", False)) else "NO_SEND"
        )
        no_send_evidence = _normalized_no_send_evidence(last_state)
        submit_evidence = _submit_evidence_record(
            error=error,
            parsed=last_state,
            no_send_evidence=no_send_evidence,
        )
        raise RuntimeError(
            json.dumps(
                {
                    "error": error,
                    "retry_safe": bool(no_send_evidence.get("retry_safe", False)),
                    "no_send_evidence": no_send_evidence,
                    "submit_evidence": submit_evidence,
                },
                ensure_ascii=True,
            )
        )

    def _wait_for_input_ready(self) -> dict[str, object]:
        last_status: dict[str, object] = {}
        for _attempt in range(10):
            result = self._run_eval_with_retry(_input_ready_script())
            parsed = _decode_backend_json(result)
            last_status = parsed
            if bool(parsed.get("ready", False)):
                return parsed
            time.sleep(1.0)
        return last_status

    def read_response_state(self) -> dict[str, object]:
        payload = json.dumps(
            {
                "stopSelectors": self._stop_selectors,
                "sendSelectors": self._send_selectors,
                "responseSelectors": self._response_selectors,
            },
            ensure_ascii=False,
        )
        result = self._run_eval_with_retry(_response_script(payload))
        parsed = _decode_backend_json(result)
        return {
            "has_stop": bool(parsed.get("has_stop", False)),
            "has_send_button": bool(parsed.get("has_send_button", False)),
            "assistant_text": str(parsed.get("assistant_text", "")),
            "assistant_block_count": parsed.get("assistant_block_count", 0),
            "legacy_blocks": parsed.get("legacy_blocks", []),
            "has_recovery_cta": bool(parsed.get("has_recovery_cta", False)),
            "recovery_clicked": bool(parsed.get("recovery_clicked", False)),
            "thinking_stopped": bool(parsed.get("thinking_stopped", False)),
            "upstream_error_retry_exhausted": bool(
                parsed.get("upstream_error_retry_exhausted", False)
            ),
            "selected_tab": self._current_selected_tab(),
            "backend_fallbacks": self._fallback_events_payload(),
        }

    def _run_eval_with_retry(self, script: str) -> str:
        last_error: RuntimeError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                self._ensure_chatgpt_target_selected()
                return self._runner(
                    [
                        "agent-browser",
                        "--cdp",
                        str(self._port),
                        "eval",
                        script,
                    ],
                    60,
                )
            except RuntimeError as exc:
                last_error = exc
                if (
                    not _is_retryable_backend_error(str(exc))
                    or attempt >= self._max_retries
                ):
                    break
                time.sleep(1.0)
        try:
            raw_target = _select_page_target(self._port, self._expected_url_substring)
            self._remember_target(raw_target)
        except RuntimeError:
            raise
        self._record_fallback("eval_raw_cdp_fallback")
        return _run_raw_cdp_eval(
            raw_target["webSocketDebuggerUrl"],
            script,
            timeout_sec=self._raw_cdp_timeout(30.0),
        )

    def _ensure_chatgpt_target_selected(self) -> None:
        self._ensure_custom_gpt_page()
        target_index = self._chatgpt_tab_index()
        if target_index is None:
            return
        _ = self._runner(
            [
                "agent-browser",
                "--cdp",
                str(self._port),
                "tab",
                str(target_index),
            ],
            15,
        )

    def _ensure_custom_gpt_page(self) -> None:
        try:
            target = _select_page_target(self._port, self._expected_url_substring)
            self._remember_target(target)
            return
        except RuntimeError:
            self._record_fallback("custom_page_select_fallback")
        generic = _select_generic_chatgpt_target(self._port)
        if generic is None:
            return
        self._remember_target(generic)
        _run_raw_cdp_method(
            generic["webSocketDebuggerUrl"],
            "Page.navigate",
            {"url": CHATGPT_LONGFORM_URL},
            timeout_sec=self._raw_cdp_timeout(30.0),
        )
        time.sleep(2.0)
        try:
            _wait_for_chatgpt_prompt_ready(
                generic["webSocketDebuggerUrl"],
                timeout_sec=self._raw_cdp_timeout(30.0),
            )
        except RuntimeError:
            self._record_fallback("custom_page_prompt_ready_timeout")
        self._remember_target(
            {
                "webSocketDebuggerUrl": generic["webSocketDebuggerUrl"],
                "url": CHATGPT_LONGFORM_URL,
                "title": generic.get("title", CHATGPT_LONGFORM_TITLE_SUBSTRING),
            }
        )

    def _chatgpt_tab_index(self) -> int | None:
        try:
            output = self._runner(
                ["agent-browser", "--cdp", str(self._port), "tab", "list"],
                15,
            )
            parsed = parse_tab_list_output(output)
            best = select_best_tab(
                parsed,
                expected_url_substring=self._expected_url_substring,
                expected_title_substring=self._expected_title_substring,
            )
            if best is not None:
                return best
        except RuntimeError:
            self._record_fallback("tab_list_http_fallback")
        return _chatgpt_tab_index_from_http(
            self._port,
            expected_url_substring=self._expected_url_substring,
            expected_title_substring=self._expected_title_substring,
        )

    def _current_selected_tab(self) -> dict[str, str]:
        try:
            target = _select_page_target(self._port, self._expected_url_substring)
            return self._remember_target(target)
        except RuntimeError:
            self._record_fallback("current_tab_http_fallback")
            return dict(self._last_selected_target)

    def _record_fallback(self, event: str) -> None:
        normalized = str(event).strip()
        if normalized and normalized not in self._fallback_events:
            self._fallback_events.append(normalized)

    def _fallback_events_payload(self) -> list[str]:
        return list(self._fallback_events)


def reset_chatgpt_context(
    port: int,
    *,
    expected_url_substring: str = CHATGPT_LONGFORM_URL_SUBSTRING,
    target_url: str = CHATGPT_LONGFORM_URL,
    deadline_ts: float | None = None,
) -> dict[str, object]:
    def _raw_cdp_timeout(default: float) -> float:
        if deadline_ts is None:
            return default
        remaining = deadline_ts - time.time()
        if remaining <= 0:
            return 1.0
        return min(default, max(1.0, remaining))

    try:
        target = _select_page_target(port, expected_url_substring)
    except RuntimeError:
        target = _select_generic_chatgpt_target(port)
        if target is None:
            raise RuntimeError("chatgpt_context_target_missing")
    try:
        _wait_for_chatgpt_prompt_ready(target["webSocketDebuggerUrl"], timeout_sec=2.0)
    except RuntimeError:
        pass
    _run_raw_cdp_method(
        target["webSocketDebuggerUrl"],
        "Page.navigate",
        {"url": target_url},
        timeout_sec=_raw_cdp_timeout(30.0),
    )
    _run_raw_cdp_method(
        target["webSocketDebuggerUrl"],
        "Page.reload",
        {"ignoreCache": True},
        timeout_sec=_raw_cdp_timeout(30.0),
    )
    _wait_for_chatgpt_prompt_ready(
        target["webSocketDebuggerUrl"], timeout_sec=_raw_cdp_timeout(10.0)
    )
    new_chat = _start_new_chat(
        target["webSocketDebuggerUrl"], timeout_sec=_raw_cdp_timeout(10.0)
    )
    if not bool(new_chat.get("clicked", False)):
        raise RuntimeError("chatgpt_new_chat_unavailable")
    sleep_budget = 3.0
    if deadline_ts is not None:
        sleep_budget = min(sleep_budget, max(0.0, deadline_ts - time.time()))
    time.sleep(sleep_budget)
    _wait_for_chatgpt_prompt_ready(
        target["webSocketDebuggerUrl"], timeout_sec=_raw_cdp_timeout(30.0)
    )
    return {
        "status": "ok",
        "port": port,
        "target_url": target_url,
        "target": target,
    }


def chatgpt_context_ready(
    port: int,
    *,
    expected_url_substring: str = CHATGPT_LONGFORM_URL_SUBSTRING,
) -> bool:
    try:
        target = _select_page_target(port, expected_url_substring)
    except RuntimeError:
        return False
    try:
        _wait_for_chatgpt_prompt_ready(target["webSocketDebuggerUrl"], timeout_sec=2.0)
    except RuntimeError:
        return False
    return True


def _wait_for_chatgpt_prompt_ready(
    websocket_url: str, *, timeout_sec: float = 20.0
) -> None:
    deadline = time.time() + timeout_sec
    expression = (
        "(() => {"
        "const visibleNode = (node) => { if (!node) return false; const rects = typeof node.getClientRects === 'function' ? node.getClientRects() : []; const visible = !!node.isConnected && ((rects && rects.length > 0) || node.offsetParent !== null); const style = window.getComputedStyle(node); return visible && style.visibility !== 'hidden' && style.display !== 'none'; };"
        "const candidates = [document.querySelector('#prompt-textarea'), document.querySelector(\"div[contenteditable=\\\"true\\\"]\"), document.querySelector('textarea')].filter(Boolean);"
        "const hydratedInput = candidates.find((node) => visibleNode(node) && ((node.getAttribute && node.getAttribute('contenteditable') === 'true') || node.tagName === 'TEXTAREA'));"
        "const inputReady = !!hydratedInput;"
        "const send = document.querySelector('#composer-submit-button') || document.querySelector('button[data-testid=\"send-button\"]') || document.querySelector('button[aria-label=\"프롬프트 보내기\"]');"
        "const sendReady = !!send && visibleNode(send) && !send.disabled;"
        "return inputReady && sendReady;"
        "})()"
    )
    while time.time() < deadline:
        try:
            remaining = max(1.0, deadline - time.time())
            payload = _run_raw_cdp_method(
                websocket_url,
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
                timeout_sec=remaining,
            )
            result = cast(dict[str, object], payload.get("result", {}))
            if bool(result.get("value", False)):
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("chatgpt_prompt_not_ready")


def _prepare_input_script(payload: str) -> str:
    return (
        "(() => {"
        "try {"
        f"const config = {payload};"
        "const selectors = config.inputSelectors || [];"
        "let selectorError = '';"
        "const safeQuery = (selector) => { try { return document.querySelector(selector); } catch (error) { selectorError = String((error && error.message) || error || 'selector_error'); return null; } };"
        "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',keyCode:27,bubbles:true}));"
        "const closeSelectors=['button[aria-label=\"닫기\"]','button[aria-label=\"Close\"]','button[aria-label*=\"close\"]','button[aria-label*=\"dismiss\"]','.modal-close','[data-testid*=\"close\"]','[data-testid*=\"dismiss\"]'];"
        "for (const selector of closeSelectors) { for (const btn of Array.from(document.querySelectorAll(selector))) { try { const visible = !!btn && !!btn.isConnected && (((btn.getClientRects && btn.getClientRects().length > 0)) || btn.offsetParent !== null); if (visible) btn.click(); } catch (_) {} } }"
        "let input = null;"
        "let visibleSelectorMatches = 0;"
        "for (const selector of selectors) { const candidate = safeQuery(selector); const visible = !!candidate && !!candidate.isConnected && (((candidate.getClientRects && candidate.getClientRects().length > 0)) || candidate.offsetParent !== null); if (visible) { input = candidate; break; } }"
        "for (const selector of selectors) { const candidate = safeQuery(selector); const visible = !!candidate && !!candidate.isConnected && (((candidate.getClientRects && candidate.getClientRects().length > 0)) || candidate.offsetParent !== null); if (visible) visibleSelectorMatches += 1; }"
        "const chatInput = document.querySelector('[data-testid=\"chat-input\"]');"
        "let visibleChatInputEditor = false;"
        "if (!input && chatInput) { const editor = chatInput.querySelector('.ProseMirror, [contenteditable=\"true\"]'); const visible = !!editor && !!editor.isConnected && (((editor.getClientRects && editor.getClientRects().length > 0)) || editor.offsetParent !== null); visibleChatInputEditor = visible; if (visible) input = editor; }"
        "const editors = Array.from(document.querySelectorAll('[contenteditable=\"true\"]')).filter((el) => el && el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null) && !el.closest('article') && !el.closest('[data-message-author-role=\"assistant\"]'));"
        "if (!input && editors.length) input = editors[0];"
        "const proseMirrors = Array.from(document.querySelectorAll('.ProseMirror')).filter((el) => el && el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null) && !el.closest('[data-message-author-role=\"assistant\"]'));"
        "if (!input && proseMirrors.length) input = proseMirrors[0];"
        "if (!input) return JSON.stringify({ok:false,error: selectorError ? 'INPUT_SELECTOR_ERROR' : 'NO_INPUT', inputSelectorError: selectorError, visibleSelectorMatches: visibleSelectorMatches, visibleChatInputEditor: visibleChatInputEditor, visibleContenteditableCount: editors.length, visibleProseMirrorCount: proseMirrors.length});"
        "if (typeof input.click === 'function') input.click();"
        "input.focus();"
        "let inputSuccess = false;"
        "const normalize = (value) => String(value || '').replace(/\\r\\n/g, '\\n').replace(/\\n{2,}/g, '\\n').trim();"
        "const isProseMirror = !!(input.classList && (input.classList.contains('ProseMirror') || input.classList.contains('tiptap')));"
        "if (isProseMirror) {"
        "  const sel = window.getSelection(); const range = document.createRange(); range.selectNodeContents(input); sel.removeAllRanges(); sel.addRange(range);"
        "  document.execCommand('delete', false, null);"
        "  const inserted = document.execCommand('insertText', false, config.prompt);"
        "  if (!inserted) { input.innerHTML = ''; const p = document.createElement('p'); p.textContent = config.prompt; input.appendChild(p); }"
        "  input.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,data:config.prompt,inputType:'insertText'}));"
        "  input.dispatchEvent(new Event('change',{bubbles:true}));"
        "  input.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:'a'}));"
        "  const finalText = normalize(input.innerText || input.textContent || '');"
        "  inputSuccess = finalText === normalize(config.prompt);"
        "  var inputFinalText = finalText;"
        "} else if (input.tagName === 'TEXTAREA') {"
        "  input.value = config.prompt;"
        "  input.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,data:config.prompt,inputType:'insertText'}));"
        "  input.dispatchEvent(new Event('change',{bubbles:true}));"
        "  inputSuccess = normalize(input.value || '') === normalize(config.prompt);"
        "  var inputFinalText = normalize(input.value || '');"
        "} else {"
        "  input.innerText = config.prompt;"
        "  input.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,data:config.prompt,inputType:'insertText'}));"
        "  input.dispatchEvent(new Event('change',{bubbles:true}));"
        "  inputSuccess = normalize(input.innerText || input.textContent || '') === normalize(config.prompt);"
        "  var inputFinalText = normalize(input.innerText || input.textContent || '');"
        "}"
        "const matchedSelector = selectors.find(s => safeQuery(s)===input) || '';"
        "return JSON.stringify({ok:true,inputSelector: matchedSelector, inputSelectorError: selectorError, inputSuccess: inputSuccess, inputFinalText: inputFinalText || '', inputPromptNormalized: normalize(config.prompt)});"
        "} catch (error) { return JSON.stringify({ok:false,error:'INPUT_EVAL_EXCEPTION', detail:String((error && error.message) || error || '')}); }"
        "})()"
    )


def _send_control_state_script(payload: str) -> str:
    return (
        "(() => {"
        f"const config = {payload};"
        "const sendSelectors = config.sendSelectors || [];"
        "const stopSelectors = config.stopSelectors || [];"
        "const snapshot = (candidate) => {"
        "  if (!candidate) return {send_found:false, send_enabled:false, send_disabled:false, send_test_id:'', send_aria_label:'', aria_disabled:'', aria_busy:'', class_name:'', button_text:'', pointer_events:'', visible:false, is_connected:false, in_flight_marker:false, state_transition:false, retry_safe:true};"
        "  const className = String(candidate.className || '');"
        "  const ariaDisabled = candidate.getAttribute ? (candidate.getAttribute('aria-disabled') || '') : '';"
        "  const ariaBusy = candidate.getAttribute ? (candidate.getAttribute('aria-busy') || '') : '';"
        "  const inFlight = !!(candidate.querySelector && candidate.querySelector('[role=\"progressbar\"], .spinner, .loading')) || className.toLowerCase().includes('loading') || ariaBusy === 'true';"
        "  return {send_found:true, send_enabled:!candidate.disabled, send_disabled:!!candidate.disabled, send_test_id: candidate.getAttribute ? (candidate.getAttribute('data-testid') || '') : '', send_aria_label: candidate.getAttribute ? (candidate.getAttribute('aria-label') || '') : '', aria_disabled:ariaDisabled, aria_busy:ariaBusy, class_name:className, button_text:String(candidate.innerText || candidate.textContent || candidate.value || '').trim(), pointer_events:String((window.getComputedStyle && window.getComputedStyle(candidate).pointerEvents) || ''), visible:!!candidate.offsetParent, is_connected:!!candidate.isConnected, in_flight_marker:inFlight, state_transition:false, retry_safe:!candidate.disabled && !inFlight};"
        "};"
        "let hasStop = stopSelectors.some(selector => { const el = document.querySelector(selector); return !!(el && el.offsetParent !== null); });"
        "let send = null;"
        "for (const selector of sendSelectors) { const candidate = document.querySelector(selector); if (!candidate) continue; if (candidate.getAttribute && candidate.getAttribute('data-testid') === 'stop-button') continue; send = candidate; break; }"
        "const evidence = snapshot(send);"
        "evidence.in_flight_marker = evidence.in_flight_marker || hasStop;"
        "evidence.state_transition = evidence.in_flight_marker;"
        "evidence.retry_safe = !evidence.in_flight_marker;"
        "return JSON.stringify(evidence);"
        "})()"
    )


def _click_send_script(payload: str) -> str:
    return (
        "(() => {"
        f"const config = {payload};"
        "const selectors = config.inputSelectors || [];"
        "const sendSelectors = config.sendSelectors || [];"
        "let input = null;"
        "for (const selector of selectors) { try { const candidate = document.querySelector(selector); if (!candidate) continue; const visible = !!candidate && !!candidate.isConnected && (((candidate.getClientRects && candidate.getClientRects().length > 0)) || candidate.offsetParent !== null); if (visible) { input = candidate; break; } } catch (_) {} }"
        "if (!input) { const chatInput = document.querySelector('[data-testid=\"chat-input\"]'); if (chatInput) { const editor = chatInput.querySelector('.ProseMirror, [contenteditable=\"true\"]'); const visible = !!editor && !!editor.isConnected && (((editor.getClientRects && editor.getClientRects().length > 0)) || editor.offsetParent !== null); if (visible) input = editor; } }"
        "if (!input) { const proseMirrors = Array.from(document.querySelectorAll('.ProseMirror')).filter((el) => el && el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null) && !el.closest('[data-message-author-role=\"assistant\"]')); if (proseMirrors.length) input = proseMirrors[0]; }"
        "if (!input) return JSON.stringify({ok:false,error:'NO_SEND_INPUT'});"
        "if (typeof input.focus === 'function') input.focus();"
        "for (const selector of sendSelectors) { try { const send = document.querySelector(selector); if (!send) continue; const visible = !!send && !!send.isConnected && (((send.getClientRects && send.getClientRects().length > 0)) || send.offsetParent !== null); const disabled = !!send.disabled || (send.getAttribute && send.getAttribute('aria-disabled') === 'true'); if (!visible || disabled) continue; if (typeof send.focus === 'function') send.focus(); if (typeof send.click === 'function') send.click(); return JSON.stringify({ok:true,sendClicked:true,sendTestId:(send.getAttribute ? (send.getAttribute('data-testid') || 'send-button') : 'send-button'),sendAriaLabel:(send.getAttribute ? (send.getAttribute('aria-label') || '') : '')}); } catch (_) {} }"
        "['keydown','keypress','keyup'].forEach(type => input.dispatchEvent(new KeyboardEvent(type,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true})));"
        "return JSON.stringify({ok:true,sendClicked:true,sendTestId:'enter-key',sendAriaLabel:'Enter'});"
        "})()"
    )


def _response_script(payload: str) -> str:
    return (
        "(() => {"
        f"const config = {payload};"
        "const stopSelectors = config.stopSelectors || [];"
        "const sendSelectors = config.sendSelectors || [];"
        "const responseSelectors = config.responseSelectors || [];"
        "const isStopLike = (el) => { const aria = ((el && el.getAttribute && el.getAttribute('aria-label')) || '').toLowerCase(); return aria.includes('중지') || aria.includes('stop'); };"
        "const isSendLike = (el) => { const aria = ((el && el.getAttribute && el.getAttribute('aria-label')) || '').toLowerCase(); return aria.includes('전송') || aria.includes('send'); };"
        "let hasStop = stopSelectors.some(selector => { const el = document.querySelector(selector); return !!(el && el.offsetParent !== null && !isSendLike(el)); });"
        "let hasSendButton = sendSelectors.some(selector => { const el = document.querySelector(selector); return !!(el && el.offsetParent !== null && !el.disabled && !isStopLike(el)); });"
        "const composerBtn = document.getElementById('composer-submit-button');"
        "if (composerBtn) { if (!hasStop && isStopLike(composerBtn)) hasStop = true; if (!hasSendButton && isSendLike(composerBtn)) hasSendButton = true; }"
        "let assistantBlocks = [];"
        "for (const selector of responseSelectors) { const found = Array.from(document.querySelectorAll(selector)).filter(el => !el.closest('form')); if (found.length) { assistantBlocks = found; break; } }"
        "if (!assistantBlocks.length) { assistantBlocks = Array.from(document.querySelectorAll('section[data-testid^=\"conversation-turn-\"]')).filter(el => { const text=((el.innerText || el.textContent || '').trim()); if (!text) return false; if (text.startsWith('나의 말:') || text.startsWith('You said:')) return false; return text.includes('의 말:') || text.includes('said:'); }); }"
        "const last = assistantBlocks.length ? assistantBlocks[assistantBlocks.length - 1] : null;"
        "const text = last ? ((last.innerText || last.textContent || '').trim()) : '';"
        "const bodyText = document.body ? ((document.body.innerText || document.body.textContent || '').trim()) : '';"
        "const recoveryCandidates = Array.from(document.querySelectorAll('a,button')).filter(el => { const txt = ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).trim(); return txt.includes('지금 응답 받기') || txt.includes('Get response now'); });"
        "const recovery = recoveryCandidates.find(el => el && el.offsetParent !== null) || null;"
        "let recoveryClicked = false;"
        "const legacyLabels = ['[Voice]','[Title]','[Title for Thumb]','[Description]','[Keywords]','[BGM]','[URL]','[Ref Img 1]','[Ref Img 2]','[Shorts Description]','[Shorts Voice]','[Shorts Clip Mapping]'];"
        "const isLegacyHeading = (label) => legacyLabels.includes(label) || /^\\[Video\\d+/.test(label) || /^\\[#\\d+/.test(label) || /^Scene\\s*\\d+/i.test(label) || /^Video\\d+/i.test(label);"
        "let currentHeading = '';"
        "let lastSubLabel = '';"
        "const seenLegacy = new Set();"
        "const legacyBlocks = [];"
        "for (const node of Array.from(document.querySelectorAll('h1,h2,h3,p,pre'))) {"
        "  const textValue = ((node.innerText || node.textContent || '').trim());"
        "  if (!textValue) continue;"
        "  const tag = String(node.tagName || '').toLowerCase();"
        "  if (tag === 'h1' || tag === 'h2' || tag === 'h3') { if (isLegacyHeading(textValue)) { currentHeading = textValue; lastSubLabel = ''; } continue; }"
        "  if (tag === 'p') { if (isLegacyHeading(textValue)) { lastSubLabel = textValue; } continue; }"
        "  if (tag === 'pre') { const label = lastSubLabel || currentHeading || ''; if (!label) continue; const key = label + '::' + textValue.slice(0,100); if (seenLegacy.has(key)) continue; seenLegacy.add(key); legacyBlocks.push({label: label, body: textValue}); if (lastSubLabel) lastSubLabel = ''; }"
        "}"
        "return JSON.stringify({has_stop: hasStop, has_send_button: hasSendButton, assistant_block_count: assistantBlocks.length, assistant_text: text, legacy_blocks: legacyBlocks, has_recovery_cta: !!recovery, recovery_clicked: recoveryClicked, thinking_stopped: bodyText.includes('생각 중지됨') || bodyText.includes('Stopped thinking'), upstream_error_retry_exhausted: (bodyText.includes('문제가 발생했습니다') || bodyText.includes('Something went wrong')) && (bodyText.includes('다시 시도') || bodyText.includes('Try again'))});"
        "})()"
    )


def _input_ready_script() -> str:
    return (
        "(() => {"
        "const interactive = document.querySelector('[data-testid=\"prompt-input-ssr-interactive\"]');"
        "const ssr = document.querySelector('[data-testid=\"chat-input-ssr\"]');"
        "const chatInput = document.querySelector('[data-testid=\"chat-input\"]');"
        "const proseMirror = document.querySelector('.ProseMirror');"
        "const visible = (el) => !!el && !!el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null);"
        "const chatInputEditor = chatInput ? chatInput.querySelector('.ProseMirror, [contenteditable=\"true\"]') : null;"
        "const ready = visible(proseMirror) || visible(interactive) || visible(chatInputEditor);"
        "return JSON.stringify({ready, hasInteractive: !!interactive, hasSsr: !!ssr, hasChatInput: !!chatInput, hasProseMirror: !!proseMirror});"
        "})()"
    )


def _default_runner(command: list[str], timeout_sec: int) -> str:
    resolved = _resolve_agent_browser_command(command)
    try:
        completed = subprocess.run(
            resolved,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(str(exc)) from exc
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or str(completed.returncode)
        )
        raise RuntimeError(detail)
    stdout = completed.stdout.strip()
    if not stdout:
        return completed.stdout
    return stdout


def _chatgpt_tab_index_from_http(
    port: int,
    *,
    expected_url_substring: str,
    expected_title_substring: str,
) -> int | None:
    tabs = _http_cdp_tab_list(port)
    for index, tab in enumerate(tabs, start=1):
        url = str(tab.get("url", "")).lower()
        title = str(tab.get("title", "")).lower()
        if (
            expected_url_substring.lower() in url
            or expected_title_substring.lower() in title
        ):
            return index
    return None


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
        item = raw_item
        if str(item.get("type", "")) != "page":
            continue
        tabs.append(
            {
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
            }
        )
    return tabs


def _select_page_target(
    port: int,
    expected_url_substring: str,
    expected_title_substring: str = CHATGPT_LONGFORM_TITLE_SUBSTRING,
) -> dict[str, str]:
    def _normalize_longform_url(value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized.startswith("https://"):
            normalized = normalized[len("https://") :]
        elif normalized.startswith("http://"):
            normalized = normalized[len("http://") :]
        return normalized.rstrip("/")

    def _matches_longform_target(url: str, expected: str) -> bool:
        normalized_url = _normalize_longform_url(url)
        normalized_expected = _normalize_longform_url(expected)
        if normalized_url == normalized_expected:
            return True
        for marker in ("/", "?", "#"):
            if normalized_url.startswith(normalized_expected + marker):
                return True
        return False

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=10
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc
    if not isinstance(payload, list):
        raise RuntimeError("CDP_TARGET_NOT_FOUND")
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        item = raw_item
        if str(item.get("type", "")) != "page":
            continue
        url = str(item.get("url", ""))
        title = str(item.get("title", ""))
        if expected_url_substring == CHATGPT_LONGFORM_URL_SUBSTRING:
            if not _matches_longform_target(url, expected_url_substring):
                continue
        elif expected_url_substring not in url:
            continue
        ws_url = str(item.get("webSocketDebuggerUrl", "")).strip()
        if not ws_url:
            continue
        return {
            "webSocketDebuggerUrl": ws_url,
            "url": url,
            "title": title,
        }
    raise RuntimeError("CDP_TARGET_NOT_FOUND")


def _select_generic_chatgpt_target(port: int) -> dict[str, str] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=10
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        item = raw_item
        if str(item.get("type", "")) != "page":
            continue
        url = str(item.get("url", "")).strip()
        ws_url = str(item.get("webSocketDebuggerUrl", "")).strip()
        if not ws_url:
            continue
        if url.startswith("https://chatgpt.com/"):
            return {"webSocketDebuggerUrl": ws_url, "url": url}
    return None


def _run_raw_cdp_method(
    ws_url: str,
    method: str,
    params: dict[str, object],
    *,
    timeout_sec: float = 30.0,
) -> dict[str, object]:
    try:
        ws = websocket.create_connection(
            ws_url, timeout=timeout_sec, suppress_origin=True
        )
        try:
            deadline_ts = time.time() + timeout_sec
            ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": method,
                        "params": params,
                    },
                    ensure_ascii=True,
                )
            )
            while True:
                if time.time() >= deadline_ts:
                    raise RuntimeError("CDP_METHOD_TIMEOUT")
                response = json.loads(ws.recv())
                if response.get("id") != 1:
                    continue
                if not isinstance(response, dict):
                    raise RuntimeError("CDP_METHOD_INVALID")
                if response.get("error") is not None:
                    raise RuntimeError("CDP_METHOD_ERROR")
                result = response.get("result", {})
                return result if isinstance(result, dict) else {}
        finally:
            ws.close()
    except websocket.WebSocketTimeoutException as exc:
        raise RuntimeError("CDP_METHOD_TIMEOUT") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc


def _run_raw_cdp_eval(ws_url: str, script: str, *, timeout_sec: float = 30.0) -> str:
    result = _run_raw_cdp_method(
        ws_url,
        "Runtime.evaluate",
        {"expression": script, "returnByValue": True},
        timeout_sec=timeout_sec,
    )
    exception = result.get("exceptionDetails")
    if exception is not None:
        detail = "CDP_EVAL_EXCEPTION"
        if isinstance(exception, dict):
            text = str(exception.get("text", "")).strip()
            description = str(
                cast(dict[str, object], exception.get("exception", {})).get(
                    "description", ""
                )
            ).strip()
            line_number = int(exception.get("lineNumber", 0) or 0)
            column_number = int(exception.get("columnNumber", 0) or 0)
            if description:
                detail = f"CDP_EVAL_EXCEPTION: {description}"
            elif text:
                detail = f"CDP_EVAL_EXCEPTION: {text}"
            if line_number or column_number:
                detail = f"{detail} @ {line_number}:{column_number}"
        raise RuntimeError(detail)
    inner = result.get("result", {})
    if not isinstance(inner, dict):
        raise RuntimeError("CDP_EVAL_INVALID")
    return str(inner.get("value", ""))


def _is_retryable_backend_error(message: str) -> bool:
    lowered = message.lower()
    return "10060" in lowered or "timeout" in lowered or "failed to read" in lowered


def _decode_backend_json(result: str) -> dict[str, object]:
    parsed = json.loads(result)
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    if not isinstance(parsed, dict):
        raise RuntimeError("chatgpt_backend_invalid_json")
    return parsed


def _normalized_no_send_evidence(parsed: dict[str, object]) -> dict[str, object]:
    raw = parsed.get("noSendEvidence", {})
    if not isinstance(raw, dict):
        evidence_keys = {
            "send_found",
            "send_enabled",
            "send_disabled",
            "send_test_id",
            "send_aria_label",
            "aria_disabled",
            "aria_busy",
            "class_name",
            "button_text",
            "pointer_events",
            "visible",
            "is_connected",
            "in_flight_marker",
            "state_transition",
            "retry_safe",
        }
        if any(key in parsed for key in evidence_keys):
            raw = parsed
        else:
            return {
                "send_found": False,
                "send_disabled": False,
                "aria_disabled": "",
                "aria_busy": "",
                "class_name": "",
                "button_text": "",
                "pointer_events": "",
                "visible": False,
                "is_connected": False,
                "in_flight_marker": False,
                "state_transition": False,
                "retry_safe": False,
            }
    normalized = cast(
        dict[str, object],
        {
            "send_found": bool(raw.get("send_found", False)),
            "send_disabled": bool(raw.get("send_disabled", False)),
            "aria_disabled": str(raw.get("aria_disabled", "")),
            "aria_busy": str(raw.get("aria_busy", "")),
            "class_name": str(raw.get("class_name", "")),
            "button_text": str(raw.get("button_text", "")),
            "pointer_events": str(raw.get("pointer_events", "")),
            "visible": bool(raw.get("visible", False)),
            "is_connected": bool(raw.get("is_connected", False)),
            "in_flight_marker": bool(raw.get("in_flight_marker", False)),
            "state_transition": bool(raw.get("state_transition", False)),
            "retry_safe": bool(raw.get("retry_safe", False)),
        },
    )
    diagnostics_keys = {
        "visibleSelectorMatches",
        "visibleChatInputEditor",
        "visibleContenteditableCount",
        "visibleProseMirrorCount",
        "inputSelectorError",
    }
    diagnostics = cast(
        dict[str, object],
        {
            key: parsed.get(key)
            for key in diagnostics_keys
            if key in parsed and parsed.get(key) is not None
        },
    )
    if diagnostics:
        normalized["no_input_diagnostics"] = diagnostics
    input_success_keys = {
        "inputSuccess",
        "inputFinalText",
        "inputPromptNormalized",
    }
    input_success_diagnostics = cast(
        dict[str, object],
        {
            key: parsed.get(key)
            for key in input_success_keys
            if key in parsed and parsed.get(key) is not None
        },
    )
    if input_success_diagnostics:
        normalized["input_success_diagnostics"] = input_success_diagnostics
    return normalized


def _submit_evidence_record(
    *,
    error: str,
    parsed: dict[str, object],
    no_send_evidence: dict[str, object],
) -> dict[str, object]:
    if bool(parsed.get("ok", False)):
        raw_submit_evidence = parsed.get("submitEvidence", {})
        submit_evidence = (
            cast(dict[str, object], raw_submit_evidence)
            if isinstance(raw_submit_evidence, dict)
            else {}
        )
        in_flight_observed = bool(submit_evidence.get("in_flight_observed", False))
        terminal_success_observed = bool(
            submit_evidence.get("terminal_success_observed", False)
        )
        classification = (
            "sent" if in_flight_observed or terminal_success_observed else "ambiguous"
        )
        classification_reason = (
            "submit_confirmed" if classification == "sent" else "submit_ui_unconfirmed"
        )
        return {
            "attempt_key": "attempt-1",
            "classification": classification,
            "classification_reason": classification_reason,
            "retry_safe_decision": False,
            "send_test_id": str(parsed.get("sendTestId", "")),
            "send_aria_label": str(parsed.get("sendAriaLabel", "")),
            "pre": submit_evidence.get("pre", {}),
            "post": submit_evidence.get("post", {}),
            "in_flight_observed": in_flight_observed,
            "terminal_success_observed": terminal_success_observed,
        }
    if error == "NO_SEND" and bool(no_send_evidence.get("retry_safe", False)):
        return {
            "attempt_key": "attempt-1",
            "classification": "not_sent",
            "classification_reason": "send_control_missing",
            "retry_safe_decision": True,
            "no_send_evidence": no_send_evidence,
        }
    return {
        "attempt_key": "attempt-1",
        "classification": "ambiguous",
        "classification_reason": error or "submit_failed",
        "retry_safe_decision": False,
        "no_send_evidence": no_send_evidence,
    }


def _resolve_agent_browser_command(command: list[str]) -> list[str]:
    if not command or command[0] != "agent-browser":
        return command
    resolved = shutil.which("agent-browser")
    if resolved:
        return [resolved, *command[1:]]
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        npm_root = Path(appdata) / "npm"
        candidates = [
            npm_root / "agent-browser.cmd",
            npm_root
            / "node_modules"
            / "agent-browser"
            / "bin"
            / "agent-browser-win32-x64.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return [str(candidate), *command[1:]]
    return command

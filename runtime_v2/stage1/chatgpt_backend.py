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
    ) -> None:
        self._port = port
        self._input_selectors = input_selectors
        self._send_selectors = send_selectors
        self._stop_selectors = stop_selectors
        self._response_selectors = response_selectors
        self._expected_url_substring = expected_url_substring
        self._expected_title_substring = expected_title_substring
        self._runner = _default_runner if command_runner is None else command_runner
        self._max_retries = 2
        self._fallback_events: list[str] = []

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
            result = self._run_eval_with_retry(_prepare_input_script(payload))
            parsed = _decode_backend_json(result)
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
                parsed = _decode_backend_json(
                    _run_raw_cdp_eval(
                        raw_target["webSocketDebuggerUrl"],
                        _prepare_input_script(payload),
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
                click_result = _decode_backend_json(
                    self._run_eval_with_retry(_click_send_script(payload))
                )
                post_state = _decode_backend_json(
                    self._run_eval_with_retry(_send_control_state_script(payload))
                )
                submit_evidence = {
                    "attempt_key": "attempt-1",
                    "classification": "sent",
                    "classification_reason": "send_button_clicked",
                    "retry_safe_decision": False,
                    "pre": state,
                    "post": post_state,
                    "in_flight_observed": bool(
                        post_state.get("in_flight_marker", False)
                    ),
                    "terminal_success_observed": bool(
                        post_state.get("in_flight_marker", False)
                    ),
                    "state_transition": bool(post_state.get("in_flight_marker", False)),
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
        raw_target = _select_page_target(self._port, self._expected_url_substring)
        self._record_fallback("eval_raw_cdp_fallback")
        return _run_raw_cdp_eval(raw_target["webSocketDebuggerUrl"], script)

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
            _select_page_target(self._port, self._expected_url_substring)
            return
        except RuntimeError:
            self._record_fallback("custom_page_select_fallback")
        generic = _select_generic_chatgpt_target(self._port)
        if generic is None:
            return
        _run_raw_cdp_method(
            generic["webSocketDebuggerUrl"],
            "Page.navigate",
            {"url": CHATGPT_LONGFORM_URL},
        )
        time.sleep(2.0)

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
            return _select_page_target(self._port, self._expected_url_substring)
        except RuntimeError:
            self._record_fallback("current_tab_http_fallback")
            generic = _select_generic_chatgpt_target(self._port)
            return {} if generic is None else generic

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
) -> dict[str, object]:
    try:
        target = _select_page_target(port, expected_url_substring)
    except RuntimeError:
        target = _select_generic_chatgpt_target(port)
        if target is None:
            raise RuntimeError("chatgpt_context_target_missing")
    _run_raw_cdp_method(
        target["webSocketDebuggerUrl"],
        "Page.navigate",
        {"url": CHATGPT_LONGFORM_URL},
    )
    time.sleep(2.0)
    _run_raw_cdp_method(
        target["webSocketDebuggerUrl"],
        "Page.reload",
        {"ignoreCache": True},
    )
    time.sleep(1.0)
    return {
        "status": "ok",
        "port": port,
        "target_url": CHATGPT_LONGFORM_URL,
        "target": target,
    }


def _prepare_input_script(payload: str) -> str:
    return (
        "(() => {"
        f"const config = {payload};"
        "const selectors = config.inputSelectors || [];"
        "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',keyCode:27,bubbles:true}));"
        "const closeSelectors=['button[aria-label=\"닫기\"]','button[aria-label=\"Close\"]','button[aria-label*=\"close\"]','button[aria-label*=\"dismiss\"]','.modal-close','[data-testid*=\"close\"]','[data-testid*=\"dismiss\"]'];"
        "for (const selector of closeSelectors) { for (const btn of Array.from(document.querySelectorAll(selector))) { try { const visible = !!btn && !!btn.isConnected && (((btn.getClientRects && btn.getClientRects().length > 0)) || btn.offsetParent !== null); if (visible) btn.click(); } catch (_) {} } }"
        "let input = null;"
        "for (const selector of selectors) { const candidate = document.querySelector(selector); const visible = !!candidate && !!candidate.isConnected && (((candidate.getClientRects && candidate.getClientRects().length > 0)) || candidate.offsetParent !== null); if (visible) { input = candidate; break; } }"
        "if (!input) { const chatInput = document.querySelector('[data-testid=\"chat-input\"]'); if (chatInput) { const editor = chatInput.querySelector('.ProseMirror, [contenteditable=\"true\"]'); const visible = !!editor && !!editor.isConnected && (((editor.getClientRects && editor.getClientRects().length > 0)) || editor.offsetParent !== null); if (visible) input = editor; } }"
        "if (!input) { const editors = Array.from(document.querySelectorAll('[contenteditable=\"true\"]')).filter((el) => el && el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null) && !el.closest('article') && !el.closest('[data-message-author-role=\"assistant\"]')); if (editors.length) input = editors[0]; }"
        "if (!input) return JSON.stringify({ok:false,error:'NO_INPUT'});"
        "if (typeof input.click === 'function') input.click();"
        "input.focus();"
        "let inputSuccess = false;"
        "const isProseMirror = !!(input.classList && (input.classList.contains('ProseMirror') || input.classList.contains('tiptap')));"
        "if (isProseMirror) {"
        "  const sel = window.getSelection(); const range = document.createRange(); range.selectNodeContents(input); sel.removeAllRanges(); sel.addRange(range);"
        "  document.execCommand('delete', false, null);"
        "  const inserted = document.execCommand('insertText', false, config.prompt);"
        "  if (!inserted) { input.innerHTML = ''; const p = document.createElement('p'); p.textContent = config.prompt; input.appendChild(p); }"
        "  input.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,data:config.prompt,inputType:'insertText'}));"
        "  input.dispatchEvent(new Event('change',{bubbles:true}));"
        "  input.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:'a'}));"
        "  const finalText = (input.innerText || input.textContent || '').trim();"
        "  inputSuccess = finalText.length > 0;"
        "} else if (input.tagName === 'TEXTAREA') {"
        "  input.value = config.prompt;"
        "  input.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,data:config.prompt,inputType:'insertText'}));"
        "  input.dispatchEvent(new Event('change',{bubbles:true}));"
        "  inputSuccess = String(input.value || '').trim().length > 0;"
        "} else {"
        "  input.innerText = config.prompt;"
        "  input.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,data:config.prompt,inputType:'insertText'}));"
        "  input.dispatchEvent(new Event('change',{bubbles:true}));"
        "  inputSuccess = String(input.innerText || input.textContent || '').trim().length > 0;"
        "}"
        "return JSON.stringify({ok:true,inputSelector: selectors.find(s => document.querySelector(s)===input) || '', inputSuccess: inputSuccess});"
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
        "const sendSelectors = config.sendSelectors || [];"
        "let send = null;"
        "for (const selector of sendSelectors) { const candidate = document.querySelector(selector); if (!candidate) continue; if (candidate.getAttribute && candidate.getAttribute('data-testid') === 'stop-button') continue; send = candidate; break; }"
        "if (!send) return JSON.stringify({ok:false,error:'NO_SEND'});"
        "['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type => send.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window})));"
        "if (typeof send.click === 'function') send.click();"
        "return JSON.stringify({ok:true,sendClicked:true,sendTestId: send.getAttribute ? (send.getAttribute('data-testid') || '') : '', sendAriaLabel: send.getAttribute ? (send.getAttribute('aria-label') || '') : ''});"
        "})()"
    )


def _response_script(payload: str) -> str:
    return (
        "(() => {"
        f"const config = {payload};"
        "const stopSelectors = config.stopSelectors || [];"
        "const sendSelectors = config.sendSelectors || [];"
        "const responseSelectors = config.responseSelectors || [];"
        "let hasStop = stopSelectors.some(selector => { const el = document.querySelector(selector); return !!(el && el.offsetParent !== null); });"
        "let hasSendButton = sendSelectors.some(selector => { const el = document.querySelector(selector); return !!(el && el.offsetParent !== null && !el.disabled); });"
        "const composerBtn = document.getElementById('composer-submit-button');"
        "if (composerBtn) { const ariaLabel = (composerBtn.getAttribute('aria-label') || '').toLowerCase(); if (!hasStop && (ariaLabel.includes('중지') || ariaLabel.includes('stop'))) hasStop = true; if (!hasSendButton && (ariaLabel.includes('전송') || ariaLabel.includes('send'))) hasSendButton = true; }"
        "let assistantBlocks = [];"
        "for (const selector of responseSelectors) { const found = Array.from(document.querySelectorAll(selector)).filter(el => !el.closest('form')); if (found.length) { assistantBlocks = found; break; } }"
        "const last = assistantBlocks.length ? assistantBlocks[assistantBlocks.length - 1] : null;"
        "const text = last ? ((last.innerText || last.textContent || '').trim()) : '';"
        "const legacyLabels = ['[Voice]','[Title]','[Title for Thumb]','[Description]','[Keywords]','[BGM]','[URL]','[Ref Img 1]','[Ref Img 2]','[Shorts Description]','[Shorts Voice]','[Shorts Clip Mapping]'];"
        "const legacyBlocks = Array.from(document.querySelectorAll('p')).map((p)=>{ const label=(p.innerText||p.textContent||'').trim(); if(!(legacyLabels.includes(label) || /^\\[Video\\d+/.test(label) || /^\\[#\\d+/.test(label))) return null; let next=p.nextElementSibling; while(next && next.tagName!=='PRE') next=next.nextElementSibling; return {label, body: next ? ((next.innerText||next.textContent||'').trim()) : ''}; }).filter(Boolean);"
        "return JSON.stringify({has_stop: hasStop, has_send_button: hasSendButton, assistant_block_count: assistantBlocks.length, assistant_text: text, legacy_blocks: legacyBlocks});"
        "})()"
    )


def _input_ready_script() -> str:
    return (
        "(() => {"
        "const interactive = document.querySelector('[data-testid=\"prompt-input-ssr-interactive\"]');"
        "const ssr = document.querySelector('[data-testid=\"chat-input-ssr\"]');"
        "const chatInput = document.querySelector('[data-testid=\"chat-input\"]');"
        "const proseMirror = document.querySelector('.ProseMirror[contenteditable=\"true\"]');"
        "const visible = (el) => !!el && !!el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null);"
        "const ready = visible(proseMirror) || visible(interactive) || (!!chatInput && !ssr);"
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
        if expected_url_substring not in url and not (
            url.startswith("https://chatgpt.com/c/")
            and expected_title_substring.lower() in title.lower()
        ):
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
    ws_url: str, method: str, params: dict[str, object]
) -> dict[str, object]:
    try:
        ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        try:
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


def _run_raw_cdp_eval(ws_url: str, script: str) -> str:
    result = _run_raw_cdp_method(
        ws_url,
        "Runtime.evaluate",
        {"expression": script, "returnByValue": True},
    )
    exception = result.get("exceptionDetails")
    if exception is not None:
        raise RuntimeError("CDP_EVAL_EXCEPTION")
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
    return {
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
    }


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
            "sent" if in_flight_observed and terminal_success_observed else "ambiguous"
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

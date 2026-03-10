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
            },
            ensure_ascii=False,
        )
        result = self._run_eval_with_retry(_submit_script(payload))
        parsed = _decode_backend_json(result)
        if not bool(parsed.get("ok", False)):
            error = str(parsed.get("error", "chatgpt_submit_failed"))
            no_send_evidence = _normalized_no_send_evidence(parsed)
            submit_evidence = _submit_evidence_record(
                error=error,
                parsed=parsed,
                no_send_evidence=no_send_evidence,
            )
            if error in {"NO_SEND", "SEND_DISABLED"} and bool(
                no_send_evidence.get("retry_safe", False)
            ):
                raw_target = _select_page_target(
                    self._port, self._expected_url_substring
                )
                parsed = _decode_backend_json(
                    _run_raw_cdp_eval(
                        raw_target["webSocketDebuggerUrl"], _submit_script(payload)
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

    def read_response_state(self) -> dict[str, object]:
        payload = json.dumps(
            {
                "stopSelectors": self._stop_selectors,
                "responseSelectors": self._response_selectors,
            },
            ensure_ascii=False,
        )
        result = self._run_eval_with_retry(_response_script(payload))
        parsed = _decode_backend_json(result)
        return {
            "has_stop": bool(parsed.get("has_stop", False)),
            "assistant_text": str(parsed.get("assistant_text", "")),
            "assistant_block_count": parsed.get("assistant_block_count", 0),
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


def _submit_script(payload: str) -> str:
    return (
        "(() => {"
        f"const config = {payload};"
        "const selectors = config.inputSelectors || [];"
        "const sendSelectors = config.sendSelectors || [];"
        "let input = null;"
        "for (const selector of selectors) { input = document.querySelector(selector); if (input) break; }"
        "if (!input) return JSON.stringify({ok:false,error:'NO_INPUT'});"
        "input.focus();"
        "if (input.classList && input.classList.contains('ProseMirror')) {"
        "  const sel = window.getSelection(); const range = document.createRange(); range.selectNodeContents(input); sel.removeAllRanges(); sel.addRange(range); document.execCommand('delete'); document.execCommand('insertText', false, config.prompt);"
        "  input.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,cancelable:true,data:config.prompt,inputType:'insertText'}));"
        "  input.textContent = config.prompt;"
        "} else if (input.tagName === 'TEXTAREA') { input.value = config.prompt; } else { input.textContent = config.prompt; }"
        "input.dispatchEvent(new InputEvent('input',{bubbles:true,data:config.prompt,inputType:'insertText'}));"
        "input.dispatchEvent(new Event('change',{bubbles:true}));"
        "input.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:'Enter',code:'Enter'}));"
        "input.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:'a'}));"
        "const snapshot = (candidate) => {"
        "  if (!candidate) return {send_found:false, send_disabled:false, aria_disabled:'', aria_busy:'', class_name:'', button_text:'', pointer_events:'', visible:false, is_connected:false, in_flight_marker:false, state_transition:false, retry_safe:true};"
        "  const className = String(candidate.className || '');"
        "  const ariaDisabled = candidate.getAttribute ? (candidate.getAttribute('aria-disabled') || '') : '';"
        "  const ariaBusy = candidate.getAttribute ? (candidate.getAttribute('aria-busy') || '') : '';"
        "  const inFlight = !!(candidate.querySelector && candidate.querySelector('[role=\"progressbar\"], .spinner, .loading')) || className.toLowerCase().includes('loading') || ariaBusy === 'true';"
        "  return {send_found:true, send_disabled:!!candidate.disabled, aria_disabled:ariaDisabled, aria_busy:ariaBusy, class_name:className, button_text:String(candidate.innerText || candidate.textContent || candidate.value || '').trim(), pointer_events:String((window.getComputedStyle && window.getComputedStyle(candidate).pointerEvents) || ''), visible:!!candidate.offsetParent, is_connected:!!candidate.isConnected, in_flight_marker:inFlight, state_transition:false, retry_safe:!candidate.disabled && !inFlight};"
        "};"
        "let send = null;"
        "for (const selector of sendSelectors) {"
        "  const candidate = document.querySelector(selector);"
        "  if (!candidate) continue;"
        "  if (candidate.getAttribute && candidate.getAttribute('data-testid') === 'stop-button') continue;"
        "  send = candidate;"
        "  break;"
        "}"
        "if (!send) return JSON.stringify({ok:false,error:'NO_SEND',noSendEvidence:snapshot(null)});"
        "if (send.disabled) return JSON.stringify({ok:false,error:'SEND_DISABLED',noSendEvidence:snapshot(send)});"
        "['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type => send.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window})));"
        "if (typeof send.click === 'function') send.click();"
        "input.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:'Enter',code:'Enter'}));"
        "input.dispatchEvent(new KeyboardEvent('keypress',{bubbles:true,key:'Enter',code:'Enter'}));"
        "input.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:'Enter',code:'Enter'}));"
        "return JSON.stringify({ok:true,inputSelector: selectors.find(s => document.querySelector(s)===input) || '', sendClicked:true, sendTestId: send.getAttribute ? (send.getAttribute('data-testid') || '') : '', sendAriaLabel: send.getAttribute ? (send.getAttribute('aria-label') || '') : ''});"
        "})()"
    )


def _response_script(payload: str) -> str:
    return (
        "(() => {"
        f"const config = {payload};"
        "const stopSelectors = config.stopSelectors || [];"
        "const responseSelectors = config.responseSelectors || [];"
        "const hasStop = stopSelectors.some(selector => { const el = document.querySelector(selector); return !!(el && el.offsetParent !== null); });"
        "let blocks = [];"
        "for (const selector of responseSelectors) { blocks = Array.from(document.querySelectorAll(selector)); if (blocks.length) break; }"
        "const assistantBlocks = blocks.filter(el => !el.closest('form'));"
        "const last = assistantBlocks.length ? assistantBlocks[assistantBlocks.length - 1] : null;"
        "const text = last ? ((last.innerText || last.textContent || '').trim()) : '';"
        "const legacyLabels = ['[Voice]','[Title]','[Title for Thumb]','[Description]','[Keywords]','[BGM]','[URL]','[Ref Img 1]','[Ref Img 2]','[Shorts Description]','[Shorts Voice]','[Shorts Clip Mapping]'];"
        "const legacyBlocks = Array.from(document.querySelectorAll('p')).map((p)=>{ const label=(p.innerText||p.textContent||'').trim(); if(!(legacyLabels.includes(label) || /^\\[Video\\d+/.test(label) || /^\\[#\\d+/.test(label))) return null; let next=p.nextElementSibling; while(next && next.tagName!=='PRE') next=next.nextElementSibling; return {label, body: next ? ((next.innerText||next.textContent||'').trim()) : ''}; }).filter(Boolean);"
        "return JSON.stringify({has_stop: hasStop, assistant_block_count: assistantBlocks.length, assistant_text: text, legacy_blocks: legacyBlocks});"
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


def _select_page_target(port: int, expected_url_substring: str) -> dict[str, str]:
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
        if expected_url_substring not in str(item.get("url", "")):
            continue
        ws_url = str(item.get("webSocketDebuggerUrl", "")).strip()
        if not ws_url:
            continue
        return {
            "webSocketDebuggerUrl": ws_url,
            "url": str(item.get("url", "")),
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

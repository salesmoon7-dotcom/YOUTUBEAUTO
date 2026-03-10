from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Protocol

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
            if error in {"NO_SEND", "SEND_DISABLED"}:
                raw_target = _select_page_target(
                    self._port, self._expected_url_substring
                )
                parsed = _decode_backend_json(
                    _run_raw_cdp_eval(
                        raw_target["webSocketDebuggerUrl"], _submit_script(payload)
                    )
                )
                if bool(parsed.get("ok", False)):
                    return parsed
            raise RuntimeError(error)
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
        return _run_raw_cdp_eval(raw_target["webSocketDebuggerUrl"], script)
        if last_error is not None:
            raise last_error
        raise RuntimeError("chatgpt_backend_failed")

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
            pass
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
            pass
        return _chatgpt_tab_index_from_http(
            self._port,
            expected_url_substring=self._expected_url_substring,
            expected_title_substring=self._expected_title_substring,
        )


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
        "let send = null;"
        "for (const selector of sendSelectors) {"
        "  const candidate = document.querySelector(selector);"
        "  if (!candidate) continue;"
        "  if (candidate.getAttribute && candidate.getAttribute('data-testid') === 'stop-button') continue;"
        "  send = candidate;"
        "  break;"
        "}"
        "if (!send) return JSON.stringify({ok:false,error:'NO_SEND'});"
        "if (send.disabled) return JSON.stringify({ok:false,error:'SEND_DISABLED'});"
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
        "return JSON.stringify({has_stop: hasStop, assistant_block_count: assistantBlocks.length, assistant_text: text});"
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

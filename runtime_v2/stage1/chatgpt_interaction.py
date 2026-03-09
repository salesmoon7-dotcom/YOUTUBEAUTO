from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

CHATGPT_INPUT_SELECTORS = [
    "#prompt-textarea",
    "div.ProseMirror[contenteditable='true']",
    "div[contenteditable='true'][id='prompt-textarea']",
    "div[contenteditable='true']",
    "textarea[name='prompt-textarea']",
    "textarea",
]

CHATGPT_SEND_SELECTORS = [
    "button[data-testid='send-button']",
    "#composer-submit-button",
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
    command_runner: Callable[[list[str], int], str] | None = None,
) -> dict[str, object]:
    runner = _default_runner if command_runner is None else command_runner
    try:
        submit_info = _submit_prompt(prompt=prompt, port=port, runner=runner)
    except RuntimeError as exc:
        return _interaction_failure(
            failure_stage="submit",
            error_code="CHATGPT_BACKEND_UNAVAILABLE",
            backend_error=str(exc),
        )
    started = time.time()
    last_text = ""
    stable_count = 0
    last_state: dict[str, object] = {}
    while time.time() - started < timeout_sec:
        try:
            state = _read_response_state(port=port, runner=runner)
        except RuntimeError as exc:
            return _interaction_failure(
                failure_stage="read",
                error_code="CHATGPT_BACKEND_UNAVAILABLE",
                backend_error=str(exc),
                submit_info=submit_info,
            )
        last_state = state
        text = str(state.get("assistant_text", "")).strip()
        has_stop = bool(state.get("has_stop", False))
        if text and not has_stop:
            if text == last_text:
                stable_count += 1
            else:
                stable_count = 0
            last_text = text
            if stable_count >= 1:
                return {
                    "status": "ok",
                    "response_text": text,
                    "submit_info": submit_info,
                    "final_state": state,
                }
        time.sleep(poll_interval_sec)
    return {
        "status": "failed",
        "error_code": "CHATGPT_RESPONSE_TIMEOUT",
        "failure_stage": "read",
        "submit_info": submit_info,
        "final_state": last_state,
    }


def _interaction_failure(
    *,
    failure_stage: str,
    error_code: str,
    backend_error: str,
    submit_info: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "status": "failed",
        "error_code": error_code,
        "failure_stage": failure_stage,
        "submit_info": {} if submit_info is None else submit_info,
        "final_state": {},
        "details": {
            "backend_error": backend_error,
        },
    }


def _submit_prompt(
    *, prompt: str, port: int, runner: Callable[[list[str], int], str]
) -> dict[str, object]:
    payload = json.dumps(
        {
            "prompt": prompt,
            "inputSelectors": CHATGPT_INPUT_SELECTORS,
            "sendSelectors": CHATGPT_SEND_SELECTORS,
        },
        ensure_ascii=False,
    )
    result = runner(
        [
            "agent-browser",
            "--cdp",
            str(port),
            "eval",
            _submit_script(payload),
        ],
        60,
    )
    parsed = json.loads(result)
    if not bool(parsed.get("ok", False)):
        raise RuntimeError(str(parsed.get("error", "chatgpt_submit_failed")))
    return parsed


def _read_response_state(
    *, port: int, runner: Callable[[list[str], int], str]
) -> dict[str, object]:
    payload = json.dumps(
        {
            "stopSelectors": CHATGPT_STOP_SELECTORS,
            "responseSelectors": CHATGPT_RESPONSE_SELECTORS,
        },
        ensure_ascii=False,
    )
    result = runner(
        [
            "agent-browser",
            "--cdp",
            str(port),
            "eval",
            _response_script(payload),
        ],
        60,
    )
    return json.loads(result)


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
        "} else if (input.tagName === 'TEXTAREA') { input.value = config.prompt; } else { input.textContent = config.prompt; }"
        "input.dispatchEvent(new InputEvent('input',{bubbles:true,data:config.prompt,inputType:'insertText'}));"
        "input.dispatchEvent(new Event('change',{bubbles:true}));"
        "input.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:'a'}));"
        "let send = null;"
        "for (const selector of sendSelectors) { send = document.querySelector(selector); if (send) break; }"
        "if (!send) return JSON.stringify({ok:false,error:'NO_SEND'});"
        "if (send.disabled) return JSON.stringify({ok:false,error:'SEND_DISABLED'});"
        "send.click();"
        "return JSON.stringify({ok:true,inputSelector: selectors.find(s => document.querySelector(s)===input) || '', sendClicked:true});"
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
    completed = subprocess.run(
        resolved,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_sec,
        check=False,
    )
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or str(completed.returncode)
        )
        raise RuntimeError(detail)
    return completed.stdout


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

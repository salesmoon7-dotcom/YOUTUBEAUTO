from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Protocol


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
        command_runner: Callable[[list[str], int], str] | None = None,
    ) -> None:
        self._port = port
        self._input_selectors = input_selectors
        self._send_selectors = send_selectors
        self._stop_selectors = stop_selectors
        self._response_selectors = response_selectors
        self._runner = _default_runner if command_runner is None else command_runner

    def submit_prompt(self, prompt: str) -> dict[str, object]:
        payload = json.dumps(
            {
                "prompt": prompt,
                "inputSelectors": self._input_selectors,
                "sendSelectors": self._send_selectors,
            },
            ensure_ascii=False,
        )
        result = self._runner(
            [
                "agent-browser",
                "--cdp",
                str(self._port),
                "eval",
                _submit_script(payload),
            ],
            60,
        )
        parsed = json.loads(result)
        if not bool(parsed.get("ok", False)):
            raise RuntimeError(str(parsed.get("error", "chatgpt_submit_failed")))
        return parsed

    def read_response_state(self) -> dict[str, object]:
        payload = json.dumps(
            {
                "stopSelectors": self._stop_selectors,
                "responseSelectors": self._response_selectors,
            },
            ensure_ascii=False,
        )
        result = self._runner(
            [
                "agent-browser",
                "--cdp",
                str(self._port),
                "eval",
                _response_script(payload),
            ],
            60,
        )
        parsed = json.loads(result)
        return {
            "has_stop": bool(parsed.get("has_stop", False)),
            "assistant_text": str(parsed.get("assistant_text", "")),
            "assistant_block_count": parsed.get("assistant_block_count", 0),
        }


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

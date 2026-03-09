from __future__ import annotations

import json
import time
import urllib.request
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
    session_probe: Callable[[int], dict[str, object]] | None = None,
    backend: ChatGPTBackend | None = None,
) -> dict[str, object]:
    probe = _default_session_probe if session_probe is None else session_probe
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
    try:
        submit_info = interaction_backend.submit_prompt(prompt)
    except RuntimeError as exc:
        return _interaction_failure(
            failure_stage="submit",
            error_code="CHATGPT_BACKEND_UNAVAILABLE",
            backend_error=str(exc),
            final_state=probe(port),
        )
    started = time.time()
    last_text = ""
    stable_count = 0
    last_state: dict[str, object] = {}
    while time.time() - started < timeout_sec:
        try:
            state = interaction_backend.read_response_state()
        except RuntimeError as exc:
            return _interaction_failure(
                failure_stage="read",
                error_code="CHATGPT_BACKEND_UNAVAILABLE",
                backend_error=str(exc),
                submit_info=submit_info,
                final_state=probe(port),
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
    final_state: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "status": "failed",
        "error_code": error_code,
        "failure_stage": failure_stage,
        "submit_info": {} if submit_info is None else submit_info,
        "final_state": {} if final_state is None else final_state,
        "details": {
            "backend_error": backend_error,
            "backend_fallback": "raw_cdp_http",
        },
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

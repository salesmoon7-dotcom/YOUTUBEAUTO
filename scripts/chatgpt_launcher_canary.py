from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from runtime_v2.browser.manager import (
    BrowserManager,
    BrowserSession,
    open_browser_for_login,
)
from runtime_v2.config import browser_session_root


def cdp_ok(port: int) -> bool:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/version", timeout=5
    ) as response:
        payload = json.loads(response.read().decode("utf-8", "ignore"))
    return isinstance(payload, dict) and bool(payload.get("webSocketDebuggerUrl"))


def main() -> int:
    port = 9222
    profile = (browser_session_root() / "chatgpt-canary").resolve()
    manager = BrowserManager(
        sessions=[
            BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="canary",
                port=port,
                profile_dir=str(profile),
                status="stopped",
                browser_family="chrome",
            )
        ]
    )
    payload = open_browser_for_login("chatgpt", manager=manager)
    payload["cdp_ok"] = cdp_ok(port)
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if bool(payload.get("launched")) and bool(payload.get("cdp_ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

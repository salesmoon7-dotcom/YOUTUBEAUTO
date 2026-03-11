from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime_v2.browser.manager import (
    BrowserManager,
    BrowserSession,
    open_browser_for_login,
)
from runtime_v2.config import browser_session_root


def cdp_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=5
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except OSError:
        return False
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
    payload["cdp_ok"] = cdp_ok(port) if bool(payload.get("launched")) else False
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if bool(payload.get("launched")) and bool(payload.get("cdp_ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

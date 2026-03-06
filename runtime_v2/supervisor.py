from __future__ import annotations

from runtime_v2.browser.manager import BrowserManager
from runtime_v2.gpu.lease import LeaseStore


def run_once(owner: str) -> dict[str, str]:
    lease_store = LeaseStore()
    lease = lease_store.acquire("gpu-global", owner)
    if lease is None:
        return {"status": "failed", "code": "GPU_LEASE_BUSY"}

    browser = BrowserManager()
    browser.start()
    healthy = browser.is_healthy()
    lease_store.release("gpu-global", owner)
    return {"status": "ok" if healthy else "failed"}

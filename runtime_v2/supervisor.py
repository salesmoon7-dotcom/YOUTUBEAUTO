from __future__ import annotations

from time import time

from runtime_v2.browser.manager import BrowserManager
from runtime_v2.gpu.lease import LeaseStore
from runtime_v2.gpt.floor import GptEndpoint, ok_count


def run_once(
    owner: str,
    lease_store: LeaseStore | None = None,
    force_browser_fail: bool = False,
    force_gpt_fail: bool = False,
) -> dict[str, object]:
    store = lease_store or LeaseStore()
    lease = store.acquire("gpu-global", owner)
    if lease is None:
        return {"status": "failed", "code": "GPU_LEASE_BUSY"}

    try:
        browser = BrowserManager()
        browser.start()
        healthy = browser.is_healthy() and (not force_browser_fail)
        if not healthy:
            return {"status": "failed", "code": "BROWSER_UNHEALTHY", "gpt_ok_count": 0}

        endpoint_status = "FAILED" if force_gpt_fail else "OK"
        endpoints = [
            GptEndpoint(name="default", status=endpoint_status, last_seen_at=time())
        ]
        floor_count = ok_count(endpoints, fresh_sec=3600)
        floor_ok = floor_count >= 1
        if not floor_ok:
            return {
                "status": "failed",
                "code": "GPT_FLOOR_FAIL",
                "gpt_ok_count": floor_count,
            }

        return {"status": "ok", "code": "OK", "gpt_ok_count": floor_count}
    finally:
        store.release("gpu-global", owner)


def run_selftest(owner: str) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    store = LeaseStore()

    held = store.acquire("gpu-global", owner="holder")
    blocked = run_once(owner=owner, lease_store=store)
    checks.append(
        {
            "name": "gpu_lease_contention",
            "pass": held is not None and blocked.get("code") == "GPU_LEASE_BUSY",
            "observed": blocked,
        }
    )
    if held is not None:
        store.release("gpu-global", "holder")

    after_release = run_once(owner=owner, lease_store=store)
    checks.append(
        {
            "name": "lease_release_then_run",
            "pass": after_release.get("status") == "ok",
            "observed": after_release,
        }
    )

    browser_fail = run_once(owner=owner, lease_store=store, force_browser_fail=True)
    checks.append(
        {
            "name": "browser_health_fail_path",
            "pass": browser_fail.get("code") == "BROWSER_UNHEALTHY",
            "observed": browser_fail,
        }
    )

    floor_fail = run_once(owner=owner, lease_store=store, force_gpt_fail=True)
    checks.append(
        {
            "name": "gpt_floor_fail_path",
            "pass": floor_fail.get("code") == "GPT_FLOOR_FAIL",
            "observed": floor_fail,
        }
    )

    passed = all(bool(check["pass"]) for check in checks)
    return {
        "status": "ok" if passed else "failed",
        "code": "OK" if passed else "SELFTEST_FAIL",
        "checks": checks,
    }

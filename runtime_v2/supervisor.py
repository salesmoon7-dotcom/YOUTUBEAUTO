from __future__ import annotations

from collections.abc import Callable
import threading
from time import time
from typing import cast

from runtime_v2.browser.manager import BrowserManager
from runtime_v2.browser.supervisor import BrowserSupervisor
from runtime_v2.config import (
    GpuWorkload,
    RuntimeConfig,
    WorkloadName,
    required_browser_services,
    workload_requires_browser_health,
    workload_requires_gpt_floor,
    workload_requires_gpu_lease,
)
from runtime_v2.gpu.lease import (
    Lease,
    LeaseStore,
    build_gpu_health_payload,
    lease_key_for_workload,
    lease_store_for_workload,
    write_gpu_health_payload,
)
from runtime_v2.gpt.floor import (
    GptEndpoint,
    build_gpt_status_payload,
    load_gpt_status,
    ok_count,
    write_gpt_status,
)
from runtime_v2.worker_registry import stalled_workloads


WorkerRunner = Callable[[], dict[str, object]]


def _runtime_gpt_endpoints(
    config: RuntimeConfig,
    *,
    force_gpt_fail: bool,
    allow_default_ok_status: bool = True,
) -> list[GptEndpoint]:
    loaded_status = load_gpt_status(config.gpt_status_file)
    if loaded_status is None:
        return []
    loaded_endpoints_raw: object = loaded_status.get("endpoints", [])
    endpoints: list[GptEndpoint] = []
    if isinstance(loaded_endpoints_raw, list):
        raw_endpoints = cast(list[object], loaded_endpoints_raw)
        for entry in raw_endpoints:
            if not isinstance(entry, dict):
                continue
            typed_entry = cast(dict[object, object], entry)
            status = (
                "FAILED" if force_gpt_fail else str(typed_entry.get("status", "FAILED"))
            )
            last_seen_raw = typed_entry.get("last_seen_at", time())
            last_seen_at = (
                float(last_seen_raw)
                if isinstance(last_seen_raw, (int, float, str))
                else time()
            )
            endpoints.append(
                GptEndpoint(
                    name=str(typed_entry.get("name", "default")),
                    status=status,
                    last_seen_at=last_seen_at,
                )
            )
    if endpoints:
        return endpoints
    if not allow_default_ok_status or force_gpt_fail:
        return [GptEndpoint(name="default", status="FAILED", last_seen_at=time())]
    return []


def _required_browser_summary(
    browser_runtime: dict[str, object], required_services: tuple[str, ...]
) -> dict[str, object]:
    if not required_services:
        return {"all_healthy": True, "unhealthy_services": [], "blocked_services": []}
    sessions = _as_browser_sessions(browser_runtime.get("sessions"))
    unhealthy: list[str] = []
    blocked: list[str] = []
    for service in required_services:
        matched = next(
            (entry for entry in sessions if str(entry.get("service", "")) == service),
            None,
        )
        if matched is None or not bool(matched.get("healthy", False)):
            unhealthy.append(service)
            status = "" if matched is None else str(matched.get("status", ""))
            if status in {"login_required", "busy_lock", "unknown_lock"}:
                blocked.append(service)
    return {
        "all_healthy": len(unhealthy) == 0,
        "unhealthy_services": unhealthy,
        "blocked_services": blocked,
    }


def run_gated(
    owner: str,
    execute: WorkerRunner,
    *,
    lease_store: LeaseStore | None = None,
    force_browser_fail: bool = False,
    force_gpt_fail: bool = False,
    require_browser_healthy: bool = True,
    run_id: str = "unknown",
    config: RuntimeConfig | None = None,
    workload: WorkloadName = "qwen3_tts",
    allow_runtime_side_effects: bool = True,
) -> dict[str, object]:
    return run_once(
        owner=owner,
        lease_store=lease_store,
        force_browser_fail=force_browser_fail,
        force_gpt_fail=force_gpt_fail,
        require_browser_healthy=require_browser_healthy,
        run_id=run_id,
        config=config,
        workload=workload,
        worker_runner=execute,
        allow_runtime_side_effects=allow_runtime_side_effects,
    )


def run_once(
    owner: str,
    lease_store: LeaseStore | None = None,
    force_browser_fail: bool = False,
    force_gpt_fail: bool = False,
    require_browser_healthy: bool = True,
    run_id: str = "unknown",
    config: RuntimeConfig | None = None,
    workload: WorkloadName = "qwen3_tts",
    worker_runner: WorkerRunner | None = None,
    allow_runtime_side_effects: bool = True,
) -> dict[str, object]:
    runtime_config = config or RuntimeConfig()
    browser_runtime: dict[str, object]
    if allow_runtime_side_effects:
        browser = BrowserManager()
        browser.start()
        browser_supervisor = BrowserSupervisor(browser)
        tick_browser = cast(Callable[..., dict[str, object]], browser_supervisor.tick)
        browser_runtime = tick_browser(
            registry_file=runtime_config.browser_registry_file,
            health_file=runtime_config.browser_health_file,
            events_file=runtime_config.control_plane_events_file,
            run_id=run_id,
            force_unhealthy_service="chatgpt" if force_browser_fail else None,
            recover_unhealthy=not force_browser_fail,
            restart_threshold=1,
            cooldown_sec=0,
        )
    else:
        browser_runtime = cast(
            dict[str, object],
            {
                "run_id": run_id,
                "runtime": "runtime_v2",
                "sessions": [],
                "side_effects_skipped": True,
            },
        )
    browser_sessions = _as_browser_sessions(browser_runtime.get("sessions"))
    browser_summary = _required_browser_summary(
        browser_runtime, required_browser_services(workload)
    )
    lease_key = f"lock:{workload}"
    gpu_workload: GpuWorkload | None = None
    if workload_requires_gpu_lease(workload):
        gpu_workload = cast(GpuWorkload, workload)
    store = (
        None
        if gpu_workload is None
        else (lease_store or lease_store_for_workload(runtime_config, gpu_workload))
    )
    lease = None
    if gpu_workload is not None:
        lease_key = lease_key_for_workload(gpu_workload)
        assert store is not None
        lease = store.acquire(
            lease_key,
            owner,
            ttl_sec=runtime_config.lease_ttl_sec,
            run_id=run_id,
        )
        if lease is None:
            snapshot = store.snapshot(lease_key)
            _persist_gpu_health_runtime_state(
                runtime_config, gpu_workload, lease_key, snapshot, event="lock_busy"
            )
            return {
                "status": "failed",
                "code": "GPU_LEASE_BUSY",
                "workload": workload,
                "lock_key": lease_key,
                "browser": browser_runtime,
                "browser_sessions": browser_sessions,
                "lease": snapshot.to_dict() if snapshot is not None else None,
            }

    try:
        if gpu_workload is not None and lease is not None:
            _persist_gpu_health_runtime_state(
                runtime_config, gpu_workload, lease_key, lease, event="lock_acquire"
            )
        if (
            require_browser_healthy
            and workload_requires_browser_health(workload)
            and not bool(browser_summary.get("all_healthy", False))
        ):
            blocked_services = cast(
                list[object], browser_summary.get("blocked_services", [])
            )
            blocked = [str(service) for service in blocked_services]
            if blocked:
                return {
                    "status": "blocked",
                    "code": "BROWSER_BLOCKED",
                    "gpt_ok_count": 0,
                    "workload": workload,
                    "lock_key": lease_key,
                    "browser": browser_runtime,
                    "browser_sessions": browser_sessions,
                    "worker_result": {
                        "status": "failed",
                        "stage": "runtime_preflight",
                        "error_code": "BROWSER_BLOCKED",
                        "retryable": True,
                        "next_jobs": [],
                        "completion": {"state": "blocked", "final_output": False},
                        "details": {"blocked_services": blocked},
                    },
                }
            return {
                "status": "failed",
                "code": "BROWSER_UNHEALTHY",
                "gpt_ok_count": 0,
                "workload": workload,
                "lock_key": lease_key,
                "browser": browser_runtime,
                "browser_sessions": browser_sessions,
                "worker_result": {
                    "status": "failed",
                    "stage": "runtime_preflight",
                    "error_code": "BROWSER_UNHEALTHY",
                    "retryable": True,
                    "next_jobs": [],
                    "completion": {"state": "failed", "final_output": False},
                },
            }

        endpoints = _runtime_gpt_endpoints(
            runtime_config,
            force_gpt_fail=force_gpt_fail,
            allow_default_ok_status=allow_runtime_side_effects,
        )
        gpt_status = _persist_gpt_runtime_state(endpoints, runtime_config)
        floor_count = ok_count(endpoints)
        floor_ok = floor_count >= 1
        lease_payload = None if lease is None else lease.to_dict()
        if workload_requires_gpt_floor(workload) and not floor_ok:
            return {
                "status": "failed",
                "code": "GPT_FLOOR_FAIL",
                "gpt_ok_count": floor_count,
                "gpt_status": gpt_status,
                "workload": workload,
                "lock_key": lease_key,
                "browser": browser_runtime,
                "browser_sessions": browser_sessions,
                "lease": lease_payload,
            }

        runtime_result: dict[str, object] = {
            "status": "ok",
            "code": "OK",
            "gpt_ok_count": floor_count,
            "gpt_status": gpt_status,
            "workload": workload,
            "lock_key": lease_key,
            "browser": browser_runtime,
            "browser_sessions": browser_sessions,
            "lease": lease_payload,
        }
        runtime_result["worker_stalls"] = stalled_workloads(
            runtime_config.worker_registry_file,
            now_ts=time(),
            timeout_sec=runtime_config.progress_stall_timeout_sec,
        )
        if worker_runner is None:
            return runtime_result
        if gpu_workload is not None and store is not None and lease is not None:
            worker_result, lease = _run_worker_with_lease_heartbeat(
                store,
                lease_key,
                lease,
                owner=owner,
                workload=gpu_workload,
                config=runtime_config,
                worker_runner=worker_runner,
            )
        else:
            worker_result = worker_runner()
        runtime_result["worker_result"] = worker_result
        if str(worker_result.get("error_code", "")) == "gpu_lease_renew_failed":
            runtime_result["status"] = "failed"
            runtime_result["code"] = "GPU_LEASE_RENEW_FAILED"
        return runtime_result
    finally:
        if gpu_workload is not None and store is not None and lease is not None:
            _persist_gpu_health_runtime_state(
                runtime_config, gpu_workload, lease_key, lease, event="lock_release"
            )
            _ = store.release(lease_key, owner, token=lease.token)


def _run_worker_with_lease_heartbeat(
    store: LeaseStore,
    lease_key: str,
    lease: Lease,
    *,
    owner: str,
    workload: GpuWorkload,
    config: RuntimeConfig,
    worker_runner: WorkerRunner,
) -> tuple[dict[str, object], Lease]:
    result_box: dict[str, dict[str, object]] = {}
    error_box: dict[str, BaseException] = {}
    done = threading.Event()

    def _target() -> None:
        try:
            result_box["worker_result"] = worker_runner()
        except BaseException as exc:
            error_box["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(
        target=_target, name=f"runtime_v2-{workload}-{lease.run_id}", daemon=True
    )
    thread.start()
    renew_interval = max(1.0, float(config.renew_interval_sec))
    current_lease = lease
    renew_failed = False

    while not done.wait(timeout=renew_interval):
        renewed = store.renew(
            lease_key,
            owner=owner,
            token=current_lease.token,
            ttl_sec=config.lease_ttl_sec,
        )
        if renewed is None:
            renew_failed = True
            _persist_gpu_health_runtime_state(
                config, workload, lease_key, current_lease, event="renew_failed"
            )
            break
        current_lease = renewed

    thread.join()
    if "error" in error_box:
        raise error_box["error"]
    if renew_failed:
        return {
            "status": "failed",
            "stage": "lease_heartbeat",
            "error_code": "gpu_lease_renew_failed",
            "retryable": True,
            "details": {
                "workload": workload,
                "lock_key": lease_key,
            },
            "next_jobs": [],
            "completion": {
                "state": "blocked",
                "final_output": False,
            },
        }, current_lease
    return result_box.get(
        "worker_result",
        {
            "status": "failed",
            "stage": "worker_missing_result",
            "error_code": "missing_worker_result",
            "retryable": True,
            "next_jobs": [],
            "completion": {
                "state": "blocked",
                "final_output": False,
            },
        },
    ), current_lease


def _as_browser_sessions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    raw_items = cast(list[object], value)
    sessions: list[dict[str, object]] = []
    for raw_item in raw_items:
        if isinstance(raw_item, dict):
            item = cast(dict[object, object], raw_item)
            session: dict[str, object] = {}
            for raw_key in item:
                session[str(raw_key)] = item[raw_key]
            sessions.append(session)
    return sessions


def _persist_gpt_runtime_state(
    endpoints: list[GptEndpoint],
    config: RuntimeConfig,
) -> dict[str, object]:
    previous_status = load_gpt_status(config.gpt_status_file)
    payload = build_gpt_status_payload(
        endpoints,
        min_ok=config.gpt_floor_min_ok,
        breach_sec=config.gpt_breach_sec,
        previous_status=previous_status,
        cooldown_sec=config.gpt_spawn_cooldown_sec,
    )
    _ = write_gpt_status(payload, config.gpt_status_file)
    return payload


def _persist_gpu_health_runtime_state(
    config: RuntimeConfig,
    workload: GpuWorkload,
    lock_key: str,
    lease: Lease | None,
    event: str,
) -> None:
    payload = build_gpu_health_payload(workload, lock_key, lease, event)
    _ = write_gpu_health_payload(payload, config.lease_file)


def run_selftest(
    owner: str,
    run_id: str = "unknown",
    config: RuntimeConfig | None = None,
    inject_browser_fail: bool = False,
    inject_gpt_fail: bool = False,
    workload: GpuWorkload = "qwen3_tts",
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    runtime_config = config or RuntimeConfig()
    lease_key = lease_key_for_workload(workload)
    store = lease_store_for_workload(runtime_config, workload)

    held = store.acquire(lease_key, owner="holder", run_id=f"{run_id}-holder")
    blocked = run_once(
        owner=owner,
        lease_store=store,
        require_browser_healthy=False,
        run_id=run_id,
        config=runtime_config,
        workload=workload,
    )
    checks.append(
        {
            "name": "gpu_lease_contention",
            "pass": held is not None and blocked.get("code") == "GPU_LEASE_BUSY",
            "observed": blocked,
        }
    )
    if held is not None:
        _ = store.release(lease_key, "holder", token=held.token)

    after_release = run_once(
        owner=owner,
        lease_store=store,
        require_browser_healthy=False,
        run_id=run_id,
        config=runtime_config,
        workload=workload,
    )
    checks.append(
        {
            "name": "lease_release_then_run",
            "pass": after_release.get("code") == "OK",
            "observed": after_release,
        }
    )

    browser_fail = run_once(
        owner=owner,
        lease_store=store,
        force_browser_fail=True,
        run_id=run_id,
        config=runtime_config,
        workload="chatgpt",
    )
    checks.append(
        {
            "name": "browser_health_fail_path",
            "pass": browser_fail.get("code") == "BROWSER_UNHEALTHY",
            "observed": browser_fail,
        }
    )

    floor_fail = run_once(
        owner=owner,
        lease_store=store,
        force_gpt_fail=True,
        require_browser_healthy=False,
        run_id=run_id,
        config=runtime_config,
        workload="chatgpt",
    )
    checks.append(
        {
            "name": "gpt_floor_fail_path",
            "pass": floor_fail.get("code") == "GPT_FLOOR_FAIL",
            "observed": floor_fail,
        }
    )

    if inject_browser_fail:
        checks.append(
            {
                "name": "injected_browser_fail",
                "pass": browser_fail.get("code") == "BROWSER_UNHEALTHY",
                "observed": browser_fail,
            }
        )

    if inject_gpt_fail:
        checks.append(
            {
                "name": "injected_gpt_fail",
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

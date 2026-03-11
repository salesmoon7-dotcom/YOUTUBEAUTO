from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import os
from pathlib import Path
from typing import Literal


GpuWorkload = Literal["qwen3_tts", "rvc", "kenburns"]
BrowserWorkload = Literal[
    "chatgpt", "genspark", "seaart", "geminigen", "canva", "agent_browser_verify"
]
LocalWorkload = Literal["render", "dev_plan", "dev_implement", "dev_replan"]
WorkloadName = Literal[
    "qwen3_tts",
    "rvc",
    "kenburns",
    "chatgpt",
    "genspark",
    "seaart",
    "geminigen",
    "canva",
    "agent_browser_verify",
    "dev_plan",
    "dev_implement",
    "dev_replan",
    "render",
]
WorkloadKind = Literal["gpu", "browser", "local"]

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


WORKLOAD_KINDS: dict[WorkloadName, WorkloadKind] = {
    "qwen3_tts": "gpu",
    "rvc": "gpu",
    "kenburns": "gpu",
    "chatgpt": "browser",
    "genspark": "browser",
    "seaart": "browser",
    "geminigen": "browser",
    "canva": "browser",
    "agent_browser_verify": "browser",
    "dev_plan": "local",
    "dev_implement": "local",
    "dev_replan": "local",
    "render": "local",
}

WORKLOAD_BROWSER_SERVICES: dict[WorkloadName, tuple[str, ...]] = {
    "qwen3_tts": (),
    "rvc": (),
    "kenburns": (),
    "chatgpt": ("chatgpt",),
    "genspark": ("genspark",),
    "seaart": ("seaart",),
    "geminigen": ("geminigen",),
    "canva": ("canva",),
    "agent_browser_verify": (),
    "dev_plan": (),
    "dev_implement": (),
    "dev_replan": (),
    "render": (),
}


def workload_kind(workload: WorkloadName) -> WorkloadKind:
    return WORKLOAD_KINDS[workload]


def workload_requires_gpu_lease(workload: WorkloadName) -> bool:
    return workload_kind(workload) == "gpu"


def workload_requires_browser_health(workload: WorkloadName) -> bool:
    return workload_kind(workload) == "browser"


def workload_requires_gpt_floor(workload: WorkloadName) -> bool:
    return workload in {"chatgpt"}


def required_browser_services(workload: WorkloadName) -> tuple[str, ...]:
    return WORKLOAD_BROWSER_SERVICES[workload]


def allowed_workloads() -> tuple[WorkloadName, ...]:
    return tuple(WORKLOAD_KINDS.keys())


def external_runtime_root() -> Path:
    override = os.environ.get("RUNTIME_V2_EXTERNAL_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    if WORKSPACE_ROOT.drive:
        return Path(f"{WORKSPACE_ROOT.drive}\\YOUTUBEAUTO_RUNTIME").resolve()
    return (WORKSPACE_ROOT.parent / "YOUTUBEAUTO_RUNTIME").resolve()


def browser_session_root() -> Path:
    override = os.environ.get("RUNTIME_V2_SESSION_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return (external_runtime_root() / "sessions").resolve()


def probe_runtime_root() -> Path:
    override = os.environ.get("RUNTIME_V2_PROBE_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return (external_runtime_root() / "probe").resolve()


def runtime_scratch_root() -> Path:
    override = os.environ.get("RUNTIME_V2_SCRATCH_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return (external_runtime_root() / "scratch").resolve()


@dataclass(slots=True)
class RuntimeConfig:
    lease_ttl_sec: int = 180
    renew_interval_sec: int = 30
    lock_mutex_stale_sec: int = 30
    gpt_floor_min_ok: int = 1
    gpt_breach_sec: int = 120
    gpt_spawn_cooldown_sec: int = 300
    gpt_spawn_hourly_limit: int = 6
    max_retry_attempts: int = 3
    circuit_breaker_threshold: int = 5
    running_stale_sec: int = 300
    lease_file: Path = Path("system/runtime_v2/health/gpu_scheduler_health.json")
    lock_root: Path = Path("system/runtime_v2/locks")
    gui_status_file: Path = Path("system/runtime_v2/health/gui_status.json")
    browser_health_file: Path = Path("system/runtime_v2/health/browser_health.json")
    browser_registry_file: Path = Path(
        "system/runtime_v2/health/browser_session_registry.json"
    )
    gpt_status_file: Path = Path("system/runtime_v2/health/gpt_status.json")
    control_plane_events_file: Path = Path(
        "system/runtime_v2/evidence/control_plane_events.jsonl"
    )
    queue_store_file: Path = Path("system/runtime_v2/state/job_queue.json")
    feeder_state_file: Path = Path("system/runtime_v2/state/feeder_state.json")
    artifact_root: Path = Path("system/runtime_v2/artifacts")
    input_root: Path = Path("system/runtime_v2/inbox")
    result_router_file: Path = Path("system/runtime_v2/evidence/result.json")
    latest_active_run_file: Path = Path("system/runtime_v2/latest_active_run.json")
    latest_completed_run_file: Path = Path(
        "system/runtime_v2/latest_completed_run.json"
    )
    failure_summary_file: Path = Path("system/runtime_v2/evidence/failure_summary.json")
    debug_log_root: Path = Path("system/runtime_v2/logs")
    worker_registry_file: Path = Path("system/runtime_v2/health/worker_registry.json")
    stable_file_age_sec: int = 3
    progress_stall_timeout_sec: int = 120
    callback_timeout_sec: float = 5.0
    callback_max_attempts: int = 3
    callback_backoff_sec: float = 0.5
    blocked_backoff_sec: float = 30.0
    allow_mock_chain: bool = False

    def replace(self, **changes: object) -> "RuntimeConfig":
        return dataclass_replace(self, **changes)

    @classmethod
    def from_root(cls, root: Path) -> "RuntimeConfig":
        resolved_root = root.resolve()
        return cls(
            lease_file=resolved_root / "health" / "gpu_scheduler_health.json",
            lock_root=resolved_root / "locks",
            gui_status_file=resolved_root / "health" / "gui_status.json",
            browser_health_file=resolved_root / "health" / "browser_health.json",
            browser_registry_file=resolved_root
            / "health"
            / "browser_session_registry.json",
            gpt_status_file=resolved_root / "health" / "gpt_status.json",
            control_plane_events_file=resolved_root
            / "evidence"
            / "control_plane_events.jsonl",
            queue_store_file=resolved_root / "state" / "job_queue.json",
            feeder_state_file=resolved_root / "state" / "feeder_state.json",
            artifact_root=resolved_root / "artifacts",
            input_root=resolved_root / "inbox",
            result_router_file=resolved_root / "evidence" / "result.json",
            latest_active_run_file=resolved_root / "latest_active_run.json",
            latest_completed_run_file=resolved_root / "latest_completed_run.json",
            failure_summary_file=resolved_root / "evidence" / "failure_summary.json",
            debug_log_root=resolved_root / "logs",
            worker_registry_file=resolved_root / "health" / "worker_registry.json",
        )

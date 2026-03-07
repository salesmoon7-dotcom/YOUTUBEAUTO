from __future__ import annotations

from runtime_v2.config import GpuWorkload, RuntimeConfig
from runtime_v2.supervisor import run_once


def run_gpu_preflight(owner: str, workload: GpuWorkload, config: RuntimeConfig | None = None) -> dict[str, object]:
    return run_once(owner=owner, workload=workload, config=config)


def run_gpu_workload(owner: str, workload: GpuWorkload, config: RuntimeConfig | None = None) -> dict[str, object]:
    return run_gpu_preflight(owner=owner, workload=workload, config=config)

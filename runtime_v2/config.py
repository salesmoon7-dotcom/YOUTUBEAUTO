from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RuntimeConfig:
    lease_key: str = "gpu-global"
    lease_ttl_sec: int = 180
    renew_interval_sec: int = 30
    gpt_floor_min_ok: int = 1
    gpt_breach_sec: int = 120

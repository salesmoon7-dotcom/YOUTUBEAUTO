from __future__ import annotations

from runtime_v2.supervisor import run_once


def run_control_loop_once(owner: str) -> dict[str, str]:
    return run_once(owner)

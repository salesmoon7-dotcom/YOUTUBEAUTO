from __future__ import annotations


def build_gui_status_payload(status: dict[str, str]) -> dict[str, str]:
    """Local GUI payload contract for on-machine dashboard."""
    return {
        "execution_env": "local_gui",
        "runtime": "runtime_v2",
        "status": status,
    }

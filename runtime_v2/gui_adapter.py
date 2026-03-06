from __future__ import annotations


def build_gui_status_payload(
    status: dict[str, object],
    run_id: str,
    mode: str,
    stage: str,
    exit_code: int,
) -> dict[str, object]:
    """Local GUI payload contract for on-machine dashboard."""
    return {
        "schema_version": "1.0",
        "execution_env": "local_gui",
        "runtime": "runtime_v2",
        "run_id": run_id,
        "mode": mode,
        "stage": stage,
        "exit_code": exit_code,
        "status": status,
    }

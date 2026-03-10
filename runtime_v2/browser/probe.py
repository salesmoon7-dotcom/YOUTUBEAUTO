from __future__ import annotations

from typing import cast


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return 0


def summarize_browser_health(sessions: list[dict[str, object]]) -> dict[str, object]:
    blocked_statuses = {
        "login_required",
        "busy_lock",
        "unknown_lock",
        "restart_exhausted",
    }
    unhealthy_services = [
        str(session.get("service", "unknown"))
        for session in sessions
        if not bool(session.get("healthy", False))
    ]
    blocked_services = [
        str(session.get("service", "unknown"))
        for session in sessions
        if str(session.get("status", "")) in blocked_statuses
    ]
    group_health: dict[str, dict[str, object]] = {}
    for session in sessions:
        group = str(session.get("group", "browser_pool"))
        healthy = bool(session.get("healthy", False))
        if group not in group_health:
            group_health[group] = {"total": 0, "healthy": 0, "unhealthy_services": []}
        group_summary = group_health[group]
        total_value = group_summary["total"]
        group_summary["total"] = _to_int(total_value) + 1
        if healthy:
            healthy_value = group_summary["healthy"]
            group_summary["healthy"] = _to_int(healthy_value) + 1
        else:
            unhealthy_list = group_summary["unhealthy_services"]
            if isinstance(unhealthy_list, list):
                cast(list[str], unhealthy_list).append(
                    str(session.get("service", "unknown"))
                )
    return {
        "total": len(sessions),
        "healthy": len(sessions) - len(unhealthy_services),
        "unhealthy_services": unhealthy_services,
        "blocked_services": blocked_services,
        "groups": group_health,
        "all_healthy": len(unhealthy_services) == 0,
    }

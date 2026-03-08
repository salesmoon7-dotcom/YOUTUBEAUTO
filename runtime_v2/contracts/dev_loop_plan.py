from __future__ import annotations

from typing import cast


REQUIRED_DEV_LOOP_FIELDS = (
    "goal",
    "tasks",
    "verification",
    "browser_checks",
    "replan_on_failure",
)


def parse_dev_loop_plan(payload: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    goal = str(payload.get("goal", "")).strip()
    if not goal:
        raise ValueError("missing_goal")
    normalized["goal"] = goal
    for field_name in ("tasks", "verification", "browser_checks"):
        raw_value = payload.get(field_name)
        if not isinstance(raw_value, list) or not raw_value:
            raise ValueError(f"missing_{field_name}")
        normalized[field_name] = list(cast(list[object], raw_value))
    if "replan_on_failure" not in payload:
        raise ValueError("missing_replan_on_failure")
    normalized["replan_on_failure"] = bool(payload.get("replan_on_failure", False))
    if "replan_payload" in payload and isinstance(payload.get("replan_payload"), dict):
        normalized["replan_payload"] = dict(
            cast(dict[str, object], payload["replan_payload"])
        )
    return normalized

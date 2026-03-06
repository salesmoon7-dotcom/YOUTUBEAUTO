from __future__ import annotations

import json
from time import time
from typing import Any


def now_ts() -> float:
    return round(time(), 3)


def emit_event(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=True)


def final_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=True)


def validate_contract(obj: dict[str, Any]) -> tuple[bool, list[str]]:
    required = ["run_id", "event", "ts"]
    missing = [key for key in required if key not in obj]
    return (len(missing) == 0, missing)

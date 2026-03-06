from __future__ import annotations

import json
from typing import Any


def emit_event(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=True)


def validate_contract(obj: dict[str, Any]) -> tuple[bool, list[str]]:
    required = ["run_id", "event", "ts"]
    missing = [k for k in required if k not in obj]
    return (len(missing) == 0, missing)

from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(slots=True)
class GptEndpoint:
    name: str
    status: str
    last_seen_at: float


def ok_count(endpoints: list[GptEndpoint], fresh_sec: int = 60) -> int:
    now = time()
    return sum(1 for e in endpoints if e.status == "OK" and now - e.last_seen_at <= fresh_sec)

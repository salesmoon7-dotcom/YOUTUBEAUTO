from __future__ import annotations


def within_retry_budget(attempts: int, max_attempts: int = 3) -> bool:
    return attempts < max_attempts


def next_backoff_sec(attempts: int, base_sec: int = 10) -> int:
    multiplier = 1
    for _ in range(max(0, attempts)):
        multiplier *= 2
    return base_sec * multiplier

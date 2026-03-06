from __future__ import annotations


def should_spawn(ok_count_value: int, breach_sec: int, cooldown_sec: int) -> bool:
    return ok_count_value < 1 and breach_sec >= 120 and cooldown_sec >= 300

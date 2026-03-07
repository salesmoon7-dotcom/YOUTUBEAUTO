from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(slots=True)
class CircuitState:
    failure_count: int = 0
    opened_at: float | None = None


def _within_retry_budget(attempts: int, max_attempts: int = 3) -> bool:
    return attempts < max_attempts


def _next_backoff_sec(attempts: int, base_sec: int = 10) -> int:
    multiplier = 1
    for _ in range(max(0, attempts)):
        multiplier *= 2
    return base_sec * multiplier


def _record_failure(state: CircuitState, threshold: int = 5) -> None:
    state.failure_count += 1
    if state.failure_count >= threshold and state.opened_at is None:
        state.opened_at = time()


def _reset_circuit(state: CircuitState) -> None:
    state.failure_count = 0
    state.opened_at = None


def _is_circuit_open(state: CircuitState) -> bool:
    return state.opened_at is not None


def evaluate_recovery(attempts: int, *, success: bool, circuit: CircuitState) -> dict[str, object]:
    if success:
        _reset_circuit(circuit)
        return {"action": "completed", "backoff_sec": 0, "circuit_open": False}

    _record_failure(circuit)
    if _is_circuit_open(circuit):
        return {"action": "circuit_open", "backoff_sec": 0, "circuit_open": True}
    if _within_retry_budget(attempts):
        return {
            "action": "retry",
            "backoff_sec": _next_backoff_sec(attempts),
            "circuit_open": False,
        }
    return {"action": "failed", "backoff_sec": 0, "circuit_open": False}

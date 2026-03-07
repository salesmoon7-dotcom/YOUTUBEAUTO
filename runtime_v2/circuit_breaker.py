from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(slots=True)
class CircuitState:
    failure_count: int = 0
    opened_at: float | None = None


def record_failure(state: CircuitState, threshold: int = 5) -> CircuitState:
    state.failure_count += 1
    if state.failure_count >= threshold and state.opened_at is None:
        state.opened_at = time()
    return state


def reset_circuit(state: CircuitState) -> CircuitState:
    state.failure_count = 0
    state.opened_at = None
    return state


def is_circuit_open(state: CircuitState) -> bool:
    return state.opened_at is not None

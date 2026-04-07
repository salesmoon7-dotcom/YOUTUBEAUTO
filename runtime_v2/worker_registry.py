from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from time import sleep
from time import time


_WORKER_REGISTRY_REPLACE_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.5, 1.0)
_WORKER_REGISTRY_LOCKS: dict[str, threading.Lock] = {}
_WORKER_REGISTRY_LOCKS_GUARD = threading.Lock()


def _worker_registry_lock(path: Path) -> threading.Lock:
    key = str(path.resolve()).lower()
    with _WORKER_REGISTRY_LOCKS_GUARD:
        lock = _WORKER_REGISTRY_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _WORKER_REGISTRY_LOCKS[key] = lock
        return lock


def load_worker_registry(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)
    }


def write_worker_registry(path: Path, payload: dict[str, dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_text = json.dumps(payload, ensure_ascii=True, indent=2)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload_text)
        temp_path = Path(handle.name)
    last_error: PermissionError | None = None
    for delay in (*_WORKER_REGISTRY_REPLACE_RETRY_DELAYS, None):
        try:
            temp_path.replace(path)
            break
        except PermissionError as exc:
            last_error = exc
            if getattr(exc, "winerror", None) != 5 or delay is None:
                if getattr(exc, "winerror", None) == 5 and delay is None:
                    path.write_text(payload_text, encoding="utf-8")
                    temp_path.unlink(missing_ok=True)
                    break
                raise
            sleep(delay)
    if last_error is not None and not path.exists():
        raise last_error
    return path


def update_worker_state(
    path: Path,
    *,
    workload: str,
    state: str,
    run_id: str,
    progress_ts: float | None = None,
) -> Path:
    with _worker_registry_lock(path):
        registry = load_worker_registry(path)
        existing = registry.get(workload, {})
        existing.update(
            {
                "workload": workload,
                "state": state,
                "run_id": run_id,
                "last_seen": round(time(), 3),
                "progress_ts": round(time() if progress_ts is None else progress_ts, 3),
            }
        )
        registry[workload] = existing
        return write_worker_registry(path, registry)


def has_progress_stall(
    entry: dict[str, object], *, now_ts: float, timeout_sec: int
) -> bool:
    progress_ts = entry.get("progress_ts", 0.0)
    if not isinstance(progress_ts, (int, float)):
        return True
    return float(now_ts) - float(progress_ts) >= float(timeout_sec)


def stalled_workloads(path: Path, *, now_ts: float, timeout_sec: int) -> list[str]:
    registry = load_worker_registry(path)
    stalled: list[str] = []
    for workload, entry in registry.items():
        state = str(entry.get("state", "")).strip().lower()
        if state not in {"running", "busy"}:
            continue
        if has_progress_stall(entry, now_ts=now_ts, timeout_sec=timeout_sec):
            stalled.append(workload)
    return stalled

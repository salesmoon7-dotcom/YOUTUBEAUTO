from __future__ import annotations

import json
import os
from pathlib import Path
from time import time


def _lock_file(lock_root: Path) -> Path:
    return lock_root / "repo_writer.lock"


def acquire_repo_writer_lock(lock_root: Path, *, owner: str) -> dict[str, object]:
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_file = _lock_file(lock_root)
    payload = {"owner": owner, "pid": os.getpid(), "acquired_at": round(time(), 3)}
    try:
        with lock_file.open("x", encoding="utf-8") as handle:
            _ = handle.write(json.dumps(payload, ensure_ascii=True))
        return {"locked": True, **payload, "lock_file": str(lock_file.resolve())}
    except FileExistsError:
        if lock_file.exists():
            try:
                existing = json.loads(lock_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        else:
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
        return {
            "locked": False,
            **{str(k): v for k, v in existing.items()},
            "lock_file": str(lock_file.resolve()),
        }


def release_repo_writer_lock(lock_root: Path, *, owner: str) -> None:
    lock_file = _lock_file(lock_root)
    if not lock_file.exists():
        return
    try:
        existing = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    if isinstance(existing, dict) and str(existing.get("owner", "")) not in {"", owner}:
        return
    try:
        lock_file.unlink()
    except OSError:
        return

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from time import perf_counter


def run_external_process(
    command: list[str],
    *,
    cwd: Path,
    extra_env: dict[str, str] | None = None,
    timeout_sec: int = 3600,
) -> dict[str, object]:
    run_env = os.environ.copy()
    if extra_env is not None:
        run_env.update(extra_env)
    started_at = perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=run_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
            "timeout_sec": timeout_sec,
            "duration_sec": round(perf_counter() - started_at, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": 124,
            "stdout": "" if exc.stdout is None else str(exc.stdout),
            "stderr": "" if exc.stderr is None else str(exc.stderr),
            "timed_out": True,
            "timeout_sec": timeout_sec,
            "duration_sec": round(perf_counter() - started_at, 3),
        }
    except OSError as exc:
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
            "timed_out": False,
            "timeout_sec": timeout_sec,
            "duration_sec": round(perf_counter() - started_at, 3),
        }

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from time import perf_counter
from typing import cast

from runtime_v2.workers.job_runtime import resolve_local_input


REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _resolve_output_target(raw_path: str) -> Path | None:
    text = raw_path.strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
        return None
    return candidate


def _file_signature(path: Path | None) -> tuple[int, int] | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


def run_verified_adapter_command(
    workspace: Path,
    *,
    adapter_command: list[str],
    service_artifact_path: str,
    adapter_error_code: str,
    timeout_sec: int = 3600,
) -> dict[str, object]:
    target_path = _resolve_output_target(service_artifact_path)
    before_signature = _file_signature(target_path)
    process_result = run_external_process(
        adapter_command,
        cwd=workspace,
        timeout_sec=timeout_sec,
    )
    stdout_path = workspace / "adapter_stdout.log"
    stderr_path = workspace / "adapter_stderr.log"
    _ = stdout_path.write_text(str(process_result.get("stdout", "")), encoding="utf-8")
    _ = stderr_path.write_text(str(process_result.get("stderr", "")), encoding="utf-8")
    exit_code = process_result.get("exit_code", 1)
    exit_code_int = int(exit_code) if isinstance(exit_code, (int, float, str)) else 1
    base_payload: dict[str, object] = {
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "details": {
            "returncode": exit_code_int,
            "timed_out": bool(process_result.get("timed_out", False)),
        },
    }
    if exit_code_int != 0:
        base_payload["ok"] = False
        base_payload["error_code"] = adapter_error_code
        return base_payload
    verified_output = (
        None if target_path is None else resolve_local_input(str(target_path))
    )
    if verified_output is None:
        base_payload["ok"] = False
        base_payload["error_code"] = "missing_service_artifact_path"
        return base_payload
    after_signature = _file_signature(verified_output)
    if before_signature is not None and before_signature == after_signature:
        base_payload["ok"] = False
        base_payload["error_code"] = "stale_service_artifact_path"
        details = dict(cast(dict[str, object], base_payload["details"]))
        details["service_artifact_path"] = str(verified_output.resolve())
        base_payload["details"] = details
        return base_payload
    base_payload["ok"] = True
    base_payload["output_path"] = verified_output
    return base_payload

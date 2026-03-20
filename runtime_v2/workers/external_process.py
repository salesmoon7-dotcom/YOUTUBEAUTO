from __future__ import annotations

import os
import subprocess
from pathlib import Path
from time import perf_counter
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_RESERVED_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _has_reserved_windows_name(candidate: Path) -> bool:
    for part in candidate.parts:
        normalized = part.rstrip(" .:").upper()
        if normalized in WINDOWS_RESERVED_DEVICE_NAMES:
            return True
    return False


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


def _resolve_output_target(raw_path: str, approved_root: Path) -> Path | None:
    text = raw_path.strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    approved_root = approved_root.resolve()
    if not candidate.is_absolute():
        candidate = (approved_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if _has_reserved_windows_name(candidate):
        return None
    if approved_root not in candidate.parents and candidate != approved_root:
        return None
    return candidate


def _resolve_output_target_info(
    raw_path: str, approved_root: Path
) -> tuple[Path | None, str | None]:
    text = raw_path.strip()
    if not text:
        return None, "OUTPUT_PATH_INVALID"
    candidate = Path(text).expanduser()
    approved_root = approved_root.resolve()
    if not candidate.is_absolute():
        candidate = (approved_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if _has_reserved_windows_name(candidate):
        return None, "OUTPUT_PATH_INVALID"
    if approved_root not in candidate.parents and candidate != approved_root:
        return None, "OUTPUT_OUTSIDE_ROOT"
    return candidate, None


def _file_signature(path: Path | None) -> tuple[int, int] | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


def run_verified_adapter_command(
    workspace: Path,
    *,
    approved_root: Path,
    adapter_command: list[str],
    service_artifact_path: str,
    adapter_error_code: str,
    extra_env: dict[str, str] | None = None,
    timeout_sec: int = 3600,
) -> dict[str, object]:
    approved_root = approved_root.resolve()
    target_path, target_error = _resolve_output_target_info(
        service_artifact_path, approved_root
    )
    before_signature = _file_signature(target_path)
    process_result = run_external_process(
        adapter_command,
        cwd=workspace,
        extra_env=extra_env,
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
            "service_artifact_path": service_artifact_path,
            "resolved_output_path": "" if target_path is None else str(target_path),
            "approved_root": str(approved_root),
            "stdout_path": str(stdout_path.resolve()),
            "stderr_path": str(stderr_path.resolve()),
            "before_signature": before_signature,
        },
    }
    if target_error is not None:
        base_payload["ok"] = False
        base_payload["error_code"] = target_error
        return base_payload
    if exit_code_int != 0:
        base_payload["ok"] = False
        stderr_text = str(process_result.get("stderr", ""))
        if bool(process_result.get("timed_out", False)):
            base_payload["error_code"] = "ADAPTER_TIMEOUT"
        elif exit_code_int == 20:
            base_payload["error_code"] = "BROWSER_UNHEALTHY"
        elif exit_code_int == 21:
            base_payload["error_code"] = "BROWSER_BLOCKED"
        elif (
            "No such file" in stderr_text
            or "cannot find the file" in stderr_text.lower()
        ):
            base_payload["error_code"] = "ADAPTER_NOT_FOUND"
        else:
            base_payload["error_code"] = "ADAPTER_NONZERO_EXIT"
        return base_payload
    verified_output = (
        None
        if target_path is None
        else _resolve_output_target(str(target_path), approved_root)
    )
    if verified_output is not None and (
        not verified_output.exists() or not verified_output.is_file()
    ):
        verified_output = None
    if verified_output is None:
        base_payload["ok"] = False
        base_payload["error_code"] = "OUTPUT_NOT_CREATED"
        return base_payload
    after_signature = _file_signature(verified_output)
    details = dict(cast(dict[str, object], base_payload["details"]))
    details["after_signature"] = after_signature
    if before_signature is not None and before_signature == after_signature:
        details["service_artifact_path"] = str(verified_output.resolve())
        details["reused"] = True
        base_payload["details"] = details
        base_payload["ok"] = True
        base_payload["reused"] = True
        base_payload["error_code"] = "OUTPUT_UNCHANGED_REUSED"
        base_payload["output_path"] = verified_output
        return base_payload
    base_payload["details"] = details
    base_payload["ok"] = True
    base_payload["reused"] = False
    base_payload["output_path"] = verified_output
    return base_payload

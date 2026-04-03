from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from time import sleep
from time import time


_SUMMARY_HEARTBEAT_SEC = 5.0
_SUMMARY_REPLACE_RETRY_DELAYS = (0.05, 0.1, 0.2)


def _write_summary(out_root: Path, payload: dict[str, object]) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    summary_file = out_root / "summary.json"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=out_root,
        prefix="summary.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
        temp_path = Path(handle.name)
    last_error: PermissionError | None = None
    for delay in (*_SUMMARY_REPLACE_RETRY_DELAYS, None):
        try:
            _ = temp_path.replace(summary_file)
            break
        except PermissionError as exc:
            last_error = exc
            if getattr(exc, "winerror", None) != 5 or delay is None:
                raise
            sleep(delay)
    if last_error is not None and not summary_file.exists():
        raise last_error
    return summary_file


def _wait_with_summary_updates(
    child: subprocess.Popen[str],
    *,
    probe_root: Path,
    command: list[str],
    stdout_file: Path,
    stderr_file: Path,
    started_at: float,
) -> int:
    while True:
        returncode = child.poll()
        if returncode is not None:
            _ = _write_summary(
                probe_root,
                {
                    "started_at": started_at,
                    "finished_at": round(time(), 3),
                    "command": command,
                    "exit_code": returncode,
                    "kind": "runtime_v2_cli",
                    "probe_root": str(probe_root),
                    "stdout_log": str(stdout_file),
                    "stderr_log": str(stderr_file),
                    "pid": child.pid,
                },
            )
            return int(returncode)
        _ = _write_summary(
            probe_root,
            {
                "started_at": started_at,
                "finished_at": None,
                "command": command,
                "exit_code": None,
                "kind": "runtime_v2_cli_running",
                "probe_root": str(probe_root),
                "stdout_log": str(stdout_file),
                "stderr_log": str(stderr_file),
                "pid": child.pid,
                "heartbeat_at": round(time(), 3),
            },
        )
        sleep(_SUMMARY_HEARTBEAT_SEC)


def main() -> int:
    worker = False
    if "--worker" in sys.argv[1:]:
        worker = True
        argv = [arg for arg in sys.argv[1:] if arg != "--worker"]
    else:
        argv = list(sys.argv[1:])

    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--probe-root", required=True)
    args, cli_args = parser.parse_known_args(argv)

    probe_root = Path(args.probe_root).resolve()
    logs_root = probe_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    stdout_file = logs_root / "detached_cli_stdout.log"
    stderr_file = logs_root / "detached_cli_stderr.log"

    if cli_args and cli_args[0] == "--":
        cli_args = cli_args[1:]

    if worker:
        if cli_args and cli_args[0] == "--stage5-row1-detached":
            cli_args = [
                "--stage5-row1-probe-child",
                "--owner",
                "runtime_v2",
                "--probe-root",
                str(probe_root),
                *cli_args[1:],
            ]
        elif cli_args and cli_args[0] == "--stage5b-5row-detached":
            cli_args = [
                "--stage5b-5row-probe-child",
                "--owner",
                "runtime_v2",
                "--probe-root",
                str(probe_root),
                *cli_args[1:],
            ]
        command = [
            sys.executable,
            "-u",
            "-m",
            "runtime_v2.cli",
            *cli_args,
        ]
        started_at = round(time(), 3)
        completed_returncode = 1
        with (
            stdout_file.open("a", encoding="utf-8", buffering=1) as stdout_handle,
            stderr_file.open("a", encoding="utf-8", buffering=1) as stderr_handle,
        ):
            try:
                child = subprocess.Popen(
                    command,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(Path(__file__).resolve().parents[1]),
                )
                completed_returncode = _wait_with_summary_updates(
                    child,
                    probe_root=probe_root,
                    command=command,
                    stdout_file=stdout_file,
                    stderr_file=stderr_file,
                    started_at=started_at,
                )
            except Exception:
                stderr_handle.write(traceback.format_exc())
                stderr_handle.flush()
        _ = _write_summary(
            probe_root,
            {
                "started_at": started_at,
                "finished_at": round(time(), 3),
                "command": command,
                "exit_code": completed_returncode,
                "kind": "runtime_v2_cli",
                "probe_root": str(probe_root),
                "stdout_log": str(stdout_file),
                "stderr_log": str(stderr_file),
            },
        )
        return completed_returncode

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--probe-root",
        str(probe_root),
        "--worker",
        *cli_args,
    ]
    creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
        getattr(subprocess, "DETACHED_PROCESS", 0)
    )
    creationflags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    child = subprocess.Popen(command, creationflags=creationflags)
    _ = _write_summary(
        probe_root,
        {
            "started_at": round(time(), 3),
            "finished_at": None,
            "command": command,
            "exit_code": None,
            "kind": "runtime_v2_cli_spawned",
            "probe_root": str(probe_root),
            "stdout_log": str(stdout_file),
            "stderr_log": str(stderr_file),
            "pid": child.pid,
        },
    )
    print(
        json.dumps(
            {
                "status": "spawned",
                "pid": child.pid,
                "probe_root": str(probe_root),
                "stdout_log": str(stdout_file),
                "stderr_log": str(stderr_file),
                "summary_file": str(probe_root / "summary.json"),
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

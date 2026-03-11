from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from time import time
from uuid import uuid4

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from runtime_v2.config import runtime_scratch_root


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
    _ = temp_path.replace(summary_file)
    return summary_file


def _default_out_root() -> Path:
    return runtime_scratch_root() / "detached_pytest" / str(uuid4())


def main() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("target")
    _ = parser.add_argument("extra_args", nargs="*")
    _ = parser.add_argument("--out-root", default="")
    _ = parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    out_root = (
        Path(args.out_root).resolve()
        if args.out_root
        else _default_out_root().resolve()
    )
    logs_root = out_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    stdout_file = logs_root / "stdout.log"
    stderr_file = logs_root / "stderr.log"

    if args.worker:
        command = [sys.executable, "-m", "pytest", args.target, *args.extra_args]
        started_at = round(time(), 3)
        with (
            stdout_file.open("w", encoding="utf-8") as stdout_handle,
            stderr_file.open("w", encoding="utf-8") as stderr_handle,
        ):
            completed = subprocess.run(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        _ = _write_summary(
            out_root,
            {
                "started_at": started_at,
                "finished_at": round(time(), 3),
                "command": command,
                "exit_code": completed.returncode,
                "kind": "pytest",
                "target": args.target,
                "out_root": str(out_root),
                "stdout_log": str(stdout_file),
                "stderr_log": str(stderr_file),
            },
        )
        return completed.returncode

    command = [
        sys.executable,
        __file__,
        args.target,
        *args.extra_args,
        "--out-root",
        str(out_root),
        "--worker",
    ]
    creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
        getattr(subprocess, "DETACHED_PROCESS", 0)
    )
    child = subprocess.Popen(command, creationflags=creationflags)
    print(
        json.dumps(
            {
                "status": "spawned",
                "pid": child.pid,
                "target": args.target,
                "out_root": str(out_root),
                "stdout_log": str(stdout_file),
                "stderr_log": str(stderr_file),
                "summary_file": str(out_root / "summary.json"),
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

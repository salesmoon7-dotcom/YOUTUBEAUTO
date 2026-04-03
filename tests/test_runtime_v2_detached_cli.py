from __future__ import annotations

import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "runtime_v2_detached_cli.py"
)
_SPEC = importlib.util.spec_from_file_location("runtime_v2_detached_cli", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_wait_with_summary_updates = _MODULE._wait_with_summary_updates


class _FakeChild:
    def __init__(self) -> None:
        self.pid = 1234
        self._polls = [None, 0]

    def poll(self) -> int | None:
        return self._polls.pop(0)


class RuntimeV2DetachedCliTests(unittest.TestCase):
    def test_wait_with_summary_updates_writes_running_then_final_summary(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            stdout_file = root / "stdout.log"
            stderr_file = root / "stderr.log"
            child = _FakeChild()

            with patch.object(_MODULE, "sleep", return_value=None):
                returncode = _wait_with_summary_updates(
                    child,
                    probe_root=root,
                    command=["python", "-m", "runtime_v2.cli", "--help"],
                    stdout_file=stdout_file,
                    stderr_file=stderr_file,
                    started_at=1.0,
                )

            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(returncode, 0)
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(summary["kind"], "runtime_v2_cli")
        self.assertEqual(summary["pid"], 1234)

    def test_write_summary_retries_winerror_5(self) -> None:
        root = Path(tempfile.mkdtemp(dir=r"D:\YOUTUBEAUTO"))
        payload = {"status": "running"}
        original_replace = Path.replace
        calls = {"count": 0}

        def flaky_replace(self: Path, target: Path) -> Path:
            if self.suffix == ".tmp" and calls["count"] < 2:
                calls["count"] += 1
                error = PermissionError("locked")
                error.winerror = 5
                raise error
            return original_replace(self, target)

        with (
            patch.object(_MODULE, "sleep", return_value=None),
            patch.object(Path, "replace", new=flaky_replace),
        ):
            written = _MODULE._write_summary(root, payload)

        written_payload = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(written_payload["status"], "running")

    def test_write_spawn_record_writes_spawn_json(self) -> None:
        root = Path(tempfile.mkdtemp(dir=r"D:\YOUTUBEAUTO"))
        written = _MODULE._write_spawn_record(root, {"status": "spawned", "pid": 7})
        payload = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(written.name, "spawn.json")
        self.assertEqual(payload["status"], "spawned")
        self.assertEqual(payload["pid"], 7)


if __name__ == "__main__":
    _ = unittest.main()

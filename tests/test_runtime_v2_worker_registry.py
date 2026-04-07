from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.worker_registry import update_worker_state
from runtime_v2.worker_registry import write_worker_registry


class RuntimeV2WorkerRegistryTests(unittest.TestCase):
    def test_write_worker_registry_retries_winerror_5(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "worker_registry.json"
            payload: dict[str, dict[str, object]] = {
                "chatgpt": {
                    "workload": "chatgpt",
                    "state": "busy",
                    "run_id": "run-1",
                    "last_seen": 1.0,
                    "progress_ts": 1.0,
                }
            }
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
                patch("runtime_v2.worker_registry.sleep", return_value=None),
                patch.object(Path, "replace", new=flaky_replace),
            ):
                written = write_worker_registry(output_path, payload)

            written_payload = json.loads(written.read_text(encoding="utf-8"))

        self.assertEqual(written, output_path)
        self.assertIn("chatgpt", written_payload)

    def test_write_worker_registry_survives_longer_winerror_5_burst(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "worker_registry.json"
            payload: dict[str, dict[str, object]] = {
                "chatgpt": {
                    "workload": "chatgpt",
                    "state": "busy",
                    "run_id": "run-1",
                    "last_seen": 1.0,
                    "progress_ts": 1.0,
                }
            }
            original_replace = Path.replace
            calls = {"count": 0}

            def flaky_replace(self: Path, target: Path) -> Path:
                if self.suffix == ".tmp" and calls["count"] < 5:
                    calls["count"] += 1
                    error = PermissionError("locked")
                    error.winerror = 5
                    raise error
                return original_replace(self, target)

            with (
                patch("runtime_v2.worker_registry.sleep", return_value=None),
                patch.object(Path, "replace", new=flaky_replace),
            ):
                written = write_worker_registry(output_path, payload)

            written_payload = json.loads(written.read_text(encoding="utf-8"))

        self.assertEqual(written, output_path)
        self.assertIn("chatgpt", written_payload)

    def test_write_worker_registry_falls_back_to_direct_write_after_retry_exhausted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "worker_registry.json"
            payload: dict[str, dict[str, object]] = {
                "chatgpt": {
                    "workload": "chatgpt",
                    "state": "busy",
                    "run_id": "run-1",
                    "last_seen": 1.0,
                    "progress_ts": 1.0,
                }
            }

            def always_locked_replace(self: Path, target: Path) -> Path:
                if self.suffix == ".tmp":
                    error = PermissionError("locked")
                    error.winerror = 5
                    raise error
                raise AssertionError("unexpected replace target")

            with (
                patch("runtime_v2.worker_registry.sleep", return_value=None),
                patch.object(Path, "replace", new=always_locked_replace),
            ):
                written = write_worker_registry(output_path, payload)

            written_payload = json.loads(written.read_text(encoding="utf-8"))

        self.assertEqual(written, output_path)
        self.assertEqual(written_payload["chatgpt"]["run_id"], "run-1")

    def test_update_worker_state_serializes_same_path_writers(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "worker_registry.json"
            errors: list[Exception] = []

            def worker(run_id: str) -> None:
                try:
                    _ = update_worker_state(
                        output_path,
                        workload="chatgpt",
                        state="busy",
                        run_id=run_id,
                    )
                except Exception as exc:  # pragma: no cover - assertion below checks
                    errors.append(exc)

            thread_a = threading.Thread(target=worker, args=("run-a",))
            thread_b = threading.Thread(target=worker, args=("run-b",))
            thread_a.start()
            thread_b.start()
            thread_a.join()
            thread_b.join()

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(errors, [])
        self.assertEqual(payload["chatgpt"]["workload"], "chatgpt")
        self.assertEqual(payload["chatgpt"]["state"], "busy")


if __name__ == "__main__":
    _ = unittest.main()

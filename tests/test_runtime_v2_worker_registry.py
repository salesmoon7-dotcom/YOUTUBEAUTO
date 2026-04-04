from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.worker_registry import write_worker_registry


class RuntimeV2WorkerRegistryTests(unittest.TestCase):
    def test_write_worker_registry_retries_winerror_5(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "worker_registry.json"
            payload = {
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


if __name__ == "__main__":
    _ = unittest.main()

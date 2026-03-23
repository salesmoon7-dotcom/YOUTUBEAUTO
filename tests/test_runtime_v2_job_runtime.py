from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.workers.job_runtime import resolve_local_input
from runtime_v2.workers.job_runtime import write_json_atomic


class RuntimeV2JobRuntimeTests(unittest.TestCase):
    def test_resolve_local_input_accepts_external_runtime_root_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO_RUNTIME") as tmp_dir:
            root = Path(tmp_dir)
            source = root / "probe" / "sample.wav"
            source.parent.mkdir(parents=True, exist_ok=True)
            _ = source.write_bytes(b"wav")

            resolved = resolve_local_input(str(source))

        self.assertEqual(resolved, source.resolve())

    def test_write_json_atomic_retries_permission_error_on_replace(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            path = Path(tmp_dir) / "result.json"
            replace_calls = {"count": 0}
            original_replace = Path.replace

            def flaky_replace(self: Path, target: Path) -> Path:
                if self.suffix == ".tmp" and replace_calls["count"] < 2:
                    replace_calls["count"] += 1
                    raise PermissionError("locked")
                return original_replace(self, target)

            with patch(
                "runtime_v2.workers.job_runtime.Path.replace", new=flaky_replace
            ):
                written = write_json_atomic(path, {"status": "ok"})
                contents = path.read_text(encoding="utf-8")

        self.assertEqual(written, path)
        self.assertIn('"status": "ok"', contents)


if __name__ == "__main__":
    _ = unittest.main()

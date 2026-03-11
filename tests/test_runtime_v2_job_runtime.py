from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime_v2.workers.job_runtime import resolve_local_input


class RuntimeV2JobRuntimeTests(unittest.TestCase):
    def test_resolve_local_input_accepts_external_runtime_root_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO_RUNTIME") as tmp_dir:
            root = Path(tmp_dir)
            source = root / "probe" / "sample.wav"
            source.parent.mkdir(parents=True, exist_ok=True)
            _ = source.write_bytes(b"wav")

            resolved = resolve_local_input(str(source))

        self.assertEqual(resolved, source.resolve())


if __name__ == "__main__":
    _ = unittest.main()

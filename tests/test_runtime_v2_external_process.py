from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

from runtime_v2.workers.external_process import run_external_process


class RuntimeV2ExternalProcessTests(unittest.TestCase):
    def test_external_process_returns_structured_timeout_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = Path(tmp_dir)
            result = run_external_process(
                [sys.executable, "-c", "import time; time.sleep(0.2)"],
                cwd=cwd,
                timeout_sec=0,
            )
        exit_code = cast(int, result["exit_code"])
        timed_out = cast(bool, result["timed_out"])
        self.assertTrue(timed_out)
        self.assertEqual(exit_code, 124)
        self.assertEqual(result["cwd"], str(cwd))
        self.assertEqual(result["timeout_sec"], 0)
        self.assertIn("duration_sec", result)

    def test_external_process_returns_structured_spawn_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = Path(tmp_dir)
            result = run_external_process(["__missing_runtime_v2_binary__"], cwd=cwd)
        exit_code = cast(int, result["exit_code"])
        timed_out = cast(bool, result["timed_out"])
        self.assertFalse(timed_out)
        self.assertNotEqual(exit_code, 0)
        self.assertEqual(result["cwd"], str(cwd))
        self.assertEqual(result["command"], ["__missing_runtime_v2_binary__"])
        self.assertTrue(str(result["stderr"]).strip())


if __name__ == "__main__":
    _ = unittest.main()

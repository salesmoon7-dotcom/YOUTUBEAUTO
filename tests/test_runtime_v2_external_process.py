from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

from runtime_v2.workers.external_process import (
    run_external_process,
    run_verified_adapter_command,
)


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

    def test_verified_adapter_command_reports_timeout_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            result = run_verified_adapter_command(
                workspace,
                approved_root=workspace,
                adapter_command=[sys.executable, "-c", "import time; time.sleep(1)"],
                service_artifact_path=str(workspace / "out.txt"),
                adapter_error_code="ignored_adapter_failed",
                timeout_sec=0,
            )

        self.assertFalse(bool(result["ok"]))
        self.assertEqual(result["error_code"], "ADAPTER_TIMEOUT")

    def test_verified_adapter_command_reports_output_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            result = run_verified_adapter_command(
                workspace,
                approved_root=workspace,
                adapter_command=[sys.executable, "-c", "print('ok')"],
                service_artifact_path="C:/Windows/out.txt",
                adapter_error_code="ignored_adapter_failed",
            )

        self.assertFalse(bool(result["ok"]))
        self.assertEqual(result["error_code"], "OUTPUT_OUTSIDE_ROOT")

    def test_verified_adapter_command_rejects_windows_reserved_device_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            result = run_verified_adapter_command(
                workspace,
                approved_root=workspace,
                adapter_command=[sys.executable, "-c", "print('ok')"],
                service_artifact_path="NUL",
                adapter_error_code="ignored_adapter_failed",
            )

        self.assertFalse(bool(result["ok"]))
        self.assertEqual(result["error_code"], "OUTPUT_PATH_INVALID")

    def test_verified_adapter_command_marks_reused_output_with_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            output_path = workspace / "out.txt"
            _ = output_path.write_text("same", encoding="utf-8")
            result = run_verified_adapter_command(
                workspace,
                approved_root=workspace,
                adapter_command=[sys.executable, "-c", "pass"],
                service_artifact_path=str(output_path),
                adapter_error_code="ignored_adapter_failed",
            )

        self.assertTrue(bool(result["ok"]))
        self.assertEqual(result["error_code"], "OUTPUT_UNCHANGED_REUSED")

    def test_verified_adapter_command_accepts_relative_output_inside_approved_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            result = run_verified_adapter_command(
                workspace,
                approved_root=workspace,
                adapter_command=[
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "p=Path(r'child/out.txt'); "
                        "p.parent.mkdir(parents=True, exist_ok=True); "
                        "p.write_text('ok', encoding='utf-8')"
                    ),
                ],
                service_artifact_path="child/out.txt",
                adapter_error_code="ignored_adapter_failed",
            )

        self.assertTrue(bool(result["ok"]))
        self.assertTrue(str(result["output_path"]).endswith("child\\out.txt"))

    def test_verified_adapter_command_reports_missing_output_when_not_created(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            result = run_verified_adapter_command(
                workspace,
                approved_root=workspace,
                adapter_command=[sys.executable, "-c", "print('ok')"],
                service_artifact_path="missing/out.txt",
                adapter_error_code="ignored_adapter_failed",
            )

        self.assertFalse(bool(result["ok"]))
        self.assertEqual(result["error_code"], "OUTPUT_NOT_CREATED")


if __name__ == "__main__":
    _ = unittest.main()

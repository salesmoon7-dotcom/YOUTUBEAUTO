from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from runtime_v2 import exit_codes
from runtime_v2.cli import CliArgs, _run_browser_recovery_probe, _spawn_detached_probe
from runtime_v2.config import RuntimeConfig


class RuntimeV2CliDetachedRecoveryTests(unittest.TestCase):
    def test_spawn_detached_probe_uses_browser_recovery_child_flag(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            args = CliArgs()
            args.probe_root = str(root / "probe")
            args.runtime_root = str(root / "runtime")
            popen_result = MagicMock()
            popen_result.pid = 43210

            with patch(
                "runtime_v2.cli.subprocess.Popen", return_value=popen_result
            ) as popen_mock:
                exit_code = _spawn_detached_probe(args, mode="browser_recover")

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        command = popen_mock.call_args.args[0]
        self.assertIn("--browser-recover-probe-child", command)
        self.assertIn("--runtime-root", command)
        self.assertIn(str(root / "runtime"), command)

    def test_run_browser_recovery_probe_writes_probe_result(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root / "runtime")
            probe_root = root / "probe"
            supervisor_instance = MagicMock()
            supervisor_instance.tick.return_value = {
                "restarted_services": ["seaart", "geminigen"],
                "initial_summary": {"all_healthy": False, "healthy": 3},
                "final_summary": {"all_healthy": False, "healthy": 3, "unhealthy": 2},
            }

            with (
                patch("runtime_v2.cli.BrowserManager"),
                patch(
                    "runtime_v2.cli.BrowserSupervisor", return_value=supervisor_instance
                ),
                patch(
                    "runtime_v2.cli.tick_gpt_status",
                    return_value={"ok_count": 2, "floor_breached": False},
                ),
            ):
                report = _run_browser_recovery_probe(
                    config=config,
                    probe_root=probe_root,
                    run_id="browser-recover-run-1",
                )

            payload = json.loads(
                (probe_root / "probe_result.json").read_text(encoding="utf-8")
            )

        self.assertEqual(report["code"], "BROWSER_UNHEALTHY")
        self.assertEqual(payload["run_id"], "browser-recover-run-1")
        self.assertEqual(payload["mode"], "browser_recover")
        self.assertEqual(payload["restarted_services"], ["seaart", "geminigen"])
        self.assertEqual(payload["gpt_status"]["ok_count"], 2)


if __name__ == "__main__":
    _ = unittest.main()

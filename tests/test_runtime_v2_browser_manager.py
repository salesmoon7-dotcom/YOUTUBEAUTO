from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from runtime_v2.browser.manager import _pid_is_running


class RuntimeV2BrowserManagerTests(unittest.TestCase):
    def test_pid_is_running_uses_tasklist_fallback_on_windows(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["tasklist"],
            returncode=0,
            stdout="python.exe                   33588 Console                    1     55,440 K\n",
            stderr="",
        )

        with (
            patch("runtime_v2.browser.manager.os.kill", side_effect=OSError("win")),
            patch("runtime_v2.browser.manager.os.name", "nt"),
            patch("runtime_v2.browser.manager.subprocess.run", return_value=completed),
        ):
            self.assertTrue(_pid_is_running(33588))

    def test_pid_is_running_returns_false_when_tasklist_reports_no_match(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["tasklist"],
            returncode=0,
            stdout="INFO: No tasks are running which match the specified criteria.\n",
            stderr="",
        )

        with (
            patch("runtime_v2.browser.manager.os.kill", side_effect=OSError("win")),
            patch("runtime_v2.browser.manager.os.name", "nt"),
            patch("runtime_v2.browser.manager.subprocess.run", return_value=completed),
        ):
            self.assertFalse(_pid_is_running(33588))

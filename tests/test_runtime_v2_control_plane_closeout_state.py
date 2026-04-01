from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime_v2.config import RuntimeConfig
from runtime_v2.control_plane import run_control_loop_once


class RuntimeV2ControlPlaneCloseoutStateTests(unittest.TestCase):
    def test_run_control_loop_short_circuits_when_same_run_already_terminal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            config.queue_store_file.parent.mkdir(parents=True, exist_ok=True)
            config.closeout_state_file.parent.mkdir(parents=True, exist_ok=True)
            config.queue_store_file.write_text("[]", encoding="utf-8")
            config.control_plane_events_file.write_text("", encoding="utf-8")
            config.closeout_state_file.write_text(
                json.dumps(
                    {
                        "run_id": "closeout-run-1",
                        "status": "failed",
                        "reason": "BROWSER_UNHEALTHY",
                        "attempt": 1,
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            result = run_control_loop_once(
                owner="test-owner",
                config=config,
                run_id="closeout-run-1",
                allow_runtime_side_effects=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_UNHEALTHY")

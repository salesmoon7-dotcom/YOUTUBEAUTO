from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2 import exit_codes
from runtime_v2.cli import CliArgs, _run_agent_browser_stage2_adapter_child


class RuntimeV2CliAgentBrowserStage2AdapterTests(unittest.TestCase):
    def test_stage2_adapter_child_writes_placeholder_artifact_after_verify(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"

            with patch(
                "runtime_v2.cli.run_agent_browser_verify_job",
                return_value={"status": "ok"},
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            self.assertTrue(output_path.exists())
            self.assertIn(
                "agent-browser-stage2-placeholder",
                output_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    _ = unittest.main()

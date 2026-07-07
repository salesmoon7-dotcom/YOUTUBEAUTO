from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call
from unittest.mock import patch

from runtime_v2 import exit_codes
from runtime_v2.cli import CliArgs, _run_agent_browser_stage2_adapter_child


class RuntimeV2GeminiGenAdapterPollingTests(unittest.TestCase):
    def test_geminigen_adapter_polls_functional_capture_when_video_is_not_ready(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "geminigen-scene-01.mp4"
            (root / "request.json").write_text(
                json.dumps(
                    {"payload": {"prompt": "Create a calm four second video."}},
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            args = CliArgs()
            args.service = "geminigen"
            args.port = 9555
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "geminigen.ai"
            args.expected_title_substring = "Gemini"

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    side_effect=RuntimeError("GEMINIGEN_VIDEO_URL_NOT_FOUND"),
                ) as evidence_mock,
                patch("runtime_v2.cli.sleep") as sleep_mock,
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
        self.assertEqual(evidence_mock.call_count, 12)
        self.assertEqual(sleep_mock.call_count, 12)
        sleep_mock.assert_has_calls([call(10)] * 12)
        self.assertEqual(evidence["service"], "geminigen")
        self.assertTrue(bool(evidence["placeholder_artifact"]))
        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()

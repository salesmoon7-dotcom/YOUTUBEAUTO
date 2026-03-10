from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.agent_browser.cdp_capture import write_functional_evidence_bundle


class RuntimeV2CdpCaptureTests(unittest.TestCase):
    def test_write_functional_evidence_bundle_copies_downloaded_asset(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            target_path = root / "exports" / "seaart.png"

            def fake_screenshot(
                port: int, expected_url_substring: str, output_path: Path
            ) -> Path:
                _ = port
                _ = expected_url_substring
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_bytes(b"png")
                return output_path

            def fake_asset(
                port: int, expected_url_substring: str, output_path: Path
            ) -> tuple[Path, str]:
                _ = port
                _ = expected_url_substring
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_bytes(b"image")
                return output_path, "sha256-test"

            with (
                patch(
                    "runtime_v2.agent_browser.cdp_capture.capture_page_screenshot",
                    side_effect=fake_screenshot,
                ),
                patch(
                    "runtime_v2.agent_browser.cdp_capture.capture_primary_image_asset",
                    side_effect=fake_asset,
                ),
            ):
                evidence = write_functional_evidence_bundle(
                    workspace=root,
                    service="seaart",
                    port=9444,
                    expected_url_substring="seaart.ai",
                    service_artifact_path=target_path,
                )

            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_bytes(), b"image")
            self.assertEqual(evidence["sha256"], "sha256-test")
            payload = json.loads(
                (root / "functional_evidence" / "evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(payload["service"], "seaart")


if __name__ == "__main__":
    _ = unittest.main()

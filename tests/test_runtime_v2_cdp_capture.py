from __future__ import annotations

import base64
import json
import tempfile
import urllib.error
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from runtime_v2.agent_browser.cdp_capture import (
    capture_primary_image_asset,
    write_functional_evidence_bundle,
)


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

    def test_capture_primary_image_asset_falls_back_to_page_context_fetch_on_403(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "genspark.png"
            encoded = base64.b64encode(b"image-bytes").decode("ascii")

            def fake_cdp(
                ws_url: str, *, method: str, params: dict[str, object]
            ) -> dict[str, object]:
                _ = ws_url
                if method == "Runtime.evaluate" and params.get("awaitPromise"):
                    return {
                        "result": {"result": {"value": {"ok": True, "base64": encoded}}}
                    }
                return {
                    "result": {
                        "result": {
                            "value": "https://www.genspark.ai/api/files/example.png"
                        }
                    }
                }

            with (
                patch(
                    "runtime_v2.agent_browser.cdp_capture._select_page_target",
                    return_value={
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9333/devtools/page/1",
                        "url": "https://www.genspark.ai/agents?id=1",
                    },
                ),
                patch(
                    "runtime_v2.agent_browser.cdp_capture.urllib.request.urlopen",
                    side_effect=urllib.error.HTTPError(
                        "https://www.genspark.ai/api/files/example.png",
                        403,
                        "Forbidden",
                        hdrs=Message(),
                        fp=None,
                    ),
                ),
                patch(
                    "runtime_v2.agent_browser.cdp_capture._cdp_command",
                    side_effect=fake_cdp,
                ),
            ):
                asset_path, sha256 = capture_primary_image_asset(
                    9333,
                    "genspark.ai",
                    output_path,
                    service="genspark",
                )
                self.assertTrue(asset_path.exists())
                self.assertEqual(asset_path.read_bytes(), b"image-bytes")

        self.assertEqual(len(sha256), 64)


if __name__ == "__main__":
    _ = unittest.main()

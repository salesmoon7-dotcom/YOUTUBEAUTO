from __future__ import annotations

import base64
import json
import tempfile
import urllib.error
import urllib.request
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from runtime_v2.agent_browser.cdp_capture import (
    capture_primary_video_asset,
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
                port: int,
                expected_url_substring: str,
                output_path: Path,
                *,
                service: str = "",
            ) -> tuple[Path, str]:
                _ = port
                _ = expected_url_substring
                _ = service
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

    def test_write_functional_evidence_bundle_uses_page_screenshot_for_canva(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            target_path = root / "exports" / "canva.png"

            def fake_screenshot(
                port: int, expected_url_substring: str, output_path: Path
            ) -> Path:
                _ = port
                _ = expected_url_substring
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_bytes(b"screen-png")
                return output_path

            with patch(
                "runtime_v2.agent_browser.cdp_capture.capture_page_screenshot",
                side_effect=fake_screenshot,
            ) as screenshot_mock:
                evidence = write_functional_evidence_bundle(
                    workspace=root,
                    service="canva",
                    port=9666,
                    expected_url_substring="canva.com",
                    service_artifact_path=target_path,
                )
                self.assertEqual(screenshot_mock.call_count, 2)
                self.assertTrue(target_path.exists())
                self.assertEqual(target_path.read_bytes(), b"screen-png")
                self.assertEqual(
                    Path(str(evidence["downloaded_asset"])).read_bytes(), b"screen-png"
                )

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

    def test_capture_primary_image_asset_accepts_relative_genspark_api_file_url(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "genspark-relative.png"
            encoded = base64.b64encode(b"image-bytes-relative").decode("ascii")

            def fake_cdp(
                ws_url: str, *, method: str, params: dict[str, object]
            ) -> dict[str, object]:
                _ = ws_url
                if method == "Runtime.evaluate" and params.get("awaitPromise"):
                    return {
                        "result": {"result": {"value": {"ok": True, "base64": encoded}}}
                    }
                return {
                    "result": {"result": {"value": "/api/files/example-relative.png"}}
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
                    side_effect=ValueError("relative-url"),
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
                self.assertEqual(asset_path.read_bytes(), b"image-bytes-relative")

        self.assertEqual(len(sha256), 64)

    def test_capture_primary_image_asset_prefers_newest_genspark_result_tab(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "genspark-newest.png"

            class FakeResponse:
                def __init__(self, payload: object) -> None:
                    self._payload = payload

                def read(self) -> bytes:
                    if isinstance(self._payload, bytes):
                        return self._payload
                    return json.dumps(self._payload, ensure_ascii=True).encode("utf-8")

                def __enter__(self) -> "FakeResponse":
                    return self

                def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
                    _ = exc_type
                    _ = exc
                    _ = tb
                    return None

            def fake_urlopen(url: str, timeout: int = 30) -> FakeResponse:
                _ = timeout
                if url == "http://127.0.0.1:9333/json/list":
                    return FakeResponse(
                        [
                            {
                                "type": "page",
                                "url": "https://www.genspark.ai/agents?id=stale",
                                "title": "image_generation_agent",
                                "webSocketDebuggerUrl": "ws://stale",
                            },
                            {
                                "type": "page",
                                "url": "https://www.genspark.ai/agents?id=fresh",
                                "title": "Genspark Agents",
                                "webSocketDebuggerUrl": "ws://fresh",
                            },
                        ]
                    )
                if url == "https://www.genspark.ai/api/files/fresh.png":
                    return FakeResponse(b"fresh-image")
                raise AssertionError(url)

            def fake_cdp(
                ws_url: str, *, method: str, params: dict[str, object]
            ) -> dict[str, object]:
                _ = method
                _ = params
                if ws_url == "ws://fresh":
                    return {
                        "result": {
                            "result": {
                                "value": "https://www.genspark.ai/api/files/fresh.png"
                            }
                        }
                    }
                return {
                    "result": {
                        "result": {
                            "value": "https://www.genspark.ai/api/files/stale.png"
                        }
                    }
                }

            with (
                patch(
                    "runtime_v2.agent_browser.cdp_capture.urllib.request.urlopen",
                    side_effect=fake_urlopen,
                ),
                patch(
                    "runtime_v2.agent_browser.cdp_capture._cdp_command",
                    side_effect=fake_cdp,
                ),
            ):
                asset_path, _ = capture_primary_image_asset(
                    9333,
                    "genspark.ai/agents?type=image_generation_agent",
                    output_path,
                    service="genspark",
                )
                self.assertTrue(asset_path.exists())
                self.assertEqual(asset_path.read_bytes(), b"fresh-image")

    def test_capture_primary_image_asset_prefers_newest_canva_edit_tab(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "canva-newest.png"

            class FakeResponse:
                def __init__(self, payload: object) -> None:
                    self._payload = payload

                def read(self) -> bytes:
                    if isinstance(self._payload, bytes):
                        return self._payload
                    return json.dumps(self._payload, ensure_ascii=True).encode("utf-8")

                def __enter__(self) -> "FakeResponse":
                    return self

                def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
                    _ = (exc_type, exc, tb)
                    return None

            def fake_urlopen(url: str, timeout: int = 30) -> FakeResponse:
                _ = timeout
                if url == "http://127.0.0.1:9666/json/list":
                    return FakeResponse(
                        [
                            {
                                "type": "page",
                                "url": "https://www.canva.com/design/old/edit",
                                "title": "Old Canva",
                                "webSocketDebuggerUrl": "ws://old",
                            },
                            {
                                "type": "page",
                                "url": "https://www.canva.com/design/new/edit",
                                "title": "New Canva",
                                "webSocketDebuggerUrl": "ws://new",
                            },
                        ]
                    )
                if url == "https://example.com/new-image.png":
                    return FakeResponse(b"new-canva-image")
                raise AssertionError(url)

            def fake_cdp(
                ws_url: str, *, method: str, params: dict[str, object]
            ) -> dict[str, object]:
                _ = method
                _ = params
                if ws_url == "ws://new":
                    return {
                        "result": {
                            "result": {"value": "https://example.com/new-image.png"}
                        }
                    }
                return {
                    "result": {"result": {"value": "https://example.com/old-image.png"}}
                }

            with (
                patch(
                    "runtime_v2.agent_browser.cdp_capture.urllib.request.urlopen",
                    side_effect=fake_urlopen,
                ),
                patch(
                    "runtime_v2.agent_browser.cdp_capture._cdp_command",
                    side_effect=fake_cdp,
                ),
            ):
                asset_path, _ = capture_primary_image_asset(
                    9666,
                    "canva.com",
                    output_path,
                    service="canva",
                )
                self.assertTrue(asset_path.exists())
                self.assertEqual(asset_path.read_bytes(), b"new-canva-image")

    def test_write_functional_evidence_bundle_copies_downloaded_video_for_geminigen(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            target_path = root / "exports" / "geminigen.mp4"

            def fake_screenshot(
                port: int, expected_url_substring: str, output_path: Path
            ) -> Path:
                _ = port
                _ = expected_url_substring
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_bytes(b"png")
                return output_path

            def fake_video(
                port: int,
                expected_url_substring: str,
                output_path: Path,
                *,
                service: str = "",
            ) -> tuple[Path, str]:
                _ = port
                _ = expected_url_substring
                _ = service
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_bytes(b"video")
                return output_path, "sha256-video"

            with (
                patch(
                    "runtime_v2.agent_browser.cdp_capture.capture_page_screenshot",
                    side_effect=fake_screenshot,
                ),
                patch(
                    "runtime_v2.agent_browser.cdp_capture.capture_primary_video_asset",
                    side_effect=fake_video,
                ),
            ):
                evidence = write_functional_evidence_bundle(
                    workspace=root,
                    service="geminigen",
                    port=9555,
                    expected_url_substring="geminigen.ai",
                    service_artifact_path=target_path,
                )
                self.assertTrue(target_path.exists())
                self.assertEqual(target_path.read_bytes(), b"video")
                self.assertEqual(evidence["sha256"], "sha256-video")

    def test_capture_primary_video_asset_reads_video_src(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "geminigen.mp4"
            encoded = base64.b64encode(b"video-bytes").decode("ascii")

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
                            "value": "https://www.geminigen.ai/api/files/example.mp4"
                        }
                    }
                }

            with (
                patch(
                    "runtime_v2.agent_browser.cdp_capture._select_page_target",
                    return_value={
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9555/devtools/page/1",
                        "url": "https://www.geminigen.ai/create/video",
                    },
                ),
                patch(
                    "runtime_v2.agent_browser.cdp_capture.urllib.request.urlopen",
                    side_effect=urllib.error.HTTPError(
                        "https://www.geminigen.ai/api/files/example.mp4",
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
                asset_path, sha256 = capture_primary_video_asset(
                    9555,
                    "geminigen.ai",
                    output_path,
                    service="geminigen",
                )
                self.assertTrue(asset_path.exists())
                self.assertEqual(asset_path.read_bytes(), b"video-bytes")
                self.assertEqual(len(sha256), 64)


if __name__ == "__main__":
    _ = unittest.main()

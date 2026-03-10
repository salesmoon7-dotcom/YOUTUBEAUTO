from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.config import RuntimeConfig
from runtime_v2.preflight import build_preflight_report, write_preflight_report


class RuntimeV2PreflightTests(unittest.TestCase):
    def test_build_preflight_report_includes_browser_services_and_warnings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = RuntimeConfig.from_root(Path(tmp_dir))
            report = build_preflight_report(config)

        self.assertEqual(report["mode"], "warn")
        self.assertIn("browser_services", report)
        self.assertIsInstance(report["warnings"], list)

    def test_write_preflight_report_creates_json_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = RuntimeConfig.from_root(Path(tmp_dir))
            with patch(
                "runtime_v2.preflight.default_browser_sessions_by_service",
                return_value={},
            ):
                output = write_preflight_report(config)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(output.name.endswith("preflight_report.json"))
        self.assertEqual(payload["schema_version"], "1.0")


if __name__ == "__main__":
    _ = unittest.main()

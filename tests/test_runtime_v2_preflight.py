from __future__ import annotations

import io
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2 import exit_codes
from runtime_v2.cli import main
from runtime_v2.config import RuntimeConfig
from runtime_v2.preflight import build_preflight_report, write_preflight_report
from runtime_v2.browser.manager import RUNTIME_APP_CONFIG


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

    def test_build_preflight_report_uses_canonical_runtime_app_config_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = RuntimeConfig.from_root(Path(tmp_dir))
            report = build_preflight_report(config)
            sources = cast(dict[str, object], report["sources"])

        self.assertEqual(
            sources["runtime_app_config"], str(RUNTIME_APP_CONFIG.resolve())
        )

    def test_build_preflight_report_includes_rvc_applio_core_and_python_warnings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root)
            fake_rvc_config = root / "rvc_config.json"
            fake_rvc_config.write_text(
                json.dumps(
                    {
                        "applio_python": str((root / "missing_python.exe").resolve()),
                        "applio_core": str((root / "missing_core.py").resolve()),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            original_path = Path

            def fake_path(value: str | Path = ".") -> Path:
                if str(value) == r"D:/YOUTUBE_AUTO/system/config/rvc_config.json":
                    return fake_rvc_config
                return original_path(value)

            with patch("runtime_v2.preflight.Path", side_effect=fake_path):
                report = build_preflight_report(config)

        warnings = cast(list[object], report["warnings"])
        warning_sources = {
            str(cast(dict[object, object], item).get("source", ""))
            for item in warnings
            if isinstance(item, dict)
        }
        self.assertIn("rvc_python", warning_sources)
        self.assertIn("rvc_core", warning_sources)

    def test_main_keeps_running_when_preflight_report_write_fails(self) -> None:
        stderr = io.StringIO()
        with (
            patch("sys.argv", ["runtime_v2.cli", "--readiness-check"]),
            patch(
                "runtime_v2.cli.write_preflight_report",
                side_effect=OSError("permission denied"),
            ),
            patch(
                "runtime_v2.cli.load_runtime_readiness",
                return_value={"ready": True, "code": "OK", "blockers": []},
            ),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = main()

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        self.assertIn("warning: preflight report write failed:", stderr.getvalue())


if __name__ == "__main__":
    _ = unittest.main()

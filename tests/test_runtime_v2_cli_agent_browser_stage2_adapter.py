from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2 import exit_codes
from runtime_v2.cli import (
    CliArgs,
    _run_agent_browser_stage2_adapter_child,
    _run_stage2_row1_probe,
)
from runtime_v2.config import RuntimeConfig


class RuntimeV2CliAgentBrowserStage2AdapterTests(unittest.TestCase):
    def test_stage2_adapter_child_writes_functional_evidence_for_genspark(
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
                with (
                    patch("runtime_v2.cli.Path.cwd", return_value=root),
                    patch(
                        "runtime_v2.cli.write_functional_evidence_bundle",
                        return_value={"service": "genspark", "sha256": "ok"},
                    ) as evidence_mock,
                ):
                    exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            evidence_mock.assert_called_once()
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["service"], "genspark")
            self.assertEqual(evidence["status"], "ok")
            self.assertTrue(bool(evidence["probe_debug_only"]))
            self.assertFalse(bool(evidence["recovery_attempted"]))
            self.assertTrue(bool(evidence["placeholder_artifact"]))

    def test_stage2_adapter_child_fails_closed_without_internal_recovery(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"
            args.runtime_root = str(root / "runtime")

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={
                        "status": "failed",
                        "error_code": "AGENT_BROWSER_TIMEOUT",
                    },
                ) as verify_mock,
                patch("runtime_v2.cli.Path.cwd", return_value=root),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            self.assertEqual(verify_mock.call_count, 1)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertTrue(bool(evidence["probe_debug_only"]))
            self.assertFalse(bool(evidence["recovery_attempted"]))
            self.assertFalse(bool(evidence["placeholder_artifact"]))
            self.assertFalse(output_path.exists())

    def test_stage2_adapter_child_writes_functional_evidence_for_canva(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "THUMB.png"
            args = CliArgs()
            args.service = "canva"
            args.port = 9666
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "canva.com"
            args.expected_title_substring = "Canva"

            with patch(
                "runtime_v2.cli.run_agent_browser_verify_job",
                return_value={"status": "ok"},
            ):
                with (
                    patch("runtime_v2.cli.Path.cwd", return_value=root),
                    patch(
                        "runtime_v2.cli.write_functional_evidence_bundle",
                        return_value={"service": "canva", "sha256": "ok"},
                    ) as evidence_mock,
                ):
                    exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        evidence_mock.assert_called_once()

    def test_stage2_row1_probe_records_all_browser_results(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root / "runtime")
            ok_result = {
                "status": "ok",
                "details": {"attach_evidence_path": str(root / "attach_evidence.json")},
                "completion": {"state": "succeeded"},
            }

            with (
                patch("runtime_v2.cli.run_genspark_job", return_value=ok_result),
                patch("runtime_v2.cli.run_seaart_job", return_value=ok_result),
                patch("runtime_v2.cli.run_geminigen_job", return_value=ok_result),
                patch("runtime_v2.cli.run_canva_job", return_value=ok_result),
            ):
                report = _run_stage2_row1_probe(
                    config=config,
                    probe_root=root / "probe",
                    run_id="stage2-row1-run-1",
                    agent_browser_services=["genspark", "seaart", "geminigen", "canva"],
                )

        self.assertEqual(report["code"], "OK")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(len(cast(list[object], report["results"])), 4)
        self.assertEqual(report["readiness_scope"], "stage2_probe")
        self.assertEqual(report["live_readiness"], "full")
        self.assertEqual(cast(list[object], report["placeholder_services"]), [])
        self.assertEqual(
            cast(list[object], report["live_ready_services"]),
            ["genspark", "seaart", "geminigen", "canva"],
        )
        self.assertTrue(bool(report["probe_success"]))

    def test_stage2_row1_probe_falls_back_after_attach_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root / "runtime")
            failed_result = {
                "status": "failed",
                "error_code": "genspark_adapter_failed",
                "details": {},
                "completion": {"state": "failed"},
            }
            ok_result = {
                "status": "ok",
                "details": {},
                "completion": {"state": "succeeded"},
            }

            with (
                patch(
                    "runtime_v2.cli.run_genspark_job",
                    side_effect=[failed_result, ok_result],
                ),
                patch("runtime_v2.cli.run_seaart_job", return_value=ok_result),
                patch("runtime_v2.cli.run_geminigen_job", return_value=ok_result),
                patch("runtime_v2.cli.run_canva_job", return_value=ok_result),
            ):
                report = _run_stage2_row1_probe(
                    config=config,
                    probe_root=root / "probe",
                    run_id="stage2-row1-run-2",
                    agent_browser_services=["genspark"],
                )

        self.assertEqual(report["code"], "OK")
        first = cast(list[dict[str, object]], report["results"])[0]
        self.assertTrue(bool(first["attach_attempt_failed"]))
        self.assertTrue(bool(first["fallback_used"]))
        self.assertEqual(report["readiness_scope"], "stage2_probe")
        self.assertEqual(report["live_readiness"], "partial")
        self.assertEqual(
            cast(list[object], report["placeholder_services"]),
            ["genspark", "seaart", "geminigen", "canva"],
        )
        self.assertEqual(cast(list[object], report["live_ready_services"]), [])
        self.assertTrue(bool(report["probe_success"]))


if __name__ == "__main__":
    _ = unittest.main()

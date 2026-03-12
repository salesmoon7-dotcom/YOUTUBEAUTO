from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime_v2.config import RuntimeConfig
from runtime_v2.soak_report import (
    append_soak_event,
    build_soak_snapshot,
    load_soak_events,
    summarize_soak_events,
    write_soak_report,
)


class RuntimeV2SoakReportTests(unittest.TestCase):
    def test_soak_report_summarizes_events_and_writes_markdown(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = RuntimeConfig.from_root(Path(tmp_dir) / "runtime")
            _ = append_soak_event(
                config,
                run_id="run-1",
                mode="once",
                status="ok",
                code="OK",
                exit_code=0,
                debug_log="logs/run-1.jsonl",
                summary={
                    "manifest_path": "",
                    "final_artifact_path": "artifact-a.mp4",
                    "soak_snapshot": {
                        "promotion_gates": {
                            "A": {"passed": True, "reason": ""},
                            "B": {"passed": True, "reason": ""},
                            "C": {
                                "passed": False,
                                "reason": "missing_voice_json_or_kenburns_role",
                            },
                            "D": {"passed": True, "reason": ""},
                        }
                    },
                },
            )
            _ = append_soak_event(
                config,
                run_id="run-2",
                mode="once",
                status="failed",
                code="GPU_LEASE_BUSY",
                exit_code=10,
                debug_log="logs/run-2.jsonl",
                summary={"manifest_path": "manifest.json", "final_artifact_path": ""},
            )

            events = load_soak_events(config.soak_events_file)
            summary = summarize_soak_events(events)
            report_path = write_soak_report(config)
            report_text = report_path.read_text(encoding="utf-8")

        self.assertEqual(summary["observation_count"], 2)
        self.assertEqual(summary["gpu_duplicate_count"], 1)
        self.assertEqual(summary["failure_count"], 1)
        self.assertIn("# Soak 24h Report", report_text)
        self.assertIn("GPU Duplicate Run: 1", report_text)
        self.assertIn("manifest.json", report_text)
        self.assertIn("Gate C: FAIL missing_voice_json_or_kenburns_role", report_text)

    def test_build_soak_snapshot_uses_readiness_payload(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = RuntimeConfig.from_root(Path(tmp_dir) / "runtime")
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")

            snapshot = build_soak_snapshot(config)

        self.assertIn("ready", snapshot)
        self.assertIn("code", snapshot)
        self.assertIn("blockers", snapshot)


if __name__ == "__main__":
    _ = unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.debug_log import summarize_cli_report
from runtime_v2.gpt.floor import write_gpt_status
from runtime_v2.gpt_autospawn import apply_autospawn_decision
from runtime_v2.gpt_pool_monitor import monitor_gpt_pool, tick_gpt_status
from runtime_v2.supervisor import gpt_endpoints_from_browser_runtime


class RuntimeV2GptHealthTests(unittest.TestCase):
    def test_summarize_cli_report_preserves_top_level_failure_code(self) -> None:
        summary = summarize_cli_report(
            {
                "run_id": "run-1",
                "event": "run_finished",
                "mode": "control_once",
                "status": "failed",
                "code": "native_genspark_not_implemented",
                "exit_code": 1,
                "result": {
                    "status": "failed",
                    "code": "native_genspark_not_implemented",
                    "job": {
                        "job_id": "job-1",
                        "workload": "genspark",
                        "status": "retry",
                    },
                    "result": {"status": "ok", "code": "OK"},
                    "worker_result": {
                        "status": "failed",
                        "stage": "genspark",
                        "error_code": "native_genspark_not_implemented",
                    },
                    "recovery": {"action": "retry", "backoff_sec": 30.0},
                },
            },
            Path("system/runtime_v2/logs/run-1.jsonl"),
        )

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["code"], "native_genspark_not_implemented")
        self.assertEqual(summary["error_code"], "native_genspark_not_implemented")

    def test_apply_autospawn_decision_handles_non_finite_status_fields(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            status_file = root / "health" / "gpt_status.json"
            config = RuntimeConfig(
                gpt_status_file=status_file,
                gpt_spawn_cooldown_sec=300,
                gpt_spawn_hourly_limit=2,
            )
            _ = write_gpt_status(
                {
                    "schema_version": "1.0",
                    "runtime": "runtime_v2",
                    "checked_at": 1.0,
                    "ok_count": 0,
                    "min_ok": 1,
                    "floor_breached": True,
                    "breach_started_at": 1.0,
                    "breach_sec": 300,
                    "pending_boot": float("inf"),
                    "last_spawn_at": float("nan"),
                    "spawn_fail_count": 0,
                    "spawn_needed": True,
                    "warning_active": True,
                    "last_warning_at": 1.0,
                    "cooldown_sec": 300,
                    "cooldown_elapsed_sec": 0,
                    "hourly_spawn_count": 0,
                    "spawn_history": [float("nan")],
                    "endpoints": [],
                },
                status_file,
            )

            result = apply_autospawn_decision(status_file, config)

        self.assertTrue(bool(result["spawned"]))
        self.assertEqual(result["pending_boot"], 1)

    def test_monitor_gpt_pool_fail_closes_when_min_ok_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            status_file = root / "health" / "gpt_status.json"
            _ = write_gpt_status(
                {
                    "schema_version": "1.0",
                    "runtime": "runtime_v2",
                    "checked_at": 1.0,
                    "ok_count": 0,
                    "min_ok": "bad-min-ok",
                    "floor_breached": True,
                    "breach_started_at": 1.0,
                    "breach_sec": 1,
                    "pending_boot": 0,
                    "last_spawn_at": None,
                    "spawn_fail_count": 0,
                    "spawn_needed": True,
                    "warning_active": True,
                    "last_warning_at": 1.0,
                    "cooldown_sec": 300,
                    "cooldown_elapsed_sec": 1,
                    "hourly_spawn_count": 0,
                    "spawn_history": [],
                    "endpoints": [],
                },
                status_file,
            )

            result = monitor_gpt_pool(status_file)

        self.assertFalse(bool(result["ok"]))
        self.assertEqual(result["ok_count"], 0)

    def test_tick_gpt_status_uses_browser_health_as_actual_gpt_source(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            status_file = root / "health" / "gpt_status.json"
            browser_health_file = root / "health" / "browser_health.json"
            fresh_seen_at = round(time(), 3)
            config = RuntimeConfig(
                gpt_status_file=status_file,
                browser_health_file=browser_health_file,
                gpt_floor_min_ok=1,
            )
            browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            _ = write_gpt_status(
                {
                    "schema_version": "1.0",
                    "runtime": "runtime_v2",
                    "checked_at": 1.0,
                    "ok_count": 0,
                    "min_ok": 1,
                    "floor_breached": True,
                    "breach_started_at": 1.0,
                    "breach_sec": 100,
                    "pending_boot": 0,
                    "last_spawn_at": None,
                    "spawn_fail_count": 0,
                    "spawn_needed": True,
                    "warning_active": True,
                    "last_warning_at": 1.0,
                    "cooldown_sec": 300,
                    "cooldown_elapsed_sec": 100,
                    "hourly_spawn_count": 0,
                    "spawn_history": [],
                    "endpoints": [
                        {"name": "default", "status": "FAILED", "last_seen_at": 1.0}
                    ],
                },
                status_file,
            )
            _ = browser_health_file.write_text(
                f'{{"schema_version":"1.0","runtime":"runtime_v2","run_id":"run-1","checked_at":{fresh_seen_at},"session_count":1,"healthy_count":1,"unhealthy_count":0,"sessions":[{{"service":"chatgpt","group":"llm","healthy":true,"last_seen_at":{fresh_seen_at}}}]}}',
                encoding="utf-8",
            )

            result = tick_gpt_status(status_file, config)

        self.assertEqual(result["ok_count"], 1)
        self.assertFalse(bool(result["floor_breached"]))
        endpoints = result["endpoints"]
        self.assertIsInstance(endpoints, list)
        typed_endpoints = cast(list[dict[str, object]], endpoints)
        self.assertEqual(str(typed_endpoints[0]["status"]), "OK")

    def test_supervisor_only_counts_chatgpt_session_for_gpt_floor(self) -> None:
        endpoints = gpt_endpoints_from_browser_runtime(
            {
                "sessions": [
                    {"service": "genspark", "group": "llm", "healthy": True},
                    {"service": "geminigen", "group": "llm", "healthy": True},
                ]
            },
            force_gpt_fail=False,
        )

        self.assertEqual(endpoints, [])


if __name__ == "__main__":
    _ = unittest.main()

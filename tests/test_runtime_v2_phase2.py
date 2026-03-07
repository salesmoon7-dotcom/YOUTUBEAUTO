from __future__ import annotations

import json
import sys
import socket
import tempfile
import threading
import unittest
from typing import override
from pathlib import Path
from typing import cast
from unittest.mock import patch

from http.server import BaseHTTPRequestHandler, HTTPServer

from runtime_v2 import exit_codes
from runtime_v2.cli import exit_code_from_status, main
from runtime_v2.config import RuntimeConfig
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status
from runtime_v2.gpu.lease import LeaseStore, lease_key_for_workload
from runtime_v2.n8n_adapter import build_n8n_webhook_response, post_callback
from runtime_v2.gpt.floor import write_gpt_status
from runtime_v2.supervisor import run_once, run_selftest


class RuntimeV2Phase2Tests(unittest.TestCase):
    def test_exit_code_mapping_includes_callback_fail(self) -> None:
        self.assertEqual(exit_code_from_status("OK"), exit_codes.SUCCESS)
        self.assertEqual(exit_code_from_status("GPU_LEASE_BUSY"), exit_codes.LEASE_BUSY)
        self.assertEqual(exit_code_from_status("CALLBACK_FAIL"), exit_codes.CALLBACK_FAIL)
        self.assertEqual(exit_code_from_status("UNKNOWN"), exit_codes.CLI_USAGE)

    def test_n8n_payload_preserves_required_schema(self) -> None:
        payload = build_n8n_webhook_response(
            {"status": "ok", "code": "OK"},
            callback_url="https://example.test/webhook",
            run_id="run-1",
            mode="once",
            exit_code=0,
        )
        self.assertEqual(
            set(payload),
            {
                "schema_version",
                "execution_env",
                "callback_url",
                "run_id",
                "mode",
                "exit_code",
                "ok",
                "runtime",
                "status",
            },
        )
        self.assertEqual(payload["execution_env"], "remote_n8n")

    def test_post_callback_retries_until_success(self) -> None:
        attempts: list[int] = []

        class RetryHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                content_length = int(self.headers.get("Content-Length", "0"))
                _ = self.rfile.read(content_length)
                attempts.append(1)
                if len(attempts) < 3:
                    self.send_response(500)
                else:
                    self.send_response(202)
                self.end_headers()

            @override
            def log_message(self, format: str, *args: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), RetryHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            callback_url = f"http://127.0.0.1:{server.server_port}/webhook"
            payload = build_n8n_webhook_response(
                {"status": "ok", "code": "OK"},
                callback_url=callback_url,
                run_id="run-1",
                mode="once",
                exit_code=0,
            )
            result = post_callback(payload, timeout_sec=0.2, max_attempts=3, backoff_sec=0.01)
            self.assertTrue(result["ok"])
            self.assertEqual(result["attempts"], 3)
            self.assertEqual(result["status_code"], 202)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_main_returns_callback_fail_when_post_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            gui_status_out = str(Path(tmp_dir) / "gui_status.json")
            args = [
                "runtime_v2.cli",
                "--once",
                "--callback-url",
                "http://127.0.0.1:1/webhook",
                "--gui-status-out",
                gui_status_out,
            ]
            with patch.object(sys, "argv", args):
                exit_code = main()
            self.assertEqual(exit_code, exit_codes.CALLBACK_FAIL)

    def test_gui_status_write_is_atomic_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "gui_status.json"
            payload = build_gui_status_payload(
                {"status": "ok", "code": "OK"},
                run_id="run-1",
                mode="once",
                stage="finished",
                exit_code=0,
            )
            written = write_gui_status(payload, output)
            raw_loaded = cast(object, json.loads(written.read_text(encoding="utf-8")))
            self.assertIsInstance(raw_loaded, dict)
            if not isinstance(raw_loaded, dict):
                self.fail("gui status payload is not an object")
            raw_loaded_dict = cast(dict[object, object], raw_loaded)
            loaded: dict[str, object] = {}
            for raw_name, raw_value in raw_loaded_dict.items():
                loaded[str(raw_name)] = raw_value
            self.assertEqual(loaded["execution_env"], "local_gui")
            self.assertEqual(loaded["run_id"], "run-1")

    def test_stale_lease_is_recovered_from_persisted_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            lease_file = Path(tmp_dir) / "gpu_scheduler_health.json"
            store = LeaseStore(lease_file=lease_file)
            lease_key = lease_key_for_workload("qwen3_tts")
            acquired = store.acquire(
                lease_key,
                owner="runtime_v2",
                ttl_sec=1,
                run_id="run-1",
                pid=999999,
                started_at=1.0,
                host=socket.gethostname(),
            )
            self.assertIsNotNone(acquired)

            recovered = LeaseStore(lease_file=lease_file)
            reacquired = recovered.acquire(
                lease_key,
                owner="runtime_v2",
                ttl_sec=1,
                run_id="run-2",
                pid=999998,
                started_at=2.0,
                host=socket.gethostname(),
            )
            self.assertIsNotNone(reacquired)
            if reacquired is None:
                self.fail("stale lease was not recovered")
            self.assertEqual(reacquired.run_id, "run-2")

    def test_run_once_and_selftest_use_persistent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                lease_file=root / "gpu_scheduler_health.json",
                gui_status_file=root / "gui_status.json",
            )
            once = run_once(owner="runtime_v2", run_id="run-1", config=config)
            self.assertEqual(once["code"], "OK")
            self.assertTrue(config.lease_file.exists())

            selftest = run_selftest(
                owner="runtime_v2",
                run_id="run-1",
                config=config,
                inject_browser_fail=True,
                inject_gpt_fail=True,
            )
            self.assertEqual(selftest["code"], "OK")
            checks = selftest.get("checks")
            self.assertIsInstance(checks, list)
            if not isinstance(checks, list):
                self.fail("selftest checks missing")
            raw_checks = cast(list[object], checks)
            typed_checks: list[dict[object, object]] = []
            for entry in raw_checks:
                if isinstance(entry, dict):
                    typed_checks.append(cast(dict[object, object], entry))
            check_names: set[str] = set()
            for check in typed_checks:
                if "name" in check:
                    check_names.add(str(check["name"]))
            self.assertIn("injected_browser_fail", check_names)
            self.assertIn("injected_gpt_fail", check_names)

    def test_run_once_uses_existing_gpt_status_source_instead_of_fake_ok_endpoint(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(gpt_status_file=root / "health" / "gpt_status.json")
            _ = write_gpt_status(
                {
                    "schema_version": "1.0",
                    "runtime": "runtime_v2",
                    "checked_at": 1.0,
                    "ok_count": 0,
                    "min_ok": 1,
                    "floor_breached": True,
                    "breach_started_at": 1.0,
                    "breach_sec": 10,
                    "pending_boot": 0,
                    "last_spawn_at": None,
                    "spawn_fail_count": 0,
                    "spawn_needed": False,
                    "warning_active": True,
                    "last_warning_at": 1.0,
                    "cooldown_sec": 300,
                    "cooldown_elapsed_sec": 10,
                    "hourly_spawn_count": 0,
                    "spawn_history": [],
                    "endpoints": [{"name": "default", "status": "FAILED", "last_seen_at": 1.0}],
                },
                config.gpt_status_file,
            )

            result = run_once(
                owner="runtime_v2",
                run_id="chatgpt-run-1",
                config=config,
                workload="chatgpt",
                require_browser_healthy=False,
                worker_runner=lambda: {"status": "ok", "stage": "chatgpt"},
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "GPT_FLOOR_FAIL")

    def test_selftest_probe_child_keeps_run_id_aligned_across_outputs(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            probe_root = Path(tmp_dir) / "probe"
            args = [
                "runtime_v2.cli",
                "--selftest-probe-child",
                "--probe-root",
                str(probe_root),
            ]
            with (
                patch("runtime_v2.browser.manager._probe_local_port", return_value=True),
                patch("runtime_v2.browser.manager._launch_debug_browser", return_value=True),
                patch.object(sys, "argv", args),
            ):
                exit_code = main()

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            probe_result = cast(dict[object, object], json.loads((probe_root / "probe_result.json").read_text(encoding="utf-8")))
            gui_status = cast(dict[object, object], json.loads((probe_root / "health" / "gui_status.json").read_text(encoding="utf-8")))
            result_snapshot = cast(dict[object, object], json.loads((probe_root / "evidence" / "result.json").read_text(encoding="utf-8")))
            browser_health = cast(dict[object, object], json.loads((probe_root / "health" / "browser_health.json").read_text(encoding="utf-8")))

            run_id = str(probe_result["run_id"])
            result_metadata = cast(dict[object, object], result_snapshot["metadata"])
            self.assertEqual(str(gui_status["run_id"]), run_id)
            self.assertEqual(str(result_metadata["run_id"]), run_id)
            self.assertEqual(str(browser_health["run_id"]), run_id)

    def test_control_once_detached_propagates_seed_mock_chain_flag(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            probe_root = Path(tmp_dir) / "probe"
            args = [
                "runtime_v2.cli",
                "--control-once-detached",
                "--seed-mock-chain",
                "--probe-root",
                str(probe_root),
            ]
            with (
                patch.object(sys, "argv", args),
                patch("runtime_v2.cli.subprocess.Popen") as popen,
            ):
                popen.return_value.pid = 12345
                exit_code = main()

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            called_command = popen.call_args.args[0]
            self.assertIn("--seed-mock-chain", called_command)

    def test_control_once_probe_child_seed_mock_chain_runs_to_final_output(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            probe_root = Path(tmp_dir) / "probe"
            args = [
                "runtime_v2.cli",
                "--control-once-probe-child",
                "--seed-mock-chain",
                "--probe-root",
                str(probe_root),
            ]

            with patch.object(sys, "argv", args):
                exit_code = main()

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            probe_result = cast(dict[object, object], json.loads((probe_root / "probe_result.json").read_text(encoding="utf-8")))
            result_snapshot = cast(dict[object, object], json.loads((probe_root / "evidence" / "result.json").read_text(encoding="utf-8")))
            result_metadata = cast(dict[object, object], result_snapshot["metadata"])
            events_path = probe_root / "evidence" / "control_plane_events.jsonl"
            event_lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertTrue(event_lines)
            final_event = cast(dict[object, object], json.loads(event_lines[-1]))

            self.assertEqual(str(probe_result["status"]), "ok")
            self.assertEqual(str(probe_result["code"]), "OK")
            self.assertEqual(str(result_metadata["run_id"]), str(probe_result["run_id"]))
            self.assertEqual(str(result_metadata["completion_state"]), "completed")
            self.assertTrue(bool(result_metadata["final_output"]))
            self.assertEqual(str(final_event.get("event", "")), "job_summary")
            self.assertEqual(str(final_event.get("completion_state", "")), "completed")
            self.assertTrue(bool(final_event.get("final_output", False)))


if __name__ == "__main__":
    _ = unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from runtime_v2.cli import main
from runtime_v2.config import RuntimeConfig
from runtime_v2.control_plane import seed_local_jobs
from runtime_v2.manager import seed_excel_row
from runtime_v2.supervisor import run_once


def _write_excel_fixture(path: Path, *, topic: str, status: str = "") -> Path:
    workbook = Workbook()
    sheet = cast(Worksheet, workbook.active)
    sheet.title = "Sheet1"
    sheet.append(["Topic", "Status"])
    sheet.append([topic, status])
    workbook.save(path)
    workbook.close()
    return path


def _write_excel_headers_fixture(
    path: Path, *, headers: list[str], values: list[str]
) -> Path:
    workbook = Workbook()
    sheet = cast(Worksheet, workbook.active)
    sheet.title = "Sheet1"
    sheet.append(headers)
    sheet.append(values)
    workbook.save(path)
    workbook.close()
    return path


class RuntimeV2ExcelBridgeTests(unittest.TestCase):
    def test_excel_topic_row_seeds_topic_spec_before_stage1_runner(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                input_root=root / "inbox",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
            )
            excel_path = _write_excel_fixture(root / "topic.xlsx", topic="Bridge topic")

            result = seed_excel_row(
                config=config,
                run_id="excel-audit-run-1",
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
            )

        self.assertEqual(result["status"], "seeded")
        topic_spec = cast(dict[str, object], result["topic_spec"])
        self.assertEqual(str(topic_spec["topic"]), "Bridge topic")
        self.assertEqual(str(topic_spec["row_ref"]), "Sheet1!row1")

    def test_topic_spec_remains_excel_agnostic_while_job_payload_keeps_excel_context(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                input_root=root / "inbox",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
            )
            excel_path = _write_excel_fixture(root / "topic.xlsx", topic="Bridge topic")

            result = seed_excel_row(
                config=config,
                run_id="excel-run-1",
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
            )

            payload = result["topic_spec"]
            self.assertIsInstance(payload, dict)
            queued_jobs = seed_local_jobs(config)
            self.assertEqual(queued_jobs, [])
            self.assertFalse(config.queue_store_file.exists())
            contract_text = str(result.get("contract", {}))
            self.assertIn("excel_path", contract_text)
            self.assertIn("sheet_name", contract_text)
            self.assertIn("row_index", contract_text)
            snapshot_hash = str(
                cast(dict[str, object], payload).get("excel_snapshot_hash", "")
            )
            self.assertIn(
                f"'checkpoint_key': 'topic_spec:Sheet1!row1:{snapshot_hash}'",
                contract_text,
            )
            self.assertIn("'local_only': True", contract_text)
            self.assertNotIn("excel_path", str(payload))

    def test_excel_seed_uses_checkpoint_key_and_local_only_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                input_root=root / "inbox",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
            )
            excel_path = _write_excel_fixture(root / "topic.xlsx", topic="Bridge topic")

            result = seed_excel_row(
                config=config,
                run_id="excel-run-1",
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
            )

            self.assertEqual(result["status"], "seeded")
            contract_files = list((config.input_root / "chatgpt").glob("*.job.json"))
            self.assertEqual(len(contract_files), 1)
            contract_text = contract_files[0].read_text(encoding="utf-8")
            self.assertIn('"local_only": true', contract_text)
            self.assertIn('"checkpoint_key": "topic_spec:Sheet1!row1:', contract_text)
            self.assertIn('"excel_path":', contract_text)
            self.assertIn('"sheet_name": "Sheet1"', contract_text)
            self.assertIn('"row_index": 0', contract_text)

    def test_excel_selector_accepts_case_insensitive_headers(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(input_root=root / "inbox")
            excel_path = _write_excel_headers_fixture(
                root / "topic.xlsx",
                headers=["topic", "STATUS"],
                values=["Bridge topic", ""],
            )

            result = seed_excel_row(
                config=config,
                run_id="excel-run-1",
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
            )

            self.assertEqual(result["status"], "seeded")

    def test_resident_worker_poll_enforces_configured_stable_file_age(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                input_root=root / "inbox",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
                stable_file_age_sec=999,
            )
            contract_root = config.input_root / "chatgpt"
            contract_root.mkdir(parents=True, exist_ok=True)
            contract_path = contract_root / "fresh.job.json"
            _ = contract_path.write_text(
                '{"contract":"runtime_v2_inbox_job","contract_version":"1.0","local_only":true,"job":{"job_id":"fresh-chatgpt","worker":"chatgpt","checkpoint_key":"topic_spec:Sheet1!row1","payload":{"run_id":"run-1","topic_spec":{"run_id":"run-1","row_ref":"Sheet1!row1","topic":"T","status_snapshot":"","excel_snapshot_hash":"x"}}}}',
                encoding="utf-8",
            )

            seeded = seed_local_jobs(config)

            self.assertEqual(seeded, [])

    def test_no_work_fast_path_skips_worker_launch_and_is_not_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            excel_path = _write_excel_fixture(root / "topic.xlsx", topic="", status="")

            with patch("runtime_v2.cli.run_control_loop_once") as run_control_loop_once:
                with patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--excel-once",
                        "--excel-path",
                        str(excel_path),
                        "--sheet-name",
                        "Sheet1",
                        "--row-index",
                        "0",
                    ],
                ):
                    exit_code = main()

            self.assertEqual(exit_code, 0)
            run_control_loop_once.assert_not_called()

    def test_excel_once_rejects_negative_row_index(self) -> None:
        with patch(
            "sys.argv",
            [
                "runtime_v2.cli",
                "--excel-once",
                "--excel-path",
                "topic.xlsx",
                "--sheet-name",
                "Sheet1",
                "--row-index",
                "-1",
            ],
        ):
            exit_code = main()

        self.assertEqual(exit_code, 2)

    def test_excel_once_seeded_path_does_not_report_idle_while_waiting_for_stable_age(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            excel_path = _write_excel_fixture(
                root / "topic.xlsx", topic="Bridge topic", status=""
            )

            with patch("runtime_v2.cli.run_control_loop_once") as run_control_loop_once:
                with patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--excel-once",
                        "--excel-path",
                        str(excel_path),
                        "--sheet-name",
                        "Sheet1",
                        "--row-index",
                        "0",
                    ],
                ):
                    exit_code = main()

            self.assertEqual(exit_code, 0)
            run_control_loop_once.assert_not_called()

    def test_main_does_not_swallow_keyboard_interrupt(self) -> None:
        with patch(
            "sys.argv",
            [
                "runtime_v2.cli",
                "--selftest",
            ],
        ):
            with patch("runtime_v2.cli.run_selftest", side_effect=KeyboardInterrupt()):
                with self.assertRaises(KeyboardInterrupt):
                    _ = main()

    def test_main_does_not_swallow_system_exit(self) -> None:
        with patch(
            "sys.argv",
            [
                "runtime_v2.cli",
                "--selftest",
            ],
        ):
            with patch("runtime_v2.cli.run_selftest", side_effect=SystemExit(7)):
                with self.assertRaises(SystemExit) as raised:
                    _ = main()

        self.assertEqual(raised.exception.code, 7)

    def test_preflight_login_guard_checks_only_required_services(self) -> None:
        browser_runtime = {
            "sessions": [
                {"service": "chatgpt", "healthy": True},
                {"service": "genspark", "healthy": False},
            ]
        }
        with patch("runtime_v2.supervisor.BrowserManager.start"):
            with patch(
                "runtime_v2.supervisor.BrowserSupervisor.tick",
                return_value=browser_runtime,
            ):
                result = run_once(
                    owner="runtime_v2",
                    run_id="chatgpt-run-1",
                    workload="chatgpt",
                    worker_runner=lambda: {"status": "ok"},
                )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["code"], "OK")


if __name__ == "__main__":
    _ = unittest.main()

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import run_control_loop_once
from runtime_v2.queue_store import QueueStore


class RuntimeV2ControlPlaneCloseoutStateTests(unittest.TestCase):
    def test_run_control_loop_short_circuits_when_same_run_already_terminal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            config.queue_store_file.parent.mkdir(parents=True, exist_ok=True)
            config.closeout_state_file.parent.mkdir(parents=True, exist_ok=True)
            config.queue_store_file.write_text("[]", encoding="utf-8")
            config.control_plane_events_file.write_text("", encoding="utf-8")
            config.closeout_state_file.write_text(
                json.dumps(
                    {
                        "run_id": "closeout-run-1",
                        "status": "failed",
                        "reason": "BROWSER_UNHEALTHY",
                        "attempt": 1,
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            result = run_control_loop_once(
                owner="test-owner",
                config=config,
                run_id="closeout-run-1",
                allow_runtime_side_effects=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_UNHEALTHY")

    def test_run_control_loop_reports_backoff_wait_when_same_run_backlog_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            config.queue_store_file.parent.mkdir(parents=True, exist_ok=True)
            config.closeout_state_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.write_text("", encoding="utf-8")
            run_id = "backoff-wait-run"
            row_ref = "Sheet1!row15"
            future_retry_at = time.time() + 3600
            queue_store = QueueStore(config.queue_store_file)
            queue_store.save(
                [
                    JobContract(
                        job_id="chatgpt-backoff-wait-run",
                        workload="chatgpt",
                        status="completed",
                        checkpoint_key="topic_spec:Sheet1!row15:backoff-wait-run",
                        payload={"run_id": run_id, "row_ref": row_ref},
                    ),
                    JobContract(
                        job_id="genspark-backoff-wait-run-1",
                        workload="genspark",
                        status="retry",
                        attempts=1,
                        checkpoint_key="derived:genspark:backoff-wait-run:1",
                        payload={
                            "run_id": run_id,
                            "row_ref": row_ref,
                            "promotion_gate": "A",
                            "last_error_code": "BROWSER_UNHEALTHY",
                            "next_attempt_at": future_retry_at,
                        },
                    ),
                    JobContract(
                        job_id="geminigen-backoff-wait-run-1",
                        workload="geminigen",
                        status="queued",
                        checkpoint_key="derived:geminigen:backoff-wait-run:1",
                        payload={
                            "run_id": run_id,
                            "row_ref": row_ref,
                            "promotion_gate": "B",
                        },
                    ),
                    JobContract(
                        job_id="render-backoff-wait-run",
                        workload="render",
                        status="queued",
                        checkpoint_key="derived:render:backoff-wait-run",
                        payload={
                            "run_id": run_id,
                            "row_ref": row_ref,
                            "promotion_gate": "D",
                        },
                    ),
                ]
            )

            result = run_control_loop_once(
                owner="test-owner",
                config=config,
                run_id=run_id,
                allow_runtime_side_effects=False,
            )
            closeout_state = json.loads(
                config.closeout_state_file.read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "waiting")
        self.assertEqual(result["code"], "BACKOFF_WAIT")
        self.assertEqual(result["queue_status"], "backoff_wait")
        self.assertEqual(closeout_state["status"], "running")
        self.assertEqual(closeout_state["reason"], "backoff_wait")
        self.assertNotEqual(closeout_state["status"], "completed")
        self.assertNotEqual(closeout_state["reason"], "NO_JOB")

    def test_current_terminal_failure_writes_failed_closeout_state(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.write_text("", encoding="utf-8")
            run_id = "restart-exhausted-run"
            queue_store = QueueStore(config.queue_store_file)
            queue_store.save(
                [
                    JobContract(
                        job_id="geminigen-restart-exhausted-run-5",
                        workload="geminigen",
                        checkpoint_key="derived:geminigen:restart-exhausted-run:5",
                        payload={
                            "run_id": run_id,
                            "row_ref": "Sheet1!row15",
                            "promotion_gate": "B",
                        },
                    )
                ]
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                return_value={
                    "status": "failed",
                    "code": "BROWSER_RESTART_EXHAUSTED",
                    "worker_result": {
                        "status": "failed",
                        "stage": "runtime_preflight",
                        "error_code": "BROWSER_RESTART_EXHAUSTED",
                        "retryable": False,
                        "details": {
                            "blocked_reason": "restart_budget_exhausted"
                        },
                        "completion": {
                            "state": "failed",
                            "final_output": False,
                        },
                    },
                },
            ):
                result = run_control_loop_once(
                    owner="test-owner",
                    config=config,
                    run_id=run_id,
                    allow_runtime_side_effects=False,
                )
            closeout_state = json.loads(
                config.closeout_state_file.read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_RESTART_EXHAUSTED")
        self.assertEqual(closeout_state["run_id"], run_id)
        self.assertEqual(closeout_state["status"], "failed")
        self.assertEqual(closeout_state["reason"], "BROWSER_RESTART_EXHAUSTED")

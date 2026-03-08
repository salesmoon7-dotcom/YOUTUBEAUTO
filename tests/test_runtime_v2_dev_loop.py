from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime_v2.config import RuntimeConfig, allowed_workloads
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import run_control_loop_once, seed_control_job
from runtime_v2.dev_writer_lock import (
    acquire_repo_writer_lock,
    release_repo_writer_lock,
)
from runtime_v2.latest_run import load_joined_latest_run
from runtime_v2.stage1.gpt_plan_parser import (
    extract_dev_loop_plan_json,
    parse_dev_loop_plan,
)
from runtime_v2.workers.dev_implement_worker import run_dev_implement_job


def _runtime_config(root: Path) -> RuntimeConfig:
    return RuntimeConfig.from_root(root)


class RuntimeV2DevLoopTests(unittest.TestCase):
    def test_dev_loop_workloads_are_registered(self) -> None:
        workloads = allowed_workloads()

        self.assertIn("dev_plan", workloads)
        self.assertIn("dev_implement", workloads)
        self.assertIn("dev_replan", workloads)

    def test_extract_dev_loop_plan_requires_json_fence(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_dev_loop_json_fence"):
            _ = extract_dev_loop_plan_json('plain text {"goal": "x"}')

    def test_parse_dev_loop_plan_requires_required_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_browser_checks"):
            _ = parse_dev_loop_plan(
                {
                    "goal": "ship feature",
                    "tasks": ["implement"],
                    "verification": ["pytest"],
                    "replan_on_failure": True,
                }
            )

    def test_dev_implement_worker_requires_repo_writer_lock(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            lock = acquire_repo_writer_lock(config.lock_root, owner="foreign-owner")
            self.assertTrue(lock["locked"])
            job = JobContract(
                job_id="dev-implement-job",
                workload="dev_implement",
                checkpoint_key="seed:dev-implement-job",
                payload={"run_id": "dev-run-1", "tasks": ["implement"]},
            )

            try:
                result = run_dev_implement_job(job, config.artifact_root, config=config)
            finally:
                release_repo_writer_lock(config.lock_root, owner="foreign-owner")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "repo_writer_lock_busy")

    def test_dev_loop_failure_seeds_replan_job_with_same_run_id(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            plan = {
                "goal": "verify closed loop",
                "tasks": ["implement feature"],
                "verification": ["pytest"],
                "browser_checks": [
                    {
                        "service": "chatgpt",
                        "port": 9222,
                        "expected_url_substring": "chatgpt.com",
                    }
                ],
                "replan_on_failure": True,
            }
            seed_control_job(
                JobContract(
                    job_id="dev-plan-job",
                    workload="dev_plan",
                    checkpoint_key="seed:dev-plan-job",
                    payload={"run_id": "dev-run-1", "plan": plan},
                ),
                config=config,
            )

            result_plan = run_control_loop_once(
                owner="runtime_v2",
                config=config,
                run_id="control-run-dev-plan",
                allow_runtime_side_effects=False,
            )
            result_implement = run_control_loop_once(
                owner="runtime_v2",
                config=config,
                run_id="control-run-dev-implement",
                allow_runtime_side_effects=False,
            )
            result_verify = run_control_loop_once(
                owner="runtime_v2",
                config=config,
                run_id="control-run-dev-verify",
                allow_runtime_side_effects=False,
            )

            queue_payload = json.loads(
                config.queue_store_file.read_text(encoding="utf-8")
            )
            queued_items = [item for item in queue_payload if isinstance(item, dict)]
            replan_job = next(
                item
                for item in queued_items
                if str(item.get("workload", "")) == "dev_replan"
            )

        self.assertEqual(result_plan["status"], "ok")
        self.assertEqual(result_implement["status"], "ok")
        self.assertEqual(result_verify["code"], "BROWSER_BLOCKED")
        self.assertEqual(str(replan_job["status"]), "queued")
        self.assertEqual(str(replan_job["payload"]["run_id"]), "dev-run-1")

    def test_agent_browser_verify_respects_allow_runtime_side_effects_false(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="agent-browser-safe-job",
                    workload="agent_browser_verify",
                    checkpoint_key="seed:agent-browser-safe-job",
                    payload={
                        "run_id": "dev-run-safe",
                        "service": "chatgpt",
                        "expected_url_substring": "chatgpt.com",
                    },
                ),
                config=config,
            )

            result = run_control_loop_once(
                owner="runtime_v2",
                config=config,
                run_id="control-run-safe-browser",
                allow_runtime_side_effects=False,
            )
            queue_payload = json.loads(
                config.queue_store_file.read_text(encoding="utf-8")
            )
            queued_items = [item for item in queue_payload if isinstance(item, dict)]
            job_payload = next(
                item
                for item in queued_items
                if str(item.get("job_id", "")) == "agent-browser-safe-job"
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_BLOCKED")
        self.assertEqual(str(job_payload["status"]), "failed")

    def test_agent_browser_failure_is_normalized_into_result_metadata(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="agent-browser-evidence-job",
                    workload="agent_browser_verify",
                    checkpoint_key="seed:agent-browser-evidence-job",
                    payload={
                        "run_id": "dev-run-evidence",
                        "service": "chatgpt",
                        "expected_url_substring": "chatgpt.com",
                    },
                ),
                config=config,
            )

            _ = run_control_loop_once(
                owner="runtime_v2",
                config=config,
                run_id="control-run-evidence",
                allow_runtime_side_effects=False,
            )
            latest = load_joined_latest_run(config, completed=True)
            metadata = latest["result_metadata"]
            self.assertIsInstance(metadata, dict)
            typed = metadata if isinstance(metadata, dict) else {}

        self.assertEqual(str(typed.get("worker_error_code", "")), "BROWSER_BLOCKED")
        self.assertEqual(str(typed.get("completion_state", "")), "blocked")
        self.assertIn("browser_evidence", typed)


if __name__ == "__main__":
    _ = unittest.main()

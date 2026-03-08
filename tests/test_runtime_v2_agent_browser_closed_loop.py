from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import run_control_loop_once, seed_control_job


class RuntimeV2AgentBrowserClosedLoopTests(unittest.TestCase):
    def test_probe_root_closed_loop_replans_after_browser_failure_then_completes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root)
            plan = {
                "goal": "closed loop smoke",
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
                "replan_payload": {
                    "tasks": ["implement fix"],
                    "browser_checks": [
                        {
                            "service": "chatgpt",
                            "port": 9222,
                            "expected_url_substring": "chatgpt.com",
                            "allow_in_safe_mode": True,
                        }
                    ],
                },
            }
            seed_control_job(
                JobContract(
                    job_id="dev-plan-smoke",
                    workload="dev_plan",
                    checkpoint_key="seed:dev-plan-smoke",
                    payload={"run_id": "probe-run-1", "plan": plan},
                ),
                config=config,
            )

            results = []
            for index in range(6):
                results.append(
                    run_control_loop_once(
                        owner="runtime_v2",
                        config=config,
                        run_id=f"probe-loop-{index}",
                        allow_runtime_side_effects=False,
                    )
                )

            queue_payload = json.loads(
                config.queue_store_file.read_text(encoding="utf-8")
            )
            queued_items = [item for item in queue_payload if isinstance(item, dict)]
            completed_verify_jobs = [
                item
                for item in queued_items
                if str(item.get("workload", "")) == "agent_browser_verify"
                and str(item.get("status", "")) == "completed"
            ]

        self.assertTrue(completed_verify_jobs)
        self.assertTrue(
            any(
                str(item.get("code", "")) == "BROWSER_BLOCKED"
                for item in results
                if isinstance(item, dict)
            )
        )
        self.assertTrue(
            any(
                str(item.get("status", "")) == "ok"
                for item in results
                if isinstance(item, dict)
            )
        )


if __name__ == "__main__":
    _ = unittest.main()

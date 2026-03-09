from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.config import allowed_workloads
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import _run_worker


class RuntimeV2AgentBrowserTests(unittest.TestCase):
    def test_agent_browser_workload_is_registered(self) -> None:
        self.assertIn("agent_browser_verify", allowed_workloads())

    def test_build_snapshot_command_uses_cdp_and_interactive_snapshot(self) -> None:
        from runtime_v2.agent_browser.command_builder import build_snapshot_command

        command = build_snapshot_command(port=9222, max_output=1200)

        self.assertEqual(
            command,
            [
                "agent-browser",
                "--cdp",
                "9222",
                "snapshot",
                "-i",
                "--max-output",
                "1200",
            ],
        )

    def test_parse_tab_list_prefers_matching_tab_over_omnibox(self) -> None:
        from runtime_v2.agent_browser.result_parser import (
            parse_tab_list_output,
            select_best_tab,
        )

        tab_output = """\
-> [0] Omnibox Popup - chrome://omnibox-popup.top-chrome/omnibox_popup_aim.html
  [1] Omnibox Popup - chrome://omnibox-popup.top-chrome/
  [2] ChatGPT - https://chatgpt.com/
  [3]  - https://chatgpt.com/
"""

        tabs = parse_tab_list_output(tab_output)
        index = select_best_tab(
            tabs,
            expected_url_substring="chatgpt.com",
            expected_title_substring="ChatGPT",
        )

        self.assertEqual(index, 2)

    def test_run_worker_dispatches_agent_browser_verify(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            registry_file = Path(tmp_dir) / "worker_registry.json"
            job = JobContract(
                job_id="agent-browser-job",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-job",
                payload={
                    "service": "chatgpt",
                    "port": 9222,
                    "expected_url_substring": "chatgpt.com",
                    "expected_title_substring": "ChatGPT",
                },
            )

            with patch(
                "runtime_v2.control_plane.run_agent_browser_verify_job",
                return_value={
                    "status": "ok",
                    "stage": "agent_browser_verify",
                    "manifest_path": str(
                        (artifact_root / "x" / "manifest.json").resolve()
                    ),
                    "result_path": str((artifact_root / "x" / "result.json").resolve()),
                    "artifacts": [],
                    "retryable": False,
                    "completion": {"state": "verified", "final_output": False},
                },
            ) as run_verify:
                result = _run_worker(
                    job,
                    artifact_root=artifact_root,
                    registry_file=registry_file,
                )

        self.assertEqual(result["stage"], "agent_browser_verify")
        run_verify.assert_called_once()

    def test_agent_browser_verify_requires_explicit_target_matcher(self) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-no-target",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-no-target",
                payload={"service": "chatgpt", "port": 9222},
            )

            result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "AGENT_BROWSER_TARGET_REQUIRED")

    def test_agent_browser_verify_failure_does_not_emit_replan_policy(self) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-replan-leak",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-replan-leak",
                payload={
                    "service": "chatgpt",
                    "port": 9222,
                    "expected_url_substring": "chatgpt.com",
                    "replan_on_failure": True,
                    "verification": ["pytest"],
                    "browser_checks": [{"service": "chatgpt"}],
                    "replan_payload": {"tasks": ["implement fix"]},
                },
            )

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=RuntimeError("boom"),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "AGENT_BROWSER_COMMAND_FAILED")
        self.assertFalse(result.get("next_jobs", []))


if __name__ == "__main__":
    _ = unittest.main()

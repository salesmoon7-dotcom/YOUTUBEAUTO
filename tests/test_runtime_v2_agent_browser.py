from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.stage2.agent_browser_adapter import (
    build_stage2_agent_browser_adapter_command,
)
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

    def test_parse_tab_list_handles_titles_with_hyphen_and_keeps_url(self) -> None:
        from runtime_v2.agent_browser.result_parser import (
            parse_tab_list_output,
            select_best_tab,
        )

        tab_output = "[0] 4 머니 - YouTube 썸네일 - https://www.canva.com/design/DAHAnm1uUBA/-FWB5gw_ir1U7Ls0ZHF9Ig/edit\n"

        tabs = parse_tab_list_output(tab_output)
        index = select_best_tab(
            tabs,
            expected_url_substring="canva.com",
            expected_title_substring="Canva",
        )

        self.assertEqual(
            str(tabs[0]["url"]),
            "https://www.canva.com/design/DAHAnm1uUBA/-FWB5gw_ir1U7Ls0ZHF9Ig/edit",
        )
        self.assertEqual(index, 0)

    def test_parse_tab_list_strips_ansi_prefix_before_matching(self) -> None:
        from runtime_v2.agent_browser.result_parser import (
            parse_tab_list_output,
            select_best_tab,
        )

        tab_output = "\u001b[36m→\u001b[0m [0] 4 머니 - YouTube 썸네일 - https://www.canva.com/design/DAHAnm1uUBA/-FWB5gw_ir1U7Ls0ZHF9Ig/edit\n"

        tabs = parse_tab_list_output(tab_output)
        index = select_best_tab(tabs, expected_url_substring="canva.com")

        self.assertEqual(len(tabs), 1)
        self.assertEqual(index, 0)

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

    def test_stage2_adapter_command_uses_canonical_genspark_target_contract(
        self,
    ) -> None:
        command = build_stage2_agent_browser_adapter_command(
            service="genspark",
            service_artifact_path="D:/runtime/output.png",
        )

        self.assertIn("--expected-url-substring", command)
        self.assertIn("genspark.ai/agents?type=image_generation_agent", command)
        self.assertIn("--expected-title-substring", command)
        self.assertIn("Genspark", command)

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

    def test_agent_browser_worker_resolves_executable_from_appdata_npm(self) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _resolve_agent_browser_command,
        )

        with patch.dict(
            "os.environ", {"APPDATA": r"C:\Users\1\AppData\Roaming"}, clear=False
        ):
            with patch(
                "runtime_v2.workers.agent_browser_worker.shutil.which",
                return_value=None,
            ):
                resolved = _resolve_agent_browser_command(
                    ["agent-browser", "--cdp", "9222", "tab", "list"]
                )

        self.assertTrue(
            str(resolved[0]).endswith("agent-browser.cmd")
            or str(resolved[0]).endswith("agent-browser-win32-x64.exe")
        )

    def test_agent_browser_worker_uses_longer_timeout_for_seaart(self) -> None:
        from runtime_v2.workers.agent_browser_worker import _service_timeout_sec

        self.assertEqual(_service_timeout_sec("seaart"), 60)
        self.assertEqual(_service_timeout_sec("geminigen"), 60)
        self.assertEqual(_service_timeout_sec("canva"), 30)

    def test_agent_browser_verify_skips_snapshot_for_non_chatgpt_services(self) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-canva-no-snapshot",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-canva-no-snapshot",
                payload={
                    "service": "canva",
                    "port": 9666,
                    "expected_url_substring": "canva.com",
                },
            )

            outputs = iter(
                [
                    "[0] Canva design - https://www.canva.com/design/foo/edit\n",
                    "selected",
                    "https://www.canva.com/design/foo/edit",
                    "Canva design",
                ]
            )

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=lambda *args, **kwargs: next(outputs),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        details = cast(dict[str, object], result["details"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(str(details["snapshot_path"]), "")

    def test_agent_browser_verify_can_fallback_to_raw_cdp_http_for_non_chatgpt(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-seaart-http-fallback",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-seaart-http-fallback",
                payload={
                    "service": "seaart",
                    "port": 9444,
                    "expected_url_substring": "seaart.ai",
                    "expected_title_substring": "SeaArt",
                },
            )

            outputs = iter(
                [
                    RuntimeError("Failed to read: os error 10060"),
                    "selected",
                    "https://www.seaart.ai/ko/create/image?id=abc",
                    "AI 이미지 생성기 - SeaArt",
                ]
            )

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                value = next(outputs)
                if isinstance(value, Exception):
                    raise value
                return value

            with (
                patch(
                    "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                    side_effect=fake_run,
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._http_cdp_tab_list",
                    return_value=[
                        {
                            "index": 0,
                            "title": "AI 이미지 생성기 - SeaArt",
                            "url": "https://www.seaart.ai/ko/create/image?id=abc",
                        }
                    ],
                ),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            str(details["current_url"]), "https://www.seaart.ai/ko/create/image?id=abc"
        )


if __name__ == "__main__":
    _ = unittest.main()

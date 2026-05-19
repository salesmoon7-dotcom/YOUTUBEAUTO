from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from runtime_v2.stage2.agent_browser_adapter import (
    build_stage2_agent_browser_adapter_command,
)
from runtime_v2.config import RuntimeConfig, allowed_workloads
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import _run_worker


class RuntimeV2AgentBrowserTests(unittest.TestCase):
    def test_recover_agent_browser_service_uses_probe_root_runtime_config(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _recover_agent_browser_service,
        )

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            manager = MagicMock()
            supervisor = MagicMock()
            cfg = MagicMock()
            cfg.browser_registry_file = (
                root / "health" / "browser_session_registry.json"
            )
            cfg.browser_health_file = root / "health" / "browser_health.json"

            with (
                patch(
                    "runtime_v2.workers.agent_browser_worker.BrowserManager",
                    return_value=manager,
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker.BrowserSupervisor",
                    return_value=supervisor,
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker.RuntimeConfig.from_root",
                    return_value=cfg,
                ) as from_root_mock,
            ):
                _recover_agent_browser_service("genspark", artifact_root=artifact_root)

        from_root_mock.assert_called_once_with(root)
        tick_kwargs = supervisor.tick.call_args.kwargs
        self.assertEqual(tick_kwargs["registry_file"], cfg.browser_registry_file)
        self.assertEqual(tick_kwargs["health_file"], cfg.browser_health_file)

    def test_recover_agent_browser_service_forces_target_service_unhealthy(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _recover_agent_browser_service,
        )

        manager = MagicMock()
        supervisor = MagicMock()

        with (
            patch(
                "runtime_v2.workers.agent_browser_worker.BrowserManager",
                return_value=manager,
            ),
            patch(
                "runtime_v2.workers.agent_browser_worker.BrowserSupervisor",
                return_value=supervisor,
            ),
        ):
            _recover_agent_browser_service("genspark")

        manager.start.assert_called_once_with()
        tick_kwargs = supervisor.tick.call_args.kwargs
        self.assertEqual(tick_kwargs["force_unhealthy_service"], "genspark")
        self.assertEqual(tick_kwargs["restart_threshold"], 1)
        self.assertEqual(tick_kwargs["cooldown_sec"], 0)

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

    def test_select_best_tab_prefers_url_match_over_title_only_match(self) -> None:
        from runtime_v2.agent_browser.result_parser import select_best_tab

        tabs = cast(
            list[dict[str, object]],
            [
                {
                    "index": 0,
                    "title": "ChatGPT - 롱폼",
                    "url": "https://chatgpt.com/c/legacy-thread",
                },
                {
                    "index": 1,
                    "title": "ChatGPT",
                    "url": "https://chatgpt.com/g/g-696a6d74fbd48191a1ffdc5f8ea90a1b-rongpom/c/active-thread",
                },
            ],
        )

        index = select_best_tab(
            tabs,
            expected_url_substring="chatgpt.com/g/g-696a6d74fbd48191a1ffdc5f8ea90a1b-rongpom",
            expected_title_substring="롱폼",
        )

        self.assertEqual(index, 1)

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

    def test_agent_browser_error_code_uses_embedded_payload_error(self) -> None:
        from runtime_v2.workers.agent_browser_worker import _agent_browser_error_code

        exc = RuntimeError(
            'agent_browser_action_failed:{"ok": false, "error": "CANVA_AUTH_CONSENT_REQUIRED"}'
        )

        self.assertEqual(_agent_browser_error_code(exc), "CANVA_AUTH_CONSENT_REQUIRED")

    def test_run_agent_browser_actions_dispatches_playwright_canva_background_generate(
        self,
    ) -> None:
        from runtime_v2.workers import agent_browser_worker as worker_module

        transcript: list[dict[str, object]] = []

        with patch(
            "runtime_v2.workers.agent_browser_worker._playwright_canva_background_generate",
            return_value={"ok": True, "step": "submitted_background_generate_iframe"},
        ) as helper:
            worker_module._run_agent_browser_actions(
                service="canva",
                port=9666,
                transcript=transcript,
                actions=[
                    {
                        "type": "playwright_canva_background_generate",
                        "bg_prompt": "quiet waiting area",
                    }
                ],
                timeout_sec=30,
            )

        helper.assert_called_once_with(
            port=9666,
            bg_prompt="quiet waiting area",
            timeout_sec=30,
        )
        self.assertEqual(
            transcript[0]["command"], ["playwright-canva-background-generate"]
        )

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

    def test_last_visible_locator_prefers_last_visible_candidate(self) -> None:
        from runtime_v2.workers.agent_browser_worker import _last_visible_locator

        class FakeCandidate:
            def __init__(self, width: int, height: int) -> None:
                self._box = {"width": width, "height": height}

            def bounding_box(self):
                return self._box

        class FakeLocator:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

        hidden = FakeCandidate(0, 0)
        first_visible = FakeCandidate(120, 30)
        last_visible = FakeCandidate(80, 20)
        locator = FakeLocator([hidden, first_visible, last_visible])

        target = _last_visible_locator(locator)

        self.assertIs(target, last_visible)

    def test_canva_background_generate_reuses_visible_iframe_before_tab_click(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box, *, text: str = "", aria: str = "") -> None:
                self._box = box
                self.clicked = False
                self.filled = ""
                self._text = text
                self._aria = aria

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            def inner_text(self, timeout=None):
                return self._text

            def get_attribute(self, name: str, timeout=None):
                if name == "aria-label":
                    return self._aria
                return ""

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakeFrame:
            def __init__(self) -> None:
                self.input = FakeNode({"width": 100, "height": 20})
                self.generate = FakeNode({"width": 80, "height": 20})

            def locator(self, selector: str):
                if (
                    selector
                    == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                ):
                    return FakeLocatorList([self.input])
                raise AssertionError(selector)

            def get_by_role(self, role: str, name: str):
                if role == "button" and name == "생성":
                    return self.generate
                raise AssertionError((role, name))

        class FakeHandle:
            def __init__(self, frame):
                self._frame = frame

            def content_frame(self):
                return self._frame

        class FakeIframe:
            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

            def element_handle(self, timeout=None):
                return FakeHandle(frame)

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.tab = FakeNode({"width": 90, "height": 20})
                self.wait_calls = 0
                self._eval_calls = 0

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return True
                if self._eval_calls == 2:
                    return "panel-123"
                if "button,[role=button],[aria-label]" in script:
                    return False
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == "#panel-123":

                    class EmptyPanel:
                        def locator(self, selector: str, has_text=None):
                            if (
                                selector
                                == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                            ):
                                return FakeLocatorList([])
                            if (
                                selector == "button,[role=button]"
                                and has_text == "생성"
                            ):
                                return FakeLocatorList([])
                            if (
                                selector == "button,[role=button]"
                                and has_text == "파일 선택하기"
                            ):
                                return FakeLocatorList([])
                            raise AssertionError((selector, has_text))

                    return EmptyPanel()
                if selector == 'iframe[title="Product Background"]':
                    return FakeIframe()
                raise AssertionError((selector, has_text))

        frame = FakeFrame()
        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertFalse(page.tab.clicked)
        self.assertEqual(frame.input.filled, "hello")

    def test_canva_background_generate_accepts_panel_contenteditable_input(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box, *, text: str = "", aria: str = "") -> None:
                self._box = box
                self.clicked = False
                self.filled = ""
                self._text = text
                self._aria = aria

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            def inner_text(self, timeout=None):
                return self._text

            def get_attribute(self, name: str, timeout=None):
                if name == "aria-label":
                    return self._aria
                return ""

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

        class FakePanel:
            def __init__(self) -> None:
                self.input = FakeNode({"width": 120, "height": 24})
                self.generate = FakeNode({"width": 80, "height": 20})

            def locator(self, selector: str, has_text=None):
                if selector == "textarea,[role=textbox],input[type=text]":
                    return FakeLocatorList([])
                if (
                    selector
                    == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                ):
                    return FakeLocatorList([self.input])
                if selector == "button,[role=button]" and has_text == "생성":
                    return FakeLocatorList([self.generate])
                raise AssertionError((selector, has_text))

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self.panel = FakePanel()
                self._eval_calls = 0

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return True
                if self._eval_calls == 2:
                    return "panel-123"
                if "button,[role=button],[aria-label]" in script:
                    return False
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == "#panel-123":
                    return self.panel
                raise AssertionError((selector, has_text))

        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["step"], "submitted_background_generate_panel")
        self.assertEqual(page.panel.input.filled, "hello")
        self.assertTrue(page.panel.generate.clicked)

    def test_canva_background_generate_prefers_legacy_top_dom_prompt_path(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box, *, text: str = "", aria: str = "") -> None:
                self._box = box
                self.clicked = False
                self.filled = ""
                self._text = text
                self._aria = aria

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            def inner_text(self, timeout=None):
                return self._text

            def get_attribute(self, name: str, timeout=None):
                if name == "aria-label":
                    return self._aria
                return ""

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0
                self.top_prompt = FakeNode({"width": 120, "height": 24})
                self.top_generate = FakeNode(
                    {"width": 80, "height": 20}, text="Generate", aria=""
                )
                self.bg_button = FakeNode(
                    {"width": 90, "height": 20}, text="배경 생성", aria="배경 생성"
                )

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == "button,[role=button]" and has_text == "배경 생성":
                    return FakeLocatorList([self.bg_button])
                if selector in {
                    "textarea[placeholder*='예시']",
                    "textarea[placeholder*='Describe']",
                    "textarea[placeholder*='prompt']",
                    "textarea[aria-label*='프롬프트'],textarea[aria-label*='Prompt']",
                    "div[role='dialog'] textarea",
                    "div[contenteditable='true'][role='textbox']",
                    "div[contenteditable='true'][data-lexical-editor='true']",
                    "[role='textbox'][contenteditable='true']",
                    "textarea",
                    "[role=textbox]",
                    "input[type=text]",
                    "[contenteditable='true']",
                }:
                    return FakeLocatorList([self.top_prompt])
                if selector == "button,[role=button]":
                    return FakeLocatorList([self.bg_button, self.top_generate])
                raise AssertionError((selector, has_text))

        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["step"], "submitted_background_generate_topdom")
        self.assertTrue(page.bg_button.clicked)
        self.assertEqual(page.top_prompt.filled, "hello")
        self.assertTrue(page.top_generate.clicked)

    def test_canva_background_generate_uses_legacy_generate_fallback(self) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box, *, text: str = "", aria: str = "") -> None:
                self._box = box
                self.clicked = False
                self.filled = ""
                self._text = text
                self._aria = aria

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            def inner_text(self, timeout=None):
                return self._text

            def get_attribute(self, name: str, timeout=None):
                if name == "aria-label":
                    return self._aria
                return ""

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0
                self.top_prompt = FakeNode({"width": 120, "height": 24})
                self.bg_button = FakeNode(
                    {"width": 90, "height": 20}, text="배경 생성", aria="배경 생성"
                )
                self.run_button = FakeNode(
                    {"width": 90, "height": 20}, text="배경 생성 4개", aria=""
                )

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == "button,[role=button]" and has_text == "배경 생성":
                    return FakeLocatorList([self.bg_button])
                if selector in {
                    "textarea[placeholder*='예시']",
                    "textarea[placeholder*='Describe']",
                    "textarea[placeholder*='prompt']",
                    "textarea[aria-label*='프롬프트'],textarea[aria-label*='Prompt']",
                    "div[role='dialog'] textarea",
                    "div[contenteditable='true'][role='textbox']",
                    "div[contenteditable='true'][data-lexical-editor='true']",
                    "[role='textbox'][contenteditable='true']",
                    "textarea",
                    "[role=textbox]",
                    "input[type=text]",
                    "[contenteditable='true']",
                }:
                    return FakeLocatorList([self.top_prompt])
                if selector == "button,[role=button]":
                    return FakeLocatorList([self.bg_button, self.run_button])
                raise AssertionError((selector, has_text))

        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["step"], "submitted_background_generate_topdom")
        self.assertFalse(page.bg_button.clicked and page.bg_button.filled)
        self.assertTrue(page.run_button.clicked)

    def test_canva_background_generate_falls_back_to_generic_iframe_locator(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box) -> None:
                self._box = box
                self.clicked = False
                self.filled = ""

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakeFrame:
            def __init__(self) -> None:
                self.input = FakeNode({"width": 100, "height": 20})
                self.generate = FakeNode({"width": 80, "height": 20})

            def locator(self, selector: str):
                if (
                    selector
                    == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                ):
                    return FakeLocatorList([self.input])
                raise AssertionError(selector)

            def get_by_role(self, role: str, name: str):
                if role == "button" and name == "생성":
                    return self.generate
                raise AssertionError((role, name))

        class FakeHandle:
            def __init__(self, frame):
                self._frame = frame

            def content_frame(self):
                return self._frame

        class FakeIframe:
            def __init__(self, frame, count: int) -> None:
                self._frame = frame
                self._count = count

            @property
            def first(self):
                return self

            def count(self) -> int:
                return self._count

            def element_handle(self, timeout=None):
                if self._count <= 0:
                    return None
                return FakeHandle(self._frame)

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                if "button,[role=button],[aria-label]" in script:
                    return False
                if "button[role=tab][aria-controls]" in script:
                    return ""
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == 'iframe[title="Product Background"]':
                    return FakeIframe(frame, 0)
                if selector == "iframe":
                    return FakeIframe(frame, 1)
                raise AssertionError((selector, has_text))

        frame = FakeFrame()
        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["step"], "submitted_background_generate_iframe")
        self.assertEqual(frame.input.filled, "hello")

    def test_canva_background_generate_opens_sidebar_entry_before_iframe_retry(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box) -> None:
                self._box = box
                self.clicked = False
                self.filled = ""

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakeFrame:
            def __init__(self) -> None:
                self.input = FakeNode({"width": 100, "height": 20})
                self.generate = FakeNode({"width": 80, "height": 20})

            def locator(self, selector: str):
                if (
                    selector
                    == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                ):
                    return FakeLocatorList([self.input])
                raise AssertionError(selector)

            def get_by_role(self, role: str, name: str):
                if role == "button" and name == "생성":
                    return self.generate
                raise AssertionError((role, name))

        class FakeHandle:
            def __init__(self, frame):
                self._frame = frame

            def content_frame(self):
                return self._frame

        class FakeIframe:
            def __init__(self, page, frame) -> None:
                self._page = page
                self._frame = frame

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1 if self._page.sidebar_opened else 0

            def element_handle(self, timeout=None):
                if not self._page.sidebar_opened:
                    return None
                return FakeHandle(self._frame)

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0
                self.sidebar_opened = False

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                if "Product Background" in script and "querySelectorAll" in script:
                    self.sidebar_opened = True
                    return True
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == 'iframe[title="Product Background"]':
                    return FakeIframe(self, frame)
                if selector == "iframe":
                    return FakeIframe(self, frame)
                raise AssertionError((selector, has_text))

        frame = FakeFrame()
        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertTrue(page.sidebar_opened)
        self.assertEqual(result["step"], "submitted_background_generate_iframe")
        self.assertEqual(frame.input.filled, "hello")

    def test_canva_background_generate_clicks_product_background_tab_when_eval_misses(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box, page=None) -> None:
                self._box = box
                self.clicked = False
                self.filled = ""
                self._page = page

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True
                if self._page is not None:
                    self._page.tab_clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakeFrame:
            def __init__(self) -> None:
                self.input = FakeNode({"width": 100, "height": 20})
                self.generate = FakeNode({"width": 80, "height": 20})

            def locator(self, selector: str):
                if (
                    selector
                    == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                ):
                    return FakeLocatorList([self.input])
                raise AssertionError(selector)

            def get_by_role(self, role: str, name: str):
                if role == "button" and name == "생성":
                    return self.generate
                raise AssertionError((role, name))

        class FakeHandle:
            def __init__(self, frame):
                self._frame = frame

            def content_frame(self):
                return self._frame

        class FakeIframe:
            def __init__(self, page, frame) -> None:
                self._page = page
                self._frame = frame

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1 if self._page.tab_clicked else 0

            def element_handle(self, timeout=None):
                if not self._page.tab_clicked:
                    return None
                return FakeHandle(self._frame)

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0
                self.tab_clicked = False
                self.tab = FakeNode({"width": 90, "height": 20}, page=self)

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                if "button,[role=button],[aria-label]" in script:
                    return False
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if (
                    selector == 'button[role="tab"],[role=tab]'
                    and has_text == "Product Background"
                ):
                    return FakeLocatorList([self.tab])
                if selector == 'iframe[title="Product Background"]':
                    return FakeIframe(self, frame)
                if selector == "iframe":
                    return FakeIframe(self, frame)
                raise AssertionError((selector, has_text))

        frame = FakeFrame()
        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertTrue(page.tab_clicked)
        self.assertEqual(result["step"], "submitted_background_generate_iframe")
        self.assertEqual(frame.input.filled, "hello")

    def test_canva_background_generate_uses_page_frames_when_content_frame_is_none(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box) -> None:
                self._box = box
                self.clicked = False
                self.filled = ""

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakeFrame:
            def __init__(self) -> None:
                self.url = "https://app-aagfbubmjom.canva-apps.com/app-sandbox/editor/AAGfbuBmjOM/11?locale=ko-KR"
                self.input = FakeNode({"width": 100, "height": 20})
                self.generate = FakeNode({"width": 80, "height": 20})

            def locator(self, selector: str):
                if (
                    selector
                    == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                ):
                    return FakeLocatorList([self.input])
                raise AssertionError(selector)

            def get_by_role(self, role: str, name: str):
                if role == "button" and name == "생성":
                    return self.generate
                raise AssertionError((role, name))

        class FakeHandle:
            def content_frame(self):
                return None

        class FakeIframe:
            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

            def element_handle(self, timeout=None):
                return FakeHandle()

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0
                self.frames = [frame]

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                if "button,[role=button],[aria-label]" in script:
                    return False
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == 'iframe[title="Product Background"]':
                    return FakeIframe()
                if selector == "iframe":
                    return FakeIframe()
                raise AssertionError((selector, has_text))

        frame = FakeFrame()
        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["step"], "submitted_background_generate_iframe")
        self.assertEqual(frame.input.filled, "hello")

    def test_canva_background_generate_focuses_canvas_before_iframe_attach(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box) -> None:
                self._box = box
                self.clicked = False
                self.filled = ""

            def bounding_box(self):
                return self._box

            def click(self, timeout=None, force=False):
                self.clicked = True

            def fill(self, value: str, timeout=None):
                self.filled = value

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakeFrame:
            def __init__(self) -> None:
                self.url = "https://app-aagfbubmjom.canva-apps.com/app-sandbox/editor/AAGfbuBmjOM/11?locale=ko-KR"
                self.input = FakeNode({"width": 100, "height": 20})
                self.generate = FakeNode({"width": 80, "height": 20})

            def locator(self, selector: str):
                if (
                    selector
                    == "textarea,[role=textbox],input[type=text],[contenteditable='true']"
                ):
                    return FakeLocatorList([self.input])
                raise AssertionError(selector)

            def get_by_role(self, role: str, name: str):
                if role == "button" and name == "생성":
                    return self.generate
                raise AssertionError((role, name))

        class FakeHandle:
            def __init__(self, page, frame):
                self._page = page
                self._frame = frame

            def content_frame(self):
                return self._frame if self._page.canvas_focused else None

        class FakeIframe:
            def __init__(self, page, frame):
                self._page = page
                self._frame = frame

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

            def element_handle(self, timeout=None):
                return FakeHandle(self._page, self._frame)

        class FakeMouse:
            def __init__(self, page) -> None:
                self._page = page
                self.clicks = []

            def click(self, x: float, y: float):
                self.clicks.append((x, y))
                self._page.canvas_focused = True

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0
                self.canvas_focused = False
                self.mouse = FakeMouse(self)
                self.canvas = FakeNode({"x": 10, "y": 20, "width": 200, "height": 100})
                self.frames = [frame]

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                if "button,[role=button],[aria-label]" in script:
                    return False
                if "button[role=tab][aria-controls]" in script:
                    return ""
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == '[aria-label="캔버스 진입점"]':
                    return FakeLocatorList([self.canvas])
                if selector == 'iframe[title="Product Background"]':
                    return FakeIframe(self, frame)
                if selector == "iframe":
                    return FakeIframe(self, frame)
                raise AssertionError((selector, has_text))

        frame = FakeFrame()
        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertTrue(result["ok"])
        self.assertTrue(page.canvas_focused)
        self.assertEqual(page.mouse.clicks, [(110.0, 35.0)])
        self.assertEqual(result["step"], "submitted_background_generate_iframe")
        self.assertEqual(frame.input.filled, "hello")

    def test_canva_background_generate_rejects_about_blank_child_frame_without_commit(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _playwright_canva_background_generate,
        )

        class FakeNode:
            def __init__(self, box) -> None:
                self._box = box

            def bounding_box(self):
                return self._box

            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

        class FakeLocatorList:
            def __init__(self, items) -> None:
                self._items = items

            def count(self) -> int:
                return len(self._items)

            def nth(self, index: int):
                return self._items[index]

            @property
            def first(self):
                return self._items[0]

        class FakeHandle:
            def content_frame(self):
                return None

        class FakeIframe:
            @property
            def first(self):
                return self

            def count(self) -> int:
                return 1

            def element_handle(self, timeout=None):
                return FakeHandle()

        class FakeFrame:
            def __init__(self, url: str) -> None:
                self.url = url

        class FakePage:
            def __init__(self) -> None:
                self.keyboard = MagicMock()
                self.wait_calls = 0
                self._eval_calls = 0
                self.frames = [main_frame, child_frame]
                self.mouse = MagicMock()

            def wait_for_timeout(self, ms: int):
                self.wait_calls += 1
                return None

            def evaluate(self, script: str):
                self._eval_calls += 1
                if self._eval_calls == 1:
                    return False
                if self._eval_calls == 2:
                    return ""
                if "button,[role=button],[aria-label]" in script:
                    return False
                if "button[role=tab][aria-controls]" in script:
                    return ""
                raise AssertionError(script)

            def locator(self, selector: str, has_text=None):
                if selector == '[aria-label="캔버스 진입점"]':
                    return FakeLocatorList(
                        [FakeNode({"x": 10, "y": 20, "width": 200, "height": 100})]
                    )
                if selector == 'iframe[title="Product Background"]':
                    return FakeIframe()
                if selector == "iframe":
                    return FakeIframe()
                raise AssertionError((selector, has_text))

        main_frame = FakeFrame("https://www.canva.com/design/foo/edit")
        child_frame = FakeFrame("about:blank")
        page = FakePage()
        browser = MagicMock()

        with patch(
            "runtime_v2.workers.agent_browser_worker._select_canva_page",
            return_value=(browser, page),
        ):
            result = _playwright_canva_background_generate(
                port=9666, bg_prompt="hello", timeout_sec=30
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "PRODUCT_BACKGROUND_IFRAME_UNAVAILABLE")

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

    def test_agent_browser_verify_fail_closes_when_raw_cdp_http_fallback_errors(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-http-fallback-error",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-http-fallback-error",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                },
            )

            with (
                patch(
                    "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                    side_effect=RuntimeError("Failed to read: os error 10060"),
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._http_cdp_tab_list",
                    side_effect=TimeoutError("raw cdp timeout"),
                ),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "agent_browser_verify")
        self.assertEqual(result["error_code"], "AGENT_BROWSER_COMMAND_FAILED")

    def test_agent_browser_verify_fail_closes_unexpected_exception_with_details(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-unexpected-exception",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-unexpected-exception",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                },
            )

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=TypeError("unexpected parser shape"),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        details = cast(dict[str, object], result["details"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "AGENT_BROWSER_VERIFY_FAILED")
        self.assertEqual(str(details["exception_type"]), "TypeError")

    def test_agent_browser_verify_preserves_current_url_when_action_fails(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-geminigen-action-failure",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-geminigen-action-failure",
                payload={
                    "service": "geminigen",
                    "port": 9555,
                    "expected_url_substring": "geminigen.ai",
                    "expected_title_substring": "Grok",
                    "capture_snapshot": False,
                    "actions": [
                        {
                            "type": "wait",
                            "target": "textarea[placeholder*='Describe the video']",
                        }
                    ],
                },
            )

            outputs = iter(
                [
                    "[0] Grok - https://geminigen.ai/app/video-gen/grok\n",
                    "selected geminigen",
                    "https://geminigen.ai/app/video-gen/grok",
                    "Grok",
                ]
            )

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                if command[-2:] == [
                    "wait",
                    "textarea[placeholder*='Describe the video']",
                ]:
                    raise RuntimeError("page.waitForSelector: Timeout 10000ms exceeded")
                return next(outputs)

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=fake_run,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        details = cast(dict[str, object], result["details"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "AGENT_BROWSER_COMMAND_FAILED")
        self.assertEqual(
            str(details["current_url"]), "https://geminigen.ai/app/video-gen/grok"
        )
        self.assertEqual(str(details["current_title"]), "Grok")

    def test_agent_browser_verify_does_not_claim_service_recovered_when_retry_still_fails(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-recovery-retry-fails",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-recovery-retry-fails",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            with (
                patch(
                    "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                    side_effect=RuntimeError(
                        "Failed to connect via CDP to http://localhost:9333"
                    ),
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._http_cdp_tab_list",
                    side_effect=ConnectionRefusedError("WinError 10061"),
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._recover_agent_browser_service"
                ),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

            transcript_path = Path(
                str(cast(dict[str, object], result["details"])["transcript_path"])
            )
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "AGENT_BROWSER_COMMAND_FAILED")
        self.assertEqual(len(cast(list[object], transcript["steps"])), 1)
        step = cast(dict[str, object], cast(list[object], transcript["steps"])[0])
        self.assertEqual(step["command"], ["recovery"])
        self.assertEqual(step["output"], "service_recovery_failed")
        self.assertTrue(bool(step["recovery_attempted"]))

    def test_agent_browser_verify_retries_once_more_after_recovery_settle(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-recovery-settle",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-recovery-settle",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            command_calls = {"count": 0}

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                command_calls["count"] += 1
                if command_calls["count"] <= 2:
                    raise RuntimeError(
                        "Failed to connect via CDP to http://localhost:9333"
                    )
                if command[3:] == ["tab", "list"]:
                    return (
                        "\u001b[36m\u2192\u001b[0m [0] AI 이미지 - "
                        "https://www.genspark.ai/agents?type=image_generation_agent\n"
                    )
                if command[3:] == ["tab", "0"]:
                    return (
                        "\u001b[32m\u2713\u001b[0m \u001b[1mAI 이미지\u001b[0m\n"
                        "  https://www.genspark.ai/agents?type=image_generation_agent\n"
                    )
                if command[3:] == ["get", "url"]:
                    return "https://www.genspark.ai/agents?type=image_generation_agent"
                if command[3:] == ["get", "title"]:
                    return "AI 이미지"
                raise AssertionError(command)

            with (
                patch(
                    "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                    side_effect=fake_run,
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._http_cdp_tab_list",
                    side_effect=ConnectionRefusedError("WinError 10061"),
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._recover_agent_browser_service"
                ),
                patch("runtime_v2.workers.agent_browser_worker.time.sleep"),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

            transcript_path = Path(
                str(cast(dict[str, object], result["details"])["transcript_path"])
            )
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(str(result.get("error_code", "")), "")
        self.assertEqual(command_calls["count"], 6)
        steps = cast(list[object], transcript["steps"])
        self.assertTrue(
            any(
                isinstance(step, dict)
                and step.get("command") == ["recovery"]
                and step.get("output") == "service_recovered"
                for step in steps
            )
        )

    def test_agent_browser_verify_does_not_retry_non_connect_runtime_error(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-non-connect-runtime-error",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-non-connect-runtime-error",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            command_calls = {"count": 0}

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                command_calls["count"] += 1
                if command[3:] == ["tab", "list"]:
                    return (
                        "\u001b[36m\u2192\u001b[0m [0] AI 이미지 - "
                        "https://www.genspark.ai/agents?type=image_generation_agent\n"
                    )
                if command[3:] == ["tab", "0"]:
                    return (
                        "\u001b[32m\u2713\u001b[0m \u001b[1mAI 이미지\u001b[0m\n"
                        "  https://www.genspark.ai/agents?type=image_generation_agent\n"
                    )
                if command[3:] == ["get", "url"]:
                    raise RuntimeError(
                        'agent_browser_action_failed:{"error":"NO_PROMPT_INPUT"}'
                    )
                raise AssertionError(command)

            with (
                patch(
                    "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                    side_effect=fake_run,
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._http_cdp_tab_list",
                    side_effect=AssertionError("http fallback unused"),
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._recover_agent_browser_service"
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker.time.sleep"
                ) as sleep_mock,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "NO_PROMPT_INPUT")
        self.assertEqual(command_calls["count"], 6)
        sleep_mock.assert_not_called()

    def test_agent_browser_verify_marks_probe_browser_unhealthy_on_attach_failure(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            config = RuntimeConfig.from_root(root)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "probe-run",
                        "checked_at": 1.0,
                        "session_count": 1,
                        "healthy_count": 1,
                        "unhealthy_count": 0,
                        "availability_percent": 100.0,
                        "sessions": [
                            {
                                "service": "genspark",
                                "port": 9333,
                                "healthy": True,
                                "status": "running",
                                "cdp_endpoint_ready": True,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            job = JobContract(
                job_id="agent-browser-genspark-health-downgrade",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-health-downgrade",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            with (
                patch(
                    "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                    side_effect=RuntimeError("connect ECONNREFUSED 127.0.0.1:9333"),
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._http_cdp_tab_list",
                    side_effect=ConnectionRefusedError("WinError 10061"),
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._recover_agent_browser_service"
                ),
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

            health_payload = json.loads(
                config.browser_health_file.read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "failed")
        session = cast(dict[str, object], health_payload["sessions"][0])
        self.assertFalse(bool(session["healthy"]))
        self.assertEqual(str(session["status"]), "unhealthy")
        self.assertFalse(bool(session["cdp_endpoint_ready"]))

    def test_agent_browser_verify_marks_probe_browser_login_required_when_login_page_seen(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            config = RuntimeConfig.from_root(root)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "probe-run",
                        "checked_at": 1.0,
                        "session_count": 1,
                        "healthy_count": 1,
                        "unhealthy_count": 0,
                        "availability_percent": 100.0,
                        "sessions": [
                            {
                                "service": "geminigen",
                                "port": 9555,
                                "healthy": True,
                                "status": "running",
                                "cdp_endpoint_ready": True,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            job = JobContract(
                job_id="agent-browser-geminigen-login-health-downgrade",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-geminigen-login-health-downgrade",
                payload={
                    "service": "geminigen",
                    "port": 9555,
                    "expected_url_substring": "geminigen.ai",
                    "expected_title_substring": "Grok",
                    "capture_snapshot": False,
                    "actions": [
                        {
                            "type": "wait",
                            "target": "textarea[placeholder*='Describe the video']",
                        }
                    ],
                },
            )

            outputs = iter(
                [
                    "[0] Login - Access Your GeminiGen AI Account - https://geminigen.ai/auth/login\n",
                    "selected geminigen",
                    "https://geminigen.ai/auth/login",
                    "Login - Access Your GeminiGen AI Account",
                ]
            )

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                if command[-2:] == [
                    "wait",
                    "textarea[placeholder*='Describe the video']",
                ]:
                    raise RuntimeError("page.waitForSelector: Timeout 10000ms exceeded")
                return next(outputs)

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=fake_run,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

            health_payload = json.loads(
                config.browser_health_file.read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "failed")
        session = cast(dict[str, object], health_payload["sessions"][0])
        self.assertFalse(bool(session["healthy"]))
        self.assertEqual(str(session["status"]), "login_required")
        self.assertTrue(bool(session["cdp_endpoint_ready"]))

    def test_agent_browser_verify_accepts_legacy_string_actions(self) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-legacy-actions",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-legacy-actions",
                payload={
                    "service": "chatgpt",
                    "port": 9222,
                    "expected_url_substring": "chatgpt.com",
                    "actions": ["window.__test = true"],
                },
            )

            outputs = iter(
                [
                    "[0] ChatGPT - https://chatgpt.com/\n",
                    "selected",
                    "https://chatgpt.com/",
                    "ChatGPT",
                    '{"ok": true}',
                    "snapshot",
                ]
            )

            commands: list[list[str]] = []

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                commands.append(command)
                return next(outputs)

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=fake_run,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(
            any(command[-1] == "window.__test = true" for command in commands)
        )

    def test_agent_browser_actions_support_structured_commands_and_genspark_reselect(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import _run_agent_browser_actions

        transcript: list[dict[str, object]] = []
        commands: list[list[str]] = []
        outputs = iter(
            [
                '{"ok": true, "step": "navigated_image_agent"}',
                '{"ok": true}',
                "tab-list",
                "selected",
                '{"ok": true, "step": "clicked_generate"}',
                "tab-list",
                "selected",
            ]
        )

        def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
            _ = timeout_sec
            commands.append(command)
            return next(outputs)

        with (
            patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=fake_run,
            ),
            patch(
                "runtime_v2.workers.agent_browser_worker.build_tab_list_command",
                return_value=["agent-browser", "tab-list"],
            ),
            patch(
                "runtime_v2.workers.agent_browser_worker.build_tab_select_command",
                return_value=["agent-browser", "tab-select", "0"],
            ) as select_tab_mock,
            patch(
                "runtime_v2.workers.agent_browser_worker.parse_tab_list_output",
                return_value=[
                    {
                        "index": 0,
                        "title": "Genspark",
                        "url": "https://www.genspark.ai/agents?id=123",
                    }
                ],
            ),
            patch(
                "runtime_v2.workers.agent_browser_worker.select_best_tab",
                return_value=0,
            ),
            patch("runtime_v2.workers.agent_browser_worker.time.sleep") as sleep_mock,
        ):
            _run_agent_browser_actions(
                service="genspark",
                port=9333,
                transcript=transcript,
                actions=[
                    {
                        "type": "upload",
                        "selector": "input[type=file]",
                        "files": ["a.png"],
                    },
                    {"type": "wait", "target": "selector:#ready"},
                    {"type": "eval", "script": "generate()"},
                ],
                timeout_sec=30,
            )

        self.assertTrue(any("upload" in command for command in commands))
        self.assertTrue(any("wait" in command for command in commands))
        self.assertGreaterEqual(select_tab_mock.call_count, 2)
        sleep_mock.assert_called_once_with(5)
        self.assertGreaterEqual(len(transcript), 5)

    def test_genspark_initial_attach_prefers_result_tab_when_present(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-compose-tab",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-compose-tab",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            outputs = iter(
                [
                    "[0] AI 이미지 - https://www.genspark.ai/agents?type=image_generation_agent\n[1] image_generation_agent - https://www.genspark.ai/agents?id=stale\n",
                    "selected result",
                    "https://www.genspark.ai/agents?id=stale",
                    "image_generation_agent",
                ]
            )
            commands: list[list[str]] = []

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                commands.append(command)
                return next(outputs)

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=fake_run,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            str(details["current_url"]),
            "https://www.genspark.ai/agents?id=stale",
        )
        self.assertEqual(str(details["current_title"]), "image_generation_agent")

    def test_genspark_refreshes_current_url_after_actions_create_result_tab(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-refresh-after-actions",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-refresh-after-actions",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                    "actions": [
                        {
                            "type": "eval",
                            "script": "(() => JSON.stringify({ok:true, step:'clicked_generate'}))()",
                        }
                    ],
                },
            )

            outputs = iter(
                [
                    "[0] AI 이미지 - https://www.genspark.ai/agents?type=image_generation_agent\n",
                    "selected compose",
                    "https://www.genspark.ai/agents?type=image_generation_agent",
                    "AI 이미지",
                    '"{\\"ok\\":true,\\"step\\":\\"clicked_generate\\"}"',
                    "[0] AI 이미지 - https://www.genspark.ai/agents?type=image_generation_agent\n[1] Genspark Agents - https://www.genspark.ai/agents?id=result123\n",
                    "selected result",
                    "[0] AI 이미지 - https://www.genspark.ai/agents?type=image_generation_agent\n[1] Genspark Agents - https://www.genspark.ai/agents?id=result123\n",
                    "selected result",
                    "https://www.genspark.ai/agents?id=result123",
                    "Genspark Agents",
                ]
            )

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                return next(outputs)

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=fake_run,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            str(details["current_url"]),
            "https://www.genspark.ai/agents?id=result123",
        )

    def test_genspark_retries_after_browser_recovery_on_tab_list_failure(self) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-recover-tab-list",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-recover-tab-list",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            outputs = iter(
                [
                    RuntimeError("connect ECONNREFUSED 127.0.0.1:9333"),
                    "[0] Genspark Agents - https://www.genspark.ai/agents?id=result123\n",
                    "selected result",
                    "https://www.genspark.ai/agents?id=result123",
                    "Genspark Agents",
                ]
            )

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = (command, timeout_sec)
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
                    "runtime_v2.workers.agent_browser_worker._recover_agent_browser_service"
                ) as recover_mock,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        recover_mock.assert_called_once_with("genspark")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            str(details["current_url"]),
            "https://www.genspark.ai/agents?id=result123",
        )

    def test_genspark_uses_http_fallback_before_recovery_on_tab_list_failure(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-http-fallback",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-http-fallback",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            outputs = iter([RuntimeError("No page found")])

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = (command, timeout_sec)
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
                            "type": "page",
                            "url": "https://www.genspark.ai/agents?id=result123",
                            "title": "Genspark Agents",
                        }
                    ],
                ),
                patch(
                    "runtime_v2.workers.agent_browser_worker._recover_agent_browser_service"
                ) as recover_mock,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        recover_mock.assert_not_called()
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            str(details["current_url"]),
            "https://www.genspark.ai/agents?id=result123",
        )

    def test_seaart_retries_after_browser_recovery_on_tab_list_failure(self) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-seaart-recover-tab-list",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-seaart-recover-tab-list",
                payload={
                    "service": "seaart",
                    "port": 9444,
                    "expected_url_substring": "seaart.ai",
                    "expected_title_substring": "SeaArt",
                    "capture_snapshot": False,
                },
            )

            outputs = iter(
                [
                    RuntimeError("connect ECONNREFUSED 127.0.0.1:9444"),
                    "[0] AI 이미지 생성기 - 텍스트와 이미지에서 독특한 아트 만들기 - https://www.seaart.ai/ko/create/image?id=test\n",
                    "selected seaart",
                    "https://www.seaart.ai/ko/create/image?id=test",
                    "AI 이미지 생성기 - 텍스트와 이미지에서 독특한 아트 만들기",
                ]
            )

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = (command, timeout_sec)
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
                    "runtime_v2.workers.agent_browser_worker._recover_agent_browser_service"
                ) as recover_mock,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            str(details["current_url"]),
            "https://www.seaart.ai/ko/create/image?id=test",
        )

    def test_genspark_initial_attach_accepts_single_remaining_result_tab(self) -> None:
        from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="agent-browser-genspark-single-tab",
                workload="agent_browser_verify",
                checkpoint_key="seed:agent-browser-genspark-single-tab",
                payload={
                    "service": "genspark",
                    "port": 9333,
                    "expected_url_substring": "genspark.ai/agents?type=image_generation_agent",
                    "expected_title_substring": "Genspark",
                    "capture_snapshot": False,
                },
            )

            outputs = iter(
                [
                    "[0] image_generation_agent - https://www.genspark.ai/agents?id=single\n",
                    "selected single",
                    "https://www.genspark.ai/agents?id=single",
                    "image_generation_agent",
                ]
            )

            def fake_run(command: list[str], *, timeout_sec: int = 30) -> str:
                _ = timeout_sec
                return next(outputs)

            with patch(
                "runtime_v2.workers.agent_browser_worker._run_agent_browser_command",
                side_effect=fake_run,
            ):
                result = run_agent_browser_verify_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            str(details["current_url"]),
            "https://www.genspark.ai/agents?id=single",
        )

    def test_prefer_genspark_compose_tab_returns_result_tab_when_both_exist(
        self,
    ) -> None:
        from runtime_v2.workers.agent_browser_worker import _prefer_genspark_compose_tab

        tabs = cast(
            list[dict[str, object]],
            [
                {
                    "index": 0,
                    "url": "https://www.genspark.ai/agents?type=image_generation_agent",
                },
                {
                    "index": 1,
                    "url": "https://www.genspark.ai/agents?id=ea70b8cb-336d-454f-a485-cd44fc607f7e",
                },
            ],
        )

        self.assertEqual(_prefer_genspark_compose_tab(tabs), 1)

    def test_fallback_single_genspark_tab_requires_expected_title_match(self) -> None:
        from runtime_v2.workers.agent_browser_worker import (
            _fallback_single_genspark_tab,
        )

        tabs = cast(
            list[dict[str, object]],
            [
                {
                    "index": 0,
                    "title": "image_generation_agent",
                    "url": "https://www.genspark.ai/agents?id=single",
                }
            ],
        )

        self.assertIsNone(
            _fallback_single_genspark_tab(tabs, expected_title_substring="Genspark")
        )


if __name__ == "__main__":
    _ = unittest.main()

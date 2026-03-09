from __future__ import annotations

import json
import unittest
from typing import cast

from runtime_v2.stage1.chatgpt_backend import ChatGPTBackend
from runtime_v2.stage1.chatgpt_interaction import generate_gpt_response_text


class RuntimeV2Stage1ChatgptInteractionTests(unittest.TestCase):
    def test_generate_gpt_response_text_accepts_backend_interface(self) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.read_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "sendClicked": True,
                    "inputSelector": "#prompt-textarea",
                }

            def read_response_state(self) -> dict[str, object]:
                self.read_calls += 1
                if self.read_calls == 1:
                    return {
                        "has_stop": True,
                        "assistant_text": "draft",
                        "assistant_block_count": 1,
                    }
                return {
                    "has_stop": False,
                    "assistant_text": "final json",
                    "assistant_block_count": 1,
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")

    def test_generate_gpt_response_text_submits_and_waits_for_stable_text(self) -> None:
        responses = iter(
            [
                json.dumps(
                    {
                        "ok": True,
                        "inputSelector": "#prompt-textarea",
                        "sendClicked": True,
                    }
                ),
                json.dumps(
                    {
                        "has_stop": True,
                        "assistant_block_count": 1,
                        "assistant_text": "draft",
                    }
                ),
                json.dumps(
                    {
                        "has_stop": False,
                        "assistant_block_count": 1,
                        "assistant_text": "final json",
                    }
                ),
                json.dumps(
                    {
                        "has_stop": False,
                        "assistant_block_count": 1,
                        "assistant_text": "final json",
                    }
                ),
            ]
        )

        def fake_runner(command: list[str], timeout_sec: int) -> str:
            return next(responses)

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            command_runner=fake_runner,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")

    def test_generate_gpt_response_text_reports_submit_backend_failure(self) -> None:
        def fake_runner(command: list[str], timeout_sec: int) -> str:
            raise RuntimeError("os error 10060")

        def fake_probe(port: int) -> dict[str, object]:
            return {
                "probe_backend": "raw_cdp_http",
                "port": port,
                "tab_count": 1,
                "selected_tab": {"title": "ChatGPT", "url": "https://chatgpt.com/"},
            }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            command_runner=fake_runner,
            session_probe=fake_probe,
        )
        details = cast(dict[str, object], result["details"])
        final_state = cast(dict[str, object], result["final_state"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        self.assertEqual(result["failure_stage"], "submit")
        self.assertIn("10060", str(details["backend_error"]))
        self.assertEqual(details["backend_fallback"], "raw_cdp_http")
        self.assertEqual(result["submit_info"], {})
        self.assertEqual(final_state["tab_count"], 1)

    def test_generate_gpt_response_text_reports_read_backend_failure(self) -> None:
        responses = iter(
            [
                json.dumps(
                    {
                        "ok": True,
                        "inputSelector": "#prompt-textarea",
                        "sendClicked": True,
                    }
                )
            ]
        )

        def fake_runner(command: list[str], timeout_sec: int) -> str:
            if command[-2] == "eval":
                try:
                    return next(responses)
                except StopIteration:
                    raise RuntimeError("read timeout")
            raise RuntimeError("unexpected")

        def fake_probe(port: int) -> dict[str, object]:
            return {
                "probe_backend": "raw_cdp_http",
                "port": port,
                "tab_count": 1,
                "selected_tab": {"title": "ChatGPT", "url": "https://chatgpt.com/"},
            }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            command_runner=fake_runner,
            session_probe=fake_probe,
        )
        details = cast(dict[str, object], result["details"])
        final_state = cast(dict[str, object], result["final_state"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        self.assertEqual(result["failure_stage"], "read")
        self.assertIn("read timeout", str(details["backend_error"]))
        self.assertEqual(details["backend_fallback"], "raw_cdp_http")
        self.assertTrue(bool(result["submit_info"]))
        self.assertEqual(final_state["tab_count"], 1)


if __name__ == "__main__":
    _ = unittest.main()

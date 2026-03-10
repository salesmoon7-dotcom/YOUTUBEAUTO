from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock
from typing import cast

from runtime_v2.stage1.chatgpt_backend import (
    AgentBrowserCdpBackend,
    ChatGPTBackend,
    CHATGPT_LONGFORM_TITLE_SUBSTRING,
    CHATGPT_LONGFORM_URL_SUBSTRING,
)
from runtime_v2.stage1.chatgpt_interaction import (
    _response_text_from_state,
    generate_gpt_response_text,
)


class RuntimeV2Stage1ChatgptInteractionTests(unittest.TestCase):
    def test_response_text_from_state_prefers_legacy_blocks(self) -> None:
        response = _response_text_from_state(
            "plain text",
            [
                {"label": "[Title]", "body": "COPY\n머니 제목"},
                {
                    "label": "[#01 intro Character] - Voice 1(1)",
                    "body": "COPY\nscene prompt one",
                },
            ],
        )

        self.assertIn("[Title]\n머니 제목", response)
        self.assertIn("[#01 intro Character] - Voice 1(1)\nscene prompt one", response)

    def test_agent_browser_backend_preselects_chatgpt_tab_before_eval(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str], timeout_sec: int) -> str:
            calls.append(command)
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2] == "eval":
                return json.dumps(
                    {
                        "ok": True,
                        "inputSelector": "#prompt-textarea",
                        "sendClicked": True,
                    }
                )
            return json.dumps([])

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
                return_value=[
                    {"title": "Omnibox Popup", "url": "chrome://newtab"},
                    {
                        "title": "롱폼",
                        "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
                    },
                ],
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                return_value={
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/abc",
                    "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
                },
            ),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        self.assertIn(["agent-browser", "--cdp", "9222", "tab", "2"], calls)
        self.assertIn(
            CHATGPT_LONGFORM_URL_SUBSTRING,
            str(cast(dict[str, object], result["selected_tab"])["url"]),
        )

    def test_submit_script_prefers_send_button_over_stop_button(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=[
                "button[data-testid='send-button']",
                "button[aria-label='프롬프트 보내기']",
                "#composer-submit-button",
            ],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=lambda command, timeout_sec: json.dumps(
                {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                    "sendTestId": "send-button",
                    "sendAriaLabel": "프롬프트 보내기",
                    "submitEvidence": {
                        "pre": {"send_found": True, "send_disabled": False},
                        "post": {"send_found": True, "send_disabled": True},
                        "in_flight_observed": True,
                        "terminal_success_observed": True,
                    },
                }
            )
            if command[-2] == "eval"
            else "ok",
        )

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
            return_value=[{"title": "ChatGPT", "url": "https://chatgpt.com/c/abc"}],
        ):
            result = backend.submit_prompt("hello")

        self.assertEqual(result["sendTestId"], "send-button")
        self.assertEqual(result["sendAriaLabel"], "프롬프트 보내기")
        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "sent")
        self.assertFalse(bool(submit_evidence["retry_safe_decision"]))
        self.assertEqual(submit_evidence["classification_reason"], "submit_confirmed")
        self.assertEqual(submit_evidence["attempt_key"], "attempt-1")
        self.assertTrue(bool(submit_evidence["in_flight_observed"]))
        self.assertTrue(bool(submit_evidence["terminal_success_observed"]))

    def test_submit_evidence_is_ambiguous_without_terminal_success_signal(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=lambda command, timeout_sec: json.dumps(
                {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                    "sendTestId": "send-button",
                    "sendAriaLabel": "프롬프트 보내기",
                    "submitEvidence": {
                        "pre": {"send_found": True, "send_disabled": False},
                        "post": {"send_found": True, "send_disabled": False},
                        "in_flight_observed": True,
                        "terminal_success_observed": False,
                    },
                }
            )
            if command[-2] == "eval"
            else "ok",
        )

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
            return_value=[{"title": "ChatGPT", "url": "https://chatgpt.com/c/abc"}],
        ):
            result = backend.submit_prompt("hello")

        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertFalse(bool(submit_evidence["retry_safe_decision"]))
        self.assertEqual(submit_evidence["attempt_key"], "attempt-1")
        self.assertTrue(bool(submit_evidence["in_flight_observed"]))
        self.assertFalse(bool(submit_evidence["terminal_success_observed"]))

    def test_no_send_but_stop_visible_is_treated_as_in_flight_submit(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=lambda command, timeout_sec: json.dumps(
                {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": False,
                    "submitEvidence": {
                        "pre": {
                            "send_found": False,
                            "send_disabled": False,
                            "in_flight_marker": True,
                        },
                        "post": {
                            "send_found": False,
                            "send_disabled": False,
                            "in_flight_marker": True,
                        },
                        "in_flight_observed": True,
                        "terminal_success_observed": False,
                        "state_transition": True,
                    },
                }
            )
            if command[-2] == "eval"
            else "ok",
        )

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
            return_value=[{"title": "ChatGPT", "url": "https://chatgpt.com/c/abc"}],
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertTrue(bool(submit_evidence["in_flight_observed"]))
        self.assertFalse(bool(submit_evidence["retry_safe_decision"]))

    def test_agent_browser_backend_falls_back_to_http_tab_index_when_tab_list_fails(
        self,
    ) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str], timeout_sec: int) -> str:
            calls.append(command)
            if command[-2:] == ["tab", "list"]:
                raise RuntimeError("os error 10060")
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2] == "eval":
                return json.dumps(
                    {
                        "ok": True,
                        "inputSelector": "#prompt-textarea",
                        "sendClicked": True,
                    }
                )
            return "ok"

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
            return_value=[
                {"title": "Omnibox Popup", "url": "chrome://newtab"},
                {
                    "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
                    "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
                },
            ],
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        self.assertIn(["agent-browser", "--cdp", "9222", "tab", "list"], calls)
        self.assertIn(["agent-browser", "--cdp", "9222", "tab", "2"], calls)
        self.assertIn(
            "tab_list_http_fallback", cast(list[object], result["backend_fallbacks"])
        )

    def test_default_runner_wraps_timeout_as_runtime_error(self) -> None:
        backend_module = __import__(
            "runtime_v2.stage1.chatgpt_backend", fromlist=["_default_runner"]
        )
        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["agent-browser"], timeout=5),
        ):
            with self.assertRaises(RuntimeError):
                backend_module._default_runner(["agent-browser"], 5)

    def test_agent_browser_backend_retries_retryable_eval_error(self) -> None:
        eval_calls = 0

        def fake_runner(command: list[str], timeout_sec: int) -> str:
            nonlocal eval_calls
            if command[-2] == "eval":
                eval_calls += 1
                if eval_calls == 1:
                    raise RuntimeError("os error 10060")
                return json.dumps(
                    {
                        "ok": True,
                        "inputSelector": "#prompt-textarea",
                        "sendClicked": True,
                    }
                )
            return "ok"

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
                return_value=[{"title": "ChatGPT", "url": "https://chatgpt.com/c/abc"}],
            ),
            mock.patch("runtime_v2.stage1.chatgpt_backend.time.sleep"),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        self.assertEqual(eval_calls, 2)

    def test_raw_cdp_method_timeout_is_wrapped_as_runtime_error(self) -> None:
        from runtime_v2.stage1 import chatgpt_backend as backend_module

        class _FakeSocket:
            def send(self, payload: str) -> None:
                _ = payload

            def recv(self) -> str:
                raise subprocess.TimeoutExpired(cmd=["ws"], timeout=30)

            def close(self) -> None:
                return None

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.websocket.create_connection",
                return_value=_FakeSocket(),
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.websocket.WebSocketTimeoutException",
                new=TimeoutError,
            ),
        ):
            with self.assertRaises(RuntimeError):
                backend_module._run_raw_cdp_method(
                    "ws://127.0.0.1/devtools/page/test",
                    "Page.navigate",
                    {"url": "https://chatgpt.com"},
                )

    def test_agent_browser_backend_falls_back_to_raw_cdp_eval_after_retry_failures(
        self,
    ) -> None:
        eval_calls = 0

        def fake_runner(command: list[str], timeout_sec: int) -> str:
            nonlocal eval_calls
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2] == "eval":
                eval_calls += 1
                raise RuntimeError("os error 10060")
            if command[-2:] == ["tab", "list"]:
                return f"[1] Omnibox Popup - chrome://newtab\n[2] {CHATGPT_LONGFORM_TITLE_SUBSTRING} - https://{CHATGPT_LONGFORM_URL_SUBSTRING}"
            return "ok"

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                return_value={
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/abc",
                    "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
                },
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_eval",
                return_value=json.dumps(
                    json.dumps(
                        {
                            "ok": True,
                            "inputSelector": "#prompt-textarea",
                            "sendClicked": True,
                        }
                    )
                ),
            ),
            mock.patch("runtime_v2.stage1.chatgpt_backend.time.sleep"),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        self.assertEqual(eval_calls, 3)
        self.assertIn(
            "eval_raw_cdp_fallback", cast(list[object], result["backend_fallbacks"])
        )

    def test_raw_cdp_eval_suppresses_origin_header(self) -> None:
        sent_messages: list[str] = []

        class FakeSocket:
            def send(self, payload: str) -> None:
                sent_messages.append(payload)

            def recv(self) -> str:
                return json.dumps(
                    {
                        "id": 1,
                        "result": {"result": {"value": "ChatGPT"}},
                    }
                )

            def close(self) -> None:
                return None

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend.websocket.create_connection",
            return_value=FakeSocket(),
        ) as create_connection:
            result = __import__(
                "runtime_v2.stage1.chatgpt_backend", fromlist=["_run_raw_cdp_eval"]
            )._run_raw_cdp_eval("ws://127.0.0.1/devtools/page/abc", "document.title")

        self.assertEqual(result, "ChatGPT")
        create_connection.assert_called_once_with(
            "ws://127.0.0.1/devtools/page/abc", timeout=30, suppress_origin=True
        )
        self.assertTrue(sent_messages)

    def test_agent_browser_backend_falls_back_to_raw_submit_when_send_missing(
        self,
    ) -> None:
        def fake_runner(command: list[str], timeout_sec: int) -> str:
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2] == "eval":
                return json.dumps(
                    {
                        "ok": False,
                        "error": "NO_SEND",
                        "noSendEvidence": {
                            "retry_safe": True,
                            "send_found": False,
                            "in_flight_marker": False,
                        },
                    }
                )
            return "ok"

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
                return_value=[
                    {
                        "title": "롱폼",
                        "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
                    }
                ],
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                return_value={
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/abc",
                    "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
                },
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_eval",
                return_value=json.dumps(
                    json.dumps(
                        {
                            "ok": True,
                            "inputSelector": "#prompt-textarea",
                            "sendClicked": True,
                        }
                    )
                ),
            ),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))

    def test_agent_browser_backend_emits_retry_safe_no_send_evidence(self) -> None:
        def fake_runner(command: list[str], timeout_sec: int) -> str:
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2] == "eval":
                return json.dumps(
                    {
                        "ok": False,
                        "error": "NO_SEND",
                        "noSendEvidence": {
                            "retry_safe": True,
                            "send_found": False,
                            "in_flight_marker": False,
                        },
                    }
                )
            return "ok"

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
                return_value=[{"title": "ChatGPT", "url": "https://chatgpt.com/c/abc"}],
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                return_value={
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/abc",
                    "url": "https://chatgpt.com/c/abc",
                },
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_eval",
                return_value=json.dumps(
                    json.dumps(
                        {
                            "ok": False,
                            "error": "NO_SEND",
                            "noSendEvidence": {
                                "retry_safe": True,
                                "send_found": False,
                                "in_flight_marker": False,
                            },
                        }
                    )
                ),
            ),
        ):
            with self.assertRaises(RuntimeError) as raised:
                backend.submit_prompt("hello")

        payload = json.loads(str(raised.exception))
        self.assertEqual(payload["error"], "NO_SEND")
        self.assertTrue(bool(payload["retry_safe"]))
        self.assertFalse(bool(payload["no_send_evidence"]["send_found"]))
        submit_evidence = cast(dict[str, object], payload["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "not_sent")
        self.assertTrue(bool(submit_evidence["retry_safe_decision"]))
        self.assertEqual(submit_evidence["attempt_key"], "attempt-1")

    def test_agent_browser_backend_marks_send_disabled_as_non_retry_safe(self) -> None:
        def fake_runner(command: list[str], timeout_sec: int) -> str:
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2] == "eval":
                return json.dumps(
                    {
                        "ok": False,
                        "error": "SEND_DISABLED",
                        "noSendEvidence": {
                            "retry_safe": False,
                            "send_found": True,
                            "send_disabled": True,
                            "in_flight_marker": True,
                        },
                    }
                )
            return "ok"

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
            return_value=[{"title": "ChatGPT", "url": "https://chatgpt.com/c/abc"}],
        ):
            with self.assertRaises(RuntimeError) as raised:
                backend.submit_prompt("hello")

        payload = json.loads(str(raised.exception))
        self.assertEqual(payload["error"], "SEND_DISABLED")
        self.assertFalse(bool(payload["retry_safe"]))
        self.assertTrue(bool(payload["no_send_evidence"]["in_flight_marker"]))
        submit_evidence = cast(dict[str, object], payload["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertFalse(bool(submit_evidence["retry_safe_decision"]))
        self.assertEqual(submit_evidence["attempt_key"], "attempt-1")

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
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.read_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                }

            def read_response_state(self) -> dict[str, object]:
                self.read_calls += 1
                if self.read_calls <= 2:
                    return {
                        "has_stop": True,
                        "assistant_block_count": 1,
                        "assistant_text": "draft",
                    }
                return {
                    "has_stop": False,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertEqual(event_names[0], "submit_start")
        self.assertIn("submit_ok", event_names)
        self.assertIn("streaming_seen", event_names)
        self.assertIn("response_stable", event_names)
        self.assertEqual(event_names[-1], "final_state")

    def test_generate_gpt_response_text_does_not_finish_without_streaming_transition(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                }

            def read_response_state(self) -> dict[str, object]:
                return {
                    "has_stop": False,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")

    def test_generate_gpt_response_text_reports_submit_backend_failure(self) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                raise RuntimeError("os error 10060")

            def read_response_state(self) -> dict[str, object]:
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
            session_probe=fake_probe,
            backend=FakeBackend(),
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
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                }

            def read_response_state(self) -> dict[str, object]:
                raise RuntimeError("read timeout")

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
            session_probe=fake_probe,
            backend=FakeBackend(),
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
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertEqual(event_names[0], "submit_start")
        self.assertIn("submit_ok", event_names)
        self.assertIn("read_failed", event_names)
        self.assertEqual(event_names[-1], "final_state")

    def test_generate_gpt_response_text_retries_once_with_relauncher(self) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.submit_calls = 0
                self.read_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                self.submit_calls += 1
                if self.submit_calls == 1:
                    raise RuntimeError(
                        json.dumps(
                            {
                                "error": "NO_SEND",
                                "retry_safe": True,
                                "no_send_evidence": {
                                    "send_found": False,
                                    "in_flight_marker": False,
                                    "retry_safe": True,
                                },
                            },
                            ensure_ascii=True,
                        )
                    )
                return {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                }

            def read_response_state(self) -> dict[str, object]:
                self.read_calls += 1
                if self.read_calls == 1:
                    return {
                        "has_stop": True,
                        "assistant_block_count": 1,
                        "assistant_text": "draft",
                    }
                return {
                    "has_stop": False,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        relaunch_calls: list[str] = []

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
            session_probe=fake_probe,
            backend=FakeBackend(),
            relaunch_browser=lambda: relaunch_calls.append("chatgpt"),
        )

        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(relaunch_calls, ["chatgpt"])
        self.assertIn("retry_decision", event_names)
        self.assertIn("submit_failed", event_names)
        self.assertGreaterEqual(event_names.count("submit_start"), 2)
        attempt_keys = {str(item.get("attempt_key", "")) for item in timeline}
        self.assertEqual(attempt_keys, {"attempt-1", "attempt-2"})

    def test_generate_gpt_response_text_does_not_retry_ambiguous_submit_failure(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.submit_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                self.submit_calls += 1
                raise RuntimeError(
                    json.dumps(
                        {
                            "error": "submit timeout",
                            "retry_safe": False,
                            "submit_evidence": {
                                "classification": "ambiguous",
                                "classification_reason": "submit timeout",
                                "retry_safe_decision": False,
                            },
                        },
                        ensure_ascii=True,
                    )
                )

            def read_response_state(self) -> dict[str, object]:
                raise RuntimeError("unexpected")

        relaunch_calls: list[str] = []

        def fake_probe(port: int) -> dict[str, object]:
            return {
                "probe_backend": "raw_cdp_http",
                "port": port,
                "tab_count": 1,
                "selected_tab": {"title": "ChatGPT", "url": "https://chatgpt.com/"},
            }

        backend = FakeBackend()
        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            session_probe=fake_probe,
            backend=backend,
            relaunch_browser=lambda: relaunch_calls.append("chatgpt"),
        )

        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        self.assertEqual(backend.submit_calls, 1)
        self.assertEqual(relaunch_calls, [])
        self.assertNotIn("retry_decision", event_names)
        self.assertEqual(event_names[-1], "final_state")
        submit_evidence = cast(
            dict[str, object],
            cast(dict[str, object], result["details"])["submit_evidence"],
        )
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertEqual(submit_evidence["attempt_key"], "attempt-1")

    def test_generate_gpt_response_text_does_not_resubmit_after_read_failure(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.submit_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                self.submit_calls += 1
                return {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                }

            def read_response_state(self) -> dict[str, object]:
                raise RuntimeError("read timeout")

        relaunch_calls: list[str] = []

        def fake_probe(port: int) -> dict[str, object]:
            return {
                "probe_backend": "raw_cdp_http",
                "port": port,
                "tab_count": 1,
                "selected_tab": {"title": "ChatGPT", "url": "https://chatgpt.com/"},
            }

        backend = FakeBackend()
        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            session_probe=fake_probe,
            backend=backend,
            relaunch_browser=lambda: relaunch_calls.append("chatgpt"),
        )

        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        self.assertEqual(backend.submit_calls, 1)
        self.assertEqual(relaunch_calls, [])
        self.assertNotIn("retry_decision", event_names)
        self.assertEqual(event_names[-1], "final_state")


if __name__ == "__main__":
    _ = unittest.main()

from __future__ import annotations

import json
import itertools
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import cast

from runtime_v2.stage1.chatgpt_backend import (
    AgentBrowserCdpBackend,
    ChatGPTBackend,
    CHATGPT_LONGFORM_TITLE_SUBSTRING,
    CHATGPT_LONGFORM_URL_SUBSTRING,
    _click_send_script,
    _input_ready_script,
    _normalized_no_send_evidence,
    _prepare_input_script,
    reset_chatgpt_context,
    _select_page_target,
)
from runtime_v2.stage1.chatgpt_interaction import (
    CHATGPT_INPUT_SELECTORS,
    _response_text_from_state,
    generate_gpt_response_text,
)


class RuntimeV2Stage1ChatgptInteractionTests(unittest.TestCase):
    def test_normalized_no_send_evidence_preserves_no_input_diagnostics(self) -> None:
        evidence = _normalized_no_send_evidence(
            {
                "error": "NO_INPUT",
                "visibleSelectorMatches": 0,
                "visibleChatInputEditor": False,
                "visibleContenteditableCount": 0,
                "visibleProseMirrorCount": 1,
                "inputSelectorError": "",
            }
        )

        diagnostics = cast(dict[str, object], evidence["no_input_diagnostics"])
        self.assertEqual(diagnostics["visibleSelectorMatches"], 0)
        self.assertEqual(diagnostics["visibleProseMirrorCount"], 1)

    def test_normalized_no_send_evidence_preserves_input_success_diagnostics(
        self,
    ) -> None:
        evidence = _normalized_no_send_evidence(
            {
                "error": "NO_INPUT",
                "inputSuccess": False,
                "inputFinalText": "Topic: sample\n[Voice]",
                "inputPromptNormalized": "Topic: sample [Voice] [#01]",
            }
        )

        diagnostics = cast(dict[str, object], evidence["input_success_diagnostics"])
        self.assertFalse(bool(diagnostics["inputSuccess"]))
        self.assertIn("Topic: sample", str(diagnostics["inputFinalText"]))

    def test_input_ready_script_does_not_use_chatinput_only_heuristic(self) -> None:
        script = _input_ready_script()

        self.assertNotIn("!!chatInput && !ssr", script)
        self.assertIn(
            "const proseMirror = document.querySelector('.ProseMirror')", script
        )
        self.assertIn(
            "const ready = visible(proseMirror) || visible(interactive)", script
        )

    def test_input_selectors_include_tagless_prosemirror_first(self) -> None:
        self.assertIn(".ProseMirror[contenteditable='true']", CHATGPT_INPUT_SELECTORS)
        self.assertLess(
            CHATGPT_INPUT_SELECTORS.index(".ProseMirror[contenteditable='true']"),
            CHATGPT_INPUT_SELECTORS.index("div.ProseMirror[contenteditable='true']"),
        )

    def test_default_runner_uses_tolerant_utf8_decode(self) -> None:
        with mock.patch("runtime_v2.stage1.chatgpt_backend.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=["agent-browser"],
                returncode=0,
                stdout="ok",
                stderr="",
            )

            from runtime_v2.stage1.chatgpt_backend import _default_runner

            result = _default_runner(["agent-browser", "--version"], 5)

        self.assertEqual(result, "ok")
        self.assertEqual(run_mock.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run_mock.call_args.kwargs["errors"], "replace")

    def test_generate_gpt_response_text_passes_expected_url_substring_to_backend(
        self,
    ) -> None:
        backend = mock.Mock()
        backend.submit_prompt.return_value = {
            "ok": True,
            "submit_evidence": {
                "classification": "sent",
                "classification_reason": "send_button_clicked",
                "retry_safe_decision": False,
            },
        }
        backend.read_response_state.return_value = {
            "has_stop": False,
            "has_send_button": True,
            "assistant_block_count": 1,
            "assistant_text": "final json",
            "legacy_blocks": [],
        }

        with mock.patch(
            "runtime_v2.stage1.chatgpt_interaction.AgentBrowserCdpBackend",
            return_value=backend,
        ) as backend_ctor:
            _ = generate_gpt_response_text(
                prompt="hello",
                expected_url_substring="https://chatgpt.com/g/g-foo/c/bar",
                timeout_sec=1,
                poll_interval_sec=0.01,
                completion_idle_sec=0.01,
            )

        backend_ctor.assert_called_once()
        self.assertEqual(
            backend_ctor.call_args.kwargs["expected_url_substring"],
            "https://chatgpt.com/g/g-foo/c/bar",
        )

    def test_select_page_target_rejects_longform_conversation_url_by_title(
        self,
    ) -> None:
        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend.urllib.request.urlopen"
        ) as urlopen:
            payload = [
                {
                    "type": "page",
                    "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
                    "url": "https://chatgpt.com/c/69b1bbcd-52fc-83a4-9cc4-ced9b739cc7f",
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
                }
            ]
            response = mock.MagicMock()
            response.read.return_value = json.dumps(payload).encode("utf-8")
            urlopen.return_value.__enter__.return_value = response

            with self.assertRaises(RuntimeError):
                _ = _select_page_target(9222, CHATGPT_LONGFORM_URL_SUBSTRING)

    def test_select_page_target_accepts_exact_longform_gpt_url(self) -> None:
        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend.urllib.request.urlopen"
        ) as urlopen:
            payload = [
                {
                    "type": "page",
                    "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
                    "url": CHATGPT_LONGFORM_URL_SUBSTRING,
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
                }
            ]
            response = mock.MagicMock()
            response.read.return_value = json.dumps(payload).encode("utf-8")
            urlopen.return_value.__enter__.return_value = response

            target = _select_page_target(9222, CHATGPT_LONGFORM_URL_SUBSTRING)

        self.assertEqual(target["url"], CHATGPT_LONGFORM_URL_SUBSTRING)

    def test_select_page_target_accepts_longform_gpt_url_with_scheme(self) -> None:
        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend.urllib.request.urlopen"
        ) as urlopen:
            payload = [
                {
                    "type": "page",
                    "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
                    "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}/",
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
                }
            ]
            response = mock.MagicMock()
            response.read.return_value = json.dumps(payload).encode("utf-8")
            urlopen.return_value.__enter__.return_value = response

            target = _select_page_target(9222, CHATGPT_LONGFORM_URL_SUBSTRING)

        self.assertEqual(target["url"], f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}/")

    def test_select_page_target_accepts_longform_conversation_url(self) -> None:
        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend.urllib.request.urlopen"
        ) as urlopen:
            payload = [
                {
                    "type": "page",
                    "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
                    "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}/c/abc123",
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
                }
            ]
            response = mock.MagicMock()
            response.read.return_value = json.dumps(payload).encode("utf-8")
            urlopen.return_value.__enter__.return_value = response

            target = _select_page_target(9222, CHATGPT_LONGFORM_URL_SUBSTRING)

        self.assertEqual(
            target["url"], f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}/c/abc123"
        )

    def test_current_selected_tab_prefers_remembered_longform_target_after_fallback(
        self,
    ) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["#composer-submit-button"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["div[data-message-author-role='assistant']"],
        )
        backend._last_selected_target = {
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
            "url": CHATGPT_LONGFORM_URL_SUBSTRING,
            "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
        }

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend._select_page_target",
            side_effect=RuntimeError("CDP_TARGET_NOT_FOUND"),
        ):
            selected = backend._current_selected_tab()

        self.assertEqual(selected["url"], CHATGPT_LONGFORM_URL_SUBSTRING)

    def test_ensure_custom_gpt_page_waits_for_prompt_after_fallback_navigation(
        self,
    ) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["#composer-submit-button"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["div[data-message-author-role='assistant']"],
        )
        generic = {
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
            "url": "https://chatgpt.com/",
            "title": "ChatGPT",
        }

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                side_effect=RuntimeError("CDP_TARGET_NOT_FOUND"),
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_generic_chatgpt_target",
                return_value=generic,
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_method"
            ) as nav_mock,
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._wait_for_chatgpt_prompt_ready"
            ) as wait_mock,
        ):
            backend._ensure_custom_gpt_page()

        nav_mock.assert_called_once()
        wait_mock.assert_called_once_with(
            generic["webSocketDebuggerUrl"], timeout_sec=30.0
        )

    def test_ensure_custom_gpt_page_uses_resolved_timeout_budget(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["#composer-submit-button"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["div[data-message-author-role='assistant']"],
            raw_cdp_timeout_resolver=lambda default: 7.0,
        )
        generic = {
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
            "url": "https://chatgpt.com/",
            "title": "ChatGPT",
        }

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                side_effect=RuntimeError("CDP_TARGET_NOT_FOUND"),
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_generic_chatgpt_target",
                return_value=generic,
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_method"
            ) as nav_mock,
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._wait_for_chatgpt_prompt_ready"
            ) as wait_mock,
        ):
            backend._ensure_custom_gpt_page()

        self.assertEqual(nav_mock.call_args.kwargs["timeout_sec"], 7.0)
        self.assertEqual(wait_mock.call_args.kwargs["timeout_sec"], 7.0)

    def test_reset_chatgpt_context_uses_deadline_budget(self) -> None:
        target = {
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test",
            "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
            "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
        }

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                return_value=target,
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._wait_for_chatgpt_prompt_ready",
                side_effect=[RuntimeError("not_ready"), None],
            ) as wait_mock,
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_method"
            ) as nav_mock,
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.time.time",
                side_effect=[100.0, 107.0, 108.0],
            ),
            mock.patch("runtime_v2.stage1.chatgpt_backend.time.sleep"),
        ):
            _ = reset_chatgpt_context(9222, deadline_ts=110.0)

        self.assertEqual(wait_mock.call_args_list[0].kwargs["timeout_sec"], 2.0)
        self.assertEqual(nav_mock.call_args.kwargs["timeout_sec"], 10.0)
        self.assertEqual(wait_mock.call_args_list[1].kwargs["timeout_sec"], 2.0)

    def test_wait_for_send_state_rechecks_prompt_when_send_missing(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["#composer-submit-button"],
            stop_selectors=["button[data-testid='stop-button']"],
            response_selectors=["div[data-message-author-role='assistant']"],
        )

        eval_payloads = [
            {
                "send_found": False,
                "send_enabled": False,
                "send_disabled": False,
                "in_flight_marker": False,
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
            },
            {
                "ok": True,
                "sendClicked": True,
                "sendTestId": "send-button",
                "sendAriaLabel": "보내기",
            },
            {
                "send_found": False,
                "send_enabled": False,
                "send_disabled": False,
                "in_flight_marker": True,
            },
        ]

        with (
            mock.patch.object(
                backend,
                "_run_eval_with_retry",
                side_effect=[
                    json.dumps(state, ensure_ascii=True) for state in eval_payloads
                ],
            ),
            mock.patch.object(
                backend, "_ensure_chatgpt_target_selected"
            ) as ensure_mock,
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._wait_for_chatgpt_prompt_ready"
            ) as wait_mock,
            mock.patch.object(
                backend,
                "_current_selected_tab",
                return_value={
                    "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/test"
                },
            ),
        ):
            result = backend._wait_for_send_state("payload")

        self.assertTrue(bool(result["ok"]))
        self.assertGreaterEqual(ensure_mock.call_count, 1)
        self.assertGreaterEqual(wait_mock.call_count, 1)

    def test_submit_prompt_retries_when_input_did_not_stick(self) -> None:
        eval_payloads = [
            {"ok": True, "inputSelector": "#prompt-textarea", "inputSuccess": False},
            {"ok": True, "inputSelector": "#prompt-textarea", "inputSuccess": True},
        ]
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=lambda command, timeout_sec: json.dumps(eval_payloads.pop(0))
            if command[-2] == "eval"
            else "ok",
        )

        with (
            mock.patch.object(
                backend, "_wait_for_input_ready", return_value={"ready": True}
            ),
            mock.patch.object(
                backend,
                "_wait_for_send_state",
                return_value={"ok": True, "sendClicked": True, "submit_evidence": {}},
            ),
            mock.patch.object(backend, "_ensure_custom_gpt_page") as ensure_mock,
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        self.assertGreaterEqual(ensure_mock.call_count, 1)

    def test_prepare_input_requires_exact_prompt_match(self) -> None:
        payload = json.dumps(
            {
                "prompt": "정확한 입력 문장",
                "inputSelectors": ["#prompt-textarea"],
            },
            ensure_ascii=False,
        )
        script = _prepare_input_script(payload)
        self.assertIn("finalText === normalize(config.prompt)", script)
        self.assertIn("replace(/\\n{2,}/g, '\\n')", script)
        self.assertIn(
            "normalize(input.value || '') === normalize(config.prompt)", script
        )
        self.assertIn("replace(/\\r\\n/g, '\\n')", script)
        self.assertIn("const safeQuery = (selector)", script)
        self.assertIn("inputSelectorError", script)
        self.assertIn("INPUT_EVAL_EXCEPTION", script)

    def test_prepare_and_click_scripts_include_plain_prosemirror_fallback(self) -> None:
        payload = json.dumps(
            {
                "prompt": "정확한 입력 문장",
                "inputSelectors": ["#prompt-textarea"],
                "sendSelectors": ["button[data-testid='send-button']"],
            },
            ensure_ascii=False,
        )

        prepare_script = _prepare_input_script(payload)
        click_script = _click_send_script(payload)

        self.assertIn("document.querySelectorAll('.ProseMirror')", prepare_script)
        self.assertIn("document.querySelectorAll('.ProseMirror')", click_script)
        self.assertIn(
            "const proseMirrors = Array.from(document.querySelectorAll('.ProseMirror')).filter((el) => el && el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null) && !el.closest('[data-message-author-role=\"assistant\"]'))",
            prepare_script,
        )
        self.assertIn(
            "const proseMirrors = Array.from(document.querySelectorAll('.ProseMirror')).filter((el) => el && el.isConnected && (((el.getClientRects && el.getClientRects().length > 0)) || el.offsetParent !== null) && !el.closest('[data-message-author-role=\"assistant\"]'))",
            click_script,
        )

    def test_prepare_input_no_input_returns_candidate_counts(self) -> None:
        payload = json.dumps(
            {
                "prompt": "정확한 입력 문장",
                "inputSelectors": ["#prompt-textarea"],
            },
            ensure_ascii=False,
        )

        script = _prepare_input_script(payload)

        self.assertIn("visibleSelectorMatches", script)
        self.assertIn("visibleContenteditableCount", script)
        self.assertIn("visibleProseMirrorCount", script)
        self.assertIn("visibleChatInputEditor", script)

    def test_submit_prompt_marks_send_click_without_transition_as_ambiguous(
        self,
    ) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
        )
        eval_payloads = [
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "ok": True,
                "sendClicked": True,
                "sendTestId": "send-button",
                "sendAriaLabel": "보내기",
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
        ]

        with (
            mock.patch.object(
                backend,
                "_run_eval_with_retry",
                side_effect=[
                    json.dumps(state, ensure_ascii=True) for state in eval_payloads
                ],
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.time.sleep", return_value=None
            ),
            mock.patch("runtime_v2.stage1.chatgpt_backend._SEND_ACK_TIMEOUT_SEC", 0.1),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.time.time",
                side_effect=itertools.chain(
                    [0.0, 0.0, 0.2],
                    itertools.repeat(0.2),
                ),
            ),
        ):
            result = backend._wait_for_send_state("payload")

        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertEqual(
            submit_evidence["classification_reason"], "send_click_unconfirmed"
        )

    def test_submit_prompt_waits_for_send_ack_before_marking_sent(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
        )
        eval_payloads = [
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "ok": True,
                "sendClicked": True,
                "sendTestId": "send-button",
                "sendAriaLabel": "보내기",
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": True,
                "send_enabled": True,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": False,
                "send_enabled": False,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": False,
                "send_enabled": False,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
            {
                "send_found": False,
                "send_enabled": False,
                "send_disabled": False,
                "send_test_id": "send-button",
                "send_aria_label": "보내기",
                "in_flight_marker": False,
                "state_transition": False,
            },
        ]

        with (
            mock.patch.object(
                backend,
                "_run_eval_with_retry",
                side_effect=[
                    json.dumps(state, ensure_ascii=True) for state in eval_payloads
                ],
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.time.sleep", return_value=None
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.time.time",
                side_effect=itertools.chain(
                    [0.0, 0.0, 0.5, 1.0, 1.5, 1.8, 2.1],
                    itertools.repeat(2.1),
                ),
            ),
        ):
            result = backend._wait_for_send_state("payload")

        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "sent")
        self.assertEqual(
            submit_evidence["classification_reason"], "send_button_clicked"
        )

    def test_submit_prompt_treats_click_eval_exception_as_ambiguous(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
        )

        with (
            mock.patch.object(
                backend, "_wait_for_input_ready", return_value={"ready": True}
            ),
            mock.patch.object(
                backend,
                "_run_eval_with_retry",
                side_effect=[
                    json.dumps(
                        {
                            "ok": True,
                            "inputSelector": "#prompt-textarea",
                            "inputSuccess": True,
                        },
                        ensure_ascii=True,
                    ),
                    json.dumps(
                        {
                            "send_found": True,
                            "send_enabled": True,
                            "send_disabled": False,
                            "send_test_id": "send-button",
                            "send_aria_label": "보내기",
                            "in_flight_marker": False,
                            "state_transition": False,
                        },
                        ensure_ascii=True,
                    ),
                    RuntimeError("CDP_EVAL_EXCEPTION"),
                    json.dumps(
                        {
                            "send_found": True,
                            "send_enabled": True,
                            "send_disabled": False,
                            "send_test_id": "send-button",
                            "send_aria_label": "보내기",
                            "in_flight_marker": False,
                            "state_transition": False,
                        },
                        ensure_ascii=True,
                    ),
                ],
            ),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertEqual(submit_evidence["classification_reason"], "CDP_EVAL_EXCEPTION")

    def test_submit_prompt_treats_input_eval_exception_as_ambiguous(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
        )

        with (
            mock.patch.object(
                backend, "_wait_for_input_ready", return_value={"ready": True}
            ),
            mock.patch.object(
                backend,
                "_run_eval_with_retry",
                side_effect=RuntimeError("CDP_EVAL_EXCEPTION"),
            ),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertEqual(submit_evidence["classification_reason"], "CDP_EVAL_EXCEPTION")

    def test_submit_prompt_accepts_send_state_after_click_exception(self) -> None:
        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
        )

        with (
            mock.patch.object(
                backend, "_wait_for_input_ready", return_value={"ready": True}
            ),
            mock.patch.object(
                backend,
                "_run_eval_with_retry",
                side_effect=[
                    json.dumps(
                        {
                            "ok": True,
                            "inputSelector": "#prompt-textarea",
                            "inputSuccess": True,
                        },
                        ensure_ascii=True,
                    ),
                    json.dumps(
                        {
                            "send_found": True,
                            "send_enabled": True,
                            "send_disabled": False,
                            "send_test_id": "send-button",
                            "send_aria_label": "보내기",
                            "in_flight_marker": False,
                            "state_transition": False,
                        },
                        ensure_ascii=True,
                    ),
                    RuntimeError("CDP_EVAL_EXCEPTION"),
                    json.dumps(
                        {
                            "send_found": False,
                            "send_enabled": False,
                            "send_disabled": False,
                            "send_test_id": "send-button",
                            "send_aria_label": "보내기",
                            "in_flight_marker": False,
                            "state_transition": False,
                            "terminal_success_observed": False,
                        },
                        ensure_ascii=True,
                    ),
                ],
            ),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "sent")
        self.assertEqual(
            submit_evidence["classification_reason"],
            "send_state_after_click_exception",
        )

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

    def test_response_text_from_state_accepts_label_embedded_legacy_blocks(
        self,
    ) -> None:
        response = _response_text_from_state(
            "plain text",
            [
                {
                    "label": "[#01]\n첫 번째 장면 설명",
                    "body": "",
                },
                {
                    "label": "[#02]\n두 번째 장면 설명",
                    "body": "",
                },
            ],
        )

        self.assertIn("[#01]\n첫 번째 장면 설명", response)
        self.assertIn("[#02]\n두 번째 장면 설명", response)

    def test_response_text_from_state_ignores_status_only_assistant_text(self) -> None:
        self.assertEqual(_response_text_from_state("생각 중지됨", []), "")
        self.assertEqual(_response_text_from_state("롱폼의 말:\n생각 중지됨", []), "")
        self.assertEqual(_response_text_from_state("롱폼의 말:\n문서 읽는 중", []), "")

    def test_generate_gpt_response_text_does_not_treat_recovery_cta_as_streaming(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self._reads = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "sent",
                        "classification_reason": "send_clicked",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                self._reads += 1
                if self._reads == 1:
                    return {
                        "assistant_text": "",
                        "legacy_blocks": [],
                        "has_stop": False,
                        "has_send_button": True,
                        "recovery_clicked": True,
                    }
                return {
                    "assistant_text": "[Voice]\nCOPY\nhello",
                    "legacy_blocks": [],
                    "has_stop": False,
                    "has_send_button": True,
                    "recovery_clicked": False,
                }

        result = generate_gpt_response_text(
            prompt="hello",
            backend=FakeBackend(),
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.0,
            response_start_timeout_sec=0.1,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")

    def test_response_script_falls_back_to_conversation_turn_sections(self) -> None:
        from runtime_v2.stage1.chatgpt_backend import _response_script

        script = _response_script(
            '{"stopSelectors":[],"sendSelectors":[],"responseSelectors":[]}'
        )

        self.assertIn("conversation-turn-", script)
        self.assertIn("나의 말:", script)
        self.assertIn("의 말:", script)

    def test_response_script_excludes_stop_labeled_composer_button_from_send(
        self,
    ) -> None:
        from runtime_v2.stage1.chatgpt_backend import _response_script

        script = _response_script(
            '{"stopSelectors":["button[aria-label="Stop streaming"]"],"sendSelectors":["#composer-submit-button"],"responseSelectors":[]}'
        )

        self.assertIn("!isStopLike(el)", script)
        self.assertIn("if (!hasSendButton && isSendLike(composerBtn))", script)

    def test_generate_gpt_response_text_retries_once_when_thinking_stops(self) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self._attempt = 0
                self._reads = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                self._attempt += 1
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "sent",
                        "classification_reason": "send_clicked",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                self._reads += 1
                if self._attempt == 1:
                    if self._reads == 1:
                        return {
                            "assistant_text": "",
                            "legacy_blocks": [],
                            "has_stop": True,
                            "has_send_button": False,
                            "thinking_stopped": False,
                        }
                    return {
                        "assistant_text": "",
                        "legacy_blocks": [],
                        "has_stop": False,
                        "has_send_button": False,
                        "thinking_stopped": True,
                    }
                return {
                    "assistant_text": "[Voice]\nCOPY\nhello",
                    "legacy_blocks": [],
                    "has_stop": False,
                    "has_send_button": True,
                    "thinking_stopped": False,
                }

        relaunch_calls: list[str] = []
        result = generate_gpt_response_text(
            prompt="hello",
            backend=FakeBackend(),
            timeout_sec=5,
            poll_interval_sec=0.01,
            completion_idle_sec=0.0,
            response_start_timeout_sec=0.1,
            relaunch_browser=lambda: relaunch_calls.append("relaunch"),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(relaunch_calls, ["relaunch"])

    def test_generate_gpt_response_text_fails_closed_after_retry_when_thinking_stops(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self._attempt = 0
                self._reads = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                self._attempt += 1
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "sent",
                        "classification_reason": "send_clicked",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                self._reads += 1
                if self._reads in (1, 3):
                    return {
                        "assistant_text": "",
                        "legacy_blocks": [],
                        "has_stop": True,
                        "has_send_button": False,
                        "thinking_stopped": False,
                    }
                return {
                    "assistant_text": "",
                    "legacy_blocks": [],
                    "has_stop": False,
                    "has_send_button": False,
                    "thinking_stopped": True,
                }

        relaunch_calls: list[str] = []
        result = generate_gpt_response_text(
            prompt="hello",
            backend=FakeBackend(),
            timeout_sec=5,
            poll_interval_sec=0.01,
            completion_idle_sec=0.0,
            response_start_timeout_sec=0.1,
            relaunch_browser=lambda: relaunch_calls.append("relaunch"),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_THINKING_STOPPED_NO_OUTPUT")
        self.assertEqual(relaunch_calls, ["relaunch"])

    def test_generate_gpt_response_text_does_not_retry_thinking_stopped_after_ambiguous_submit(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "ambiguous",
                        "classification_reason": "submit_ui_unconfirmed",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                return {
                    "assistant_text": "",
                    "legacy_blocks": [],
                    "has_stop": True,
                    "has_send_button": False,
                    "thinking_stopped": True,
                }

        relaunch_calls: list[str] = []
        result = generate_gpt_response_text(
            prompt="hello",
            backend=FakeBackend(),
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.0,
            response_start_timeout_sec=0.1,
            relaunch_browser=lambda: relaunch_calls.append("relaunch"),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_THINKING_STOPPED_NO_OUTPUT")
        self.assertEqual(relaunch_calls, [])
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("thinking_stopped", event_names)
        self.assertNotIn("retry_decision", event_names)

    def test_generate_gpt_response_text_surfaces_upstream_retry_exhausted(self) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self._attempt = 0
                self._reads = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                self._attempt += 1
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "sent",
                        "classification_reason": "send_clicked",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                self._reads += 1
                if self._reads in (1, 3):
                    return {
                        "assistant_text": "",
                        "legacy_blocks": [],
                        "has_stop": True,
                        "has_send_button": False,
                        "thinking_stopped": False,
                        "upstream_error_retry_exhausted": False,
                    }
                return {
                    "assistant_text": "",
                    "legacy_blocks": [],
                    "has_stop": False,
                    "has_send_button": False,
                    "thinking_stopped": True,
                    "upstream_error_retry_exhausted": True,
                }

        relaunch_calls: list[str] = []
        result = generate_gpt_response_text(
            prompt="hello",
            backend=FakeBackend(),
            timeout_sec=5,
            poll_interval_sec=0.01,
            completion_idle_sec=0.0,
            response_start_timeout_sec=0.1,
            relaunch_browser=lambda: relaunch_calls.append("relaunch"),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_UPSTREAM_ERROR_RETRY_EXHAUSTED")
        self.assertEqual(relaunch_calls, ["relaunch"])
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("thinking_stopped", event_names)
        self.assertIn("upstream_error_retry_exhausted", event_names)

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
            mock.patch.object(
                backend,
                "_wait_for_send_state",
                return_value={"ok": True, "sendClicked": True, "submit_evidence": {}},
            ),
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

    def test_click_send_script_prefers_visible_send_button_before_enter_fallback(
        self,
    ) -> None:
        payload = json.dumps(
            {
                "prompt": "hello",
                "inputSelectors": ["#prompt-textarea"],
                "sendSelectors": ["button[data-testid='send-button']"],
            },
            ensure_ascii=True,
        )

        script = _click_send_script(payload)

        self.assertIn("const sendSelectors = config.sendSelectors || []", script)
        self.assertIn("send.click()", script)
        self.assertIn("send.getAttribute('data-testid') || 'send-button'", script)
        self.assertIn("key:'Enter'", script)
        self.assertIn("sendTestId:'enter-key'", script)

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

        with (
            mock.patch.object(
                backend,
                "_wait_for_send_state",
                return_value={"ok": True, "sendClicked": True, "submit_evidence": {}},
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
                return_value=[
                    {"title": "Omnibox Popup", "url": "chrome://newtab"},
                    {
                        "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
                        "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
                    },
                ],
            ),
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
            mock.patch.object(
                backend,
                "_wait_for_send_state",
                return_value={"ok": True, "sendClicked": True, "submit_evidence": {}},
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._http_cdp_tab_list",
                return_value=[{"title": "ChatGPT", "url": "https://chatgpt.com/c/abc"}],
            ),
            mock.patch("runtime_v2.stage1.chatgpt_backend.time.sleep"),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        self.assertGreaterEqual(eval_calls, 2)

    def test_raw_cdp_method_timeout_is_wrapped_as_runtime_error(self) -> None:
        from runtime_v2.stage1 import chatgpt_backend as backend_module
        import websocket

        class _FakeSocket:
            def send(self, payload: str) -> None:
                _ = payload

            def recv(self) -> str:
                raise websocket.WebSocketTimeoutException("Connection timed out")

            def close(self) -> None:
                return None

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend.websocket.create_connection",
            return_value=_FakeSocket(),
        ):
            with self.assertRaises(RuntimeError):
                backend_module._run_raw_cdp_method(
                    "ws://127.0.0.1/devtools/page/test",
                    "Page.navigate",
                    {"url": "https://chatgpt.com"},
                )

    def test_raw_cdp_method_respects_deadline_during_event_stream(self) -> None:
        from runtime_v2.stage1 import chatgpt_backend as backend_module

        class _FakeSocket:
            def send(self, payload: str) -> None:
                _ = payload

            def recv(self) -> str:
                return json.dumps({"method": "Runtime.consoleAPICalled"})

            def close(self) -> None:
                return None

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.websocket.create_connection",
                return_value=_FakeSocket(),
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.time.time",
                side_effect=[100.0, 100.0, 100.5, 101.5],
            ),
        ):
            with self.assertRaises(RuntimeError) as exc_info:
                backend_module._run_raw_cdp_method(
                    "ws://127.0.0.1/devtools/page/test",
                    "Page.navigate",
                    {"url": "https://chatgpt.com"},
                    timeout_sec=1.0,
                )

        self.assertEqual(str(exc_info.exception), "CDP_METHOD_TIMEOUT")

    def test_wait_for_chatgpt_prompt_ready_passes_remaining_budget_to_cdp(self) -> None:
        from runtime_v2.stage1 import chatgpt_backend as backend_module

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_method",
                return_value={"result": {"value": True}},
            ) as method_mock,
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend.time.time",
                side_effect=[100.0, 100.0, 101.5],
            ),
        ):
            backend_module._wait_for_chatgpt_prompt_ready(
                "ws://127.0.0.1/devtools/page/test",
                timeout_sec=1.5,
            )

        self.assertEqual(method_mock.call_args.kwargs["timeout_sec"], 1.0)

    def test_run_raw_cdp_eval_preserves_exception_details(self) -> None:
        from runtime_v2.stage1 import chatgpt_backend as backend_module

        with mock.patch(
            "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_method",
            return_value={
                "exceptionDetails": {
                    "text": "TypeError",
                    "lineNumber": 7,
                    "columnNumber": 12,
                    "exception": {"description": "Cannot read properties of null"},
                }
            },
        ):
            with self.assertRaises(RuntimeError) as exc_info:
                backend_module._run_raw_cdp_eval(
                    "ws://127.0.0.1/devtools/page/test",
                    "(() => null.click())()",
                )

        self.assertIn("CDP_EVAL_EXCEPTION:", str(exc_info.exception))
        self.assertIn("Cannot read properties of null", str(exc_info.exception))
        self.assertIn("@ 7:12", str(exc_info.exception))

    def test_agent_browser_backend_falls_back_to_raw_cdp_eval_after_retry_failures(
        self,
    ) -> None:
        eval_calls = 0
        raw_eval_calls = 0

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

        def fake_raw_eval(ws_url: str, script: str, **kwargs) -> str:
            nonlocal raw_eval_calls
            _ = ws_url
            _ = script
            _ = kwargs
            raw_eval_calls += 1
            if raw_eval_calls == 1:
                return json.dumps(
                    json.dumps(
                        {
                            "ok": True,
                            "inputSelector": "#prompt-textarea",
                            "inputSuccess": True,
                            "sendClicked": True,
                        }
                    )
                )
            return json.dumps(
                json.dumps(
                    {
                        "send_found": False,
                        "send_enabled": False,
                        "send_disabled": False,
                        "in_flight_marker": True,
                        "assistant_text": "",
                        "assistant_block_count": 0,
                        "legacy_blocks": [],
                    }
                )
            )

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )

        with (
            mock.patch.object(
                backend,
                "_wait_for_input_ready",
                return_value={"ready": True},
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
                side_effect=fake_raw_eval,
            ),
            mock.patch("runtime_v2.stage1.chatgpt_backend.time.sleep"),
        ):
            result = backend.submit_prompt("hello")

        self.assertTrue(bool(result["ok"]))
        self.assertGreaterEqual(eval_calls, 3)
        self.assertIn(
            "eval_raw_cdp_fallback", cast(list[object], result["backend_fallbacks"])
        )

    def test_backend_raw_cdp_fallback_uses_resolved_timeout_budget(self) -> None:
        def fake_runner(command: list[str], timeout_sec: int) -> str:
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2:] == ["tab", "list"]:
                return (
                    f"[1] Omnibox Popup - chrome://newtab\n"
                    f"[2] {CHATGPT_LONGFORM_TITLE_SUBSTRING} - https://{CHATGPT_LONGFORM_URL_SUBSTRING}"
                )
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
            raw_cdp_timeout_resolver=lambda default: 7.0,
        )

        with (
            mock.patch.object(
                backend,
                "_wait_for_input_ready",
                return_value={"ready": True},
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
            ) as raw_eval,
            mock.patch("runtime_v2.stage1.chatgpt_backend.time.sleep"),
        ):
            _ = backend.submit_prompt("hello")

        self.assertEqual(raw_eval.call_args.kwargs["timeout_sec"], 7.0)

    def test_agent_browser_backend_fails_closed_when_read_target_disappears(
        self,
    ) -> None:
        def fake_runner(command: list[str], timeout_sec: int) -> str:
            if command[-2:] == ["tab", "2"]:
                return "ok"
            if command[-2:] == ["tab", "list"]:
                return f"[1] Omnibox Popup - chrome://newtab\n[2] {CHATGPT_LONGFORM_TITLE_SUBSTRING} - https://{CHATGPT_LONGFORM_URL_SUBSTRING}"
            if command[-2] == "eval":
                raise RuntimeError("CDP_TARGET_NOT_FOUND")
            return "ok"

        backend = AgentBrowserCdpBackend(
            port=9222,
            input_selectors=["#prompt-textarea"],
            send_selectors=["button[data-testid='send-button']"],
            stop_selectors=["button[aria-label='Stop streaming']"],
            response_selectors=["[data-message-author-role='assistant']"],
            command_runner=fake_runner,
        )
        selected_target = {
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/abc",
            "url": f"https://{CHATGPT_LONGFORM_URL_SUBSTRING}",
            "title": CHATGPT_LONGFORM_TITLE_SUBSTRING,
        }
        backend._last_selected_target = dict(selected_target)

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                side_effect=RuntimeError("CDP_TARGET_NOT_FOUND"),
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_backend._select_generic_chatgpt_target",
                return_value=None,
            ),
        ):
            with self.assertRaises(RuntimeError) as raised:
                _ = backend.read_response_state()

        self.assertIn("CDP_TARGET_NOT_FOUND", str(raised.exception))

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
            mock.patch.object(
                backend,
                "_wait_for_send_state",
                return_value={"ok": True, "sendClicked": True, "submit_evidence": {}},
            ),
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
            mock.patch.object(
                backend,
                "_wait_for_send_state",
                return_value={"ok": True, "sendClicked": True, "submit_evidence": {}},
            ),
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
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            response_start_timeout_sec=0.1,
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
                        "has_send_button": False,
                        "assistant_block_count": 1,
                        "assistant_text": "draft",
                    }
                return {
                    "has_stop": False,
                    "has_send_button": True,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_interaction.time.sleep", return_value=None
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_interaction.time.time",
                side_effect=itertools.chain(
                    [0.0, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 1.1],
                    itertools.repeat(1.1),
                ),
            ),
        ):
            result = generate_gpt_response_text(
                prompt="test prompt",
                port=9222,
                timeout_sec=1,
                poll_interval_sec=0.01,
                completion_idle_sec=0.01,
                response_start_timeout_sec=0.02,
                backend=FakeBackend(),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertEqual(event_names[0], "submit_start")
        self.assertIn("submit_ambiguous", event_names)
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
                    "has_send_button": False,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")

    def test_generate_gpt_response_text_finishes_after_idle_with_stop_only(
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
                    "has_stop": True,
                    "has_send_button": False,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        with (
            mock.patch(
                "runtime_v2.stage1.chatgpt_interaction.time.sleep", return_value=None
            ),
            mock.patch(
                "runtime_v2.stage1.chatgpt_interaction.time.time",
                side_effect=itertools.chain(
                    [0.0, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 1.1],
                    itertools.repeat(1.1),
                ),
            ),
        ):
            result = generate_gpt_response_text(
                prompt="test prompt",
                port=9222,
                timeout_sec=1,
                poll_interval_sec=0.01,
                completion_idle_sec=0.01,
                response_start_timeout_sec=0.02,
                backend=FakeBackend(),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("streaming_seen", event_names)
        self.assertIn("response_stable", event_names)

    def test_generate_gpt_response_text_writes_live_timeline_and_state_files(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                _ = prompt
                return {
                    "ok": True,
                    "inputSelector": "#prompt-textarea",
                    "sendClicked": True,
                }

            def read_response_state(self) -> dict[str, object]:
                return {
                    "has_stop": False,
                    "has_send_button": False,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                    "current_url": "https://chatgpt.com/g/example",
                    "current_title": "ChatGPT",
                }

        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            timeline_path = root / "chatgpt_timeline.jsonl"
            state_path = root / "chatgpt_live_state.json"

            result = generate_gpt_response_text(
                prompt="test prompt",
                port=9222,
                timeout_sec=1,
                poll_interval_sec=0.01,
                completion_idle_sec=0.01,
                backend=FakeBackend(),
                timeline_path=timeline_path,
                state_path=state_path,
            )

            timeline_lines = [
                json.loads(line)
                for line in timeline_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            state_payload = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")
        self.assertIn("submit_start", [str(item["event"]) for item in timeline_lines])
        self.assertEqual(state_payload["assistant_text_len"], len("final json"))
        self.assertEqual(state_payload["current_title"], "ChatGPT")

    def test_generate_gpt_response_text_does_not_finish_on_preamble_only_stop_state(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "sent",
                        "classification_reason": "send_button_clicked",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                return {
                    "has_stop": True,
                    "has_send_button": True,
                    "assistant_block_count": 1,
                    "assistant_text": "내용을 확정하기 위해 공적 자료를 확인하고 있습니다.",
                    "legacy_blocks": [],
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            response_start_timeout_sec=0.1,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")

    def test_generate_gpt_response_text_accepts_legacy_blocks_without_stop_gate(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.read_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "sendClicked": True,
                    "sendTestId": "send-button",
                    "submit_evidence": {
                        "classification": "ambiguous",
                        "classification_reason": "send_click_unconfirmed",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                self.read_calls += 1
                if self.read_calls == 1:
                    return {
                        "has_stop": False,
                        "has_send_button": False,
                        "assistant_block_count": 0,
                        "assistant_text": "",
                        "legacy_blocks": [],
                    }
                return {
                    "has_stop": False,
                    "has_send_button": True,
                    "assistant_block_count": 1,
                    "assistant_text": "",
                    "legacy_blocks": [
                        {"label": "[Voice]", "body": "narration"},
                        {"label": "[#01]", "body": "scene body"},
                    ],
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("[Voice]\nnarration", str(result["response_text"]))

    def test_generate_gpt_response_text_does_not_finish_on_non_scene_legacy_blocks(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.read_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "sendClicked": True,
                    "sendTestId": "send-button",
                    "submit_evidence": {
                        "classification": "ambiguous",
                        "classification_reason": "send_click_unconfirmed",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                self.read_calls += 1
                if self.read_calls == 1:
                    return {
                        "has_stop": False,
                        "has_send_button": False,
                        "assistant_block_count": 0,
                        "assistant_text": "",
                        "legacy_blocks": [],
                    }
                return {
                    "has_stop": False,
                    "has_send_button": True,
                    "assistant_block_count": 1,
                    "assistant_text": "",
                    "legacy_blocks": [
                        {"label": "[Voice]", "body": "narration"},
                        {"label": "[Title]", "body": "money title"},
                        {"label": "[Description]", "body": "desc"},
                        {"label": "[Keywords]", "body": "kw1, kw2"},
                    ],
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            response_start_timeout_sec=0.1,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")

    def test_generate_gpt_response_text_marks_ambiguous_submit_boundary(self) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "ambiguous",
                        "classification_reason": "submit_ui_unconfirmed",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                return {
                    "has_stop": False,
                    "has_send_button": False,
                    "assistant_block_count": 0,
                    "assistant_text": "",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            response_start_timeout_sec=0.1,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("submit_ambiguous", event_names)
        self.assertNotIn("submit_ok", event_names)
        self.assertNotIn("read_retry", event_names)

    def test_generate_gpt_response_text_allows_probe_after_send_click_unconfirmed(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def __init__(self) -> None:
                self.read_calls = 0

            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "sendClicked": True,
                    "sendTestId": "send-button",
                    "submit_evidence": {
                        "classification": "ambiguous",
                        "classification_reason": "send_click_unconfirmed",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                self.read_calls += 1
                if self.read_calls == 1:
                    return {
                        "has_stop": True,
                        "has_send_button": False,
                        "assistant_block_count": 1,
                        "assistant_text": "draft",
                    }
                return {
                    "has_stop": False,
                    "has_send_button": True,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")
        submit_evidence = cast(dict[str, object], result["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "sent")
        self.assertEqual(submit_evidence["classification_reason"], "streaming_observed")

    def test_generate_gpt_response_text_treats_missing_submit_evidence_as_ambiguous(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "sendClicked": True,
                    "submit_evidence": {},
                }

            def read_response_state(self) -> dict[str, object]:
                return {
                    "has_stop": False,
                    "has_send_button": False,
                    "assistant_block_count": 0,
                    "assistant_text": "",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            response_start_timeout_sec=0.1,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")
        submit_info = cast(dict[str, object], result["submit_info"])
        submit_evidence = cast(dict[str, object], submit_info["submit_evidence"])
        self.assertEqual(submit_evidence["classification"], "ambiguous")
        self.assertEqual(
            submit_evidence["classification_reason"], "submit_evidence_missing"
        )
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("submit_ambiguous", event_names)
        self.assertNotIn("submit_ok", event_names)

    def test_generate_gpt_response_text_does_not_retry_response_not_started_after_ambiguous_submit(
        self,
    ) -> None:
        class FakeBackend(ChatGPTBackend):
            def submit_prompt(self, prompt: str) -> dict[str, object]:
                return {
                    "ok": True,
                    "submit_evidence": {
                        "classification": "ambiguous",
                        "classification_reason": "submit_ui_unconfirmed",
                        "retry_safe_decision": False,
                    },
                }

            def read_response_state(self) -> dict[str, object]:
                return {
                    "has_stop": False,
                    "has_send_button": False,
                    "assistant_block_count": 0,
                    "assistant_text": "",
                }

        relaunch_calls: list[str] = []
        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            response_start_timeout_sec=0.03,
            backend=FakeBackend(),
            relaunch_browser=lambda: relaunch_calls.append("chatgpt"),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        self.assertEqual(relaunch_calls, [])
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("submit_ambiguous", event_names)
        self.assertNotIn("response_not_started", event_names)
        self.assertNotIn("retry_decision", event_names)

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
            completion_idle_sec=0.01,
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
        submit_info = cast(dict[str, object], result["submit_info"])
        self.assertEqual(
            cast(dict[str, object], submit_info["submit_evidence"])["attempt_key"],
            "attempt-1",
        )
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
        self.assertIn("submit_ambiguous", event_names)
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
            completion_idle_sec=0.01,
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
            completion_idle_sec=0.01,
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
        submit_info = cast(dict[str, object], result["submit_info"])
        self.assertEqual(
            cast(dict[str, object], submit_info["submit_evidence"])["attempt_key"],
            "attempt-1",
        )
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
            completion_idle_sec=0.01,
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

    def test_generate_gpt_response_text_retries_transient_read_timeout(self) -> None:
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
                if self.read_calls == 1:
                    raise RuntimeError("CDP_METHOD_TIMEOUT")
                if self.read_calls == 2:
                    return {
                        "has_stop": True,
                        "has_send_button": False,
                        "assistant_block_count": 1,
                        "assistant_text": "draft",
                    }
                return {
                    "has_stop": False,
                    "has_send_button": True,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "ok")
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("read_retry", event_names)
        self.assertNotIn("read_failed", event_names)

    def test_generate_gpt_response_text_retries_when_response_never_starts(
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
                return {
                    "has_stop": False,
                    "has_send_button": False,
                    "assistant_block_count": 0,
                    "assistant_text": "",
                }

        relaunch_calls: list[str] = []
        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            timeout_sec=1,
            poll_interval_sec=0.01,
            response_start_timeout_sec=0.03,
            completion_idle_sec=0.01,
            backend=FakeBackend(),
            relaunch_browser=lambda: relaunch_calls.append("chatgpt"),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(relaunch_calls, [])
        timeline = cast(list[dict[str, object]], result["timeline"])
        event_names = [str(item["event"]) for item in timeline]
        self.assertIn("response_not_started", event_names)
        self.assertNotIn("retry_decision", event_names)

    def test_generate_gpt_response_text_accepts_response_when_send_button_returns(
        self,
    ) -> None:
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
                if self.read_calls == 1:
                    return {
                        "has_stop": True,
                        "has_send_button": False,
                        "assistant_block_count": 0,
                        "assistant_text": "",
                    }
                return {
                    "has_stop": True,
                    "has_send_button": True,
                    "assistant_block_count": 1,
                    "assistant_text": "final json",
                }

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            completion_idle_sec=0.01,
            backend=FakeBackend(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")


if __name__ == "__main__":
    _ = unittest.main()

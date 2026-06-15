from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.stage1.chatgpt_runner import (
    _relaunch_chatgpt_browser,
    attach_gpt_response_text_from_browser_evidence,
    build_live_chatgpt_prompt,
    build_video_plan_from_stage1_parsed_payload,
    build_video_plan_from_topic_spec,
    run_stage1_chatgpt_job,
)
from runtime_v2.stage1.chatgpt_backend import (
    CHATGPT_LONGFORM_URL,
    CHATGPT_LONGFORM_URL_SUBSTRING,
    reset_chatgpt_context,
)
from runtime_v2.stage1.chatgpt_backend import chatgpt_context_ready
from runtime_v2.stage1.parsed_payload import build_stage1_parsed_payload_from_topic_spec


def _topic_spec(
    *, topic: str = "Bridge topic", channel: int | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract": "topic_spec",
        "contract_version": "1.0",
        "run_id": "stage1-run-1",
        "row_ref": "Sheet1!row1",
        "topic": topic,
        "status_snapshot": "",
        "excel_snapshot_hash": "hash-1",
    }
    if channel is not None:
        payload["channel"] = channel
    return payload


def _gpt_response_text() -> str:
    return """```json
{
  "story_outline": ["intro beat", "ending beat"],
  "scene_prompts": ["scene one from gpt", "scene two from gpt"],
  "videos": ["video clip one", "video clip two"],
  "voice_groups": [
    {"scene_index": 1, "voice": "narration"},
    {"scene_index": 2, "voice": "narration"}
  ]
}
```"""


def _inline_gpt_response_text() -> str:
    return """
Title: 머니 제목
Title for Thumb: 머니 썸네일 제목
Description: 머니 설명
Keywords: 머니, 연금, 생활비
Voice: 차분한 여성 내레이션
BGM: serious piano
#01: 십세부터 오십세까지 설명
#02: 육십세부터 구십세까지 설명
"""


class RuntimeV2Stage1ChatgptTests(unittest.TestCase):
    def test_chatgpt_context_ready_returns_false_when_target_missing(self) -> None:
        with patch(
            "runtime_v2.stage1.chatgpt_backend._select_page_target",
            side_effect=RuntimeError("missing"),
        ):
            self.assertFalse(chatgpt_context_ready(9222))

    def test_stage1_live_capture_uses_gpt_root_target_not_old_chat_url(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            topic_spec = _topic_spec()
            topic_spec["url"] = "https://chatgpt.com/g/g-foo/c/old-chat-id"
            browser_evidence: dict[str, object] = {"service": "chatgpt", "port": 9222}

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context"
                ) as reset_mock,
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": _gpt_response_text(),
                        "submit_info": {},
                        "final_state": {},
                        "timeline": [],
                    },
                ),
            ):
                enriched = attach_gpt_response_text_from_browser_evidence(
                    topic_spec, browser_evidence, workspace=workspace
                )

        self.assertIn("gpt_response_text", enriched)
        self.assertEqual(
            reset_mock.call_args.kwargs["expected_url_substring"],
            CHATGPT_LONGFORM_URL_SUBSTRING,
        )
        self.assertEqual(
            reset_mock.call_args.kwargs["target_url"],
            CHATGPT_LONGFORM_URL,
        )

    def test_stage1_resets_context_even_when_context_ready(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.chatgpt_context_ready",
                    return_value=True,
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context"
                ) as reset_mock,
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": "[Title]\n제목\n\n[Voice]\n1. 첫 장면\n2. 둘째 장면\n\n[#01]\n장면 하나\n\n[#02]\n장면 둘",
                        "submit_info": {},
                        "final_state": {},
                        "timeline": [],
                    },
                ),
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(),
                    workspace,
                    debug_log="logs/stage1-skip-reset.jsonl",
                )

        self.assertEqual(result["status"], "ok")
        reset_mock.assert_called_once()
        self.assertEqual(reset_mock.call_args.args, (9222,))
        self.assertIn("deadline_ts", reset_mock.call_args.kwargs)

    def test_reset_chatgpt_context_waits_for_prompt_ready(self) -> None:
        runtime_results = iter(
            [
                {"result": {"value": False}},
                {"result": {"value": False}},
                {"result": {"value": False}},
                {"result": {"value": True}},
                {"result": {"value": True}},
                {"result": {"value": True}},
            ]
        )

        def _fake_run_raw(
            ws_url: str, method: str, params: dict[str, object], **kwargs: object
        ):
            if method == "Runtime.evaluate":
                expression = str(params.get("expression", ""))
                if "New chat" in expression or "새 채팅" in expression:
                    return {
                        "result": {
                            "value": '{"clicked": true, "selector": "label_match"}'
                        }
                    }
                return next(runtime_results)
            return {}

        with (
            patch(
                "runtime_v2.stage1.chatgpt_backend._select_page_target",
                return_value={
                    "webSocketDebuggerUrl": "ws://example",
                    "url": "https://chatgpt.com/g/foo",
                    "title": "ChatGPT",
                },
            ),
            patch(
                "runtime_v2.stage1.chatgpt_backend._run_raw_cdp_method",
                side_effect=_fake_run_raw,
            ) as run_raw,
            patch(
                "runtime_v2.stage1.chatgpt_backend._start_new_chat",
                return_value={"clicked": True, "selector": "label_match"},
            ),
        ):
            result = reset_chatgpt_context(9222)

        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(run_raw.call_count, 2)

    def test_relaunch_chatgpt_browser_is_noop_in_attach_only_mode(self) -> None:
        with patch.dict(
            os.environ,
            {"RUNTIME_V2_CHATGPT_ATTACH_ONLY": "1"},
            clear=False,
        ):
            with patch(
                "runtime_v2.stage1.chatgpt_runner.open_browser_for_login"
            ) as open_browser:
                _relaunch_chatgpt_browser()

        open_browser.assert_not_called()

    def test_relaunch_chatgpt_browser_uses_legacy_launch_cmd_in_attach_only_mode(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "RUNTIME_V2_CHATGPT_ATTACH_ONLY": "1",
                "RUNTIME_V2_CHATGPT_LEGACY_LAUNCH_CMD": "python scripts/chatgpt_launcher_canary.py",
            },
            clear=False,
        ):
            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.open_browser_for_login"
                ) as open_browser,
                patch("runtime_v2.stage1.chatgpt_runner.subprocess.Popen") as popen,
                patch("runtime_v2.stage1.chatgpt_runner.sleep", return_value=None),
            ):
                _relaunch_chatgpt_browser()

        open_browser.assert_not_called()
        popen.assert_called_once()

    def test_build_live_chatgpt_prompt_requests_structured_stage1_fields(self) -> None:
        prompt = build_live_chatgpt_prompt(
            {
                "topic": "국민연금 수령 시기를 앞당기면 손해인가 이득인가",
            }
        )

        self.assertIn("국민연금 수령 시기를 앞당기면 손해인가 이득인가", prompt)
        self.assertIn("[Title]", prompt)
        self.assertIn("[Title for Thumb]", prompt)
        self.assertIn("[Description]", prompt)
        self.assertIn("[Keywords]", prompt)
        self.assertIn("[Voice]", prompt)
        self.assertIn("[#01]", prompt)

    def test_build_live_chatgpt_prompt_strips_topic_whitespace(self) -> None:
        prompt = build_live_chatgpt_prompt(
            {
                "topic": "  국민연금 수령 시기를 앞당기면 손해인가 이득인가  ",
            }
        )

        self.assertIn("국민연금 수령 시기를 앞당기면 손해인가 이득인가", prompt)
        self.assertNotIn("  국민연금 수령 시기를 앞당기면 손해인가 이득인가  ", prompt)

    def test_build_live_chatgpt_prompt_ignores_status_snapshot(
        self,
    ) -> None:
        prompt = build_live_chatgpt_prompt(
            {
                "topic": "요양 시설 비용 현실과 준비해야 할 금액",
                "status_snapshot": "OK",
            }
        )

        self.assertIn("요양 시설 비용 현실과 준비해야 할 금액", prompt)
        self.assertNotIn("status_snapshot", prompt)

    def test_stage1_runner_only_plans_from_existing_topic_spec(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": _gpt_response_text(),
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(),
                    workspace,
                    debug_log="logs/stage1-audit-run.jsonl",
                )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(cast(str, result["result_path"])).exists())
            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            handoff = cast(
                dict[str, object],
                cast(dict[str, object], result_payload["details"])["stage1_handoff"],
            )
            contract = cast(dict[str, object], handoff["contract"])

            self.assertEqual(contract["version"], "stage1_handoff.v1.0")
            self.assertIsInstance(contract["voice_texts"], list)
            self.assertIn("ref_img_1", contract)
            self.assertIn("ref_img_2", contract)
            voice_texts = cast(list[dict[str, object]], contract["voice_texts"])
            voice_groups = cast(list[dict[str, object]], contract["voice_groups"])
            self.assertEqual(voice_texts[0]["text"], voice_groups[0]["voice"])

    def test_stage1_result_includes_declared_next_jobs_from_video_plan(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": _gpt_response_text(),
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(),
                    workspace,
                    debug_log="logs/stage1-audit-run.jsonl",
                )
            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )

        self.assertEqual(result["status"], "ok")
        self.assertGreater(
            len(cast(list[object], result_payload.get("next_jobs", []))), 0
        )

    def test_stage1_does_not_gate_on_chatgpt_context_ready(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.chatgpt_context_ready",
                    return_value=False,
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.attach_gpt_response_text_from_browser_evidence",
                    return_value={
                        **_topic_spec(),
                        "browser_evidence": {"snapshot_path": "dummy.txt"},
                        "gpt_response_text": _gpt_response_text(),
                    },
                ),
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(),
                    workspace,
                    debug_log="logs/stage1-no-reset-gate.jsonl",
                )

        self.assertEqual(result["status"], "ok")

    def test_stage1_ignores_channel_hint_and_builds_native_video_plan(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": _gpt_response_text(),
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(channel=4),
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        video_plan = cast(dict[str, object], details["video_plan"])
        evidence = cast(dict[str, object], video_plan["evidence"])
        self.assertEqual(evidence["source"], "chatgpt_runner")

    def test_stage1_channel_hint_does_not_require_external_rows_json(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": _gpt_response_text(),
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(channel=4),
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

        self.assertEqual(result["status"], "ok")

    def test_stage1_builds_video_plan_from_topic_spec(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            topic_spec = _topic_spec()
            topic_spec["gpt_response_text"] = _gpt_response_text()
            video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)
            self.assertTrue((workspace / "video_plan.json").exists())

        self.assertEqual(video_plan["contract"], "video_plan")
        self.assertEqual(video_plan["run_id"], "stage1-run-1")
        self.assertEqual(video_plan["row_ref"], "Sheet1!row1")

    def test_stage1_builds_video_plan_with_videos_field_from_parsed_payload(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            parsed_payload: dict[str, object] = {
                "run_id": "stage1-run-1",
                "row_ref": "Sheet1!row1",
                "topic": "Bridge topic",
                "scene_prompts": ["scene one", "scene two"],
                "voice_groups": [
                    {"scene_index": 1, "voice": "narration"},
                    {"scene_index": 2, "voice": "narration"},
                ],
                "videos": ["video clip one", "video clip two"],
                "reason_code": "ok",
                "excel_snapshot_hash": "hash-1",
            }

            video_plan = build_video_plan_from_stage1_parsed_payload(
                parsed_payload, workspace
            )

        self.assertEqual(
            cast(list[object], cast(dict[str, object], video_plan)["videos"]),
            ["video clip one", "video clip two"],
        )

    def test_stage1_parsed_payload_falls_back_to_topic_spec_optional_fields(
        self,
    ) -> None:
        topic_spec = _topic_spec()
        topic_spec["gpt_response_text"] = _inline_gpt_response_text()
        topic_spec["ref_img_1"] = "ref prompt one"
        topic_spec["ref_img_2"] = "ref prompt two"
        topic_spec["url"] = "https://example.com/bridge"
        topic_spec["videos"] = ["video clip one", "video clip two"]

        parsed_payload = build_stage1_parsed_payload_from_topic_spec(topic_spec)

        self.assertEqual(parsed_payload["ref_img_1"], "ref prompt one")
        self.assertEqual(parsed_payload["ref_img_2"], "ref prompt two")
        self.assertEqual(parsed_payload["url"], "https://example.com/bridge")
        self.assertEqual(parsed_payload["videos"], ["video clip one", "video clip two"])

    def test_stage1_chatgpt_runner_accepts_only_topic_spec_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            result = run_stage1_chatgpt_job(
                {"contract": "not_topic_spec", "run_id": "bad-run"},
                workspace,
                debug_log="logs/stage1-run-1.jsonl",
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "invalid_topic_spec")

    def test_stage1_chatgpt_runner_rejects_unsupported_topic_spec_version(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            invalid_spec = _topic_spec()
            invalid_spec["contract_version"] = "2.0"

            result = run_stage1_chatgpt_job(
                invalid_spec,
                workspace,
                debug_log="logs/stage1-run-1.jsonl",
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "invalid_topic_spec")

    def test_video_plan_contains_scene_voice_and_reason_code(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["gpt_response_text"] = _gpt_response_text()
            video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)

        self.assertEqual(video_plan["reason_code"], "ok")
        scene_plan = cast(list[dict[str, object]], video_plan["scene_plan"])
        voice_plan = cast(dict[str, object], video_plan["voice_plan"])
        self.assertGreaterEqual(len(scene_plan), 2)
        self.assertEqual(str(voice_plan["mapping_source"]), "stage1_parsed")

    def test_stage1_result_records_debug_log_and_run_id(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": _gpt_response_text(),
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(),
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            details = cast(dict[str, object], result_payload["details"])
            stage1_result = cast(dict[str, object], details["stage1_result"])

        self.assertEqual(stage1_result["run_id"], "stage1-run-1")
        self.assertEqual(stage1_result["debug_log"], "logs/stage1-run-1.jsonl")
        self.assertTrue(
            str(stage1_result["video_plan_path"]).endswith("video_plan.json")
        )
        self.assertTrue(str(stage1_result["result_path"]).endswith("result.json"))
        self.assertTrue(
            str(stage1_result["raw_output_path"]).endswith("raw_output.json")
        )
        self.assertTrue(
            str(stage1_result["parsed_payload_path"]).endswith("parsed_payload.json")
        )
        self.assertTrue(
            str(stage1_result["handoff_path"]).endswith("stage1_handoff.json")
        )

    def test_stage1_result_keeps_downstream_seeding_data_in_video_plan_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": _gpt_response_text(),
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(),
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            details = cast(dict[str, object], result_payload["details"])
            stage1_result = cast(dict[str, object], details["stage1_result"])
            next_jobs = cast(list[object], stage1_result["next_jobs"])
            top_level_next_jobs = cast(list[object], result_payload["next_jobs"])
            video_plan = cast(dict[str, object], details["video_plan"])

        self.assertEqual(result["status"], "ok")
        self.assertEqual(next_jobs, top_level_next_jobs)
        self.assertGreater(len(next_jobs), 0)
        self.assertEqual(stage1_result["status"], "ok")
        self.assertEqual(stage1_result["row_ref"], "Sheet1!row1")
        self.assertEqual(video_plan["run_id"], "stage1-run-1")
        self.assertEqual(video_plan["row_ref"], "Sheet1!row1")
        self.assertIn("stage1_handoff", video_plan)

    def test_stage1_runner_writes_parsed_payload_and_handoff_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": _gpt_response_text(),
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(topic="Money flow"),
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            details = cast(dict[str, object], result_payload["details"])
            handoff = cast(dict[str, object], details["stage1_handoff"])
            parsed_payload = cast(dict[str, object], handoff["contract"])

            self.assertEqual(result["status"], "ok")
            self.assertEqual(parsed_payload["version"], "stage1_handoff.v1.0")
            self.assertEqual(parsed_payload["title"], "Money flow")
            self.assertTrue(Path(cast(str, handoff["raw_output_path"])).exists())
            self.assertTrue(Path(cast(str, handoff["parsed_payload_path"])).exists())

    def test_stage1_failure_preserves_raw_output_path_in_result(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["gpt_response_text"] = "not-json-response"

            result = run_stage1_chatgpt_job(
                topic_spec,
                workspace,
                debug_log="logs/stage1-run-1.jsonl",
            )

        details = cast(dict[str, object], result["details"])
        stage1_result = cast(dict[str, object], details["stage1_result"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            str(stage1_result["raw_output_path"]).endswith("raw_output.json")
        )

    def test_stage1_runner_fails_closed_without_gpt_response_text(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "failed",
                    "error_code": "CHATGPT_BACKEND_UNAVAILABLE",
                    "failure_stage": "submit",
                    "details": {"backend_error": "missing_output"},
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ) as generate_mock:
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

            raw_output = cast(
                dict[str, object],
                json.loads((workspace / "raw_output.json").read_text(encoding="utf-8")),
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        self.assertEqual(raw_output["source"], "gpt_capture_only")
        self.assertEqual(raw_output["response_text"], "")
        generate_mock.assert_called_once()

    def test_stage1_live_capture_partial_text_does_not_emit_structured_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["run_id"] = "stage1-row15-run"
            topic_spec["row_ref"] = "Sheet1!row15"
            topic_spec["browser_evidence"] = {"service": "chatgpt", "port": 9222}

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "failed",
                    "error_code": "CHATGPT_RESPONSE_TIMEOUT",
                    "failure_stage": "read",
                    "details": {},
                    "response_text": "[Title]\n介護施設の費用、",
                    "submit_info": {"sendClicked": True},
                    "final_state": {
                        "has_stop": False,
                        "has_send_button": False,
                        "assistant_text": "[Title]\n介護施設の費用、",
                        "assistant_block_count": 2,
                        "legacy_blocks": [],
                    },
                    "timeline": [
                        {"seq": 1, "event": "submit_start", "attempt": 1},
                        {"seq": 2, "event": "submit_ok", "attempt": 1},
                    ],
                },
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    workspace,
                    debug_log="logs/stage1-row15-run.jsonl",
                )

            raw_output_exists = (workspace / "raw_output.json").exists()
            parsed_payload_exists = (workspace / "parsed_payload.json").exists()
            handoff_exists = (workspace / "stage1_handoff.json").exists()
            video_plan_exists = (workspace / "video_plan.json").exists()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_RESPONSE_TIMEOUT")
        self.assertTrue(raw_output_exists)
        self.assertFalse(parsed_payload_exists)
        self.assertFalse(handoff_exists)
        self.assertFalse(video_plan_exists)

    def test_stage1_current_row_generates_same_run_artifact_bundle(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="요양 시설 비용 현실과 준비해야 할 금액")
            topic_spec["run_id"] = "stage1-row15-run"
            topic_spec["row_ref"] = "Sheet1!row15"
            topic_spec["gpt_response_text"] = _gpt_response_text()

            result = run_stage1_chatgpt_job(
                topic_spec,
                workspace,
                debug_log="logs/stage1-row15-run.jsonl",
            )

            raw_output_path = workspace / "raw_output.json"
            parsed_payload_path = workspace / "parsed_payload.json"
            handoff_path = workspace / "stage1_handoff.json"
            video_plan_path = workspace / "video_plan.json"
            parsed_payload = cast(
                dict[str, object],
                json.loads(parsed_payload_path.read_text(encoding="utf-8")),
            )
            handoff = cast(
                dict[str, object],
                json.loads(handoff_path.read_text(encoding="utf-8")),
            )
            video_plan = cast(
                dict[str, object],
                json.loads(video_plan_path.read_text(encoding="utf-8")),
            )
            raw_output_exists = raw_output_path.exists()
            parsed_payload_exists = parsed_payload_path.exists()
            handoff_exists = handoff_path.exists()
            video_plan_exists = video_plan_path.exists()

        self.assertEqual(result["status"], "ok")
        self.assertTrue(raw_output_exists)
        self.assertTrue(parsed_payload_exists)
        self.assertTrue(handoff_exists)
        self.assertTrue(video_plan_exists)
        self.assertEqual(parsed_payload["run_id"], "stage1-row15-run")
        self.assertEqual(parsed_payload["row_ref"], "Sheet1!row15")
        self.assertEqual(video_plan["run_id"], "stage1-row15-run")
        self.assertEqual(video_plan["row_ref"], "Sheet1!row15")
        self.assertIn("stage1_handoff", video_plan)
        self.assertEqual(
            cast(dict[str, object], handoff["contract"])["run_id"],
            "stage1-row15-run",
        )

    def test_stage1_runner_attempts_live_capture_without_explicit_browser_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": _gpt_response_text(),
                        "submit_info": {"sendClicked": True},
                        "final_state": {"assistant_block_count": 1},
                        "timeline": [
                            {
                                "ts": "2026-03-10T00:00:00Z",
                                "seq": 1,
                                "event": "submit_start",
                            },
                            {
                                "ts": "2026-03-10T00:00:01Z",
                                "seq": 2,
                                "event": "final_state",
                            },
                        ],
                    },
                ) as generate_mock,
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                    return_value={"status": "ok", "port": 9222},
                ) as reset_mock,
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    root / "workspace",
                    debug_log="logs/stage1-run-1.jsonl",
                )

            raw_output = cast(
                dict[str, object],
                json.loads(
                    (root / "workspace" / "raw_output.json").read_text(encoding="utf-8")
                ),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(raw_output["source"], "gpt_response_text")
        browser_evidence = cast(dict[str, object], raw_output["browser_evidence"])
        self.assertEqual(browser_evidence["service"], "chatgpt")
        self.assertEqual(browser_evidence["port"], 9222)
        reset_mock.assert_called_once()
        self.assertEqual(reset_mock.call_args.args, (9222,))
        self.assertIn("deadline_ts", reset_mock.call_args.kwargs)
        generate_mock.assert_called_once()

    def test_stage1_runner_uses_real_gpt_response_text_when_present(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["gpt_response_text"] = _gpt_response_text()

            result = run_stage1_chatgpt_job(
                topic_spec,
                workspace,
                debug_log="logs/stage1-run-1.jsonl",
            )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            details = cast(dict[str, object], result_payload["details"])
            handoff = cast(dict[str, object], details["stage1_handoff"])
            parsed_payload = cast(dict[str, object], handoff["contract"])
            raw_output = cast(
                dict[str, object],
                json.loads(
                    Path(cast(str, handoff["raw_output_path"])).read_text(
                        encoding="utf-8"
                    )
                ),
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(raw_output["source"], "gpt_response_text")
            self.assertIn(
                "scene one from gpt",
                cast(list[object], parsed_payload["scene_prompts"]),
            )
            self.assertEqual(parsed_payload["title"], "Money flow")

    def test_stage1_runner_accepts_inline_label_value_gpt_response(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["gpt_response_text"] = _inline_gpt_response_text()

            result = run_stage1_chatgpt_job(
                topic_spec,
                workspace,
                debug_log="logs/stage1-inline-run.jsonl",
            )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            details = cast(dict[str, object], result_payload["details"])
            handoff = cast(dict[str, object], details["stage1_handoff"])
            parsed_payload = cast(dict[str, object], handoff["contract"])

        self.assertEqual(result["status"], "ok")
        self.assertEqual(parsed_payload["title"], "머니 제목")
        self.assertEqual(parsed_payload["title_for_thumb"], "머니 썸네일 제목")
        self.assertEqual(parsed_payload["description"], "머니 설명")
        self.assertEqual(parsed_payload["bgm"], "serious piano")
        self.assertEqual(parsed_payload["version"], "stage1_handoff.v1.0")
        self.assertIsInstance(parsed_payload["voice_texts"], list)
        self.assertIn("ref_img_1", parsed_payload)
        self.assertIn("ref_img_2", parsed_payload)
        self.assertEqual(
            parsed_payload["scene_prompts"],
            ["십세부터 오십세까지 설명", "육십세부터 구십세까지 설명"],
        )

    def test_stage1_runner_surfaces_parse_fallback_warnings_in_handoff(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["gpt_response_text"] = _inline_gpt_response_text()

            with patch(
                "runtime_v2.stage1.gpt_response_parser.build_topic_spec_from_gpt_response",
                side_effect=ValueError("structured_parse_failed"),
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    workspace,
                    debug_log="logs/stage1-inline-run.jsonl",
                )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            details = cast(dict[str, object], result_payload["details"])
            handoff = cast(dict[str, object], details["stage1_handoff"])
            parsed_payload = cast(dict[str, object], handoff["contract"])

        self.assertEqual(result["status"], "ok")
        self.assertEqual(parsed_payload["parse_mode"], "block_fallback")
        self.assertEqual(parsed_payload["parse_warnings"], ["structured_parse_failed"])

    def test_stage1_runner_prefers_voice_lines_over_duplicated_voice_groups(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["gpt_response_text"] = "structured-json-present"

            with patch(
                "runtime_v2.stage1.parsed_payload.parse_gpt_response_text",
                return_value=(
                    {
                        "title": "Money title",
                        "title_for_thumb": "Money thumb",
                        "description": "Money description",
                        "keywords": ["money"],
                        "bgm": "serious piano",
                        "scene_prompts": ["scene one", "scene two"],
                        "voice_groups": [
                            {"scene_index": 1, "voice": "same long body"},
                            {"scene_index": 2, "voice": "same long body"},
                        ],
                        "voice_lines": ["voice one", "voice two"],
                        "videos": ["video one", "video two"],
                    },
                    [],
                ),
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

            parsed_payload = cast(
                dict[str, object],
                json.loads(
                    (workspace / "parsed_payload.json").read_text(encoding="utf-8")
                ),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            parsed_payload["voice_groups"],
            [
                {"scene_index": 1, "voice": "voice one"},
                {"scene_index": 2, "voice": "voice two"},
            ],
        )

    def test_stage1_can_attach_gpt_response_text_from_browser_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "snapshot.txt"
            _ = snapshot_path.write_text(_gpt_response_text(), encoding="utf-8")

            topic_spec = _topic_spec(topic="Money flow")
            enriched = attach_gpt_response_text_from_browser_evidence(
                topic_spec,
                {"snapshot_path": str(snapshot_path)},
            )

        self.assertEqual(str(enriched["gpt_response_source"]), "agent_browser_snapshot")
        self.assertIn("story_outline", str(enriched["gpt_response_text"]))

    def test_stage1_runner_auto_uses_browser_evidence_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "snapshot.txt"
            _ = snapshot_path.write_text(_gpt_response_text(), encoding="utf-8")
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"snapshot_path": str(snapshot_path)}

            result = run_stage1_chatgpt_job(
                topic_spec,
                root / "workspace",
                debug_log="logs/stage1-run-1.jsonl",
            )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            handoff = cast(
                dict[str, object],
                cast(dict[str, object], result_payload["details"])["stage1_handoff"],
            )
            parsed_payload = cast(dict[str, object], handoff["contract"])

        self.assertEqual(result["status"], "ok")
        self.assertIn(
            "scene one from gpt", cast(list[object], parsed_payload["scene_prompts"])
        )

    def test_stage1_runner_can_generate_gpt_response_text_from_live_browser_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"service": "chatgpt", "port": 9222}

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": _gpt_response_text(),
                        "submit_info": {"sendClicked": True},
                        "final_state": {"assistant_block_count": 1},
                        "timeline": [
                            {
                                "ts": "2026-03-10T00:00:00Z",
                                "seq": 1,
                                "event": "submit_start",
                            },
                            {
                                "ts": "2026-03-10T00:00:01Z",
                                "seq": 2,
                                "event": "submit_ok",
                            },
                            {
                                "ts": "2026-03-10T00:00:02Z",
                                "seq": 3,
                                "event": "final_state",
                            },
                        ],
                    },
                ) as generate_mock,
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                    return_value={"status": "ok", "port": 9222},
                ) as reset_mock,
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    root / "workspace",
                    debug_log="logs/stage1-run-1.jsonl",
                )

                called_prompt = cast(str, generate_mock.call_args.kwargs["prompt"])

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )
            raw_output = cast(
                dict[str, object],
                json.loads(
                    (root / "workspace" / "raw_output.json").read_text(encoding="utf-8")
                ),
            )
            gpt_capture = cast(dict[str, object], raw_output["gpt_capture"])
            timeline_path = Path(str(gpt_capture["timeline_path"]))
            timeline_lines = [
                json.loads(line)
                for line in timeline_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            capture_started_exists = Path(
                str(gpt_capture["capture_started_path"])
            ).exists()
            state_path_value = str(gpt_capture["state_path"])
            handoff = cast(
                dict[str, object],
                cast(dict[str, object], result_payload["details"])["stage1_handoff"],
            )
            parsed_payload = cast(dict[str, object], handoff["contract"])

        self.assertEqual(result["status"], "ok")
        self.assertIn("Money flow", called_prompt)
        self.assertIn("[Voice]", called_prompt)
        self.assertIn("[#01]", called_prompt)
        self.assertEqual(raw_output["prompt_text"], called_prompt)
        self.assertEqual(gpt_capture["prompt_text"], called_prompt)
        self.assertTrue(capture_started_exists)
        self.assertTrue(state_path_value.endswith("chatgpt_live_state.json"))

    def test_live_browser_capture_passes_bounded_timeout_budget(self) -> None:
        topic_spec = _topic_spec(topic="Money flow")

        with (
            patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "failed",
                    "error_code": "CHATGPT_RESPONSE_TIMEOUT",
                    "failure_stage": "read",
                    "details": {},
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ) as generate_mock,
            patch(
                "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                return_value={"status": "ok", "port": 9222},
            ),
        ):
            enriched = attach_gpt_response_text_from_browser_evidence(
                topic_spec,
                {"service": "chatgpt", "port": 9222},
            )

        self.assertEqual(
            cast(dict[str, object], enriched["gpt_capture"])["status"], "failed"
        )
        self.assertEqual(generate_mock.call_args.kwargs["timeout_sec"], 600)
        self.assertEqual(
            generate_mock.call_args.kwargs["response_start_timeout_sec"], 30.0
        )

    def test_live_browser_capture_clamps_command_runner_to_remaining_budget(
        self,
    ) -> None:
        topic_spec = _topic_spec(topic="Money flow")
        runner_calls: list[int] = []

        def fake_generate(*, command_runner=None, **kwargs):
            assert command_runner is not None
            _ = kwargs
            runner_calls.append(command_runner(["agent-browser", "eval"], 60))
            return {
                "status": "failed",
                "error_code": "CHATGPT_RESPONSE_TIMEOUT",
                "failure_stage": "read",
                "details": {},
                "submit_info": {},
                "final_state": {},
                "timeline": [],
            }

        with (
            patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                side_effect=fake_generate,
            ),
            patch(
                "runtime_v2.stage1.chatgpt_runner._default_runner",
                side_effect=lambda command, timeout_sec: timeout_sec,
            ),
            patch(
                "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                return_value={"status": "ok", "port": 9222},
            ),
            patch(
                "runtime_v2.stage1.chatgpt_runner._LIVE_CAPTURE_TIMEOUT_SEC",
                5,
            ),
            patch(
                "runtime_v2.stage1.chatgpt_runner.time",
                side_effect=[100.0, 100.0, 105.0],
            ),
        ):
            _ = attach_gpt_response_text_from_browser_evidence(
                topic_spec,
                {"service": "chatgpt", "port": 9222},
            )

        self.assertEqual(runner_calls, [5])

    def test_stage1_runner_uses_legacy_longform_url_for_live_capture(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            topic_spec = _topic_spec()
            topic_spec["url"] = "https://chatgpt.com/g/g-foo/c/bar"
            called_kwargs: dict[str, object] = {}

            def fake_generate(*, prompt: str, port: int, relaunch_browser, **kwargs):
                nonlocal called_kwargs
                _ = (prompt, port, relaunch_browser)
                called_kwargs = dict(kwargs)
                return {
                    "status": "ok",
                    "response_text": "[Title]\n제목\n\n[Voice]\n1. 첫 장면\n2. 둘째 장면\n\n[#01]\n장면 하나\n\n[#02]\n장면 둘",
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                }

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    side_effect=fake_generate,
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                ) as reset_mock,
            ):
                _ = run_stage1_chatgpt_job(
                    topic_spec,
                    workspace,
                    debug_log="logs/stage1-topic-url.jsonl",
                )

                reset_kwargs = reset_mock.call_args.kwargs

        self.assertEqual(
            called_kwargs["expected_url_substring"],
            CHATGPT_LONGFORM_URL_SUBSTRING,
        )
        self.assertEqual(
            reset_kwargs["expected_url_substring"],
            CHATGPT_LONGFORM_URL_SUBSTRING,
        )
        self.assertEqual(reset_kwargs["target_url"], CHATGPT_LONGFORM_URL)

    def test_stage1_runner_continues_when_reset_context_fails(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            topic_spec = _topic_spec()

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                    side_effect=RuntimeError("chatgpt_prompt_not_ready"),
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": "[Title]\n제목\n\n[Voice]\n1. 첫 장면\n2. 둘째 장면\n\n[#01]\n장면 하나\n\n[#02]\n장면 둘",
                        "submit_info": {},
                        "final_state": {},
                        "timeline": [],
                    },
                ),
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    workspace,
                    debug_log="logs/stage1-reset-warning.jsonl",
                )
                result_path = Path(cast(str, result["result_path"]))
                result_payload = cast(
                    dict[str, object],
                    json.loads(result_path.read_text(encoding="utf-8")),
                )
                raw_output = cast(
                    dict[str, object],
                    json.loads(
                        (workspace / "raw_output.json").read_text(encoding="utf-8")
                    ),
                )

        self.assertEqual(result["status"], "ok")
        gpt_capture = cast(dict[str, object], raw_output["gpt_capture"])
        self.assertEqual(gpt_capture["reset_warning"], "chatgpt_prompt_not_ready")
        self.assertEqual(result_payload["status"], "ok")

    def test_stage1_runner_fails_closed_when_scene_prompts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"service": "chatgpt", "port": 9222}

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": "주제를 정리하고 있습니다.",
                        "submit_info": {},
                        "final_state": {},
                        "timeline": [],
                    },
                ) as generate_mock,
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                    return_value={"status": "ok", "port": 9222},
                ),
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    workspace,
                    debug_log="logs/stage1-no-scene-prompts.jsonl",
                )

            result_path = Path(cast(str, result["result_path"]))
            result_payload = cast(
                dict[str, object], json.loads(result_path.read_text(encoding="utf-8"))
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(generate_mock.call_count, 1)
        self.assertEqual(result_payload["error_code"], "missing_scene_prompts")

    def test_stage1_runner_retries_live_chatgpt_after_relaunch(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"service": "chatgpt", "port": 9222}

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": _gpt_response_text(),
                        "final_state": {"assistant_block_count": 1},
                        "timeline": [
                            {
                                "ts": "2026-03-10T00:00:00Z",
                                "seq": 1,
                                "event": "submit_start",
                            },
                            {
                                "ts": "2026-03-10T00:00:01Z",
                                "seq": 2,
                                "event": "retry_decision",
                            },
                            {
                                "ts": "2026-03-10T00:00:02Z",
                                "seq": 3,
                                "event": "submit_start",
                            },
                            {
                                "ts": "2026-03-10T00:00:03Z",
                                "seq": 4,
                                "event": "final_state",
                            },
                        ],
                    },
                ) as generate_mock,
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                    return_value={"status": "ok", "port": 9222},
                ) as reset_mock,
                patch(
                    "runtime_v2.stage1.chatgpt_runner.open_browser_for_login"
                ) as relaunch_mock,
                patch("runtime_v2.stage1.chatgpt_runner.sleep") as sleep_mock,
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    root / "workspace",
                    debug_log="logs/stage1-run-1.jsonl",
                )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(generate_mock.call_count, 1)
        self.assertEqual(reset_mock.call_count, 1)
        relaunch_mock.assert_not_called()
        sleep_mock.assert_not_called()

    def test_stage1_runner_records_reset_warning_when_chatgpt_context_reset_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"service": "chatgpt", "port": 9222}

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": _gpt_response_text(),
                        "submit_info": {"sendClicked": True},
                        "final_state": {"assistant_block_count": 1},
                        "timeline": [
                            {
                                "ts": "2026-03-10T00:00:00Z",
                                "seq": 1,
                                "event": "submit_start",
                            },
                            {
                                "ts": "2026-03-10T00:00:01Z",
                                "seq": 2,
                                "event": "submit_ok",
                            },
                            {
                                "ts": "2026-03-10T00:00:02Z",
                                "seq": 3,
                                "event": "final_state",
                            },
                        ],
                    },
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                    side_effect=RuntimeError("chatgpt_context_target_missing"),
                ),
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    root / "workspace",
                    debug_log="logs/stage1-run-1.jsonl",
                )
                raw_output = cast(
                    dict[str, object],
                    json.loads(
                        (root / "workspace" / "raw_output.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                )

        self.assertEqual(result["status"], "ok")
        gpt_capture = cast(dict[str, object], raw_output["gpt_capture"])
        self.assertEqual(gpt_capture["reset_warning"], "chatgpt_context_target_missing")

    def test_stage1_runner_keeps_reset_warning_when_pre_submit_chatgpt_context_reset_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"service": "chatgpt", "port": 9222}

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.reset_chatgpt_context",
                    side_effect=RuntimeError("chatgpt_context_target_missing"),
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": _gpt_response_text(),
                        "submit_info": {"sendClicked": True},
                        "final_state": {"assistant_block_count": 1},
                        "timeline": [],
                    },
                ),
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    root / "workspace",
                    debug_log="logs/stage1-run-1.jsonl",
                )
                raw_output = cast(
                    dict[str, object],
                    json.loads(
                        (root / "workspace" / "raw_output.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                )

        self.assertEqual(result["status"], "ok")
        gpt_capture = cast(dict[str, object], raw_output["gpt_capture"])
        self.assertEqual(gpt_capture["reset_warning"], "chatgpt_context_target_missing")

    def test_stage1_runner_fails_closed_when_live_chatgpt_capture_stays_failed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"service": "chatgpt", "port": 9222}

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "failed",
                        "error_code": "CHATGPT_BACKEND_UNAVAILABLE",
                        "failure_stage": "read",
                        "details": {"backend_error": "os error 10060"},
                        "submit_info": {},
                        "final_state": {},
                        "timeline": [
                            {
                                "ts": "2026-03-10T00:00:00Z",
                                "seq": 1,
                                "event": "submit_start",
                                "attempt": 1,
                            },
                            {
                                "ts": "2026-03-10T00:00:01Z",
                                "seq": 2,
                                "event": "retry_decision",
                                "attempt": 1,
                            },
                            {
                                "ts": "2026-03-10T00:00:02Z",
                                "seq": 3,
                                "event": "submit_start",
                                "attempt": 2,
                            },
                            {
                                "ts": "2026-03-10T00:00:03Z",
                                "seq": 4,
                                "event": "read_failed",
                                "attempt": 2,
                            },
                            {
                                "ts": "2026-03-10T00:00:04Z",
                                "seq": 5,
                                "event": "final_state",
                                "attempt": 2,
                            },
                        ],
                    },
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.open_browser_for_login"
                ) as relaunch_mock,
                patch("runtime_v2.stage1.chatgpt_runner.sleep") as sleep_mock,
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec,
                    root / "workspace",
                    debug_log="logs/stage1-run-1.jsonl",
                )

                raw_output = cast(
                    dict[str, object],
                    json.loads(
                        (root / "workspace" / "raw_output.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                )
                gpt_capture = cast(dict[str, object], raw_output["gpt_capture"])
                timeline_path = Path(str(gpt_capture["timeline_path"]))
                timeline_lines = [
                    json.loads(line)
                    for line in timeline_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        details = cast(dict[str, object], result["details"])
        stage1_result = cast(dict[str, object], details["stage1_result"])
        executor = cast(dict[str, object], details["executor"])
        self.assertEqual(gpt_capture["status"], "failed")
        capture_meta = cast(dict[str, object], gpt_capture["capture_meta"])
        self.assertEqual(capture_meta["run_id"], "stage1-run-1")
        self.assertEqual(capture_meta["backend_mode"], "agent_browser_live")
        self.assertEqual(capture_meta["attempt_count"], 2)
        self.assertEqual(capture_meta["attempt_key"], "attempt-2")
        self.assertEqual(
            capture_meta["final_state_code"], "CHATGPT_BACKEND_UNAVAILABLE"
        )
        self.assertIn("prompt_text", capture_meta)
        self.assertEqual(
            str(capture_meta["prompt_text"]), build_live_chatgpt_prompt(topic_spec)
        )
        self.assertTrue(str(capture_meta["git_sha"]))
        self.assertTrue(str(capture_meta["timestamp_utc"]).endswith("Z"))
        event_names = [str(item["event"]) for item in timeline_lines]
        self.assertTrue(
            all(str(item.get("attempt_key", "")).strip() for item in timeline_lines)
        )
        self.assertIn("submit_start", event_names)
        self.assertIn("read_failed", event_names)
        self.assertEqual(event_names[-1], "final_state")
        self.assertEqual(raw_output["source"], "gpt_capture_only")
        self.assertEqual(
            str(raw_output["prompt_text"]), build_live_chatgpt_prompt(topic_spec)
        )
        self.assertEqual(
            cast(dict[str, object], raw_output["gpt_capture"])["status"], "failed"
        )
        self.assertTrue(
            str(stage1_result["raw_output_path"]).endswith("raw_output.json")
        )
        relaunch_mock.assert_not_called()
        sleep_mock.assert_not_called()

    def test_stage1_runner_fails_closed_when_chatgpt_live_request_has_no_port(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Money flow")
            topic_spec["browser_evidence"] = {"service": "chatgpt"}

            result = run_stage1_chatgpt_job(
                topic_spec,
                root / "workspace",
                debug_log="logs/stage1-run-1.jsonl",
            )

            raw_output = cast(
                dict[str, object],
                json.loads(
                    (root / "workspace" / "raw_output.json").read_text(encoding="utf-8")
                ),
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "CHATGPT_BACKEND_UNAVAILABLE")
        self.assertEqual(raw_output["source"], "gpt_capture_only")
        browser_evidence = cast(dict[str, object], raw_output["browser_evidence"])
        self.assertEqual(browser_evidence["service"], "chatgpt")

    def test_stage1_route_failure_becomes_structured_failed_result(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            with (
                patch(
                    "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                    return_value={
                        "status": "ok",
                        "response_text": _gpt_response_text(),
                        "submit_info": {},
                        "final_state": {},
                        "timeline": [],
                    },
                ),
                patch(
                    "runtime_v2.stage1.chatgpt_runner.build_video_plan_from_stage1_parsed_payload",
                    side_effect=ValueError("route_failed"),
                ),
            ):
                result = run_stage1_chatgpt_job(
                    _topic_spec(),
                    workspace,
                    debug_log="logs/stage1-run-1.jsonl",
                )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "route_failed")
        details = cast(dict[str, object], result["details"])
        stage1_result = cast(dict[str, object], details["stage1_result"])
        self.assertEqual(stage1_result["status"], "error")
        self.assertEqual(stage1_result["reason_code"], "route_failed")

    def test_stage1_builds_scene_plan_from_input_shape_not_fixed_placeholder_count(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec(topic="Scene split topic")
            topic_spec["gpt_response_text"] = """```json
{
  "story_outline": ["intro beat", "middle beat", "ending beat"],
  "scene_prompts": ["scene one", "scene two", "scene three"],
  "videos": ["video clip one", "video clip two", "video clip three"],
  "voice_groups": [
    {"scene_index": 1, "voice": "narration"},
    {"scene_index": 2, "voice": "narration"},
    {"scene_index": 3, "voice": "narration"}
  ]
}
```"""

            video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)

        scene_plan = cast(list[dict[str, object]], video_plan["scene_plan"])
        voice_plan = cast(dict[str, object], video_plan["voice_plan"])
        self.assertEqual(len(scene_plan), 3)
        self.assertEqual(voice_plan["scene_count"], 3)

    def test_voice_plan_records_mapping_source_and_fails_closed_on_mismatch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec()
            topic_spec["voice_groups"] = [{"scene_index": 1, "voice": "narration"}]

            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": """```json
{
  "story_outline": ["intro beat", "ending beat"],
  "scene_prompts": ["scene one", "scene two"],
  "videos": ["video clip one", "video clip two"],
  "voice_groups": [
    {"scene_index": 1, "voice": "narration"}
  ]
}
```""",
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec, workspace, debug_log="logs/stage1-run-1.jsonl"
                )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "scene_voice_count_mismatch")

    def test_voice_plan_fails_closed_on_invalid_group_shape(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec()
            with patch(
                "runtime_v2.stage1.chatgpt_runner.generate_gpt_response_text",
                return_value={
                    "status": "ok",
                    "response_text": """```json
{
  "story_outline": ["intro beat", "ending beat"],
  "scene_prompts": ["scene one", "scene two"],
  "videos": ["video clip one", "video clip two"],
  "voice_groups": ["bad", "shape"]
}
```""",
                    "submit_info": {},
                    "final_state": {},
                    "timeline": [],
                },
            ):
                result = run_stage1_chatgpt_job(
                    topic_spec, workspace, debug_log="logs/stage1-run-1.jsonl"
                )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "invalid_voice_groups")


if __name__ == "__main__":
    _ = unittest.main()

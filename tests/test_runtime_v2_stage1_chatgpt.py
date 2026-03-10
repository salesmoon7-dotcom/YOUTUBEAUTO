from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.stage1.chatgpt_runner import (
    attach_gpt_response_text_from_browser_evidence,
    build_live_chatgpt_prompt,
    build_video_plan_from_topic_spec,
    run_stage1_chatgpt_job,
)


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
    def test_build_live_chatgpt_prompt_uses_longform_instruction_template(self) -> None:
        prompt = build_live_chatgpt_prompt(
            {
                "topic": "국민연금 수령 시기를 앞당기면 손해인가 이득인가",
            }
        )

        self.assertIn("영상 제작 모드로 진행하세요.", prompt)
        self.assertIn("출력은 [Voice] 블록부터 시작하세요.", prompt)
        self.assertIn("Research Locale: JP", prompt)
        self.assertIn("Topic: 국민연금 수령 시기를 앞당기면 손해인가 이득인가", prompt)

    def test_stage1_runner_only_plans_from_existing_topic_spec(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

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

    def test_stage1_ignores_channel_hint_and_builds_native_video_plan(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
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
            result = run_stage1_chatgpt_job(
                _topic_spec(channel=4),
                workspace,
                debug_log="logs/stage1-run-1.jsonl",
            )

        self.assertEqual(result["status"], "ok")

    def test_stage1_builds_video_plan_from_topic_spec(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            video_plan = build_video_plan_from_topic_spec(_topic_spec(), workspace)
            self.assertTrue((workspace / "video_plan.json").exists())

        self.assertEqual(video_plan["contract"], "video_plan")
        self.assertEqual(video_plan["run_id"], "stage1-run-1")
        self.assertEqual(video_plan["row_ref"], "Sheet1!row1")

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

            video_plan = build_video_plan_from_topic_spec(
                _topic_spec(topic="Money flow"), workspace
            )

        self.assertEqual(video_plan["reason_code"], "ok")
        scene_plan = cast(list[dict[str, object]], video_plan["scene_plan"])
        voice_plan = cast(dict[str, object], video_plan["voice_plan"])
        self.assertGreaterEqual(len(scene_plan), 2)
        self.assertEqual(str(voice_plan["mapping_source"]), "excel_scene")

    def test_stage1_result_records_debug_log_and_run_id(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

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
            video_plan = cast(dict[str, object], details["video_plan"])

        self.assertEqual(result["status"], "ok")
        self.assertFalse(next_jobs)
        self.assertEqual(stage1_result["status"], "ok")
        self.assertEqual(stage1_result["row_ref"], "Sheet1!row1")
        self.assertEqual(video_plan["run_id"], "stage1-run-1")
        self.assertEqual(video_plan["row_ref"], "Sheet1!row1")
        self.assertIn("stage1_handoff", video_plan)

    def test_stage1_runner_writes_parsed_payload_and_handoff_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

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

            with patch(
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
                        {"ts": "2026-03-10T00:00:01Z", "seq": 2, "event": "submit_ok"},
                        {
                            "ts": "2026-03-10T00:00:02Z",
                            "seq": 3,
                            "event": "final_state",
                        },
                    ],
                },
            ) as generate_mock:
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
            handoff = cast(
                dict[str, object],
                cast(dict[str, object], result_payload["details"])["stage1_handoff"],
            )
            parsed_payload = cast(dict[str, object], handoff["contract"])

        self.assertEqual(result["status"], "ok")
        self.assertIn("영상 제작 모드로 진행하세요.", called_prompt)
        self.assertIn("Research Locale: JP", called_prompt)
        self.assertIn(
            "scene one from gpt", cast(list[object], parsed_payload["scene_prompts"])
        )
        browser_evidence = cast(dict[str, object], raw_output["browser_evidence"])
        self.assertEqual(raw_output["source"], "gpt_response_text")
        self.assertEqual(gpt_capture["status"], "ok")
        self.assertEqual(gpt_capture["source"], "agent_browser_live")
        self.assertTrue(
            bool(cast(dict[str, object], gpt_capture["submit_info"])["sendClicked"])
        )
        capture_meta = cast(dict[str, object], gpt_capture["capture_meta"])
        self.assertEqual(capture_meta["run_id"], "stage1-run-1")
        self.assertEqual(capture_meta["backend_mode"], "agent_browser_live")
        self.assertEqual(capture_meta["attempt_count"], 1)
        self.assertEqual(capture_meta["final_state_code"], "ok")
        self.assertEqual(capture_meta["fallback_chain"], [])
        self.assertTrue(str(capture_meta["git_sha"]))
        self.assertTrue(str(capture_meta["timestamp_utc"]).endswith("Z"))
        self.assertEqual(timeline_lines[0]["event"], "submit_start")
        self.assertEqual(timeline_lines[0]["run_id"], "stage1-run-1")
        self.assertEqual(timeline_lines[-1]["event"], "final_state")
        self.assertEqual(browser_evidence["service"], "chatgpt")
        self.assertEqual(browser_evidence["port"], 9222)

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
        relaunch_mock.assert_not_called()
        sleep_mock.assert_not_called()

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
        self.assertEqual(
            capture_meta["final_state_code"], "CHATGPT_BACKEND_UNAVAILABLE"
        )
        self.assertTrue(str(capture_meta["git_sha"]))
        self.assertTrue(str(capture_meta["timestamp_utc"]).endswith("Z"))
        event_names = [str(item["event"]) for item in timeline_lines]
        self.assertIn("submit_start", event_names)
        self.assertIn("read_failed", event_names)
        self.assertEqual(event_names[-1], "final_state")
        self.assertEqual(raw_output["source"], "gpt_capture_only")
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

            with patch(
                "runtime_v2.stage1.chatgpt_runner.build_video_plan",
                side_effect=ValueError("route_failed"),
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
            topic_spec["scene_prompts"] = [
                "scene one",
                "scene two",
                "scene three",
            ]
            topic_spec["voice_groups"] = [
                {"scene_index": 1, "voice": "narration"},
                {"scene_index": 2, "voice": "narration"},
                {"scene_index": 3, "voice": "narration"},
            ]

            video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)

        scene_plan = cast(list[dict[str, object]], video_plan["scene_plan"])
        voice_plan = cast(dict[str, object], video_plan["voice_plan"])
        self.assertEqual(len(scene_plan), 3)
        self.assertEqual(voice_plan["scene_count"], 3)

    def test_voice_plan_records_mapping_source_and_fails_closed_on_mismatch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec()
            topic_spec["voice_groups"] = [{"scene_index": 1, "voice": "narration"}]

            result = run_stage1_chatgpt_job(
                topic_spec, workspace, debug_log="logs/stage1-run-1.jsonl"
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "artifact_invalid")

    def test_voice_plan_fails_closed_on_invalid_group_shape(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)
            topic_spec = _topic_spec()
            topic_spec["voice_groups"] = ["bad", "shape"]

            result = run_stage1_chatgpt_job(
                topic_spec, workspace, debug_log="logs/stage1-run-1.jsonl"
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "artifact_invalid")


if __name__ == "__main__":
    _ = unittest.main()

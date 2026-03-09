from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.stage1.chatgpt_runner import (
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


class RuntimeV2Stage1ChatgptTests(unittest.TestCase):
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
            next_jobs = cast(list[object], result["next_jobs"])
            self.assertTrue(next_jobs)

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

    def test_stage1_result_contains_downstream_seed_data(self) -> None:
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

        self.assertEqual(result["status"], "ok")
        self.assertTrue(next_jobs)
        first_entry = cast(dict[str, object], next_jobs[0])
        first_job = cast(dict[str, object], first_entry["job"])
        first_payload = cast(dict[str, object], first_job["payload"])
        self.assertEqual(stage1_result["status"], "ok")
        self.assertEqual(stage1_result["row_ref"], "Sheet1!row1")
        self.assertEqual(first_payload["run_id"], "stage1-run-1")
        self.assertEqual(first_payload["row_ref"], "Sheet1!row1")
        self.assertIn("stage1_handoff", first_payload)

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
            self.assertEqual(parsed_payload["version"], "stage1.v1")
            self.assertEqual(parsed_payload["title"], "Money flow")
            self.assertTrue(Path(cast(str, handoff["raw_output_path"])).exists())
            self.assertTrue(Path(cast(str, handoff["parsed_payload_path"])).exists())

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

    def test_stage1_route_failure_becomes_structured_failed_result(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            workspace = Path(tmp_dir)

            with patch(
                "runtime_v2.stage1.chatgpt_runner.route_video_plan",
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

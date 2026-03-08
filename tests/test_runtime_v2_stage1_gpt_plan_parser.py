from __future__ import annotations

import unittest

from runtime_v2.stage1.gpt_plan_parser import (
    build_topic_spec_from_gpt_response,
    extract_stage1_gpt_plan_json,
    map_stage1_plan_to_topic_spec,
    parse_stage1_gpt_plan,
)


def _base_topic_spec() -> dict[str, object]:
    return {
        "contract": "topic_spec",
        "contract_version": "1.0",
        "run_id": "gpt-parse-run-1",
        "row_ref": "Sheet1!row1",
        "topic": "Bridge topic",
        "status_snapshot": "",
        "excel_snapshot_hash": "hash-1",
    }


class RuntimeV2Stage1GptPlanParserTests(unittest.TestCase):
    def test_extract_stage1_gpt_plan_json_prefers_json_fence(self) -> None:
        response_text = """Intro text

```json
{
  "story_outline": ["opening", "closing"],
  "scene_prompts": ["scene one", "scene two"],
  "voice_groups": [
    {"scene_index": 1, "voice": "narration"},
    {"scene_index": 2, "voice": "narration"}
  ]
}
```

Footer text
"""

        payload = extract_stage1_gpt_plan_json(response_text)

        self.assertEqual(payload["story_outline"], ["opening", "closing"])

    def test_parse_stage1_gpt_plan_rejects_missing_required_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_scene_prompts"):
            _ = parse_stage1_gpt_plan(
                {
                    "story_outline": ["opening"],
                    "voice_groups": [{"scene_index": 1, "voice": "narration"}],
                }
            )

    def test_parse_stage1_gpt_plan_rejects_invalid_voice_group_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_voice_groups"):
            _ = parse_stage1_gpt_plan(
                {
                    "story_outline": ["opening"],
                    "scene_prompts": ["scene one"],
                    "voice_groups": [{"scene_index": "1", "voice": "narration"}],
                }
            )

    def test_map_stage1_plan_to_topic_spec_adds_strict_stage1_fields(self) -> None:
        parsed_plan = parse_stage1_gpt_plan(
            {
                "story_outline": ["opening", "closing"],
                "scene_prompts": ["scene one", "scene two"],
                "voice_groups": [
                    {"scene_index": 1, "voice": "narration"},
                    {"scene_index": 2, "voice": "narration"},
                ],
            }
        )

        mapped = map_stage1_plan_to_topic_spec(_base_topic_spec(), parsed_plan)

        self.assertEqual(mapped["story_outline"], ["opening", "closing"])
        self.assertEqual(mapped["scene_prompts"], ["scene one", "scene two"])
        self.assertEqual(
            mapped["voice_groups"],
            [
                {"scene_index": 1, "voice": "narration"},
                {"scene_index": 2, "voice": "narration"},
            ],
        )

    def test_build_topic_spec_from_gpt_response_runs_extract_parse_and_map(
        self,
    ) -> None:
        response_text = """prefix
```json
{
  "story_outline": ["opening", "closing"],
  "scene_prompts": ["scene one", "scene two"],
  "voice_groups": [
    {"scene_index": 1, "voice": "narration"},
    {"scene_index": 2, "voice": "narration"}
  ]
}
```
suffix
"""

        topic_spec = build_topic_spec_from_gpt_response(
            _base_topic_spec(), response_text
        )

        self.assertEqual(topic_spec["topic"], "Bridge topic")
        self.assertEqual(topic_spec["scene_prompts"], ["scene one", "scene two"])
        self.assertEqual(topic_spec["story_outline"], ["opening", "closing"])

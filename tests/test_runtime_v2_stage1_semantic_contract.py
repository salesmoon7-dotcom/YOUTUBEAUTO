from __future__ import annotations

import unittest

from runtime_v2.stage1.parsed_payload import validate_stage1_parsed_payload


class RuntimeV2Stage1SemanticContractTests(unittest.TestCase):
    def test_rejects_unmapped_video_prompts_when_scene_contract_is_smaller(self) -> None:
        payload: dict[str, object] = {
            "version": "stage1.v1",
            "run_id": "semantic-run-1",
            "row_ref": "Sheet1!row15",
            "topic": "care facility costs",
            "title": "care facility costs",
            "title_for_thumb": "care facility costs",
            "description": "summary",
            "keywords": ["care", "facility"],
            "bgm": "steady corporate",
            "scene_prompts": ["scene one", "scene two", "scene three"],
            "voice_groups": [
                {"scene_index": 1, "voice": "voice one"},
                {"scene_index": 2, "voice": "voice two"},
                {"scene_index": 3, "voice": "voice three"},
            ],
            "videos": [f"video prompt {index}" for index in range(1, 19)],
            "reason_code": "ok",
        }

        errors = validate_stage1_parsed_payload(payload)

        self.assertIn("video_scene_link_missing", errors)

    def test_rejects_duplicate_voice_scene_indexes(self) -> None:
        payload: dict[str, object] = {
            "version": "stage1.v1",
            "run_id": "semantic-run-2",
            "row_ref": "Sheet1!row16",
            "topic": "care facility costs",
            "title": "care facility costs",
            "title_for_thumb": "care facility costs",
            "description": "summary",
            "keywords": ["care", "facility"],
            "bgm": "steady corporate",
            "scene_prompts": ["scene one", "scene two", "scene three"],
            "voice_groups": [
                {"scene_index": 1, "voice": "voice one"},
                {"scene_index": 2, "voice": "voice two"},
                {"scene_index": 3, "voice": "voice three"},
                {"scene_index": 3, "voice": "duplicate voice three"},
            ],
            "videos": ["video one", "video two", "video three"],
            "reason_code": "ok",
        }

        errors = validate_stage1_parsed_payload(payload)

        self.assertIn("invalid_voice_groups", errors)


if __name__ == "__main__":
    unittest.main()

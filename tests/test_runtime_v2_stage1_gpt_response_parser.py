from __future__ import annotations

import unittest
from typing import cast

from runtime_v2.stage1.gpt_response_parser import parse_gpt_response_text


class RuntimeV2Stage1GptResponseParserTests(unittest.TestCase):
    def test_parser_accepts_json_fenced_response(self) -> None:
        topic_spec: dict[str, object] = {
            "topic": "Money flow",
            "row_ref": "Sheet1!row1",
            "run_id": "run-1",
        }
        response_text = """```json
        {
          "story_outline": ["intro", "ending"],
          "scene_prompts": ["scene one", "scene two"],
          "voice_groups": [
            {"scene_index": 1, "voice": "narration"},
            {"scene_index": 2, "voice": "narration"}
          ]
        }
        ```"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertIn("scene one", cast(list[object], typed["scene_prompts"]))

    def test_parser_accepts_legacy_block_response(self) -> None:
        topic_spec: dict[str, object] = {
            "topic": "Money flow",
            "row_ref": "Sheet1!row1",
            "run_id": "run-1",
        }
        response_text = """
Title
머니 제목
Title for Thumb
머니 썸네일 제목
Description
머니 설명
Keywords
머니, 연금, 생활비
Voice
차분한 여성 내레이션
BGM
serious piano
#01
십세부터 오십세까지 설명
#02
육십세부터 구십세까지 설명
"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertEqual(typed["title"], "머니 제목")
        self.assertEqual(typed["title_for_thumb"], "머니 썸네일 제목")
        self.assertEqual(typed["bgm"], "serious piano")
        self.assertEqual(len(cast(list[object], typed["scene_prompts"])), 2)

    def test_parser_accepts_inline_label_value_response(self) -> None:
        topic_spec: dict[str, object] = {
            "topic": "Money flow",
            "row_ref": "Sheet1!row1",
            "run_id": "run-1",
        }
        response_text = """
Title: 머니 제목
Title for Thumb: 머니 썸네일 제목
Description: 머니 설명
Keywords: 머니, 연금, 생활비
Voice: 차분한 여성 내레이션
BGM: serious piano
#01: 십세부터 오십세까지 설명
#02: 육십세부터 구십세까지 설명
"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertEqual(typed["title"], "머니 제목")
        self.assertEqual(typed["title_for_thumb"], "머니 썸네일 제목")
        self.assertEqual(typed["description"], "머니 설명")
        self.assertEqual(typed["keywords"], ["머니", "연금", "생활비"])
        self.assertEqual(typed["bgm"], "serious piano")
        self.assertEqual(
            typed["scene_prompts"],
            ["십세부터 오십세까지 설명", "육십세부터 구십세까지 설명"],
        )


if __name__ == "__main__":
    _ = unittest.main()

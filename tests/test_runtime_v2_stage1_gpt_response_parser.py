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

    def test_parser_extracts_shorts_blocks_from_legacy_response(self) -> None:
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
BGM: serious piano
#01: 십세부터 오십세까지 설명
#02: 육십세부터 구십세까지 설명
Shorts Description: 쇼츠 설명 요약
Shorts Voice: 쇼츠 내레이션 문장
Shorts Clip Mapping: #01 -> Shorts 1\n#02 -> Shorts 2
"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertEqual(typed["shorts_description"], "쇼츠 설명 요약")
        self.assertEqual(typed["shorts_voice"], "쇼츠 내레이션 문장")
        self.assertIn("#01 -> Shorts 1", str(typed["shorts_clip_mapping"]))

    def test_parser_extracts_bracketed_legacy_blocks(self) -> None:
        topic_spec: dict[str, object] = {
            "topic": "Money flow",
            "row_ref": "Sheet1!row1",
            "run_id": "run-1",
        }
        response_text = """
[Title]
머니 제목

[Title for Thumb]
Line 1: 썸네일 제목

[Ref Img 1]
images/ref1.png

[Voice]
1. 첫 장면 설명입니다.
2. 두 번째 장면 설명입니다.

[Shorts Description]
쇼츠 설명입니다.
"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertEqual(typed["title"], "머니 제목")
        self.assertEqual(typed["ref_img_1"], "images/ref1.png")
        self.assertEqual(
            typed["scene_prompts"], ["첫 장면 설명입니다.", "두 번째 장면 설명입니다."]
        )
        self.assertEqual(typed["shorts_description"], "쇼츠 설명입니다.")


if __name__ == "__main__":
    _ = unittest.main()

from __future__ import annotations

import unittest
from typing import cast
from unittest.mock import patch

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

[URL]
https://chatgpt.com/g/g-696a6d74fbd48191a1ffdc5f8ea90a1b-rongpom/c/69aabf29-fa9c-83a3-bdea-bc5fe34b920

[Voice]
1. 첫 장면 설명입니다.
2. 두 번째 장면 설명입니다.

[Video1]
첫 번째 비디오 프롬프트

[Shorts Description]
쇼츠 설명입니다.
"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertEqual(typed["title"], "머니 제목")
        self.assertIn("rongpom", str(typed["url"]))
        self.assertEqual(typed["ref_img_1"], "images/ref1.png")
        self.assertEqual(
            typed["voice_lines"], ["첫 장면 설명입니다.", "두 번째 장면 설명입니다."]
        )
        self.assertEqual(
            typed["voice_groups"],
            [
                {
                    "scene_index": 1,
                    "voice": "첫 장면 설명입니다.",
                    "original_voices": [1],
                },
                {
                    "scene_index": 2,
                    "voice": "두 번째 장면 설명입니다.",
                    "original_voices": [2],
                },
            ],
        )
        self.assertEqual(
            typed["scene_prompts"], ["첫 장면 설명입니다.", "두 번째 장면 설명입니다."]
        )
        self.assertEqual(typed["videos"], ["첫 번째 비디오 프롬프트"])
        self.assertEqual(typed["shorts_description"], "쇼츠 설명입니다.")

    def test_parser_reports_structured_parse_failure_when_block_fallback_is_used(
        self,
    ) -> None:
        topic_spec: dict[str, object] = {
            "topic": "Money flow",
            "row_ref": "Sheet1!row1",
            "run_id": "run-1",
        }
        response_text = """
Title: 머니 제목
Voice: 1. 첫 장면 설명\n2. 두 번째 장면 설명
#01: 첫 장면 설명
#02: 두 번째 장면 설명
"""

        with patch(
            "runtime_v2.stage1.gpt_response_parser.build_topic_spec_from_gpt_response",
            side_effect=ValueError("structured_parse_failed"),
        ):
            parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertIsNotNone(parsed)
        self.assertEqual(errors, ["structured_parse_failed"])

    def test_parser_accepts_hash_blocks_with_suffix_text(self) -> None:
        topic_spec: dict[str, object] = {
            "topic": "Money flow",
            "row_ref": "Sheet1!row1",
            "run_id": "run-1",
        }
        response_text = """
[Title]
머니 제목

[Voice]
1. 보이스 하나
2. 보이스 둘

[#01 intro Character] - Voice 1(1) *BGM35
장면 프롬프트 one

[#02 background] - Voice 2(2)
장면 프롬프트 two
"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertEqual(
            typed["scene_prompts"], ["장면 프롬프트 one", "장면 프롬프트 two"]
        )
        self.assertEqual(
            typed["voice_groups"],
            [
                {"scene_index": 1, "voice": "보이스 하나", "original_voices": [1]},
                {"scene_index": 2, "voice": "보이스 둘", "original_voices": [2]},
            ],
        )

    def test_parser_maps_voice_range_suffixes_to_scene_groups(self) -> None:
        topic_spec: dict[str, object] = {
            "topic": "Money flow",
            "row_ref": "Sheet1!row1",
            "run_id": "run-1",
        }
        response_text = """
[Voice]
1. 보이스 하나
2. 보이스 둘
3. 보이스 셋

[#01 intro Character] - Voice 1-2(2)
장면 프롬프트 one

[#02 body Slides] - Voice 3(1)
장면 프롬프트 two
"""

        parsed, errors = parse_gpt_response_text(topic_spec, response_text)

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        typed = cast(dict[str, object], parsed)
        self.assertEqual(
            typed["voice_groups"],
            [
                {
                    "scene_index": 1,
                    "voice": "보이스 하나\n보이스 둘",
                    "original_voices": [1, 2],
                },
                {"scene_index": 2, "voice": "보이스 셋", "original_voices": [3]},
            ],
        )


if __name__ == "__main__":
    _ = unittest.main()

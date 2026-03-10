from __future__ import annotations

import unittest
from typing import cast

from runtime_v2.excel.stage1_handoff_bridge import (
    export_stage1_handoff_to_excel_row,
    import_stage1_handoff_from_excel_row,
)


def _handoff() -> dict[str, object]:
    return {
        "version": "stage1_handoff.v1.0",
        "run_id": "run-1",
        "row_ref": "Sheet1!row1",
        "topic": "Bridge topic",
        "title": "Bridge title",
        "title_for_thumb": "Bridge thumb",
        "description": "Bridge description",
        "keywords": ["bridge", "topic"],
        "bgm": "calm piano",
        "scene_prompts": ["scene one", "scene two"],
        "voice_groups": [
            {"scene_index": 1, "voice": "narration"},
            {"scene_index": 2, "voice": "narration"},
        ],
        "voice_texts": [
            {"col": "#01", "text": "voice one", "original_voices": [1]},
            {"col": "#02", "text": "voice two", "original_voices": [2]},
        ],
        "voice_lines": ["voice one", "voice two"],
        "url": "https://chatgpt.com/g/g-696a6d74fbd48191a1ffdc5f8ea90a1b-rongpom/c/69aabf29-fa9c-83a3-bdea-bc5fe34b920",
        "ref_img_1": "images/ref1.png",
        "ref_img_2": "images/ref2.png",
        "videos": ["video prompt 1", "video prompt 2"],
        "shorts_description": "shorts desc",
        "shorts_voice": "shorts voice",
        "shorts_clip_mapping": "1 | #01",
        "reason_code": "ok",
    }


class RuntimeV2Stage1HandoffBridgeTests(unittest.TestCase):
    def test_export_stage1_handoff_to_excel_row_includes_downstream_fields(
        self,
    ) -> None:
        row = export_stage1_handoff_to_excel_row(_handoff())

        self.assertEqual(row["Title"], "Bridge title")
        self.assertEqual(row["Title for Thumb"], "Bridge thumb")
        self.assertEqual(row["BGM"], "calm piano")
        self.assertIn("rongpom", row["URL"])
        self.assertEqual(row["Ref Img 1"], "images/ref1.png")
        self.assertEqual(row["Video1"], "video prompt 1")
        self.assertEqual(row["Video2"], "video prompt 2")
        self.assertEqual(row["Shorts Description"], "shorts desc")
        self.assertEqual(row["Shorts Voice"], "shorts voice")
        self.assertEqual(row["Shorts Clip Mapping"], "1 | #01")
        self.assertEqual(row["Shorts\nStatus"], "n")
        self.assertIn("voice one", row["Voice"])
        self.assertEqual(row["#01"], "scene one")
        self.assertIn("voice_texts.json", row)

    def test_stage1_handoff_roundtrip_preserves_contract_fields(self) -> None:
        payload = _handoff()
        exported = export_stage1_handoff_to_excel_row(payload)
        row: dict[str, object] = {key: value for key, value in exported.items()}
        restored = import_stage1_handoff_from_excel_row(base_payload=payload, row=row)

        self.assertEqual(restored["title"], payload["title"])
        self.assertEqual(restored["title_for_thumb"], payload["title_for_thumb"])
        self.assertEqual(restored["bgm"], payload["bgm"])
        self.assertEqual(restored["url"], payload["url"])
        self.assertEqual(restored["ref_img_1"], payload["ref_img_1"])
        self.assertEqual(restored["scene_prompts"], payload["scene_prompts"])
        self.assertEqual(restored["videos"], payload["videos"])
        self.assertEqual(restored["shorts_description"], payload["shorts_description"])
        self.assertEqual(restored["shorts_voice"], payload["shorts_voice"])
        self.assertEqual(
            restored["shorts_clip_mapping"], payload["shorts_clip_mapping"]
        )
        self.assertEqual(restored["voice_lines"], payload["voice_lines"])
        restored_voice_texts = cast(list[dict[str, object]], restored["voice_texts"])
        payload_voice_texts = cast(list[dict[str, object]], payload["voice_texts"])
        self.assertEqual(
            [item["text"] for item in restored_voice_texts],
            [item["text"] for item in payload_voice_texts],
        )

    def test_handoff_normalization_adds_shorts_fields(self) -> None:
        payload = _handoff()
        exported = export_stage1_handoff_to_excel_row(payload)
        row: dict[str, object] = {key: value for key, value in exported.items()}
        restored = import_stage1_handoff_from_excel_row(base_payload=payload, row=row)

        self.assertIn("shorts_description", restored)
        self.assertIn("shorts_voice", restored)
        self.assertIn("shorts_clip_mapping", restored)

    def test_export_uses_voice_lines_and_falls_back_to_n_when_empty(self) -> None:
        payload = _handoff()
        payload["voice_groups"] = [
            {"scene_index": index, "voice": "narration" * 200}
            for index in range(1, 200)
        ]

        exported = export_stage1_handoff_to_excel_row(payload)

        self.assertIn("voice one", exported["Voice"])
        self.assertIn("voice_texts.json", exported)

        payload["voice_texts"] = []
        payload["voice_lines"] = []
        exported = export_stage1_handoff_to_excel_row(payload)
        self.assertEqual(exported["Voice"], "n")


if __name__ == "__main__":
    _ = unittest.main()

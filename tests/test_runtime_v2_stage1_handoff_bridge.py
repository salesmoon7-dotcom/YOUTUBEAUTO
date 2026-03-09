from __future__ import annotations

import unittest

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
            {"col": "#01", "text": "scene one", "original_voices": [1]},
            {"col": "#02", "text": "scene two", "original_voices": [2]},
        ],
        "ref_img_1": "images/ref1.png",
        "ref_img_2": "images/ref2.png",
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
        self.assertEqual(row["Ref Img 1"], "images/ref1.png")
        self.assertEqual(row["#01"], "scene one")
        self.assertIn("voice_texts.json", row)

    def test_stage1_handoff_roundtrip_preserves_contract_fields(self) -> None:
        payload = _handoff()
        row = export_stage1_handoff_to_excel_row(payload)
        restored = import_stage1_handoff_from_excel_row(base_payload=payload, row=row)

        self.assertEqual(restored["title"], payload["title"])
        self.assertEqual(restored["title_for_thumb"], payload["title_for_thumb"])
        self.assertEqual(restored["bgm"], payload["bgm"])
        self.assertEqual(restored["ref_img_1"], payload["ref_img_1"])
        self.assertEqual(restored["scene_prompts"], payload["scene_prompts"])


if __name__ == "__main__":
    _ = unittest.main()

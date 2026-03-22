from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

from runtime_v2.stage2.json_builders import _build_thumb_data
from runtime_v2.stage2.json_builders import _build_ref_jobs


class RuntimeV2Stage2JsonBuildersTests(unittest.TestCase):
    def test_build_thumb_data_parses_structured_title_for_thumb(self) -> None:
        thumb_data = _build_thumb_data(
            prompt="scene prompt placeholder",
            stage1_contract={
                "title_for_thumb": "Background gradient prompt\nLine 1: Care cost\nLine 2: How much?"
            },
        )

        self.assertEqual(thumb_data["bg_prompt"], "Background gradient prompt")
        self.assertEqual(thumb_data["line1"], "Care cost")
        self.assertEqual(thumb_data["line2"], "How much?")

    def test_build_ref_jobs_strips_attached_image_prefixes_from_ref_prompts(
        self,
    ) -> None:
        ref_jobs, ref_img_1_path, ref_img_2_path = _build_ref_jobs(
            run_id="run-1",
            row_ref="Sheet1!row15",
            asset_root=Path(r"D:\YOUTUBEAUTO\tmp_ref_jobs"),
            stage1_handoff=None,
            stage1_contract={
                "ref_img_1": "Refer to attached character image.\nWarm gray sweater portrait",
                "ref_img_2": "Use attached images as reference.\nBright office background",
            },
            reason_code="ok",
            agent_browser_services={"genspark", "seaart"},
        )

        self.assertEqual(len(ref_jobs), 2)
        ref1_payload = cast(
            dict[str, object], cast(dict[str, object], ref_jobs[0]["job"])["payload"]
        )
        ref2_payload = cast(
            dict[str, object], cast(dict[str, object], ref_jobs[1]["job"])["payload"]
        )
        self.assertEqual(ref1_payload["prompt"], "Warm gray sweater portrait")
        self.assertEqual(ref2_payload["prompt"], "Bright office background")
        self.assertTrue(ref_img_1_path.endswith("ref-1-run-1.png"))
        self.assertTrue(ref_img_2_path.endswith("ref-2-run-1.png"))


if __name__ == "__main__":
    unittest.main()

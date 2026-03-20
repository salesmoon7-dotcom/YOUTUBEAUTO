from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2 import exit_codes
from runtime_v2.cli import main


class RuntimeV2CliBoundaryEmitTests(unittest.TestCase):
    def test_emit_boundary_contract_path_builds_qwen_job_from_stage1_handoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            handoff_path = (
                root
                / "runtime"
                / "artifacts"
                / "chatgpt"
                / "chatgpt-boundary"
                / "stage1_handoff.json"
            )
            handoff_path.parent.mkdir(parents=True, exist_ok=True)
            handoff_path.write_text(
                json.dumps(
                    {
                        "contract": {
                            "run_id": "boundary-run-1",
                            "row_ref": "Sheet1!row1",
                            "topic": "Boundary topic",
                            "voice_texts": [
                                {
                                    "col": "#01",
                                    "text": "line one",
                                    "original_voices": [1],
                                }
                            ],
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            output_path = root / "qwen-boundary.job.json"

            with patch(
                "sys.argv",
                [
                    "runtime_v2.cli",
                    "--emit-boundary-contract-path",
                    str(output_path),
                    "--boundary-workload",
                    "qwen3_tts",
                    "--stage1-handoff-path",
                    str(handoff_path),
                ],
            ):
                exit_code = main()

            contract = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        inner_job = contract["job"]
        self.assertEqual(inner_job["worker"], "qwen3_tts")
        self.assertEqual(inner_job["payload"]["voice_texts"][0]["text"], "line one")

    def test_emit_boundary_contract_path_builds_stage2_ref_job(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            asset_root = root / "assets"
            (asset_root / "images").mkdir(parents=True, exist_ok=True)
            video_plan_path = root / "video_plan.json"
            video_plan_path.write_text(
                json.dumps(
                    {
                        "run_id": "boundary-run-2",
                        "row_ref": "Sheet1!row2",
                        "reason_code": "ok",
                        "asset_plan": {
                            "asset_root": str(asset_root.resolve()),
                            "common_asset_folder": str(asset_root.resolve()),
                        },
                        "scene_plan": [
                            {"scene_index": 1, "prompt": "scene one"},
                        ],
                        "stage1_handoff": {
                            "contract": {
                                "run_id": "boundary-run-2",
                                "row_ref": "Sheet1!row2",
                                "topic": "Boundary topic",
                                "voice_texts": [],
                                "ref_img_1": "Use attached images as reference.\nPortrait prompt",
                                "ref_img_2": "",
                            }
                        },
                        "use_agent_browser_services": ["genspark", "seaart"],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            output_path = root / "genspark-ref.job.json"

            with patch(
                "sys.argv",
                [
                    "runtime_v2.cli",
                    "--emit-boundary-contract-path",
                    str(output_path),
                    "--boundary-workload",
                    "genspark",
                    "--video-plan-path",
                    str(video_plan_path),
                    "--boundary-ref-id",
                    "ref-1",
                ],
            ):
                exit_code = main()

            contract = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        inner_job = contract["job"]
        self.assertEqual(inner_job["job_id"], "genspark-boundary-run-2-ref-1")
        self.assertEqual(inner_job["worker"], "genspark")
        self.assertEqual(inner_job["payload"]["prompt"], "Portrait prompt")

    def test_emit_boundary_contract_path_builds_geminigen_agent_browser_job(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            asset_root = root / "assets"
            (asset_root / "images").mkdir(parents=True, exist_ok=True)
            video_plan_path = root / "video_plan.json"
            video_plan_path.write_text(
                json.dumps(
                    {
                        "run_id": "boundary-run-3",
                        "row_ref": "Sheet1!row3",
                        "reason_code": "ok",
                        "asset_plan": {
                            "asset_root": str(asset_root.resolve()),
                            "common_asset_folder": str(asset_root.resolve()),
                        },
                        "scene_plan": [],
                        "videos": ["video one prompt"],
                        "stage1_handoff": {
                            "contract": {
                                "run_id": "boundary-run-3",
                                "row_ref": "Sheet1!row3",
                                "topic": "Boundary topic",
                                "voice_texts": [],
                                "ref_img_1": str(
                                    (asset_root / "images" / "ref1.png").resolve()
                                ),
                                "ref_img_2": "",
                            }
                        },
                        "use_agent_browser_services": ["geminigen"],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            output_path = root / "geminigen.job.json"

            with patch(
                "sys.argv",
                [
                    "runtime_v2.cli",
                    "--emit-boundary-contract-path",
                    str(output_path),
                    "--boundary-workload",
                    "geminigen",
                    "--video-plan-path",
                    str(video_plan_path),
                ],
            ):
                exit_code = main()

            contract = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        inner_job = contract["job"]
        self.assertEqual(inner_job["worker"], "geminigen")
        self.assertTrue(bool(inner_job["payload"]["use_agent_browser"]))


if __name__ == "__main__":
    _ = unittest.main()

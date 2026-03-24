from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast

from runtime_v2.boundary_jobs import build_qwen_boundary_contract
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import _declared_stage1_qwen_job


class RuntimeV2BoundaryJobsTests(unittest.TestCase):
    def test_build_qwen_boundary_contract_limits_voice_texts_to_single_item(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            handoff_path = artifact_root / "stage1" / "handoff.json"
            handoff_path.parent.mkdir(parents=True, exist_ok=True)
            handoff_payload = {
                "run_id": "run-123",
                "row_ref": "Sheet1!row15",
                "topic": "topic",
                "voice_texts": [
                    {"col": "#02", "text": "second", "original_voices": [2]},
                    {"col": "#01", "text": "first", "original_voices": [1]},
                    {"col": "#03", "text": "third", "original_voices": [3]},
                ],
            }
            _ = handoff_path.write_text(
                json.dumps(handoff_payload, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )

            contract = build_qwen_boundary_contract(stage1_handoff_path=handoff_path)

        job = cast(dict[str, object], contract["job"])
        payload = cast(dict[str, object], job["payload"])
        voice_texts = cast(list[object], payload["voice_texts"])
        self.assertEqual(str(job["job_id"]), "qwen3-boundary-run-123")
        self.assertEqual(len(voice_texts), 1)
        selected = cast(dict[str, object], voice_texts[0])
        self.assertEqual(selected["col"], "#01")
        self.assertIn(
            r"qwen3_tts\qwen3-boundary-run-123\speech.flac",
            str(payload["service_artifact_path"]),
        )

    def test_declared_stage1_qwen_job_keeps_full_voice_batch_for_semantic_row(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            parent_job = JobContract(
                job_id="chatgpt-row15",
                workload="chatgpt",
                payload={
                    "run_id": "run-123",
                    "row_ref": "Sheet1!row15",
                    "excel_path": str(root / "topic.xlsx"),
                    "sheet_name": "Sheet1",
                    "row_index": 14,
                    "model_name": "voice-model-a",
                },
            )
            voice_texts = [
                {"col": "#01", "text": "first", "original_voices": [1]},
                {"col": "#02", "text": "second", "original_voices": [2]},
            ]
            details = cast(
                dict[str, object],
                {
                    "stage1_handoff": {
                        "contract": {
                            "run_id": "run-123",
                            "row_ref": "Sheet1!row15",
                            "topic": "topic",
                            "voice_texts": voice_texts,
                        }
                    }
                },
            )

            contract = _declared_stage1_qwen_job(details, parent_job, artifact_root)

        self.assertIsNotNone(contract)
        typed_contract = cast(dict[str, object], contract)
        job = cast(dict[str, object], typed_contract["job"])
        payload = cast(dict[str, object], job["payload"])
        typed_voice_texts = cast(list[object], payload["voice_texts"])
        self.assertEqual(str(job["job_id"]), "qwen3-run-123")
        self.assertEqual(len(typed_voice_texts), 2)

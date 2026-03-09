from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.result_router import write_result_router
from runtime_v2.stage2.json_builders import build_stage2_jobs
from runtime_v2.supervisor import run_once


def _video_plan(asset_root: str) -> dict[str, object]:
    return {
        "contract": "video_plan",
        "contract_version": "1.0",
        "run_id": "stage2-run-1",
        "row_ref": "Sheet1!row1",
        "topic": "Bridge topic",
        "scene_plan": [
            {"scene_index": 1, "prompt": "scene one"},
            {"scene_index": 2, "prompt": "scene two"},
        ],
        "asset_plan": {"asset_root": asset_root, "common_asset_folder": asset_root},
        "voice_plan": {"mapping_source": "excel_scene", "scene_count": 2, "groups": []},
        "reason_code": "ok",
        "evidence": {"source": "test"},
    }


class RuntimeV2Stage2ContractTests(unittest.TestCase):
    def test_video_plan_is_split_into_genspark_and_seaart_jobs(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            jobs, _ = build_stage2_jobs(_video_plan(tmp_dir))

        workloads = [
            cast(dict[str, object], cast(dict[str, object], job["job"]))["worker"]
            for job in jobs
        ]
        self.assertEqual(workloads[:2], ["genspark", "seaart"])

    def test_render_spec_and_stage2_contracts_include_row_binding_and_reason_code(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            jobs, render_spec = build_stage2_jobs(_video_plan(tmp_dir))

        first_job = cast(dict[str, object], jobs[0]["job"])
        first_payload = cast(dict[str, object], first_job["payload"])
        render_job = cast(dict[str, object], jobs[-1]["job"])
        render_payload = cast(dict[str, object], render_job["payload"])
        self.assertEqual(first_payload["row_ref"], "Sheet1!row1")
        self.assertEqual(first_payload["reason_code"], "ok")
        self.assertEqual(render_spec["row_ref"], "Sheet1!row1")
        self.assertEqual(render_spec["reason_code"], "ok")
        self.assertEqual(render_job["worker"], "render")
        self.assertEqual(render_payload["run_id"], "stage2-run-1")
        self.assertTrue(str(render_payload["render_folder_path"]).endswith(tmp_dir))
        self.assertTrue(str(render_payload["voice_json_path"]).endswith("voice.json"))

    def test_browser_stage2_workloads_bypass_gpu_lease_and_use_browser_gate_only(
        self,
    ) -> None:
        browser_runtime = {"sessions": [{"service": "genspark", "healthy": True}]}
        with patch("runtime_v2.supervisor.BrowserManager.start"):
            with patch(
                "runtime_v2.supervisor.BrowserSupervisor.tick",
                return_value=browser_runtime,
            ):
                with patch(
                    "runtime_v2.supervisor.lease_store_for_workload"
                ) as lease_store_for_workload:
                    result = run_once(
                        owner="runtime_v2",
                        run_id="stage2-run-1",
                        workload="genspark",
                        worker_runner=lambda: {"status": "ok", "stage": "genspark"},
                    )

        self.assertEqual(result["status"], "ok")
        lease_store_for_workload.assert_not_called()

    def test_latest_run_snapshot_records_absolute_path_hash_and_debug_log(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            artifact_root.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_root / "sample.json"
            artifact_path.write_text('{"ok": true}', encoding="utf-8")
            output_file = root / "result.json"

            write_result_router(
                [artifact_path],
                artifact_root,
                output_file,
                metadata={"debug_log": str((root / "logs" / "run.jsonl").resolve())},
            )

            payload = json.loads(output_file.read_text(encoding="utf-8"))

        artifact = payload["artifacts"][0]
        self.assertTrue(Path(artifact["path"]).is_absolute())
        self.assertTrue(str(artifact["sha256"]).strip())
        self.assertTrue(str(payload["metadata"]["debug_log"]).endswith("run.jsonl"))

    def test_stage2_contract_builders_fail_closed_when_common_asset_folder_missing(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "missing_common_asset_root"):
            _ = build_stage2_jobs(_video_plan("D:/YOUTUBEAUTO/does-not-exist-stage2"))

    def test_stage2_contract_builders_preserve_all_scenes_without_zip_truncation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            video_plan = _video_plan(tmp_dir)
            video_plan["scene_plan"] = [
                {"scene_index": 1, "prompt": "scene one"},
                {"scene_index": 2, "prompt": "scene two"},
                {"scene_index": 3, "prompt": "scene three"},
                {"scene_index": 4, "prompt": "scene four"},
                {"scene_index": 5, "prompt": "scene five"},
            ]

            jobs, _ = build_stage2_jobs(video_plan)

        self.assertEqual(len(jobs), 6)
        last_job = cast(dict[str, object], jobs[-2]["job"])
        self.assertEqual(last_job["worker"], "genspark")
        self.assertEqual(cast(dict[str, object], jobs[-1]["job"])["worker"], "render")

    def test_stage2_jobs_can_opt_in_agent_browser_services_from_video_plan(
        self,
    ) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["scene_plan"] = [
            {"scene_index": 1, "prompt": "scene one"},
            {"scene_index": 2, "prompt": "scene two"},
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ]
        video_plan["use_agent_browser_services"] = ["genspark", "canva"]

        jobs, _ = build_stage2_jobs(video_plan)
        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        genspark_job = next(
            job for job in typed_jobs if str(job["worker"]) == "genspark"
        )
        canva_job = next(job for job in typed_jobs if str(job["worker"]) == "canva")
        seaart_job = next(job for job in typed_jobs if str(job["worker"]) == "seaart")

        self.assertTrue(
            bool(cast(dict[str, object], genspark_job["payload"])["use_agent_browser"])
        )
        self.assertTrue(
            bool(cast(dict[str, object], canva_job["payload"])["use_agent_browser"])
        )
        self.assertNotIn(
            "use_agent_browser", cast(dict[str, object], seaart_job["payload"])
        )

    def test_stage2_jobs_include_stage1_handoff_when_present(self) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["stage1_handoff"] = {
            "contract": {"version": "stage1.v1", "title": "Money title"}
        }

        jobs, _ = build_stage2_jobs(video_plan)
        first_payload = cast(
            dict[str, object], cast(dict[str, object], jobs[0]["job"])["payload"]
        )
        render_payload = cast(
            dict[str, object], cast(dict[str, object], jobs[-1]["job"])["payload"]
        )

        self.assertIn("stage1_handoff", first_payload)
        self.assertIn("stage1_handoff", render_payload)

    def test_canva_stage2_payload_prefers_stage1_ref_image_when_present(self) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["scene_plan"] = [
            {"scene_index": 1, "prompt": "scene one"},
            {"scene_index": 2, "prompt": "scene two"},
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ]
        video_plan["stage1_handoff"] = {
            "contract": {
                "version": "stage1_handoff.v1.0",
                "title": "Money title",
                "title_for_thumb": "Thumb line 1\nThumb line 2",
                "ref_img_1": "images/ref1.png",
            }
        }

        jobs, _ = build_stage2_jobs(video_plan)
        canva_job = next(
            cast(dict[str, object], item["job"])
            for item in jobs
            if cast(dict[str, object], item["job"])["worker"] == "canva"
        )
        payload = cast(dict[str, object], canva_job["payload"])
        thumb_data = cast(dict[str, object], payload["thumb_data"])

        self.assertEqual(str(payload["ref_img"]), "images/ref1.png")
        self.assertEqual(str(thumb_data["line1"]), "Thumb line 1")
        self.assertEqual(str(thumb_data["line2"]), "Thumb line 2")

    def test_canva_payload_includes_thumb_data_and_deterministic_ref_img(self) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["scene_plan"] = [
            {"scene_index": 1, "prompt": "scene one"},
            {"scene_index": 2, "prompt": "scene two"},
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ]
        video_plan["stage1_handoff"] = {
            "contract": {
                "version": "stage1.v1",
                "title_for_thumb": "Legacy thumb title",
            }
        }

        jobs, _ = build_stage2_jobs(video_plan)
        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        canva_job = next(job for job in typed_jobs if str(job["worker"]) == "canva")
        canva_payload = cast(dict[str, object], canva_job["payload"])

        self.assertEqual(
            canva_payload["thumb_data"],
            {
                "bg_prompt": "scene four",
                "line1": "Legacy thumb title",
                "line2": "",
            },
        )
        self.assertEqual(
            str(canva_payload["ref_img"]).replace("\\", "/"),
            "D:/YOUTUBEAUTO/images/genspark-stage2-run-1-1.png",
        )


if __name__ == "__main__":
    _ = unittest.main()

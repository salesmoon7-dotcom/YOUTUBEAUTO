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
        first_timeline = cast(
            dict[str, object], cast(list[object], render_spec["timeline"])[0]
        )
        self.assertEqual(str(render_spec["contract_version"]), "1.1")
        self.assertEqual(cast(list[object], render_spec["audio_refs"]), [])
        self.assertEqual(str(first_timeline["asset_kind"]), "image")
        self.assertEqual(int(cast(int, first_timeline["duration_sec"])), 8)
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

    def test_stage2_jobs_assign_kenburns_manifest_ssot_under_asset_root(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            video_plan = _video_plan(tmp_dir)
            jobs, _ = build_stage2_jobs(video_plan)

        kenburns_job = next(
            cast(dict[str, object], item["job"])
            for item in jobs
            if cast(dict[str, object], item["job"])["worker"] == "kenburns"
        )
        kenburns_payload = cast(dict[str, object], kenburns_job["payload"])
        self.assertTrue(
            str(kenburns_payload["service_artifact_path"]).endswith(
                "video\\kenburns-stage2-run-1.json"
            )
        )
        self.assertTrue(
            Path(str(kenburns_payload["service_artifact_path"])).is_absolute()
        )

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

    def test_stage2_jobs_default_real_row_browser_services_to_agent_browser(
        self,
    ) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["scene_plan"] = [
            {"scene_index": 1, "prompt": "scene one"},
            {"scene_index": 2, "prompt": "scene two"},
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ]
        video_plan["stage1_handoff"] = {
            "contract": {"version": "stage1_handoff.v1.0", "title": "Money title"}
        }

        jobs, _ = build_stage2_jobs(video_plan)
        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        genspark_job = next(
            job for job in typed_jobs if str(job["worker"]) == "genspark"
        )
        seaart_job = next(job for job in typed_jobs if str(job["worker"]) == "seaart")
        canva_job = next(job for job in typed_jobs if str(job["worker"]) == "canva")

        self.assertTrue(
            bool(cast(dict[str, object], genspark_job["payload"])["use_agent_browser"])
        )
        self.assertTrue(
            bool(cast(dict[str, object], seaart_job["payload"])["use_agent_browser"])
        )
        self.assertTrue(
            bool(cast(dict[str, object], canva_job["payload"])["use_agent_browser"])
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

    def test_stage2_jobs_override_image_workers_from_korean_legacy_prefixes(
        self,
    ) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["scene_plan"] = [
            {"scene_index": 1, "prompt": "[인물] portrait prompt"},
            {"scene_index": 2, "prompt": "[사물] object prompt"},
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ]
        video_plan["stage1_handoff"] = {
            "contract": {"version": "stage1_handoff.v1.0", "title": "Money title"}
        }

        jobs, _ = build_stage2_jobs(video_plan)
        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]

        self.assertEqual(str(typed_jobs[0]["worker"]), "genspark")
        self.assertEqual(str(typed_jobs[1]["worker"]), "seaart")
        first_payload = cast(dict[str, object], typed_jobs[0]["payload"])
        second_payload = cast(dict[str, object], typed_jobs[1]["payload"])
        self.assertEqual(str(first_payload["prompt"]), "portrait prompt")
        self.assertEqual(str(second_payload["prompt"]), "object prompt")
        self.assertEqual(str(first_payload["legacy_category"]), "인물")
        self.assertEqual(str(second_payload["legacy_category"]), "사물")

    def test_stage2_jobs_override_image_workers_from_english_legacy_prefixes(
        self,
    ) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["scene_plan"] = [
            {"scene_index": 1, "prompt": "[person] portrait prompt"},
            {"scene_index": 2, "prompt": "[object] object prompt"},
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ]
        video_plan["stage1_handoff"] = {
            "contract": {"version": "stage1_handoff.v1.0", "title": "Money title"}
        }

        jobs, _ = build_stage2_jobs(video_plan)
        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]

        self.assertEqual(str(typed_jobs[0]["worker"]), "genspark")
        self.assertEqual(str(typed_jobs[1]["worker"]), "seaart")
        first_payload = cast(dict[str, object], typed_jobs[0]["payload"])
        second_payload = cast(dict[str, object], typed_jobs[1]["payload"])
        self.assertEqual(str(first_payload["prompt"]), "portrait prompt")
        self.assertEqual(str(second_payload["prompt"]), "object prompt")
        self.assertEqual(str(first_payload["legacy_category"]), "person")
        self.assertEqual(str(second_payload["legacy_category"]), "object")

    def test_stage2_jobs_ignore_unknown_bracket_labels(self) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")
        video_plan["scene_plan"] = [
            {"scene_index": 1, "prompt": "[foo] scene one"},
            {"scene_index": 2, "prompt": "scene two"},
        ]
        video_plan["stage1_handoff"] = {
            "contract": {"version": "stage1_handoff.v1.0", "title": "Money title"}
        }

        jobs, _ = build_stage2_jobs(video_plan)
        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        first_payload = cast(dict[str, object], typed_jobs[0]["payload"])

        self.assertEqual(str(typed_jobs[0]["worker"]), "genspark")
        self.assertEqual(str(first_payload["prompt"]), "[foo] scene one")
        self.assertNotIn("legacy_category", first_payload)

    def test_canva_stage2_payload_prefers_stage1_ref_image_when_present(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            video_plan = _video_plan(tmp_dir)
            ref_img = Path(tmp_dir) / "images" / "ref1.png"
            ref_img.parent.mkdir(parents=True, exist_ok=True)
            ref_img.write_bytes(b"png")
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
                    "ref_img_1": str(ref_img.resolve()),
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

        self.assertEqual(str(payload["ref_img"]), str(ref_img.resolve()))
        self.assertEqual(str(thumb_data["line1"]), "Thumb line 1")
        self.assertEqual(str(thumb_data["line2"]), "Thumb line 2")

    def test_geminigen_stage2_payload_prefers_stage1_ref_image_when_present(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            video_plan = _video_plan(tmp_dir)
            ref_img = Path(tmp_dir) / "images" / "ref1.png"
            ref_img.parent.mkdir(parents=True, exist_ok=True)
            ref_img.write_bytes(b"png")
            video_plan["scene_plan"] = [
                {"scene_index": 1, "prompt": "scene one"},
                {"scene_index": 2, "prompt": "scene two"},
                {"scene_index": 3, "prompt": "scene three"},
            ]
            video_plan["stage1_handoff"] = {
                "contract": {
                    "version": "stage1_handoff.v1.0",
                    "title": "Money title",
                    "ref_img_1": str(ref_img.resolve()),
                }
            }

            jobs, _ = build_stage2_jobs(video_plan)
        geminigen_job = next(
            cast(dict[str, object], item["job"])
            for item in jobs
            if cast(dict[str, object], item["job"])["worker"] == "geminigen"
        )
        payload = cast(dict[str, object], geminigen_job["payload"])

        self.assertEqual(str(payload["first_frame_path"]), str(ref_img.resolve()))

    def test_genspark_and_seaart_payloads_include_ref_images_from_ref_jobs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            video_plan = _video_plan(tmp_dir)
            video_plan["stage1_handoff"] = {
                "contract": {
                    "version": "stage1_handoff.v1.0",
                    "ref_img_1": "legacy ref prompt 1",
                    "ref_img_2": "legacy ref prompt 2",
                }
            }
            jobs, _ = build_stage2_jobs(video_plan)

        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        genspark_job = next(
            job
            for job in typed_jobs
            if str(job["worker"]) == "genspark"
            and str(job["job_id"]) == "genspark-stage2-run-1-1"
        )
        seaart_job = next(
            job
            for job in typed_jobs
            if str(job["worker"]) == "seaart"
            and str(job["job_id"]) == "seaart-stage2-run-1-2"
        )
        genspark_payload = cast(dict[str, object], genspark_job["payload"])
        seaart_payload = cast(dict[str, object], seaart_job["payload"])
        self.assertTrue(
            str(genspark_payload["ref_img_1"])
            .replace("\\", "/")
            .endswith("images/ref-1-stage2-run-1.png")
        )
        self.assertTrue(
            str(genspark_payload["ref_img_2"])
            .replace("\\", "/")
            .endswith("images/ref-2-stage2-run-1.png")
        )
        self.assertTrue(
            str(seaart_payload["ref_img_1"])
            .replace("\\", "/")
            .endswith("images/ref-1-stage2-run-1.png")
        )
        self.assertTrue(
            str(seaart_payload["ref_img_2"])
            .replace("\\", "/")
            .endswith("images/ref-2-stage2-run-1.png")
        )

    def test_stage2_jobs_skip_ref_generation_when_stage1_refs_are_real_files(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            video_plan = _video_plan(tmp_dir)
            ref1 = Path(tmp_dir) / "images" / "ref1.png"
            ref2 = Path(tmp_dir) / "images" / "ref2.png"
            ref1.parent.mkdir(parents=True, exist_ok=True)
            ref1.write_bytes(b"png")
            ref2.write_bytes(b"png")
            video_plan["stage1_handoff"] = {
                "contract": {
                    "version": "stage1_handoff.v1.0",
                    "ref_img_1": str(ref1.resolve()),
                    "ref_img_2": str(ref2.resolve()),
                }
            }

            jobs, _ = build_stage2_jobs(video_plan)

        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        ref_jobs = [
            job
            for job in typed_jobs
            if str(job["worker"]) in {"genspark", "seaart"}
            and str(job["job_id"]).endswith(("ref-1", "ref-2"))
        ]
        genspark_scene_job = next(
            job
            for job in typed_jobs
            if str(job["worker"]) == "genspark"
            and str(job["job_id"]) == "genspark-stage2-run-1-1"
        )
        seaart_scene_job = next(
            job
            for job in typed_jobs
            if str(job["worker"]) == "seaart"
            and str(job["job_id"]) == "seaart-stage2-run-1-2"
        )
        genspark_payload = cast(dict[str, object], genspark_scene_job["payload"])
        seaart_payload = cast(dict[str, object], seaart_scene_job["payload"])
        self.assertEqual(ref_jobs, [])
        self.assertEqual(str(genspark_payload["ref_img_1"]), str(ref1.resolve()))
        self.assertEqual(str(seaart_payload["ref_img_2"]), str(ref2.resolve()))

    def test_stage2_jobs_create_geminigen_tasks_from_stage1_videos(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            video_plan = _video_plan(tmp_dir)
            ref1 = Path(tmp_dir) / "images" / "ref1.png"
            ref1.parent.mkdir(parents=True, exist_ok=True)
            ref1.write_bytes(b"png")
            video_plan["videos"] = ["video prompt 1", "video prompt 2"]
            video_plan["stage1_handoff"] = {
                "contract": {
                    "version": "stage1_handoff.v1.0",
                    "ref_img_1": str(ref1.resolve()),
                    "videos": ["video prompt 1", "video prompt 2"],
                }
            }

            jobs, render_spec = build_stage2_jobs(video_plan)

        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        geminigen_jobs = [
            job for job in typed_jobs if str(job["worker"]) == "geminigen"
        ]

        self.assertEqual(len(geminigen_jobs), 2)
        first_payload = cast(dict[str, object], geminigen_jobs[0]["payload"])
        second_payload = cast(dict[str, object], geminigen_jobs[1]["payload"])
        self.assertEqual(str(first_payload["prompt"]), "video prompt 1")
        self.assertEqual(str(second_payload["prompt"]), "video prompt 2")
        self.assertEqual(str(first_payload["first_frame_path"]), str(ref1.resolve()))
        render_timeline = cast(list[object], render_spec["timeline"])
        gemi_timeline = [
            cast(dict[str, object], item)
            for item in render_timeline
            if isinstance(item, dict)
            and str(cast(dict[str, object], item).get("workload", "")) == "geminigen"
        ]
        self.assertEqual(len(gemi_timeline), 2)

    def test_stage2_jobs_create_kenburns_bundle_contract_for_image_scenes(self) -> None:
        video_plan = _video_plan("D:/YOUTUBEAUTO")

        jobs, render_spec = build_stage2_jobs(video_plan)
        typed_jobs = [cast(dict[str, object], item["job"]) for item in jobs[:-1]]
        kenburns_job = next(
            job for job in typed_jobs if str(job["worker"]) == "kenburns"
        )
        kenburns_payload = cast(dict[str, object], kenburns_job["payload"])
        scene_bundle_map = cast(dict[str, object], kenburns_payload["scene_bundle_map"])
        scenes = cast(list[object], scene_bundle_map["scenes"])
        render_timeline = cast(list[object], render_spec["timeline"])

        self.assertTrue(scenes)
        first_scene = cast(dict[str, object], scenes[0])
        self.assertTrue(
            str(first_scene["output_path"]).replace("\\", "/").endswith("#01_KEN.mp4")
        )
        first_render_entry = cast(dict[str, object], render_timeline[0])
        self.assertEqual(str(first_render_entry["workload"]), "kenburns")

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

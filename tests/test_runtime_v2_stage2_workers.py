from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Literal, cast

from runtime_v2.config import RuntimeConfig, WorkloadName
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import run_worker
from runtime_v2.stage2.canva_worker import run_canva_job
from runtime_v2.stage2.geminigen_worker import run_geminigen_job
from runtime_v2.stage2.genspark_worker import run_genspark_job
from runtime_v2.stage2.json_builders import build_stage2_jobs
from runtime_v2.stage2.seaart_worker import run_seaart_job
from runtime_v2.supervisor import run_once
from runtime_v2.worker_registry import update_worker_state


Stage2Workload = Literal["genspark", "seaart", "geminigen", "canva"]


def _stage2_job(workload: Stage2Workload = "genspark") -> JobContract:
    return JobContract(
        job_id=f"{workload}-job-1",
        workload=cast(WorkloadName, workload),
        checkpoint_key=f"stage2:{workload}:Sheet1!row1:1",
        payload={
            "run_id": "stage2-run-1",
            "row_ref": "Sheet1!row1",
            "scene_index": 1,
            "prompt": "scene one",
            "asset_root": "D:/YOUTUBEAUTO/system/runtime_v2/artifacts",
            "reason_code": "ok",
            "channel": 4,
            "topic": "Bridge topic",
            "row_index": 0,
            "thumb_data": {
                "bg_prompt": "scene one",
                "line1": "Legacy",
                "line2": "Thumb",
            },
        },
    )


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
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ],
        "asset_plan": {"asset_root": asset_root, "common_asset_folder": asset_root},
        "voice_plan": {"mapping_source": "excel_scene", "scene_count": 4, "groups": []},
        "reason_code": "ok",
        "evidence": {"source": "test"},
    }


class RuntimeV2Stage2WorkerTests(unittest.TestCase):
    def test_stage2_browser_workers_process_one_item_and_write_artifacts(self) -> None:
        cases = [
            (
                run_genspark_job,
                _stage2_job("genspark"),
                "genspark",
                "native_prompt.json",
                ".png",
            ),
            (
                run_seaart_job,
                _stage2_job("seaart"),
                "seaart",
                "native_prompt.json",
                ".png",
            ),
            (
                run_geminigen_job,
                _stage2_job("geminigen"),
                "geminigen",
                "native_geminigen.json",
                ".mp4",
            ),
            (run_canva_job, _stage2_job("canva"), "canva", "thumb_data.json", ".png"),
        ]
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            for runner, job, workload, request_artifact, suffix in cases:
                output_path = root / "exports" / f"{workload}-scene-01{suffix}"
                job.payload["service_artifact_path"] = str(output_path)

                result = runner(job, artifact_root)

                workspace = artifact_root / workload / job.job_id
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["stage"], workload)
                self.assertTrue(output_path.exists())
                self.assertTrue((workspace / "request.json").exists())
                self.assertTrue((workspace / request_artifact).exists())
                self.assertFalse(result.get("next_jobs", []))
                completion = cast(dict[str, object], result["completion"])
                self.assertEqual(completion["state"], "succeeded")
                self.assertTrue(bool(completion["final_output"]))
                self.assertEqual(
                    completion["final_artifact_path"], str(output_path.resolve())
                )

    def test_stage2_row_processing_handles_all_browser_worker_items_for_one_row(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            jobs, _ = build_stage2_jobs(_video_plan(tmp_dir))
            browser_jobs = [
                cast(dict[str, object], job["job"])
                for job in jobs
                if cast(dict[str, object], job["job"])["worker"] != "render"
            ]

            self.assertEqual(
                [str(job["worker"]) for job in browser_jobs],
                ["genspark", "seaart", "geminigen", "canva"],
            )

            for job_payload in browser_jobs:
                worker_name = str(job_payload["worker"])
                payload = cast(dict[str, object], job_payload["payload"])
                contract = JobContract(
                    job_id=str(job_payload["job_id"]),
                    workload=cast(WorkloadName, worker_name),
                    checkpoint_key=str(job_payload["checkpoint_key"]),
                    payload=payload,
                )
                if worker_name == "genspark":
                    result = run_genspark_job(contract, root / "artifacts")
                elif worker_name == "seaart":
                    result = run_seaart_job(contract, root / "artifacts")
                elif worker_name == "geminigen":
                    result = run_geminigen_job(contract, root / "artifacts")
                else:
                    result = run_canva_job(contract, root / "artifacts")

                self.assertEqual(result["status"], "ok")
                artifact_path = Path(str(payload["service_artifact_path"]))
                self.assertTrue(artifact_path.exists())

    def test_stage2_worker_fails_closed_when_prompt_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            job = _stage2_job("genspark")
            job.payload["prompt"] = ""
            job.payload["service_artifact_path"] = str(root / "exports" / "missing.png")

            result = run_genspark_job(job, root / "artifacts")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "missing_prompt")

    def test_genspark_worker_records_service_artifact_details_on_success(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(root / "shared" / "output.png")

            result = run_genspark_job(
                job, root / "artifacts", registry_file=registry_file
            )

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(
            details["service_artifact_path"],
            str((root / "shared" / "output.png").resolve()),
        )

    def test_stage2_worker_uses_json_input_only_and_returns_runner_result(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(root / "exports" / "output.png")

            result = run_genspark_job(
                job, root / "artifacts", registry_file=registry_file
            )

            request_payload_raw = cast(
                object,
                json.loads(
                    (
                        root
                        / "artifacts"
                        / "genspark"
                        / "genspark-job-1"
                        / "request.json"
                    ).read_text(encoding="utf-8")
                ),
            )
            self.assertIsInstance(request_payload_raw, dict)
            if not isinstance(request_payload_raw, dict):
                self.fail("request payload is not an object")
            request_payload = cast(dict[object, object], request_payload_raw)
            payload_object = cast(dict[object, object], request_payload["payload"])

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stage"], "genspark")
        self.assertEqual(str(payload_object["row_ref"]), "Sheet1!row1")
        self.assertNotIn("excel_path", json.dumps(request_payload, ensure_ascii=True))

    def test_stage2_worker_never_updates_excel_directly(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"
            job = _stage2_job("genspark")
            job.payload["excel_path"] = "D:/SHOULD/NOT/BE/USED.xlsx"
            job.payload["service_artifact_path"] = str(root / "exports" / "output.png")

            result = run_genspark_job(
                job, root / "artifacts", registry_file=registry_file
            )

        self.assertEqual(result["status"], "ok")
        self.assertFalse(
            (root / "artifacts" / "genspark" / "genspark-job-1" / "D").exists()
        )

    def test_stage2_failure_keeps_completion_blocked(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = ""

            result = run_genspark_job(job, root / "artifacts")

        completion = cast(dict[str, object], result["completion"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(completion["state"], "blocked")
        self.assertFalse(bool(completion["final_output"]))

    def test_stage2_jobs_dispatch_to_resident_workers(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                worker_registry_file=root / "health" / "worker_registry.json",
                artifact_root=root / "artifacts",
            )
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(
                root / "exports" / "dispatch-output.png"
            )
            result = run_worker(
                job, config.artifact_root, registry_file=config.worker_registry_file
            )

            registry_payload_raw = cast(
                object,
                json.loads(config.worker_registry_file.read_text(encoding="utf-8")),
            )
            self.assertIsInstance(registry_payload_raw, dict)
            if not isinstance(registry_payload_raw, dict):
                self.fail("registry payload is not an object")
            registry_payload = cast(dict[object, object], registry_payload_raw)

        self.assertEqual(result["status"], "ok")
        self.assertIn("genspark", registry_payload)
        registry_entry = cast(dict[object, object], registry_payload["genspark"])
        self.assertEqual(str(registry_entry["state"]), "idle")

    def test_resident_worker_progress_stall_is_reported_to_supervisor(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                worker_registry_file=root / "health" / "worker_registry.json",
                progress_stall_timeout_sec=1,
            )
            _ = update_worker_state(
                config.worker_registry_file,
                workload="genspark",
                state="busy",
                run_id="stage2-run-1",
                progress_ts=0.0,
            )

            result = run_once(
                owner="runtime_v2",
                run_id="stage2-run-1",
                config=config,
                workload="genspark",
                worker_runner=lambda: {"status": "ok", "stage": "genspark"},
            )

        self.assertIn("worker_stalls", result)
        worker_stalls = cast(list[object], result["worker_stalls"])
        self.assertIn("genspark", worker_stalls)


if __name__ == "__main__":
    _ = unittest.main()

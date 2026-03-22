from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Literal, cast
from unittest.mock import patch

from runtime_v2.config import RuntimeConfig, WorkloadName
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import run_worker
from runtime_v2.stage2.agent_browser_adapter import (
    build_stage2_agent_browser_adapter_command,
)
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


REPO_ROOT = Path(__file__).resolve().parents[1]


class RuntimeV2Stage2WorkerTests(unittest.TestCase):
    def test_genspark_worker_injects_pythonpath_for_agent_browser_child(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = root / "exports" / "scene-01.png"
            job = _stage2_job("genspark")
            job.payload["use_agent_browser"] = True
            job.payload["service_artifact_path"] = str(output_path)

            with patch(
                "runtime_v2.stage2.genspark_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "output_path": output_path,
                    "stdout_path": root / "stdout.log",
                    "stderr_path": root / "stderr.log",
                    "reused": False,
                },
            ) as adapter_mock:
                _ = run_genspark_job(job, artifact_root)

        kwargs = adapter_mock.call_args.kwargs
        extra_env = cast(dict[str, str], kwargs["extra_env"])
        self.assertIn("PYTHONPATH", extra_env)
        self.assertTrue(extra_env["PYTHONPATH"].startswith(str(REPO_ROOT.resolve())))

    def test_genspark_worker_marks_browser_failures_retryable(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = root / "exports" / "scene-01.png"
            job = _stage2_job("genspark")
            job.payload["use_agent_browser"] = True
            job.payload["service_artifact_path"] = str(output_path)

            with patch(
                "runtime_v2.stage2.genspark_worker.run_verified_adapter_command",
                return_value={
                    "ok": False,
                    "error_code": "BROWSER_UNHEALTHY",
                    "stdout_path": root / "stdout.log",
                    "stderr_path": root / "stderr.log",
                    "details": {},
                },
            ):
                result = run_genspark_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "BROWSER_UNHEALTHY")
        self.assertTrue(bool(result["retryable"]))

    def test_seaart_worker_marks_browser_failures_retryable(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = root / "exports" / "scene-01.png"
            job = _stage2_job("seaart")
            job.payload["use_agent_browser"] = True
            job.payload["service_artifact_path"] = str(output_path)

            with patch(
                "runtime_v2.stage2.seaart_worker.run_verified_adapter_command",
                return_value={
                    "ok": False,
                    "error_code": "BROWSER_BLOCKED",
                    "stdout_path": root / "stdout.log",
                    "stderr_path": root / "stderr.log",
                    "details": {},
                },
            ):
                result = run_seaart_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "BROWSER_BLOCKED")
        self.assertTrue(bool(result["retryable"]))

    def test_geminigen_worker_marks_browser_failures_retryable(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = root / "exports" / "scene-03.mp4"
            job = _stage2_job("geminigen")
            job.payload["use_agent_browser"] = True
            job.payload["service_artifact_path"] = str(output_path)

            with patch(
                "runtime_v2.stage2.geminigen_worker.run_verified_adapter_command",
                return_value={
                    "ok": False,
                    "error_code": "BROWSER_UNHEALTHY",
                    "stdout_path": root / "stdout.log",
                    "stderr_path": root / "stderr.log",
                    "details": {},
                },
            ):
                result = run_geminigen_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "BROWSER_UNHEALTHY")
        self.assertTrue(bool(result["retryable"]))

    def test_canva_worker_marks_browser_failures_retryable(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = root / "exports" / "scene-01.png"
            job = _stage2_job("canva")
            job.payload["use_agent_browser"] = True
            job.payload["service_artifact_path"] = str(output_path)

            with patch(
                "runtime_v2.stage2.canva_worker.run_verified_adapter_command",
                return_value={
                    "ok": False,
                    "error_code": "BROWSER_UNHEALTHY",
                    "stdout_path": root / "stdout.log",
                    "stderr_path": root / "stderr.log",
                    "details": {},
                },
            ):
                result = run_canva_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "BROWSER_UNHEALTHY")
        self.assertTrue(bool(result["retryable"]))

    def test_agent_browser_stage2_adapter_command_uses_hidden_cli_child(self) -> None:
        command = build_stage2_agent_browser_adapter_command(
            service="genspark",
            service_artifact_path="D:/YOUTUBEAUTO/system/runtime_v2/artifacts/images/test.png",
        )

        self.assertIn("--agent-browser-stage2-adapter-child", command)
        self.assertIn("--service", command)
        self.assertIn("genspark", command)
        self.assertIn("--service-artifact-path", command)
        self.assertIn("genspark.ai", command)

    def test_geminigen_worker_processes_one_item_via_explicit_adapter_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = artifact_root / "exports" / "geminigen-scene-01.mp4"
            first_frame_path = root / "exports" / "first-frame-01.png"
            _ = first_frame_path.parent.mkdir(parents=True, exist_ok=True)
            _ = first_frame_path.write_bytes(b"png")
            job = _stage2_job("geminigen")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["first_frame_path"] = str(first_frame_path)
            job.payload["adapter_command"] = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    f"p=Path(r'{str(output_path)}'); "
                    "p.parent.mkdir(parents=True, exist_ok=True); "
                    "p.write_bytes(b'mp4')"
                ),
            ]

            result = run_geminigen_job(job, artifact_root)

            workspace = artifact_root / "geminigen" / job.job_id
            self.assertEqual(result["status"], "ok")
            self.assertTrue(output_path.exists())
            self.assertTrue((workspace / "request.json").exists())
            self.assertTrue((workspace / "native_geminigen.json").exists())
            self.assertTrue((workspace / "adapter_stdout.log").exists())
            self.assertTrue((workspace / "adapter_stderr.log").exists())
            native_payload = cast(
                dict[str, object],
                json.loads(
                    (workspace / "native_geminigen.json").read_text(encoding="utf-8")
                ),
            )
            video_task = cast(
                dict[str, object], cast(list[object], native_payload["video_tasks"])[0]
            )
            completion = cast(dict[str, object], result["completion"])
            details = cast(dict[str, object], result["details"])
            self.assertEqual(completion["state"], "succeeded")
            self.assertTrue(bool(completion["final_output"]))
            self.assertEqual(
                str(video_task["first_frame_path"]), str(first_frame_path.resolve())
            )
            self.assertEqual(str(video_task["orientation"]), "landscape")
            self.assertEqual(str(video_task["resolution"]), "720p")
            self.assertEqual(str(video_task["duration"]), "6")
            self.assertEqual(str(details["orientation"]), "landscape")
            self.assertEqual(str(details["resolution"]), "720p")
            self.assertEqual(str(details["duration"]), "6")

    def test_geminigen_row_processing_handles_all_items_for_one_row_via_adapter_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            jobs, _ = build_stage2_jobs(_video_plan(tmp_dir))
            geminigen_jobs = [
                cast(dict[str, object], job["job"])
                for job in jobs
                if cast(dict[str, object], job["job"])["worker"] == "geminigen"
            ]

            self.assertTrue(geminigen_jobs)
            for index, job_payload in enumerate(geminigen_jobs, start=1):
                payload = cast(dict[str, object], job_payload["payload"])
                output_path = (
                    root / "artifacts" / "exports" / f"geminigen-row-{index:02d}.mp4"
                )
                first_frame_path = root / "exports" / f"first-frame-{index:02d}.png"
                _ = first_frame_path.parent.mkdir(parents=True, exist_ok=True)
                _ = first_frame_path.write_bytes(b"png")
                payload["service_artifact_path"] = str(output_path)
                payload["first_frame_path"] = str(first_frame_path)
                payload["adapter_command"] = [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"p=Path(r'{str(output_path)}'); "
                        "p.parent.mkdir(parents=True, exist_ok=True); "
                        "p.write_bytes(b'mp4')"
                    ),
                ]
                contract = JobContract(
                    job_id=str(job_payload["job_id"]),
                    workload="geminigen",
                    checkpoint_key=str(job_payload["checkpoint_key"]),
                    payload=payload,
                )

                result = run_geminigen_job(contract, root / "artifacts")

                self.assertEqual(result["status"], "ok")
                self.assertTrue(output_path.exists())

    def test_canva_worker_processes_one_item_via_explicit_adapter_command(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = artifact_root / "exports" / "canva-thumb-01.png"
            job = _stage2_job("canva")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["adapter_command"] = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    f"p=Path(r'{str(output_path)}'); "
                    "p.parent.mkdir(parents=True, exist_ok=True); "
                    "p.write_bytes(b'png')"
                ),
            ]
            attach_evidence = (
                artifact_root / "canva" / job.job_id / "attach_evidence.json"
            )
            attach_evidence.parent.mkdir(parents=True, exist_ok=True)
            _ = attach_evidence.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "error_code": "",
                        "placeholder_artifact": False,
                        "current_url": "https://www.canva.com/design/foo/edit",
                        "current_title": "Canva design",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            result = run_canva_job(job, artifact_root)

            workspace = artifact_root / "canva" / job.job_id
            self.assertEqual(result["status"], "ok")
            self.assertTrue(output_path.exists())
            self.assertTrue((workspace / "request.json").exists())
            self.assertTrue((workspace / "thumb_data.json").exists())
            self.assertTrue((workspace / "adapter_stdout.log").exists())
            self.assertTrue((workspace / "adapter_stderr.log").exists())
            completion = cast(dict[str, object], result["completion"])
            details = cast(dict[str, object], result["details"])
            self.assertEqual(completion["state"], "succeeded")
            self.assertTrue(bool(completion["final_output"]))
            self.assertEqual(str(details["attach_status"]), "ok")
            self.assertFalse(bool(details["placeholder_artifact"]))
            self.assertEqual(str(details["current_title"]), "Canva design")

    def test_canva_row_processing_handles_all_items_for_one_row_via_adapter_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            jobs, _ = build_stage2_jobs(_video_plan(tmp_dir))
            canva_jobs = [
                cast(dict[str, object], job["job"])
                for job in jobs
                if cast(dict[str, object], job["job"])["worker"] == "canva"
            ]

            self.assertTrue(canva_jobs)
            for index, job_payload in enumerate(canva_jobs, start=1):
                payload = cast(dict[str, object], job_payload["payload"])
                output_path = (
                    root / "artifacts" / "exports" / f"canva-row-{index:02d}.png"
                )
                payload["service_artifact_path"] = str(output_path)
                payload["adapter_command"] = [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"p=Path(r'{str(output_path)}'); "
                        "p.parent.mkdir(parents=True, exist_ok=True); "
                        "p.write_bytes(b'png')"
                    ),
                ]
                contract = JobContract(
                    job_id=str(job_payload["job_id"]),
                    workload="canva",
                    checkpoint_key=str(job_payload["checkpoint_key"]),
                    payload=payload,
                )

                result = run_canva_job(contract, root / "artifacts")

                self.assertEqual(result["status"], "ok")
                self.assertTrue(output_path.exists())

    def test_genspark_worker_processes_one_item_via_explicit_adapter_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = artifact_root / "exports" / "genspark-scene-01.png"
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["adapter_command"] = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    f"p=Path(r'{str(output_path)}'); "
                    "p.parent.mkdir(parents=True, exist_ok=True); "
                    "p.write_bytes(b'png')"
                ),
            ]

            result = run_genspark_job(job, artifact_root)

            workspace = artifact_root / "genspark" / job.job_id
            self.assertEqual(result["status"], "ok")
            self.assertTrue(output_path.exists())
            self.assertTrue((workspace / "request.json").exists())
            self.assertTrue((workspace / "native_prompt.json").exists())
            self.assertTrue((workspace / "adapter_stdout.log").exists())
            self.assertTrue((workspace / "adapter_stderr.log").exists())
            completion = cast(dict[str, object], result["completion"])
            self.assertEqual(completion["state"], "succeeded")
            self.assertTrue(bool(completion["final_output"]))

    def test_genspark_row_processing_handles_all_items_for_one_row_via_adapter_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            jobs, _ = build_stage2_jobs(_video_plan(tmp_dir))
            genspark_jobs = [
                cast(dict[str, object], job["job"])
                for job in jobs
                if cast(dict[str, object], job["job"])["worker"] == "genspark"
            ]

            self.assertTrue(genspark_jobs)
            for index, job_payload in enumerate(genspark_jobs, start=1):
                payload = cast(dict[str, object], job_payload["payload"])
                output_path = (
                    root / "artifacts" / "exports" / f"genspark-row-{index:02d}.png"
                )
                payload["service_artifact_path"] = str(output_path)
                payload["adapter_command"] = [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"p=Path(r'{str(output_path)}'); "
                        "p.parent.mkdir(parents=True, exist_ok=True); "
                        "p.write_bytes(b'png')"
                    ),
                ]
                contract = JobContract(
                    job_id=str(job_payload["job_id"]),
                    workload="genspark",
                    checkpoint_key=str(job_payload["checkpoint_key"]),
                    payload=payload,
                )

                result = run_genspark_job(contract, root / "artifacts")

                self.assertEqual(result["status"], "ok")
                self.assertTrue(output_path.exists())

    def test_genspark_worker_reuses_existing_output_as_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = artifact_root / "exports" / "genspark-stale.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"stale")
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["adapter_command"] = [sys.executable, "-c", "pass"]

            result = run_genspark_job(job, artifact_root)

        completion = cast(dict[str, object], result["completion"])
        details = cast(dict[str, object], result["details"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(completion["state"], "succeeded")
        self.assertTrue(bool(completion["final_output"]))
        self.assertTrue(bool(completion["reused"]))
        self.assertTrue(bool(details["reused"]))

    def test_genspark_worker_surfaces_standard_output_not_created_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = artifact_root / "exports" / "genspark-missing.png"
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["adapter_command"] = [sys.executable, "-c", "pass"]

            result = run_genspark_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "OUTPUT_NOT_CREATED")

    def test_seaart_worker_processes_one_item_via_explicit_adapter_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = artifact_root / "exports" / "seaart-scene-01.png"
            job = _stage2_job("seaart")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["adapter_command"] = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    f"p=Path(r'{str(output_path)}'); "
                    "p.parent.mkdir(parents=True, exist_ok=True); "
                    "p.write_bytes(b'png')"
                ),
            ]

            result = run_seaart_job(job, artifact_root)

            workspace = artifact_root / "seaart" / job.job_id
            self.assertEqual(result["status"], "ok")
            self.assertTrue(output_path.exists())
            self.assertTrue((workspace / "request.json").exists())
            self.assertTrue((workspace / "native_prompt.json").exists())
            self.assertTrue((workspace / "adapter_stdout.log").exists())
            self.assertTrue((workspace / "adapter_stderr.log").exists())
            completion = cast(dict[str, object], result["completion"])
            self.assertEqual(completion["state"], "succeeded")
            self.assertTrue(bool(completion["final_output"]))

    def test_seaart_row_processing_handles_all_items_for_one_row_via_adapter_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            jobs, _ = build_stage2_jobs(_video_plan(tmp_dir))
            seaart_jobs = [
                cast(dict[str, object], job["job"])
                for job in jobs
                if cast(dict[str, object], job["job"])["worker"] == "seaart"
            ]

            self.assertTrue(seaart_jobs)
            for index, job_payload in enumerate(seaart_jobs, start=1):
                payload = cast(dict[str, object], job_payload["payload"])
                output_path = (
                    root / "artifacts" / "exports" / f"seaart-row-{index:02d}.png"
                )
                payload["service_artifact_path"] = str(output_path)
                payload["adapter_command"] = [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"p=Path(r'{str(output_path)}'); "
                        "p.parent.mkdir(parents=True, exist_ok=True); "
                        "p.write_bytes(b'png')"
                    ),
                ]
                contract = JobContract(
                    job_id=str(job_payload["job_id"]),
                    workload="seaart",
                    checkpoint_key=str(job_payload["checkpoint_key"]),
                    payload=payload,
                )

                result = run_seaart_job(contract, root / "artifacts")

                self.assertEqual(result["status"], "ok")
                self.assertTrue(output_path.exists())

    def test_stage2_browser_workers_fail_closed_until_native_implementation_exists(
        self,
    ) -> None:
        cases = [
            (
                run_genspark_job,
                _stage2_job("genspark"),
                "genspark",
                "native_prompt.json",
            ),
            (
                run_geminigen_job,
                _stage2_job("geminigen"),
                "geminigen",
                "native_geminigen.json",
            ),
            (run_canva_job, _stage2_job("canva"), "canva", "thumb_data.json"),
        ]
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            for runner, job, workload, request_artifact in cases:
                output_path = artifact_root / "exports" / f"{workload}-scene-01.out"
                job.payload["service_artifact_path"] = str(output_path)

                result = runner(job, artifact_root)

                workspace = artifact_root / workload / job.job_id
                self.assertEqual(result["status"], "failed")
                self.assertEqual(
                    result["error_code"], f"native_{workload}_not_implemented"
                )
                self.assertEqual(result["stage"], workload)
                self.assertTrue((workspace / "request.json").exists())
                self.assertTrue((workspace / request_artifact).exists())
                self.assertFalse(output_path.exists())
                self.assertFalse(result.get("next_jobs", []))
                completion = cast(dict[str, object], result["completion"])
                self.assertEqual(completion["state"], "failed")
                self.assertFalse(bool(completion["final_output"]))

    def test_stage2_row_processing_keeps_browser_worker_items_blocked_for_one_row(
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

                self.assertEqual(result["status"], "failed")
                self.assertEqual(
                    str(result["error_code"]),
                    f"native_{worker_name}_not_implemented",
                )
                artifact_path = Path(str(payload["service_artifact_path"]))
                self.assertFalse(artifact_path.exists())

    def test_stage2_worker_fails_closed_when_prompt_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            job = _stage2_job("genspark")
            job.payload["prompt"] = ""
            job.payload["service_artifact_path"] = str(root / "exports" / "missing.png")

            result = run_genspark_job(job, root / "artifacts")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "missing_prompt")

    def test_genspark_worker_records_native_only_details(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(root / "shared" / "output.png")

            result = run_genspark_job(
                job, root / "artifacts", registry_file=registry_file
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "native_genspark_not_implemented")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(str(details["execution_mode"]), "native_only")
        self.assertEqual(
            details["service_artifact_path"], str(root / "shared" / "output.png")
        )

    def test_genspark_worker_can_use_agent_browser_adapter_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "genspark-agent-browser.png"
            attach_evidence = (
                root
                / "artifacts"
                / "genspark"
                / "genspark-job-1"
                / "attach_evidence.json"
            )
            attach_evidence.parent.mkdir(parents=True, exist_ok=True)
            _ = attach_evidence.write_text('{"status":"ok"}', encoding="utf-8")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"png")
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["use_agent_browser"] = True
            job.payload["ref_img_1"] = "images/ref1.png"
            job.payload["ref_img_2"] = "images/ref2.png"
            _ = attach_evidence.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "ref_images_requested": ["images/ref1.png", "images/ref2.png"],
                        "ref_images_resolved": [
                            "D:/YOUTUBEAUTO/images/ref1.png",
                            "D:/YOUTUBEAUTO/images/ref2.png",
                        ],
                        "ref_images_attach_attempted": True,
                        "ref_upload_error_code": "",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.stage2.genspark_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                },
            ) as run_adapter:
                result = run_genspark_job(job, root / "artifacts")

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(str(details["adapter_mode"]), "agent_browser")
        self.assertTrue(
            str(details["attach_evidence_path"]).endswith("attach_evidence.json")
        )
        self.assertEqual(str(details["ref_img_1"]), "images/ref1.png")
        self.assertEqual(str(details["ref_img_2"]), "images/ref2.png")
        self.assertEqual(
            cast(list[object], details["ref_images_requested"]),
            ["images/ref1.png", "images/ref2.png"],
        )
        self.assertTrue(bool(details["ref_images_attach_attempted"]))
        adapter_command = run_adapter.call_args.kwargs["adapter_command"]
        self.assertIn("--agent-browser-stage2-adapter-child", adapter_command)
        self.assertIn("genspark", adapter_command)

    def test_seaart_worker_can_use_agent_browser_adapter_mode_with_ref_details(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "seaart-agent-browser.png"
            attach_evidence = (
                root / "artifacts" / "seaart" / "seaart-job-1" / "attach_evidence.json"
            )
            attach_evidence.parent.mkdir(parents=True, exist_ok=True)
            _ = attach_evidence.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "ref_images_requested": ["images/ref1.png", "images/ref2.png"],
                        "ref_images_resolved": [
                            "D:/YOUTUBEAUTO/images/ref1.png",
                            "D:/YOUTUBEAUTO/images/ref2.png",
                        ],
                        "ref_images_attach_attempted": True,
                        "ref_upload_error_code": "",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"png")
            job = _stage2_job("seaart")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["use_agent_browser"] = True
            job.payload["ref_img_1"] = "images/ref1.png"
            job.payload["ref_img_2"] = "images/ref2.png"
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.stage2.seaart_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                },
            ) as run_adapter:
                result = run_seaart_job(job, root / "artifacts")

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(str(details["adapter_mode"]), "agent_browser")
        self.assertEqual(str(details["ref_img_1"]), "images/ref1.png")
        self.assertEqual(str(details["ref_img_2"]), "images/ref2.png")
        self.assertTrue(bool(details["ref_images_attach_attempted"]))
        adapter_command = run_adapter.call_args.kwargs["adapter_command"]
        self.assertIn("--agent-browser-stage2-adapter-child", adapter_command)
        self.assertIn("seaart", adapter_command)

    def test_canva_worker_can_use_agent_browser_adapter_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "canva-agent-browser.png"
            attach_evidence = (
                root / "artifacts" / "canva" / "canva-job-1" / "attach_evidence.json"
            )
            attach_evidence.parent.mkdir(parents=True, exist_ok=True)
            _ = attach_evidence.write_text('{"status":"ok"}', encoding="utf-8")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"png")
            job = _stage2_job("canva")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["use_agent_browser"] = True
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.stage2.canva_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                },
            ) as run_adapter:
                result = run_canva_job(job, root / "artifacts")

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertEqual(str(details["adapter_mode"]), "agent_browser")
        self.assertTrue(
            str(details["attach_evidence_path"]).endswith("attach_evidence.json")
        )
        adapter_command = run_adapter.call_args.kwargs["adapter_command"]
        self.assertIn("--agent-browser-stage2-adapter-child", adapter_command)
        self.assertIn("canva", adapter_command)

    def test_canva_worker_surfaces_full_legacy_sequence_details(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "canva-agent-browser.png"
            attach_evidence = (
                root / "artifacts" / "canva" / "canva-job-1" / "attach_evidence.json"
            )
            attach_evidence.parent.mkdir(parents=True, exist_ok=True)
            _ = attach_evidence.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "details": {
                            "page_count_before": 1,
                            "page_count_after": 2,
                            "clone_ok": True,
                            "background_generate_ok": True,
                            "upload_tab_ok": True,
                            "ref_image_requested": "D:/ref.png",
                            "ref_image_upload_ok": True,
                            "remove_background_ok": True,
                            "position_ok": True,
                            "text_edit_ok": True,
                            "current_page_selection_ok": True,
                            "download_options_ok": True,
                            "download_sequence_ok": True,
                            "cleanup_ok": True,
                            "bg_prompt": "legacy background",
                            "line1": "Legacy",
                            "line2": "Thumb",
                            "transcript_path": "D:/trace/agent_browser_transcript.json",
                        },
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"png")
            job = _stage2_job("canva")
            job.payload["service_artifact_path"] = str(output_path)
            job.payload["use_agent_browser"] = True
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.stage2.canva_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                },
            ):
                result = run_canva_job(job, root / "artifacts")

        self.assertEqual(result["status"], "ok")
        details = cast(dict[str, object], result["details"])
        self.assertTrue(bool(details["clone_ok"]))
        self.assertTrue(bool(details["background_generate_ok"]))
        self.assertTrue(bool(details["ref_image_upload_ok"]))
        self.assertTrue(bool(details["remove_background_ok"]))
        self.assertTrue(bool(details["position_ok"]))
        self.assertTrue(bool(details["text_edit_ok"]))
        self.assertTrue(bool(details["current_page_selection_ok"]))
        self.assertTrue(bool(details["download_options_ok"]))
        self.assertTrue(bool(details["download_sequence_ok"]))
        self.assertTrue(bool(details["cleanup_ok"]))
        self.assertEqual(str(details["bg_prompt"]), "legacy background")
        self.assertEqual(
            str(details["transcript_path"]), "D:/trace/agent_browser_transcript.json"
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

        self.assertEqual(result["status"], "failed")
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

        self.assertEqual(result["status"], "failed")
        self.assertFalse(
            (root / "artifacts" / "genspark" / "genspark-job-1" / "D").exists()
        )

    def test_stage2_failure_marks_completion_failed(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            job = _stage2_job("genspark")
            job.payload["service_artifact_path"] = ""

            result = run_genspark_job(job, root / "artifacts")

        completion = cast(dict[str, object], result["completion"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(completion["state"], "failed")
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

        self.assertEqual(result["status"], "failed")
        self.assertIn("genspark", registry_payload)
        registry_entry = cast(dict[object, object], registry_payload["genspark"])
        self.assertEqual(str(registry_entry["state"]), "idle")

    def test_run_worker_returns_registry_to_idle_when_worker_raises(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"
            artifact_root = root / "artifacts"
            job = _stage2_job("genspark")

            with patch(
                "runtime_v2.control_plane.run_genspark_job",
                side_effect=RuntimeError("dispatch exploded"),
            ):
                with self.assertRaisesRegex(RuntimeError, "dispatch exploded"):
                    _ = run_worker(
                        job,
                        artifact_root,
                        registry_file=registry_file,
                    )

            registry_payload_raw = cast(
                object,
                json.loads(registry_file.read_text(encoding="utf-8")),
            )
            self.assertIsInstance(registry_payload_raw, dict)
            if not isinstance(registry_payload_raw, dict):
                self.fail("registry payload is not an object")
            registry_payload = cast(dict[object, object], registry_payload_raw)

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

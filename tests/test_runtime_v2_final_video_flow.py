from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import _run_worker
from runtime_v2.manager import sync_final_video_result
from runtime_v2.stage3.render_worker import run_render_job


def _write_excel_fixture(path: Path, *, status: str = "Voice OK") -> Path:
    workbook = Workbook()
    sheet = cast(Worksheet, workbook.active)
    sheet.title = "Sheet1"
    sheet.append(["Topic", "Status", "Video Plan", "Reason Code"])
    sheet.append(["Bridge topic", status, "", ""])
    workbook.save(path)
    workbook.close()
    return path


def _read_status_row(path: Path) -> dict[str, object]:
    workbook = load_workbook(path)
    try:
        sheet = workbook["Sheet1"]
        return {
            "status": sheet.cell(row=2, column=2).value,
            "summary": sheet.cell(row=2, column=3).value,
            "reason_code": sheet.cell(row=2, column=4).value,
        }
    finally:
        workbook.close()


def _write_render_fixture(
    root: Path, *, final_name: str = "render_final.mp4"
) -> tuple[Path, Path, Path]:
    render_folder = root / "legacy_render"
    video_dir = render_folder / "video"
    output_dir = render_folder / "output"
    video_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_path = video_dir / "#01_RVC.mp4"
    clip_path.write_bytes(b"mp4")
    final_output = output_dir / final_name
    final_output.write_bytes(b"final-mp4")
    voice_json = root / "voice.json"
    voice_json.write_text(
        json.dumps(
            {
                "voice_texts": [
                    {"col": "#01", "text": "bridge line", "original_voices": [1]}
                ]
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    render_spec = root / "render_spec.json"
    render_spec.write_text(
        json.dumps(
            {
                "contract": "render_spec",
                "locked": True,
                "asset_refs": [str(clip_path.resolve())],
                "timeline": [
                    {"scene_index": 1, "asset_path": str(clip_path.resolve())}
                ],
                "audio_refs": [str(voice_json.resolve())],
                "thumbnail_refs": [],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    return render_folder, voice_json, render_spec


class RuntimeV2FinalVideoFlowTests(unittest.TestCase):
    def test_render_worker_fails_closed_without_render_inputs(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "artifacts"
            job = JobContract(
                job_id="render-job-fail", workload="render", payload={"timeline": []}
            )

            result = run_render_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "missing_render_inputs")

    def test_render_worker_calls_legacy_executor_and_stages_output_from_result_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            render_folder, voice_json, render_spec = _write_render_fixture(root)
            job = JobContract(
                job_id="render-job-ok",
                workload="render",
                payload={
                    "render_folder_path": str(render_folder.resolve()),
                    "voice_json_path": str(voice_json.resolve()),
                    "render_spec_path": str(render_spec.resolve()),
                },
            )
            result = run_render_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "render")
        self.assertEqual(result["error_code"], "native_render_not_implemented")

    def test_render_worker_fails_closed_when_legacy_result_json_is_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            render_folder, voice_json, render_spec = _write_render_fixture(root)
            job = JobContract(
                job_id="render-job-invalid-json",
                workload="render",
                payload={
                    "render_folder_path": str(render_folder.resolve()),
                    "voice_json_path": str(voice_json.resolve()),
                    "render_spec_path": str(render_spec.resolve()),
                },
            )
            result = run_render_job(job, artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "native_render_not_implemented")

    def test_render_worker_blocks_retry_when_render_assets_are_not_ready(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            render_folder, voice_json, render_spec = _write_render_fixture(root)
            missing_clip = render_folder / "video" / "#01_RVC.mp4"
            missing_clip.unlink()
            job = JobContract(
                job_id="render-job-blocked",
                workload="render",
                payload={
                    "render_folder_path": str(render_folder.resolve()),
                    "voice_json_path": str(voice_json.resolve()),
                    "render_spec_path": str(render_spec.resolve()),
                },
            )

            result = run_render_job(job, artifact_root)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error_code"], "render_inputs_not_ready")
            self.assertTrue(bool(result["retryable"]))
            completion = cast(dict[object, object], result["completion"])
            self.assertEqual(str(completion["state"]), "blocked")
            details = cast(dict[object, object], result["details"])
            self.assertIn(
                str(missing_clip.resolve()),
                cast(list[object], details["missing_paths"]),
            )

    def test_final_video_success_marks_excel_done_and_updates_latest_run(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            excel_path = _write_excel_fixture(root / "topic.xlsx", status="Voice OK")
            config = RuntimeConfig(result_router_file=root / "evidence" / "result.json")
            final_video = root / "final_video.mp4"
            final_video.write_bytes(b"mp4")

            updated = sync_final_video_result(
                config=config,
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
                worker_result={
                    "completion": {
                        "state": "completed",
                        "final_output": True,
                        "final_artifact": "final_video.mp4",
                        "final_artifact_path": str(final_video.resolve()),
                    },
                    "details": {"reason_code": "ok"},
                },
                run_id="final-run-1",
                artifact_root=root,
                debug_log=str((root / "logs" / "final-run-1.jsonl").resolve()),
            )

            status_row = _read_status_row(excel_path)
            latest_result = json.loads(
                config.result_router_file.read_text(encoding="utf-8")
            )

        self.assertTrue(updated)
        self.assertEqual(status_row["status"], "Done")
        self.assertEqual(len(latest_result["artifacts"]), 1)
        self.assertTrue(latest_result["metadata"]["final_output"])
        self.assertTrue(
            str(latest_result["metadata"]["final_artifact_path"]).endswith(
                "final_video.mp4"
            )
        )

    def test_partial_failure_marks_excel_partial_with_reason(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            excel_path = _write_excel_fixture(root / "topic.xlsx", status="Video OK")
            config = RuntimeConfig(result_router_file=root / "evidence" / "result.json")

            updated = sync_final_video_result(
                config=config,
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
                worker_result={
                    "completion": {"state": "failed", "final_output": False},
                    "error_code": "ffmpeg_failed",
                },
                run_id="final-run-2",
                artifact_root=root,
                debug_log=str((root / "logs" / "final-run-2.jsonl").resolve()),
            )

            status_row = _read_status_row(excel_path)

        self.assertTrue(updated)
        self.assertEqual(status_row["status"], "partial")
        self.assertEqual(status_row["reason_code"], "ffmpeg_failed")

    def test_partial_failure_with_none_reason_code_falls_back_to_ok(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            excel_path = _write_excel_fixture(root / "topic.xlsx", status="Video OK")
            config = RuntimeConfig(result_router_file=root / "evidence" / "result.json")

            updated = sync_final_video_result(
                config=config,
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
                worker_result={
                    "completion": {"state": "failed", "final_output": False},
                    "details": {"reason_code": None},
                },
                run_id="final-run-3",
                artifact_root=root,
                debug_log=str((root / "logs" / "final-run-3.jsonl").resolve()),
            )

            status_row = _read_status_row(excel_path)

        self.assertTrue(updated)
        self.assertEqual(status_row["reason_code"], "ok")

    def test_completed_final_artifact_path_without_flag_still_syncs_done(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            excel_path = _write_excel_fixture(root / "topic.xlsx", status="Voice OK")
            config = RuntimeConfig(result_router_file=root / "evidence" / "result.json")
            final_video = root / "final_video.mp4"
            final_video.write_bytes(b"mp4")

            updated = sync_final_video_result(
                config=config,
                excel_path=excel_path,
                sheet_name="Sheet1",
                row_index=0,
                worker_result={
                    "completion": {
                        "state": "completed",
                        "final_output": False,
                        "final_artifact": "final_video.mp4",
                        "final_artifact_path": str(final_video.resolve()),
                    },
                    "details": {"reason_code": "ok"},
                },
                run_id="final-run-4",
                artifact_root=root,
                debug_log=str((root / "logs" / "final-run-4.jsonl").resolve()),
            )

            status_row = _read_status_row(excel_path)

        self.assertTrue(updated)
        self.assertEqual(status_row["status"], "Done")

    def test_render_spec_is_merged_only_by_manager(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            render_folder, voice_json, canonical_render_spec = _write_render_fixture(
                root
            )
            job = JobContract(
                job_id="render-job-1",
                workload="render",
                payload={
                    "render_spec_path": str(canonical_render_spec.resolve()),
                    "render_folder_path": str(render_folder.resolve()),
                    "voice_json_path": str(voice_json.resolve()),
                },
            )
            result = run_render_job(job, artifact_root)

            workspace_spec = (
                artifact_root / "render" / "render-job-1" / "render_spec.json"
            )
            canonical_payload = canonical_render_spec.read_text(encoding="utf-8")
            workspace_spec_exists = workspace_spec.exists()

        self.assertEqual(result["status"], "failed")
        self.assertIn('"locked": true', canonical_payload)
        self.assertTrue(workspace_spec_exists)

    def test_final_stage_workers_remain_resident_while_processing_multiple_jobs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                worker_registry_file=root / "health" / "worker_registry.json",
                artifact_root=root / "artifacts",
            )
            render_folder, voice_json, _ = _write_render_fixture(root)
            render_payload = {
                "render_folder_path": str(render_folder.resolve()),
                "voice_json_path": str(voice_json.resolve()),
            }
            render_job_1 = JobContract(
                job_id="render-job-1", workload="render", payload=dict(render_payload)
            )
            render_job_2 = JobContract(
                job_id="render-job-2", workload="render", payload=dict(render_payload)
            )
            result_1 = _run_worker(
                render_job_1,
                config.artifact_root,
                registry_file=config.worker_registry_file,
            )
            result_2 = _run_worker(
                render_job_2,
                config.artifact_root,
                registry_file=config.worker_registry_file,
            )
            registry_payload = json.loads(
                config.worker_registry_file.read_text(encoding="utf-8")
            )

        self.assertEqual(result_1["status"], "failed")
        self.assertEqual(result_2["status"], "failed")
        self.assertEqual(registry_payload["render"]["state"], "idle")


if __name__ == "__main__":
    _ = unittest.main()

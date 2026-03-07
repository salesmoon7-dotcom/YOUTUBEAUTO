from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Literal, cast
from unittest.mock import patch

from runtime_v2.config import RuntimeConfig, WorkloadName
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.control_plane import _run_worker
from runtime_v2.stage2.canva_worker import run_canva_job
from runtime_v2.stage2.geminigen_worker import run_geminigen_job
from runtime_v2.stage2.genspark_worker import run_genspark_job
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
            "thumb_data": {"bg_prompt": "scene one", "line1": "Legacy", "line2": "Thumb"},
        },
    )


class RuntimeV2Stage2WorkerTests(unittest.TestCase):
    def _write_genspark_legacy_result(self, root: Path, *, output_name: str = "genspark.png") -> Path:
        output_path = root / "legacy_outputs" / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _ = output_path.write_bytes(b"png")
        return output_path

    def test_stage2_workers_require_legacy_result_outputs_before_success(self) -> None:
        cases = [
            ("runtime_v2.stage2.genspark_worker", run_genspark_job, _stage2_job("genspark"), "genspark"),
            ("runtime_v2.stage2.seaart_worker", run_seaart_job, _stage2_job("seaart"), "seaart"),
            ("runtime_v2.stage2.geminigen_worker", run_geminigen_job, _stage2_job("geminigen"), "geminigen"),
            ("runtime_v2.stage2.canva_worker", run_canva_job, _stage2_job("canva"), "canva"),
        ]
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            for module_name, runner, job, workload in cases:
                workspace = artifact_root / workload / job.job_id
                workspace.mkdir(parents=True, exist_ok=True)
                result_json = workspace / "legacy_result.json"
                _ = result_json.write_text(
                    json.dumps({"exit_code": 0, "summary": {"processed": 1}}, ensure_ascii=True),
                    encoding="utf-8",
                )
                with patch(f"{module_name}.run_external_process") as run_external_process:
                    run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                    result = runner(job, artifact_root)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["error_code"], "missing_legacy_outputs")

    def test_stage2_workers_fail_closed_when_legacy_result_json_is_invalid(self) -> None:
        cases = [
            ("runtime_v2.stage2.genspark_worker", run_genspark_job, _stage2_job("genspark"), "genspark"),
            ("runtime_v2.stage2.seaart_worker", run_seaart_job, _stage2_job("seaart"), "seaart"),
            ("runtime_v2.stage2.geminigen_worker", run_geminigen_job, _stage2_job("geminigen"), "geminigen"),
            ("runtime_v2.stage2.canva_worker", run_canva_job, _stage2_job("canva"), "canva"),
        ]
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            for module_name, runner, job, workload in cases:
                workspace = artifact_root / workload / job.job_id
                workspace.mkdir(parents=True, exist_ok=True)
                result_json = workspace / "legacy_result.json"
                _ = result_json.write_text("{not-json", encoding="utf-8")
                with patch(f"{module_name}.run_external_process") as run_external_process:
                    run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                    result = runner(job, artifact_root)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["error_code"], "invalid_legacy_result_json")

    def test_stage2_workers_call_legacy_executor_and_stage_output_from_result_json(self) -> None:
        cases = [
            ("runtime_v2.stage2.genspark_worker", run_genspark_job, _stage2_job("genspark"), "genspark", "legacy.png"),
            ("runtime_v2.stage2.seaart_worker", run_seaart_job, _stage2_job("seaart"), "seaart", "legacy.png"),
            ("runtime_v2.stage2.geminigen_worker", run_geminigen_job, _stage2_job("geminigen"), "geminigen", "legacy.mp4"),
            ("runtime_v2.stage2.canva_worker", run_canva_job, _stage2_job("canva"), "canva", "legacy-thumb.png"),
        ]
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_root = root / "legacy_outputs"
            source_root.mkdir(parents=True, exist_ok=True)
            for module_name, runner, job, workload, output_name in cases:
                shared_output = root / "shared_render_inputs" / output_name
                shared_output.parent.mkdir(parents=True, exist_ok=True)
                job.payload["service_artifact_path"] = str(shared_output.resolve())
                output_path = source_root / f"{workload}-{output_name}"
                _ = output_path.write_bytes(b"artifact")
                workspace = artifact_root / workload / job.job_id
                workspace.mkdir(parents=True, exist_ok=True)
                result_json = workspace / "legacy_result.json"
                payload: dict[str, object] = {
                    "exit_code": 0,
                    "summary": {"processed": 1, "successful": 1, "failed": 0},
                    "outputs": [str(output_path.resolve())],
                }
                if workload == "canva":
                    payload["thumbnail_path"] = str(output_path.resolve())
                _ = result_json.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
                with patch(f"{module_name}.run_external_process") as run_external_process:
                    run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                    result = runner(job, artifact_root)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["stage"], workload)
                self.assertTrue(shared_output.exists())
                run_external_process.assert_called_once()

    def test_stage2_worker_fails_closed_when_legacy_executor_result_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"

            with patch("runtime_v2.stage2.genspark_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                result = run_genspark_job(_stage2_job(), root / "artifacts", registry_file=registry_file)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "legacy_executor_failed")

    def test_stage2_worker_uses_json_input_only_and_returns_runner_result(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"
            output_path = self._write_genspark_legacy_result(root)
            job = _stage2_job()
            workspace = root / "artifacts" / "genspark" / job.job_id
            workspace.mkdir(parents=True, exist_ok=True)
            _ = (workspace / "legacy_result.json").write_text(
                json.dumps({"exit_code": 0, "summary": {"processed": 1}, "outputs": [str(output_path.resolve())]}, ensure_ascii=True),
                encoding="utf-8",
            )

            with patch("runtime_v2.stage2.genspark_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                result = run_genspark_job(job, root / "artifacts", registry_file=registry_file)
            
            request_payload = json.loads((root / "artifacts" / "genspark" / "genspark-job-1" / "request.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stage"], "genspark")
        self.assertEqual(request_payload["payload"]["row_ref"], "Sheet1!row1")
        self.assertNotIn("excel_path", json.dumps(request_payload, ensure_ascii=True))

    def test_stage2_worker_never_updates_excel_directly(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            registry_file = root / "health" / "worker_registry.json"
            job = _stage2_job()
            job.payload["excel_path"] = "D:/SHOULD/NOT/BE/USED.xlsx"
            output_path = self._write_genspark_legacy_result(root, output_name="safe.png")
            workspace = root / "artifacts" / "genspark" / job.job_id
            workspace.mkdir(parents=True, exist_ok=True)
            _ = (workspace / "legacy_result.json").write_text(
                json.dumps({"exit_code": 0, "summary": {"processed": 1}, "outputs": [str(output_path.resolve())]}, ensure_ascii=True),
                encoding="utf-8",
            )

            with patch("runtime_v2.stage2.genspark_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                result = run_genspark_job(job, root / "artifacts", registry_file=registry_file)

        self.assertEqual(result["status"], "ok")
        self.assertFalse((root / "artifacts" / "genspark" / "genspark-job-1" / "D" ).exists())

    def test_stage2_success_routes_to_next_contract_or_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = self._write_genspark_legacy_result(root, output_name="route.png")
            job = _stage2_job()
            workspace = root / "artifacts" / "genspark" / job.job_id
            workspace.mkdir(parents=True, exist_ok=True)
            _ = (workspace / "legacy_result.json").write_text(
                json.dumps({"exit_code": 0, "summary": {"processed": 1}, "outputs": [str(output_path.resolve())]}, ensure_ascii=True),
                encoding="utf-8",
            )
            with patch("runtime_v2.stage2.genspark_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                result = run_genspark_job(job, root / "artifacts")

        completion = cast(dict[str, object], result["completion"])
        self.assertEqual(completion["state"], "routed")
        self.assertFalse(bool(completion["final_output"]))

    def test_stage2_jobs_dispatch_to_resident_workers(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(worker_registry_file=root / "health" / "worker_registry.json", artifact_root=root / "artifacts")
            output_path = self._write_genspark_legacy_result(root, output_name="dispatch.png")
            job = _stage2_job()
            workspace = root / "artifacts" / "genspark" / job.job_id
            workspace.mkdir(parents=True, exist_ok=True)
            _ = (workspace / "legacy_result.json").write_text(
                json.dumps({"exit_code": 0, "summary": {"processed": 1}, "outputs": [str(output_path.resolve())]}, ensure_ascii=True),
                encoding="utf-8",
            )

            with patch("runtime_v2.stage2.genspark_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False}
                _ = _run_worker(job, config.artifact_root, registry_file=config.worker_registry_file)

            registry_payload = json.loads(config.worker_registry_file.read_text(encoding="utf-8"))

        self.assertIn("genspark", registry_payload)
        self.assertEqual(registry_payload["genspark"]["state"], "idle")

    def test_resident_worker_progress_stall_is_reported_to_supervisor(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(worker_registry_file=root / "health" / "worker_registry.json", progress_stall_timeout_sec=1)
            _ = update_worker_state(config.worker_registry_file, workload="genspark", state="busy", run_id="stage2-run-1", progress_ts=0.0)

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

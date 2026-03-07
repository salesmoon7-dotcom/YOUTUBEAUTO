from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.contracts.job_contract import EXPLICIT_CONTRACT_NAME, JobContract
from runtime_v2.workers.kenburns_worker import run_kenburns_job
from runtime_v2.workers.qwen3_worker import run_qwen3_job
from runtime_v2.workers.rvc_worker import run_rvc_job


class RuntimeV2GpuWorkerTests(unittest.TestCase):
    def test_qwen3_worker_emits_rvc_next_job_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            image_path.write_bytes(b"png")
            job = JobContract(
                job_id="qwen-job",
                workload="qwen3_tts",
                payload={"script_text": "hello world", "image_path": str(image_path.resolve()), "model_name": "voice-model-a"},
            )
            workspace = artifact_root / "qwen3_tts" / job.job_id
            workspace.mkdir(parents=True, exist_ok=True)
            output_path = root / "legacy_outputs" / "#01.flac"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"flac")
            (workspace / "legacy_result.json").write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "summary": {"processed": 1, "successful": 1, "failed": 0, "audio_generated": 1},
                        "outputs": [{"type": "audio", "path": str(output_path.resolve()), "col": "#01"}],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with patch("runtime_v2.workers.qwen3_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "", "stderr": "", "timed_out": False}
                result = run_qwen3_job(job, artifact_root=artifact_root)

        next_jobs = cast(list[object], result["next_jobs"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(next_jobs), 1)
        next_job = cast(dict[object, object], next_jobs[0])
        self.assertEqual(next_job["contract"], EXPLICIT_CONTRACT_NAME)
        job_block = cast(dict[object, object], next_job["job"])
        self.assertEqual(job_block["worker"], "rvc")
        payload = cast(dict[object, object], job_block["payload"])
        self.assertEqual(payload["chain_depth"], 1)
        self.assertEqual(payload["model_name"], "voice-model-a")
        self.assertTrue(str(payload["source_path"]).endswith("#01.flac"))
        details = cast(dict[object, object], result["details"])
        self.assertEqual(details["tts_backend"], "legacy_qwen3_tts")

    def test_qwen3_worker_fails_closed_when_legacy_result_json_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            job = JobContract(job_id="qwen-job-invalid", workload="qwen3_tts", payload={"script_text": "hello world"})
            workspace = artifact_root / "qwen3_tts" / job.job_id
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "legacy_result.json").write_text("{bad-json", encoding="utf-8")

            with patch("runtime_v2.workers.qwen3_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "", "stderr": "", "timed_out": False}
                result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "invalid_legacy_result_json")

    def test_rvc_worker_requires_model_name_for_conversion_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            source_path.write_bytes(b"flac")
            job = JobContract(
                job_id="rvc-job-missing-model",
                workload="rvc",
                payload={"source_path": str(source_path.resolve())},
            )

            result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "missing_model_name")

    def test_rvc_worker_emits_final_output_or_next_job_only(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            image_path = root / "image.png"
            source_path.write_bytes(b"flac")
            image_path.write_bytes(b"png")
            job = JobContract(
                job_id="rvc-job",
                workload="rvc",
                payload={"source_path": str(source_path.resolve()), "image_path": str(image_path.resolve()), "model_name": "voice-model-a"},
            )
            workspace = artifact_root / "rvc" / job.job_id
            project_voice = workspace / "project" / "voice"
            project_voice.mkdir(parents=True, exist_ok=True)
            converted_path = project_voice / "#01_GEMINI.flac"
            converted_path.write_bytes(b"flac")
            (workspace / "legacy_result.json").write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "summary": {"processed": 1, "successful": 1, "failed": 0, "converted_files": 1, "mode": "tts"},
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with patch("runtime_v2.workers.rvc_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "", "stderr": "", "timed_out": False}
                result = run_rvc_job(job, artifact_root=artifact_root)

        next_jobs = cast(list[object], result["next_jobs"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(next_jobs), 1)
        next_job = cast(dict[object, object], next_jobs[0])
        self.assertEqual(next_job["contract"], EXPLICIT_CONTRACT_NAME)
        completion = cast(dict[object, object], result["completion"])
        details = cast(dict[object, object], result["details"])
        self.assertEqual(completion["state"], "routed")
        self.assertFalse(bool(completion["final_output"]))
        self.assertEqual(details["model_name"], "voice-model-a")
        self.assertEqual(details["processing_backend"], "legacy_rvc_tts")

    def test_rvc_worker_fails_closed_when_legacy_result_json_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            source_path.write_bytes(b"flac")
            job = JobContract(
                job_id="rvc-job-invalid-json",
                workload="rvc",
                payload={"source_path": str(source_path.resolve()), "model_name": "voice-model-a"},
            )
            workspace = artifact_root / "rvc" / job.job_id
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "legacy_result.json").write_text("{bad-json", encoding="utf-8")

            with patch("runtime_v2.workers.rvc_worker.run_external_process") as run_external_process:
                run_external_process.return_value = {"exit_code": 0, "stdout": "", "stderr": "", "timed_out": False}
                result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "invalid_legacy_result_json")

    def test_kenburns_worker_marks_final_output_true(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "image.png"
            audio_path = root / "audio.wav"
            source_path.write_bytes(b"png")
            audio_path.write_bytes(b"wav")
            job = JobContract(
                job_id="ken-job",
                workload="kenburns",
                payload={"source_path": str(source_path.resolve()), "audio_path": str(audio_path.resolve()), "duration_sec": 8},
            )

            def fake_process(command: list[str], *, cwd: Path, extra_env: dict[str, str] | None = None, timeout_sec: int = 3600) -> dict[str, object]:
                _ = extra_env
                _ = timeout_sec
                output_name = "kenburns.mp4" if any(str(part) == "1:a:0" for part in command) else "kenburns_silent.mp4"
                (cwd / output_name).write_bytes(b"mp4")
                return {"command": command, "cwd": str(cwd), "exit_code": 0, "stdout": "", "stderr": "", "timed_out": False, "timeout_sec": 3600, "duration_sec": 0.01}

            with patch("runtime_v2.workers.kenburns_worker.run_external_process", side_effect=fake_process):
                result = run_kenburns_job(job, artifact_root=artifact_root)

        completion = cast(dict[object, object], result["completion"])
        self.assertEqual(completion["state"], "succeeded")
        self.assertTrue(bool(completion["final_output"]))
        self.assertTrue(str(completion["final_artifact_path"]).endswith("kenburns.mp4"))


if __name__ == "__main__":
    _ = unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.kenburns_worker import run_kenburns_job
from runtime_v2.workers.qwen3_worker import run_qwen3_job
from runtime_v2.workers.rvc_worker import run_rvc_job


class RuntimeV2GpuWorkerTests(unittest.TestCase):
    def test_qwen3_worker_processes_one_item_via_explicit_adapter_command(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.wav"
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="qwen-job-success",
                workload="qwen3_tts",
                payload={
                    "script_text": "hello world",
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            f"p=Path(r'{str(output_path)}'); "
                            "p.parent.mkdir(parents=True, exist_ok=True); "
                            "p.write_bytes(b'wav')"
                        ),
                    ],
                },
            )

            result = run_qwen3_job(job, artifact_root=artifact_root)

            self.assertEqual(result["status"], "ok")
            self.assertTrue(output_path.exists())
            completion = cast(dict[object, object], result["completion"])
            self.assertEqual(completion["state"], "routed")
            self.assertTrue(bool(completion["final_output"]))

    def test_qwen3_worker_can_consume_voice_texts_directly(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.wav"
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="qwen-job-voice-texts",
                workload="qwen3_tts",
                payload={
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]},
                        {"col": "#02", "text": "second line", "original_voices": [2]},
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            f"p=Path(r'{str(output_path)}'); "
                            "p.parent.mkdir(parents=True, exist_ok=True); "
                            "p.write_bytes(b'wav')"
                        ),
                    ],
                },
            )

            result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[object, object], result["details"])
        self.assertEqual(details["voice_text_count"], 2)

    def test_qwen3_worker_builds_cli_adapter_when_service_artifact_path_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.wav"
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="qwen-job-auto-adapter",
                workload="qwen3_tts",
                payload={
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]}
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                },
            )
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.workers.qwen3_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                    "reused": False,
                },
            ) as run_adapter:
                result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        adapter_command = run_adapter.call_args.kwargs["adapter_command"]
        adapter_extra_env = cast(
            dict[object, object], run_adapter.call_args.kwargs["extra_env"]
        )
        self.assertIn("--qwen3-adapter-child", adapter_command)
        self.assertTrue(
            str(adapter_extra_env["PYTHONPATH"]).startswith(
                str(Path("D:/YOUTUBEAUTO").resolve())
            )
        )

    def test_qwen3_worker_keeps_explicit_adapter_command_when_present(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.wav"
            _ = image_path.write_bytes(b"png")
            explicit_command = [sys.executable, "-c", "print('explicit')"]
            job = JobContract(
                job_id="qwen-job-explicit-adapter",
                workload="qwen3_tts",
                payload={
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]}
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": explicit_command,
                },
            )
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.workers.qwen3_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                    "reused": False,
                },
            ) as run_adapter:
                result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            run_adapter.call_args.kwargs["adapter_command"], explicit_command
        )
        self.assertIsNone(run_adapter.call_args.kwargs["extra_env"])

    def test_qwen3_worker_emits_rvc_next_job_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.wav"
            _ = image_path.write_bytes(b"png")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"stale")
            job = JobContract(
                job_id="qwen-job",
                workload="qwen3_tts",
                payload={
                    "script_text": "hello world",
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [sys.executable, "-c", "pass"],
                },
            )
            result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        next_jobs = cast(list[object], result.get("next_jobs", []))
        self.assertEqual(len(next_jobs), 1)
        next_job_contract = cast(dict[str, object], next_jobs[0])
        next_job = cast(dict[str, object], next_job_contract["job"])
        next_payload = cast(dict[str, object], next_job["payload"])
        self.assertEqual(str(next_job["worker"]), "rvc")
        self.assertEqual(str(next_job["job_id"]), "rvc-qwen-job")
        self.assertEqual(str(next_payload["source_path"]), str(output_path.resolve()))
        self.assertEqual(str(next_payload["model_name"]), "voice-model-a")
        self.assertTrue(
            str(next_payload["service_artifact_path"]).endswith("speech_rvc.wav")
        )
        completion = cast(dict[object, object], result["completion"])
        self.assertEqual(completion["state"], "routed")
        self.assertTrue(bool(completion["final_output"]))
        details = cast(dict[object, object], result["details"])
        self.assertEqual(details["model_name"], "voice-model-a")

    def test_qwen3_worker_native_only_does_not_emit_next_jobs(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="qwen-job",
                workload="qwen3_tts",
                payload={
                    "script_text": "hello world",
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                },
            )
            result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "native_qwen3_tts_not_implemented")
        self.assertFalse(result.get("next_jobs", []))
        details = cast(dict[object, object], result["details"])
        self.assertEqual(details["execution_mode"], "native_only")
        self.assertEqual(details["model_name"], "voice-model-a")

    def test_qwen3_worker_requires_adapter_command_to_create_fresh_output(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.wav"
            _ = image_path.write_bytes(b"png")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"stale")
            job = JobContract(
                job_id="qwen-job-stale-output",
                workload="qwen3_tts",
                payload={
                    "script_text": "hello world",
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [sys.executable, "-c", "pass"],
                },
            )

            result = run_qwen3_job(job, artifact_root=artifact_root)

        completion = cast(dict[object, object], result["completion"])
        details = cast(dict[object, object], result["details"])
        self.assertEqual(result["status"], "ok")
        next_jobs = cast(list[object], result.get("next_jobs", []))
        self.assertEqual(len(next_jobs), 1)
        self.assertEqual(completion["state"], "routed")
        self.assertTrue(bool(completion["final_output"]))
        self.assertTrue(bool(completion["reused"]))
        self.assertTrue(bool(details["reused"]))

    def test_qwen3_worker_surfaces_standard_output_not_created_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.wav"
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="qwen-job-missing-output",
                workload="qwen3_tts",
                payload={
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]}
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [sys.executable, "-c", "pass"],
                },
            )

            result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "OUTPUT_NOT_CREATED")

    def test_rvc_worker_processes_one_item_via_explicit_adapter_command(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            image_path = root / "image.png"
            output_path = artifact_root / "converted.wav"
            _ = source_path.write_bytes(b"flac")
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="rvc-job-success",
                workload="rvc",
                payload={
                    "source_path": str(source_path.resolve()),
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            f"p=Path(r'{str(output_path)}'); "
                            "p.parent.mkdir(parents=True, exist_ok=True); "
                            "p.write_bytes(b'wav')"
                        ),
                    ],
                },
            )

            result = run_rvc_job(job, artifact_root=artifact_root)

            self.assertEqual(result["status"], "ok")
            self.assertTrue(output_path.exists())
            completion = cast(dict[object, object], result["completion"])
            self.assertEqual(completion["state"], "succeeded")
            self.assertTrue(bool(completion["final_output"]))

    def test_rvc_worker_accepts_audio_path_in_gemi_video_source_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            audio_path = root / "gemi-audio.wav"
            output_path = artifact_root / "converted.wav"
            _ = audio_path.write_bytes(b"wav")
            job = JobContract(
                job_id="rvc-job-gemi-audio",
                workload="rvc",
                payload={
                    "audio_path": str(audio_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            f"p=Path(r'{str(output_path)}'); "
                            "p.parent.mkdir(parents=True, exist_ok=True); "
                            "p.write_bytes(b'wav')"
                        ),
                    ],
                },
            )

            result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[object, object], result["details"])
        self.assertEqual(str(details["source_mode"]), "gemi-video-source")
        self.assertEqual(str(details["audio_path"]), str(audio_path.resolve()))

    def test_rvc_worker_requires_model_name_for_conversion_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            _ = source_path.write_bytes(b"flac")
            job = JobContract(
                job_id="rvc-job-missing-model",
                workload="rvc",
                payload={"source_path": str(source_path.resolve())},
            )

            result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "missing_model_name")

    def test_rvc_worker_requires_source_or_audio_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            job = JobContract(
                job_id="rvc-job-missing-input",
                workload="rvc",
                payload={"model_name": "voice-model-a"},
            )

            result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "missing_source_path")

    def test_rvc_worker_emits_final_output_or_next_job_only(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            image_path = root / "image.png"
            _ = source_path.write_bytes(b"flac")
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="rvc-job",
                workload="rvc",
                payload={
                    "source_path": str(source_path.resolve()),
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                },
            )
            result = run_rvc_job(job, artifact_root=artifact_root)

        next_jobs = cast(list[object], result.get("next_jobs", []))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "native_rvc_not_implemented")
        self.assertEqual(len(next_jobs), 0)
        completion = cast(dict[object, object], result["completion"])
        details = cast(dict[object, object], result["details"])
        self.assertEqual(completion["state"], "failed")
        self.assertFalse(bool(completion["final_output"]))
        self.assertEqual(details["model_name"], "voice-model-a")
        self.assertEqual(details["source_mode"], "tts-source")

    def test_rvc_worker_builds_cli_adapter_when_service_artifact_path_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            image_path = root / "image.png"
            output_path = root / "converted.wav"
            _ = source_path.write_bytes(b"flac")
            _ = image_path.write_bytes(b"png")
            job = JobContract(
                job_id="rvc-job-auto-adapter",
                workload="rvc",
                payload={
                    "source_path": str(source_path.resolve()),
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                },
            )
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.workers.rvc_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                    "reused": False,
                },
            ) as run_adapter:
                result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        adapter_command = run_adapter.call_args.kwargs["adapter_command"]
        adapter_extra_env = cast(
            dict[object, object], run_adapter.call_args.kwargs["extra_env"]
        )
        self.assertIn("--rvc-adapter-child", adapter_command)
        self.assertTrue(
            str(adapter_extra_env["PYTHONPATH"]).startswith(
                str(Path("D:/YOUTUBEAUTO").resolve())
            )
        )

    def test_rvc_worker_keeps_explicit_adapter_command_when_present(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            image_path = root / "image.png"
            output_path = root / "converted.wav"
            _ = source_path.write_bytes(b"flac")
            _ = image_path.write_bytes(b"png")
            explicit_command = [sys.executable, "-c", "print('explicit')"]
            job = JobContract(
                job_id="rvc-job-explicit-adapter",
                workload="rvc",
                payload={
                    "source_path": str(source_path.resolve()),
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": explicit_command,
                },
            )
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")

            with patch(
                "runtime_v2.workers.rvc_worker.run_verified_adapter_command",
                return_value={
                    "ok": True,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "output_path": output_path,
                    "reused": False,
                },
            ) as run_adapter:
                result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            run_adapter.call_args.kwargs["adapter_command"], explicit_command
        )
        self.assertIsNone(run_adapter.call_args.kwargs["extra_env"])

    def test_kenburns_worker_marks_final_output_true(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "image.png"
            audio_path = root / "audio.wav"
            _ = source_path.write_bytes(b"png")
            _ = audio_path.write_bytes(b"wav")
            job = JobContract(
                job_id="ken-job",
                workload="kenburns",
                payload={
                    "source_path": str(source_path.resolve()),
                    "audio_path": str(audio_path.resolve()),
                    "duration_sec": 8,
                },
            )

            def fake_process(
                command: list[str],
                *,
                cwd: Path,
                extra_env: dict[str, str] | None = None,
                timeout_sec: int = 3600,
            ) -> dict[str, object]:
                _ = extra_env
                _ = timeout_sec
                output_name = (
                    "kenburns.mp4"
                    if any(str(part) == "1:a:0" for part in command)
                    else "kenburns_silent.mp4"
                )
                _ = (cwd / output_name).write_bytes(b"mp4")
                return {
                    "command": command,
                    "cwd": str(cwd),
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                    "timed_out": False,
                    "timeout_sec": 3600,
                    "duration_sec": 0.01,
                }

            with patch(
                "runtime_v2.workers.kenburns_worker.run_external_process",
                side_effect=fake_process,
            ):
                result = run_kenburns_job(job, artifact_root=artifact_root)

        completion = cast(dict[object, object], result["completion"])
        self.assertEqual(completion["state"], "succeeded")
        self.assertTrue(bool(completion["final_output"]))
        self.assertTrue(str(completion["final_artifact_path"]).endswith("kenburns.mp4"))

    def test_kenburns_worker_processes_scene_bundle_map_and_writes_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_a = root / "scene-a.png"
            image_b = root / "scene-b.png"
            audio_b = root / "scene-b.wav"
            _ = image_a.write_bytes(b"png")
            _ = image_b.write_bytes(b"png")
            _ = audio_b.write_bytes(b"wav")
            bundle_map_path = root / "scene_bundle_map.json"
            bundle_map_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_key": "scene_a",
                                "source_path": str(image_a.resolve()),
                                "duration_sec": 4,
                            },
                            {
                                "scene_key": "scene_b",
                                "source_path": str(image_b.resolve()),
                                "audio_path": str(audio_b.resolve()),
                                "duration_sec": 5,
                            },
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            job = JobContract(
                job_id="ken-bundle-job",
                workload="kenburns",
                payload={"scene_bundle_map_path": str(bundle_map_path.resolve())},
            )

            def fake_process(
                command: list[str],
                *,
                cwd: Path,
                extra_env: dict[str, str] | None = None,
                timeout_sec: int = 3600,
            ) -> dict[str, object]:
                _ = extra_env
                _ = timeout_sec
                output_path = Path(str(command[-1]))
                _ = output_path.write_bytes(b"mp4")
                return {
                    "command": command,
                    "cwd": str(cwd),
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                    "timed_out": False,
                    "timeout_sec": 3600,
                    "duration_sec": 0.01,
                }

            with patch(
                "runtime_v2.workers.kenburns_worker.run_external_process",
                side_effect=fake_process,
            ):
                result = run_kenburns_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[object, object], result["details"])
        completion = cast(dict[object, object], result["completion"])
        self.assertEqual(str(details["bundle_mode"]), "scene_bundle_map")
        self.assertEqual(int(cast(int, details["scene_count"])), 2)
        self.assertTrue(
            str(completion["final_artifact_path"]).endswith(
                "scene_bundle_manifest.json"
            )
        )

    def test_kenburns_worker_fails_closed_on_invalid_scene_bundle_map(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            bundle_map_path = root / "scene_bundle_map.json"
            bundle_map_path.write_text("{not-json", encoding="utf-8")
            job = JobContract(
                job_id="ken-bundle-invalid",
                workload="kenburns",
                payload={"scene_bundle_map_path": str(bundle_map_path.resolve())},
            )

            result = run_kenburns_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "invalid_scene_bundle_map")


if __name__ == "__main__":
    _ = unittest.main()

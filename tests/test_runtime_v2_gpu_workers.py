from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.geminigen_worker import run_geminigen_job
from runtime_v2.workers.kenburns_worker import run_kenburns_job
from runtime_v2.workers.qwen3_worker import run_qwen3_job
from runtime_v2.workers.rvc_worker import run_rvc_job


class RuntimeV2GpuWorkerTests(unittest.TestCase):
    def test_qwen3_worker_processes_one_item_via_explicit_adapter_command(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
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
            output_path = artifact_root / "speech.flac"
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
            output_path = artifact_root / "speech.flac"
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
        self.assertNotIn("--workspace-root", adapter_command)
        self.assertTrue(
            str(adapter_extra_env["PYTHONPATH"]).startswith(
                str(Path("D:/YOUTUBEAUTO").resolve())
            )
        )

    def test_qwen3_worker_passes_channel_reference_audio_to_adapter(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
            ref_audio = root / "ref.mp3"
            _ = image_path.write_bytes(b"png")
            _ = ref_audio.write_bytes(b"mp3")
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")
            job = JobContract(
                job_id="qwen-job-ref-audio",
                workload="qwen3_tts",
                payload={
                    "channel": 4,
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]}
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                },
            )

            with (
                patch(
                    "runtime_v2.workers.qwen3_worker.LEGACY_QWEN3_CONFIG",
                    root / "qwen3_tts_config.json",
                ),
                patch(
                    "runtime_v2.workers.qwen3_worker.run_verified_adapter_command",
                    return_value={
                        "ok": True,
                        "stdout_path": stdout_path,
                        "stderr_path": stderr_path,
                        "output_path": output_path,
                        "reused": False,
                    },
                ) as run_adapter,
            ):
                _ = (root / "qwen3_tts_config.json").write_text(
                    json.dumps(
                        {
                            "reference_audio_default": "",
                            "reference_audio_by_channel": {
                                "4": str(ref_audio.resolve())
                            },
                            "output_format": "mp3",
                        },
                        ensure_ascii=True,
                    ),
                    encoding="utf-8",
                )
                result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        adapter_command = run_adapter.call_args.kwargs["adapter_command"]
        self.assertIn("--ref-audio", adapter_command)
        self.assertIn(str(ref_audio.resolve()), adapter_command)
        details = cast(dict[object, object], result["details"])
        self.assertEqual(str(details["ref_audio_used"]), str(ref_audio.resolve()))
        self.assertEqual(str(details["output_format"]), "flac")

    def test_qwen3_worker_records_legacy_model_and_generation_defaults(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
            ref_audio = root / "ref.mp3"
            _ = image_path.write_bytes(b"png")
            _ = ref_audio.write_bytes(b"mp3")
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")
            job = JobContract(
                job_id="qwen-job-runtime-details",
                workload="qwen3_tts",
                payload={
                    "channel": 4,
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]}
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                },
            )

            with (
                patch(
                    "runtime_v2.workers.qwen3_worker.LEGACY_QWEN3_CONFIG",
                    root / "qwen3_tts_config.json",
                ),
                patch(
                    "runtime_v2.workers.qwen3_worker.run_verified_adapter_command",
                    return_value={
                        "ok": True,
                        "stdout_path": stdout_path,
                        "stderr_path": stderr_path,
                        "output_path": output_path,
                        "reused": False,
                    },
                ),
            ):
                _ = (root / "qwen3_tts_config.json").write_text(
                    json.dumps(
                        {
                            "python_path": "D:/qwen3_tts_env/Scripts/python.exe",
                            "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                            "device": "cuda:0",
                            "dtype": "float32",
                            "attn_implementation": "eager",
                            "reference_audio_default": str(ref_audio.resolve()),
                            "reference_audio_by_channel": {
                                "4": str(ref_audio.resolve())
                            },
                            "output_format": "mp3",
                            "generation": {
                                "x_vector_only_mode": True,
                                "language": "Auto",
                            },
                        },
                        ensure_ascii=True,
                    ),
                    encoding="utf-8",
                )
                result = run_qwen3_job(job, artifact_root=artifact_root)

        details = cast(dict[object, object], result["details"])
        generation = cast(dict[object, object], details["generation"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(details["model_id"], "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
        self.assertEqual(details["device"], "cuda:0")
        self.assertEqual(details["dtype"], "float32")
        self.assertEqual(details["attn_implementation"], "eager")
        self.assertTrue(bool(generation["x_vector_only_mode"]))
        self.assertEqual(generation["language"], "Auto")

    def test_qwen3_worker_emits_rvc_next_job_with_flac_extension_when_legacy_export_format_is_flac(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
            ref_audio = root / "ref.mp3"
            _ = image_path.write_bytes(b"png")
            _ = ref_audio.write_bytes(b"mp3")
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")
            job = JobContract(
                job_id="qwen-job-rvc-flac",
                workload="qwen3_tts",
                payload={
                    "channel": 4,
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]}
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                },
            )

            with (
                patch(
                    "runtime_v2.workers.qwen3_worker.LEGACY_QWEN3_CONFIG",
                    root / "qwen3_tts_config.json",
                ),
                patch(
                    "runtime_v2.workers.qwen3_worker.run_verified_adapter_command",
                    return_value={
                        "ok": True,
                        "stdout_path": stdout_path,
                        "stderr_path": stderr_path,
                        "output_path": output_path,
                        "reused": False,
                    },
                ),
            ):
                _ = (root / "qwen3_tts_config.json").write_text(
                    json.dumps(
                        {
                            "reference_audio_default": str(ref_audio.resolve()),
                            "reference_audio_by_channel": {
                                "4": str(ref_audio.resolve())
                            },
                            "output_format": "FLAC",
                        },
                        ensure_ascii=True,
                    ),
                    encoding="utf-8",
                )
                result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        next_jobs = cast(list[object], result.get("next_jobs", []))
        self.assertEqual(len(next_jobs), 1)
        next_job_contract = cast(dict[str, object], next_jobs[0])
        next_job = cast(dict[str, object], next_job_contract["job"])
        next_payload = cast(dict[str, object], next_job["payload"])
        self.assertTrue(
            str(next_payload["service_artifact_path"]).endswith("speech_rvc.flac")
        )
        self.assertEqual(str(next_payload["export_format"]), "FLAC")

    def test_qwen3_worker_fails_when_reference_audio_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            _ = image_path.write_bytes(b"png")
            missing_ref = root / "missing.mp3"
            job = JobContract(
                job_id="qwen-job-missing-ref-audio",
                workload="qwen3_tts",
                payload={
                    "channel": 4,
                    "voice_texts": [
                        {"col": "#01", "text": "hello world", "original_voices": [1]}
                    ],
                    "image_path": str(image_path.resolve()),
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(
                        (artifact_root / "speech.flac").resolve()
                    ),
                },
            )

            with patch(
                "runtime_v2.workers.qwen3_worker.LEGACY_QWEN3_CONFIG",
                root / "qwen3_tts_config.json",
            ):
                _ = (root / "qwen3_tts_config.json").write_text(
                    json.dumps(
                        {
                            "reference_audio_default": str(missing_ref.resolve()),
                            "reference_audio_by_channel": {
                                "4": str(missing_ref.resolve())
                            },
                            "output_format": "mp3",
                        },
                        ensure_ascii=True,
                    ),
                    encoding="utf-8",
                )
                result = run_qwen3_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "missing_reference_audio")

    def test_qwen3_worker_keeps_explicit_adapter_command_when_present(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
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

    def test_qwen3_worker_does_not_emit_rvc_next_job_by_default(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
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
        self.assertEqual(len(next_jobs), 0)
        completion = cast(dict[object, object], result["completion"])
        self.assertEqual(completion["state"], "succeeded")
        self.assertTrue(bool(completion["final_output"]))
        details = cast(dict[object, object], result["details"])
        self.assertEqual(details["model_name"], "voice-model-a")

    def test_qwen3_worker_emits_rvc_next_job_contract_when_opted_in(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
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
                    "emit_rvc_next_job": True,
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
            str(next_payload["service_artifact_path"]).endswith("speech_rvc.flac")
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
            output_path = artifact_root / "speech.flac"
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
        self.assertEqual(len(next_jobs), 0)
        self.assertEqual(completion["state"], "succeeded")
        self.assertTrue(bool(completion["final_output"]))
        self.assertTrue(bool(completion["reused"]))
        self.assertTrue(bool(details["reused"]))

    def test_qwen3_worker_surfaces_standard_output_not_created_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_path = root / "image.png"
            output_path = artifact_root / "speech.flac"
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

    def test_rvc_worker_extracts_audio_from_video_source_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            video_path = root / "gemi-video.mp4"
            output_path = artifact_root / "converted.wav"
            _ = video_path.write_bytes(b"mp4")
            job = JobContract(
                job_id="rvc-job-gemi-video",
                workload="rvc",
                payload={
                    "audio_path": str(video_path.resolve()),
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

            def fake_extract(
                command: list[str],
                *,
                cwd: Path,
                extra_env: dict[str, str] | None = None,
                timeout_sec: int = 3600,
            ) -> dict[str, object]:
                _ = extra_env
                _ = timeout_sec
                extracted = cwd / "project" / "voice" / "#01_extracted.wav"
                extracted.parent.mkdir(parents=True, exist_ok=True)
                extracted.write_bytes(b"wav")
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
                "runtime_v2.workers.rvc_worker.run_external_process",
                side_effect=fake_extract,
            ):
                result = run_rvc_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "ok")
        details = cast(dict[object, object], result["details"])
        self.assertEqual(str(details["source_mode"]), "gemi-video-source")

    def test_rvc_worker_requires_model_name_for_conversion_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            output_path = artifact_root / "converted.wav"
            _ = source_path.write_bytes(b"flac")
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")
            job = JobContract(
                job_id="rvc-job-missing-model",
                workload="rvc",
                payload={
                    "source_path": str(source_path.resolve()),
                    "service_artifact_path": str(output_path.resolve()),
                },
            )

            with (
                patch(
                    "runtime_v2.workers.rvc_worker.LEGACY_RVC_CONFIG",
                    root / "rvc_config.json",
                ),
                patch(
                    "runtime_v2.workers.rvc_worker.run_verified_adapter_command",
                    return_value={
                        "ok": True,
                        "stdout_path": stdout_path,
                        "stderr_path": stderr_path,
                        "output_path": output_path,
                        "reused": False,
                    },
                ),
            ):
                _ = (root / "rvc_config.json").write_text(
                    json.dumps({"active_model": "jp_narrator_v1"}, ensure_ascii=True),
                    encoding="utf-8",
                )
                result = run_rvc_job(job, artifact_root=artifact_root)
                request_payload = json.loads(
                    (
                        artifact_root
                        / "rvc"
                        / "rvc-job-missing-model"
                        / "rvc_request.json"
                    ).read_text(encoding="utf-8")
                )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(request_payload["model_name"], "jp_narrator_v1")

    def test_rvc_worker_records_legacy_applio_runtime_in_request_and_details(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            source_path = root / "source.flac"
            output_path = artifact_root / "converted.wav"
            stdout_path = root / "artifacts" / "stdout.log"
            stderr_path = root / "artifacts" / "stderr.log"
            _ = source_path.write_bytes(b"flac")
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            _ = stdout_path.write_text("", encoding="utf-8")
            _ = stderr_path.write_text("", encoding="utf-8")
            cfg = root / "rvc_config.json"
            _ = cfg.write_text(
                json.dumps(
                    {
                        "active_model": "jp_narrator_v1",
                        "applio_python": "D:/Applio/env/python.exe",
                        "applio_core": "D:/Applio/core.py",
                        "inference": {"export_format": "FLAC"},
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            job = JobContract(
                job_id="rvc-job-runtime-details",
                workload="rvc",
                payload={
                    "source_path": str(source_path.resolve()),
                    "service_artifact_path": str(output_path.resolve()),
                },
            )

            with (
                patch("runtime_v2.workers.rvc_worker.LEGACY_RVC_CONFIG", cfg),
                patch(
                    "runtime_v2.workers.rvc_worker.run_verified_adapter_command",
                    return_value={
                        "ok": True,
                        "stdout_path": stdout_path,
                        "stderr_path": stderr_path,
                        "output_path": output_path,
                        "reused": False,
                    },
                ),
            ):
                result = run_rvc_job(job, artifact_root=artifact_root)
                request_payload = json.loads(
                    (
                        artifact_root
                        / "rvc"
                        / "rvc-job-runtime-details"
                        / "rvc_request.json"
                    ).read_text(encoding="utf-8")
                )

        details = cast(dict[object, object], result["details"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(request_payload["applio_python"], "D:/Applio/env/python.exe")
        self.assertEqual(request_payload["applio_core"], "D:/Applio/core.py")
        self.assertEqual(request_payload["export_format"], "FLAC")
        self.assertEqual(details["applio_python"], "D:/Applio/env/python.exe")
        self.assertEqual(details["applio_core"], "D:/Applio/core.py")
        self.assertEqual(details["export_format"], "FLAC")

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
                if output_name == "kenburns_silent.mp4":
                    filter_arg = str(command[command.index("-vf") + 1])
                    self.assertIn("zoompan=", filter_arg)
                    self.assertIn("1.1300", filter_arg)
                    self.assertIn("0.4000", filter_arg)
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
                payload={
                    "scene_bundle_map_path": str(bundle_map_path.resolve()),
                    "service_artifact_path": str(
                        (artifact_root / "exports" / "kenburns-manifest.json").resolve()
                    ),
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
                output_path = Path(str(command[-1]))
                if output_path.name.endswith("_silent.mp4"):
                    filter_arg = str(command[command.index("-vf") + 1])
                    if output_path.name == "scene_a_silent.mp4":
                        self.assertIn("zoompan=", filter_arg)
                        self.assertIn("0.4000", filter_arg)
                    if output_path.name == "scene_b_silent.mp4":
                        self.assertIn("1.1300", filter_arg)
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
            str(details["bundle_manifest_path"]).endswith("kenburns-manifest.json")
        )
        self.assertTrue(
            str(completion["final_artifact_path"]).endswith("kenburns-manifest.json")
        )

    def test_kenburns_worker_cycles_default_motion_profiles_for_bundle_entries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_a = root / "scene-a.png"
            image_b = root / "scene-b.png"
            _ = image_a.write_bytes(b"png")
            _ = image_b.write_bytes(b"png")
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
                                "duration_sec": 5,
                            },
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            job = JobContract(
                job_id="ken-bundle-default-motion",
                workload="kenburns",
                payload={"scene_bundle_map_path": str(bundle_map_path.resolve())},
            )
            filter_args: dict[str, str] = {}

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
                if output_path.name.endswith("_silent.mp4"):
                    filter_args[output_path.name] = str(
                        command[command.index("-vf") + 1]
                    )
                output_path.write_bytes(b"mp4")
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
        self.assertIn("scene_a_silent.mp4", filter_args)
        self.assertIn("scene_b_silent.mp4", filter_args)
        self.assertIn("1.1300", filter_args["scene_a_silent.mp4"])
        self.assertIn("z='1.1'", filter_args["scene_b_silent.mp4"])
        self.assertNotEqual(
            filter_args["scene_a_silent.mp4"], filter_args["scene_b_silent.mp4"]
        )

    def test_kenburns_bundle_manifest_records_legacy_effect_sequence(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            scenes = []
            for idx in range(8):
                image = root / f"scene-{idx}.png"
                _ = image.write_bytes(b"png")
                scenes.append(
                    {
                        "scene_key": f"scene_{idx + 1:02d}",
                        "source_path": str(image.resolve()),
                        "duration_sec": 4,
                    }
                )
            bundle_map_path = root / "scene_bundle_map.json"
            bundle_map_path.write_text(
                json.dumps({"scenes": scenes}, ensure_ascii=True), encoding="utf-8"
            )
            job = JobContract(
                job_id="ken-effect-sequence",
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
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"mp4")
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
            manifest_path = Path(str(completion["final_artifact_path"]))
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        scenes_payload = cast(list[object], manifest_payload["scenes"])
        effect_types: list[object] = []
        for scene in scenes_payload:
            typed_scene = cast(dict[object, object], scene)
            effect_types.append(typed_scene["effect_type"])
        self.assertEqual(
            effect_types,
            [
                "zoom_in_center",
                "pan_left_to_right",
                "zoom_out_center",
                "pan_right_to_left",
                "zoom_in_top_left",
                "pan_up_to_down",
                "zoom_in_bottom_right",
                "pan_down_to_up",
            ],
        )

    def test_kenburns_static_effect_uses_static_filter_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image = root / "scene.png"
            _ = image.write_bytes(b"png")
            job = JobContract(
                job_id="ken-static",
                workload="kenburns",
                payload={
                    "source_path": str(image.resolve()),
                    "effect_type": "static",
                },
            )

            captured: list[list[str]] = []

            def fake_process(
                command: list[str],
                *,
                cwd: Path,
                extra_env: dict[str, str] | None = None,
                timeout_sec: int = 3600,
            ) -> dict[str, object]:
                _ = cwd
                _ = extra_env
                _ = timeout_sec
                captured.append(command)
                output_path = Path(str(command[-1]))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"mp4")
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
        filter_arg = captured[0][captured[0].index("-vf") + 1]
        self.assertNotIn("zoompan=", filter_arg)
        self.assertIn("pad=1920:1080", filter_arg)
        self.assertIn("fps=60", filter_arg)

    def test_kenburns_zoom_effects_keep_legacy_center_and_corner_anchors(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image = root / "scene.png"
            _ = image.write_bytes(b"png")
            filters: dict[str, str] = {}

            def run_once(effect_type: str) -> None:
                job = JobContract(
                    job_id=f"ken-{effect_type}",
                    workload="kenburns",
                    payload={
                        "source_path": str(image.resolve()),
                        "effect_type": effect_type,
                    },
                )
                captured: list[list[str]] = []

                def fake_process(
                    command: list[str],
                    *,
                    cwd: Path,
                    extra_env: dict[str, str] | None = None,
                    timeout_sec: int = 3600,
                ) -> dict[str, object]:
                    _ = cwd
                    _ = extra_env
                    _ = timeout_sec
                    captured.append(command)
                    output_path = Path(str(command[-1]))
                    output_path.write_bytes(b"mp4")
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
                filters[effect_type] = captured[0][captured[0].index("-vf") + 1]

            run_once("zoom_in_center")
            run_once("zoom_out_center")
            run_once("zoom_in_top_left")
            run_once("zoom_in_bottom_right")

        self.assertIn("x='iw/2-(iw/zoom/2)'", filters["zoom_in_center"])
        self.assertIn("y='ih/2-(ih/zoom/2)'", filters["zoom_in_center"])
        self.assertIn("x='iw/2-(iw/zoom/2)'", filters["zoom_out_center"])
        self.assertIn("y='ih/2-(ih/zoom/2)'", filters["zoom_out_center"])
        self.assertIn("x='0'", filters["zoom_in_top_left"])
        self.assertIn("y='0'", filters["zoom_in_top_left"])
        self.assertIn("x='iw/zoom-ow'", filters["zoom_in_bottom_right"])
        self.assertIn("y='ih/zoom-oh'", filters["zoom_in_bottom_right"])

    def test_kenburns_bundle_job_respects_output_path_overrides(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_a = root / "scene-a.png"
            _ = image_a.write_bytes(b"png")
            bundle_map_path = root / "scene_bundle_map.json"
            target_output = root / "assets" / "video" / "#01_KEN.mp4"
            bundle_map_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_key": "scene_a",
                                "source_path": str(image_a.resolve()),
                                "output_path": str(target_output.resolve()),
                                "duration_sec": 4,
                            }
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            job = JobContract(
                job_id="ken-bundle-output-override",
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
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"mp4")
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
                self.assertTrue(target_output.exists())

        self.assertEqual(result["status"], "ok")

    def test_kenburns_bundle_job_fails_closed_on_non_local_output_override(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            image_a = root / "scene-a.png"
            _ = image_a.write_bytes(b"png")
            bundle_map_path = root / "scene_bundle_map.json"
            bundle_map_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_key": "scene_a",
                                "source_path": str(image_a.resolve()),
                                "output_path": r"C:\Windows\Temp\scene.mp4",
                                "duration_sec": 4,
                            }
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            job = JobContract(
                job_id="ken-bundle-invalid-output",
                workload="kenburns",
                payload={"scene_bundle_map_path": str(bundle_map_path.resolve())},
            )

            result = run_kenburns_job(job, artifact_root=artifact_root)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "invalid_output_path")

    def test_geminigen_worker_emits_rvc_next_job_for_video_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            output_path = artifact_root / "exports" / "geminigen-scene-01.mp4"
            job = JobContract(
                job_id="geminigen-job-1",
                workload="geminigen",
                checkpoint_key="stage2:geminigen:Sheet1!row1:1",
                payload={
                    "run_id": "stage2-run-1",
                    "row_ref": "Sheet1!row1",
                    "scene_index": 1,
                    "prompt": "video prompt one",
                    "model_name": "voice-model-a",
                    "service_artifact_path": str(output_path),
                    "adapter_command": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            f"p=Path(r'{str(output_path)}'); "
                            "p.parent.mkdir(parents=True, exist_ok=True); "
                            "p.write_bytes(b'mp4')"
                        ),
                    ],
                },
            )

            result = run_geminigen_job(job, artifact_root)

        self.assertEqual(result["status"], "ok")
        next_jobs = cast(list[object], result["next_jobs"])
        self.assertEqual(len(next_jobs), 1)
        next_job = cast(dict[str, object], next_jobs[0])
        next_job_block = cast(dict[str, object], next_job["job"])
        next_payload = cast(dict[str, object], next_job_block["payload"])
        self.assertEqual(str(next_job_block["job_id"]), "rvc-geminigen-job-1")
        self.assertEqual(str(next_payload["audio_path"]), str(output_path.resolve()))

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

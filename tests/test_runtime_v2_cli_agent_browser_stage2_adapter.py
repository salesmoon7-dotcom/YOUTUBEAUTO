from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2 import exit_codes
from runtime_v2.cli import (
    CliArgs,
    _run_agent_browser_stage2_adapter_child,
    _run_qwen3_adapter_child,
    _run_rvc_adapter_child,
    _run_stage2_row1_probe,
    main,
)
from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract


class RuntimeV2CliAgentBrowserStage2AdapterTests(unittest.TestCase):
    def test_main_dispatches_qwen3_adapter_child_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            output_path = Path(tmp_dir) / "exports" / "speech.wav"
            with (
                patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--qwen3-adapter-child",
                        "--service-artifact-path",
                        str(output_path),
                    ],
                ),
                patch(
                    "runtime_v2.cli._run_qwen3_adapter_child",
                    return_value=exit_codes.SUCCESS,
                ) as child_mock,
            ):
                exit_code = main()

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        child_mock.assert_called_once()

    def test_main_dispatches_rvc_adapter_child_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            output_path = Path(tmp_dir) / "exports" / "converted.wav"
            with (
                patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--rvc-adapter-child",
                        "--service-artifact-path",
                        str(output_path),
                    ],
                ),
                patch(
                    "runtime_v2.cli._run_rvc_adapter_child",
                    return_value=exit_codes.SUCCESS,
                ) as child_mock,
            ):
                exit_code = main()

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        child_mock.assert_called_once()

    def test_stage2_adapter_child_writes_functional_evidence_for_genspark(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"

            with patch(
                "runtime_v2.cli.run_agent_browser_verify_job",
                return_value={"status": "ok"},
            ):
                with (
                    patch("runtime_v2.cli.Path.cwd", return_value=root),
                    patch(
                        "runtime_v2.cli.write_functional_evidence_bundle",
                        return_value={"service": "genspark", "sha256": "ok"},
                    ) as evidence_mock,
                ):
                    exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            evidence_mock.assert_called_once()
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["service"], "genspark")
            self.assertEqual(evidence["status"], "ok")
            self.assertTrue(bool(evidence["probe_debug_only"]))
            self.assertFalse(bool(evidence["recovery_attempted"]))
            self.assertTrue(bool(evidence["placeholder_artifact"]))

    def test_stage2_adapter_child_fails_closed_without_internal_recovery(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"
            args.runtime_root = str(root / "runtime")

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={
                        "status": "failed",
                        "error_code": "AGENT_BROWSER_TIMEOUT",
                    },
                ) as verify_mock,
                patch("runtime_v2.cli.Path.cwd", return_value=root),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            self.assertEqual(verify_mock.call_count, 1)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertTrue(bool(evidence["probe_debug_only"]))
            self.assertFalse(bool(evidence["recovery_attempted"]))
            self.assertFalse(bool(evidence["placeholder_artifact"]))
            self.assertFalse(output_path.exists())

    def test_stage2_adapter_child_writes_functional_evidence_for_canva(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "THUMB.png"
            args = CliArgs()
            args.service = "canva"
            args.port = 9666
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "canva.com"
            args.expected_title_substring = "Canva"

            with patch(
                "runtime_v2.cli.run_agent_browser_verify_job",
                return_value={"status": "ok"},
            ):
                with (
                    patch("runtime_v2.cli.Path.cwd", return_value=root),
                    patch(
                        "runtime_v2.cli.write_functional_evidence_bundle",
                        return_value={"service": "canva", "sha256": "ok"},
                    ) as evidence_mock,
                ):
                    exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        evidence_mock.assert_called_once()

    def test_stage2_adapter_child_fails_closed_for_geminigen_without_truthful_artifact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "geminigen-scene-01.mp4"
            args = CliArgs()
            args.service = "geminigen"
            args.port = 9555
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "geminigen.ai"
            args.expected_title_substring = "Gemini"

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["service"], "geminigen")
            self.assertEqual(evidence["status"], "ok")
            self.assertFalse(bool(evidence["placeholder_artifact"]))
            self.assertFalse(output_path.exists())

    def test_stage2_row1_probe_records_all_browser_results(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root / "runtime")
            ok_result = {
                "status": "ok",
                "details": {"attach_evidence_path": str(root / "attach_evidence.json")},
                "completion": {"state": "succeeded"},
            }

            with (
                patch("runtime_v2.cli.run_genspark_job", return_value=ok_result),
                patch("runtime_v2.cli.run_seaart_job", return_value=ok_result),
                patch("runtime_v2.cli.run_geminigen_job", return_value=ok_result),
                patch("runtime_v2.cli.run_canva_job", return_value=ok_result),
            ):
                report = _run_stage2_row1_probe(
                    config=config,
                    probe_root=root / "probe",
                    run_id="stage2-row1-run-1",
                    agent_browser_services=["genspark", "seaart", "geminigen", "canva"],
                )

        self.assertEqual(report["code"], "OK")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(len(cast(list[object], report["results"])), 4)
        self.assertEqual(report["readiness_scope"], "stage2_probe")
        self.assertEqual(report["live_readiness"], "full")
        self.assertEqual(cast(list[object], report["placeholder_services"]), [])
        self.assertEqual(
            cast(list[object], report["live_ready_services"]),
            ["genspark", "seaart", "geminigen", "canva"],
        )
        self.assertTrue(bool(report["probe_success"]))

    def test_stage2_row1_probe_writes_runtime_root_from_passed_config(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root / "runtime")
            seen_runtime_roots: list[str] = []

            def _capture(
                job: JobContract, artifact_root: Path, registry_file: Path | None = None
            ) -> dict[str, object]:
                _ = artifact_root
                _ = registry_file
                seen_runtime_roots.append(str(job.payload.get("runtime_root", "")))
                return {
                    "status": "ok",
                    "details": {},
                    "completion": {"state": "succeeded"},
                }

            with (
                patch("runtime_v2.cli.run_genspark_job", side_effect=_capture),
                patch("runtime_v2.cli.run_seaart_job", side_effect=_capture),
                patch("runtime_v2.cli.run_geminigen_job", side_effect=_capture),
                patch("runtime_v2.cli.run_canva_job", side_effect=_capture),
            ):
                _ = _run_stage2_row1_probe(
                    config=config,
                    probe_root=root / "probe",
                    run_id="stage2-row1-run-runtime-root",
                    agent_browser_services=["genspark", "seaart", "geminigen", "canva"],
                )

        self.assertEqual(
            seen_runtime_roots,
            [str((root / "runtime").resolve())] * 4,
        )

    def test_stage2_row1_probe_falls_back_after_attach_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root / "runtime")
            failed_result = {
                "status": "failed",
                "error_code": "genspark_adapter_failed",
                "details": {},
                "completion": {"state": "failed"},
            }
            ok_result = {
                "status": "ok",
                "details": {},
                "completion": {"state": "succeeded"},
            }

            with (
                patch(
                    "runtime_v2.cli.run_genspark_job",
                    side_effect=[failed_result, ok_result],
                ),
                patch("runtime_v2.cli.run_seaart_job", return_value=ok_result),
                patch("runtime_v2.cli.run_geminigen_job", return_value=ok_result),
                patch("runtime_v2.cli.run_canva_job", return_value=ok_result),
            ):
                report = _run_stage2_row1_probe(
                    config=config,
                    probe_root=root / "probe",
                    run_id="stage2-row1-run-2",
                    agent_browser_services=["genspark"],
                )

        self.assertEqual(report["code"], "OK")
        first = cast(list[dict[str, object]], report["results"])[0]
        self.assertTrue(bool(first["attach_attempt_failed"]))
        self.assertTrue(bool(first["fallback_used"]))
        self.assertEqual(report["readiness_scope"], "stage2_probe")
        self.assertEqual(report["live_readiness"], "partial")
        self.assertEqual(
            cast(list[object], report["placeholder_services"]),
            ["genspark", "seaart", "geminigen", "canva"],
        )
        self.assertEqual(cast(list[object], report["live_ready_services"]), [])
        self.assertTrue(bool(report["probe_success"]))

    def test_qwen3_adapter_child_writes_first_generated_voice_artifact(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "speech.wav"
            args = CliArgs()
            args.service_artifact_path = str(output_path)
            workspace = output_path.parent.parent
            prompt_path = workspace / "qwen_prompt.json"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "voice_texts": [
                                    {
                                        "col": "#01",
                                        "text": "hello world",
                                        "original_voices": [1],
                                    }
                                ]
                            }
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            def fake_run(*args: object, **kwargs: object):
                _ = args
                _ = kwargs
                voice_dir = workspace / "project" / "voice"
                voice_dir.mkdir(parents=True, exist_ok=True)
                _ = (voice_dir / "#00.txt").write_text("script", encoding="utf-8")
                _ = (voice_dir / "#01.flac").write_bytes(b"flac")
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "returncode", 0)
                setattr(completed, "stdout", "ok")
                setattr(completed, "stderr", "")
                return completed

            with patch("runtime_v2.cli.subprocess.run", side_effect=fake_run):
                exit_code = _run_qwen3_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"flac")

    def test_qwen3_adapter_child_prefers_cwd_workspace_when_output_path_is_external(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "worker"
            workspace.mkdir(parents=True, exist_ok=True)
            output_path = root / "exports" / "speech.wav"
            args = CliArgs()
            args.service_artifact_path = str(output_path)
            prompt_path = workspace / "qwen_prompt.json"
            prompt_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "voice_texts": [
                                    {
                                        "col": "#01",
                                        "text": "hello",
                                        "original_voices": [1],
                                    }
                                ]
                            }
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            def fake_run(*args: object, **kwargs: object):
                _ = args
                _ = kwargs
                voice_dir = workspace / "project" / "voice"
                voice_dir.mkdir(parents=True, exist_ok=True)
                _ = (voice_dir / "#01.flac").write_bytes(b"flac")
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "returncode", 0)
                setattr(completed, "stdout", "ok")
                setattr(completed, "stderr", "")
                return completed

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=workspace),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_qwen3_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"flac")

    def test_qwen3_adapter_child_fails_closed_without_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            args = CliArgs()
            args.service_artifact_path = str(root / "exports" / "speech.wav")

            exit_code = _run_qwen3_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.CLI_USAGE)

    def test_qwen3_adapter_child_returns_canonical_failure_code_on_subprocess_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "speech.wav"
            args = CliArgs()
            args.service_artifact_path = str(output_path)
            workspace = output_path.parent.parent
            prompt_path = workspace / "qwen_prompt.json"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(
                json.dumps(
                    {"rows": [{"voice_texts": [{"text": "hello"}]}]}, ensure_ascii=True
                ),
                encoding="utf-8",
            )
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "returncode", 1)
            setattr(completed, "stdout", "")
            setattr(completed, "stderr", "boom")

            with patch("runtime_v2.cli.subprocess.run", return_value=completed):
                exit_code = _run_qwen3_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.ADAPTER_FAIL)

    def test_rvc_adapter_child_runs_applio_infer_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "converted.flac"
            source_path = root / "source.flac"
            _ = source_path.write_bytes(b"source")
            args = CliArgs()
            args.service_artifact_path = str(output_path)
            workspace = output_path.parent.parent
            request_path = workspace / "rvc_request.json"
            request_path.parent.mkdir(parents=True, exist_ok=True)
            request_path.write_text(
                json.dumps(
                    {"source_path": str(source_path.resolve())}, ensure_ascii=True
                ),
                encoding="utf-8",
            )
            config_payload = {
                "applio_python": sys.executable,
                "applio_core": "applio_core.py",
                "applio_dir": str(root),
                "active_model": "main",
                "models": {"main": {"pth": "voice.pth", "index": "voice.index"}},
                "inference": {},
            }

            def fake_run(command: list[str], **kwargs: object):
                _ = command
                _ = kwargs
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_bytes(b"converted")
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "returncode", 0)
                setattr(completed, "stdout", "ok")
                setattr(completed, "stderr", "")
                return completed

            def fake_read_text(path_obj: Path, *args: object, **kwargs: object) -> str:
                _ = args
                _ = kwargs
                if path_obj == request_path:
                    return json.dumps(
                        {"source_path": str(source_path.resolve())}, ensure_ascii=True
                    )
                return json.dumps(config_payload, ensure_ascii=True)

            with (
                patch(
                    "runtime_v2.cli.Path.read_text",
                    autospec=True,
                    side_effect=fake_read_text,
                ),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_rvc_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"converted")

    def test_rvc_adapter_child_prefers_cwd_workspace_when_output_path_is_external(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "worker"
            workspace.mkdir(parents=True, exist_ok=True)
            output_path = root / "exports" / "converted.flac"
            source_path = root / "source.flac"
            _ = source_path.write_bytes(b"source")
            args = CliArgs()
            args.service_artifact_path = str(output_path)
            request_path = workspace / "rvc_request.json"
            request_path.write_text(
                json.dumps(
                    {"source_path": str(source_path.resolve())}, ensure_ascii=True
                ),
                encoding="utf-8",
            )
            config_payload = {
                "applio_python": sys.executable,
                "applio_core": "applio_core.py",
                "applio_dir": str(root),
                "active_model": "main",
                "models": {"main": {"pth": "voice.pth", "index": "voice.index"}},
                "inference": {},
            }

            def fake_read_text(path_obj: Path, *args: object, **kwargs: object) -> str:
                _ = args
                _ = kwargs
                if path_obj == request_path:
                    return json.dumps(
                        {"source_path": str(source_path.resolve())}, ensure_ascii=True
                    )
                return json.dumps(config_payload, ensure_ascii=True)

            def fake_run(command: list[str], **kwargs: object):
                _ = command
                _ = kwargs
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_bytes(b"converted")
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "returncode", 0)
                setattr(completed, "stdout", "ok")
                setattr(completed, "stderr", "")
                return completed

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=workspace),
                patch(
                    "runtime_v2.cli.Path.read_text",
                    autospec=True,
                    side_effect=fake_read_text,
                ),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_rvc_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"converted")

    def test_rvc_adapter_child_fails_closed_without_request_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            args = CliArgs()
            args.service_artifact_path = str(root / "exports" / "converted.flac")

            exit_code = _run_rvc_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.CLI_USAGE)

    def test_rvc_adapter_child_returns_canonical_failure_code_when_output_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "converted.flac"
            source_path = root / "source.flac"
            _ = source_path.write_bytes(b"source")
            args = CliArgs()
            args.service_artifact_path = str(output_path)
            workspace = output_path.parent.parent
            request_path = workspace / "rvc_request.json"
            request_path.parent.mkdir(parents=True, exist_ok=True)
            request_path.write_text(
                json.dumps(
                    {"source_path": str(source_path.resolve())}, ensure_ascii=True
                ),
                encoding="utf-8",
            )
            config_payload = {
                "applio_python": sys.executable,
                "applio_core": "applio_core.py",
                "applio_dir": str(root),
                "active_model": "main",
                "models": {"main": {"pth": "voice.pth", "index": "voice.index"}},
                "inference": {},
            }
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "returncode", 0)
            setattr(completed, "stdout", "ok")
            setattr(completed, "stderr", "")

            def fake_read_text(path_obj: Path, *args: object, **kwargs: object) -> str:
                _ = args
                _ = kwargs
                if path_obj == request_path:
                    return json.dumps(
                        {"source_path": str(source_path.resolve())}, ensure_ascii=True
                    )
                return json.dumps(config_payload, ensure_ascii=True)

            with (
                patch(
                    "runtime_v2.cli.Path.read_text",
                    autospec=True,
                    side_effect=fake_read_text,
                ),
                patch("runtime_v2.cli.subprocess.run", return_value=completed),
            ):
                exit_code = _run_rvc_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.ADAPTER_FAIL)


if __name__ == "__main__":
    _ = unittest.main()

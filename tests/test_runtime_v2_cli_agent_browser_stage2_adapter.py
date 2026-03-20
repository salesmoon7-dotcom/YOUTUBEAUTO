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
    _attach_genspark_ref_images_via_filechooser,
    _attach_seaart_ref_images_via_playwright,
    _attach_stage2_ref_images,
    _run_agent_browser_eval,
    _run_agent_browser_stage2_adapter_child,
    _run_qwen3_adapter_child,
    _run_rvc_adapter_child,
    _run_stage2_row1_probe,
    main,
)
from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract


class RuntimeV2CliAgentBrowserStage2AdapterTests(unittest.TestCase):
    def test_run_agent_browser_eval_resolves_agent_browser_binary(self) -> None:
        completed = cast(object, type("Completed", (), {})())
        setattr(completed, "stdout", '{"ok":true}')
        setattr(completed, "stderr", "")
        setattr(completed, "returncode", 0)

        with (
            patch(
                "runtime_v2.cli._resolve_agent_browser_command",
                return_value=[
                    r"C:\resolved\agent-browser.cmd",
                    "--cdp",
                    "9333",
                    "eval",
                    "script",
                ],
            ) as resolve_mock,
            patch("runtime_v2.cli.subprocess.run", return_value=completed) as run_mock,
        ):
            result = _run_agent_browser_eval(9333, "script", timeout=7)

        resolve_mock.assert_called_once_with(
            ["agent-browser", "--cdp", "9333", "eval", "script"]
        )
        run_mock.assert_called_once()
        self.assertEqual(
            run_mock.call_args.args[0][0], r"C:\resolved\agent-browser.cmd"
        )
        self.assertEqual(getattr(result, "stdout", ""), '{"ok":true}')

    def test_main_dispatches_qwen3_adapter_child_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            output_path = Path(tmp_dir) / "exports" / "speech.flac"
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
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "stdout", '{"ok":true}')
            setattr(completed, "stderr", "")

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
                    patch("runtime_v2.cli.subprocess.run", return_value=completed),
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
            self.assertFalse(bool(evidence["placeholder_artifact"]))

    def test_stage2_adapter_child_records_canva_clone_counts(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "thumb.png"
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "stdout", '{"ok":true}')
            setattr(completed, "stderr", "")
            args = CliArgs()
            args.service = "canva"
            args.port = 9666
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "canva.com"
            args.expected_title_substring = "Canva"

            transcript = [
                {"step": "page_count_before", "result": '{"ok":true,"count":1}'},
                {"step": "page_count_after", "result": '{"ok":true,"count":2}'},
            ]

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok", "transcript": transcript},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "canva", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", return_value=completed),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["status"], "ok")

    def test_stage2_adapter_child_reads_canva_step_results_from_transcript_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "thumb.png"
            workspace = root
            transcript_path = workspace / "agent_browser_transcript.json"
            transcript_path.write_text(
                json.dumps(
                    {
                        "steps": [
                            {
                                "output": '{"ok":true,"step":"page_count_before","count":1}'
                            },
                            {
                                "output": '{"ok":true,"step":"page_count_after","count":2}'
                            },
                            {
                                "output": '{"ok":true,"step":"submitted_background_generate"}'
                            },
                            {"output": '{"ok":true,"step":"selected_current_page"}'},
                            {
                                "output": '{"ok":true,"step":"confirmed_download_options"}'
                            },
                            {"output": '{"ok":true,"step":"clicked_download_execute"}'},
                            {
                                "output": '{"ok":true,"step":"cleanup_deleted_created_page"}'
                            },
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            (workspace / "thumb_data.json").write_text(
                json.dumps(
                    {
                        "bg_prompt": "legacy background",
                        "line1": "Legacy",
                        "line2": "Thumb",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            args = CliArgs()
            args.service = "canva"
            args.port = 9666
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "canva.com"
            args.expected_title_substring = "Canva"

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={
                        "status": "ok",
                        "details": {"transcript_path": str(transcript_path.resolve())},
                    },
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "canva", "sha256": "ok"},
                ),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            details = cast(dict[object, object], evidence["details"])
            self.assertEqual(details["page_count_before"], 1)
            self.assertEqual(details["page_count_after"], 2)
            self.assertTrue(bool(details["clone_ok"]))
            self.assertTrue(bool(details["background_generate_ok"]))
            self.assertTrue(bool(details["current_page_selection_ok"]))
            self.assertTrue(bool(details["download_options_ok"]))
            self.assertTrue(bool(details["download_sequence_ok"]))
            self.assertTrue(bool(details["cleanup_ok"]))
            self.assertEqual(details["bg_prompt"], "legacy background")
            self.assertEqual(details["transcript_path"], str(transcript_path.resolve()))

    def test_stage2_adapter_child_uses_native_setter_and_enter_for_genspark_prompt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "stdout", '{"ok":true}')
            setattr(completed, "stderr", "")
            captured_actions: list[dict[str, object]] = []

            def fake_verify(job: JobContract, artifact_root: Path) -> dict[str, object]:
                _ = artifact_root
                payload = cast(dict[str, object], job.payload)
                captured_actions.extend(
                    cast(list[dict[str, object]], payload.get("actions", []))
                )
                return {"status": "ok"}

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    side_effect=fake_verify,
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", return_value=completed),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        scripts = [str(action.get("script", "")) for action in captured_actions]
        self.assertTrue(
            any("HTMLTextAreaElement.prototype" in script for script in scripts)
        )
        self.assertTrue(any("KeyboardEvent" in script for script in scripts))

    def test_stage2_adapter_child_sends_legacy_yes_confirmation_when_questions_appear(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"

            responses: list[object] = []
            for payload in [
                '{"ok":false,"error":"GENSPARK_IMAGE_NOT_READY"}',
                '{"ok":true,"question_marks":2}',
                '{"ok":true,"src":"https://www.genspark.ai/api/files/example.png"}',
                '{"ok":true}',
            ]:
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", payload)
                setattr(completed, "stderr", "")
                responses.append(completed)

            commands: list[list[str]] = []

            def fake_run(*args_: object, **kwargs: object) -> object:
                _ = kwargs
                command = cast(list[str], args_[0])
                commands.append(command)
                if responses:
                    return responses.pop(0)
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", '{"ok":true}')
                setattr(completed, "stderr", "")
                return completed

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        eval_scripts = [
            cmd[-1] for cmd in commands if len(cmd) >= 5 and cmd[3] == "eval"
        ]
        self.assertTrue(any("question_marks" in script for script in eval_scripts))
        self.assertTrue(any("confirm_submitted" in script for script in eval_scripts))
        self.assertFalse(any("followup_submitted" in script for script in eval_scripts))

    def test_stage2_adapter_child_does_not_click_genspark_regenerate_when_interrupted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"

            responses: list[object] = []
            for payload in [
                '{"ok":false,"error":"GENSPARK_IMAGE_NOT_READY"}',
                '{"ok":true,"src":"https://www.genspark.ai/api/files/example.png"}',
                '{"ok":true}',
            ]:
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", payload)
                setattr(completed, "stderr", "")
                responses.append(completed)

            commands: list[list[str]] = []

            def fake_run(*args_: object, **kwargs: object) -> object:
                _ = kwargs
                command = cast(list[str], args_[0])
                commands.append(command)
                if responses:
                    return responses.pop(0)
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", '{"ok":true}')
                setattr(completed, "stderr", "")
                return completed

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch("runtime_v2.cli.sleep"),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        eval_scripts = [
            cmd[-1] for cmd in commands if len(cmd) >= 5 and cmd[3] == "eval"
        ]
        self.assertFalse(any("clicked_regenerate" in script for script in eval_scripts))

    def test_stage2_adapter_child_keeps_original_genspark_prompt_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "stdout", '{"ok":true}')
            setattr(completed, "stderr", "")
            captured_actions: list[dict[str, object]] = []

            def fake_verify(job: JobContract, artifact_root: Path) -> dict[str, object]:
                _ = artifact_root
                payload = cast(dict[str, object], job.payload)
                captured_actions.extend(
                    cast(list[dict[str, object]], payload.get("actions", []))
                )
                return {"status": "ok"}

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    side_effect=fake_verify,
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", return_value=completed),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        scripts = [str(action.get("script", "")) for action in captured_actions]
        self.assertTrue(any("scene one" in script for script in scripts))
        self.assertFalse(
            any("추가 질문 없이" in script or "16:9" in script for script in scripts)
        )

    def test_stage2_adapter_child_resolves_relative_ref_images_against_asset_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            asset_root = root / "assets"
            asset_root.mkdir(parents=True, exist_ok=True)
            ref1 = asset_root / "images" / "ref1.png"
            ref2 = asset_root / "images" / "ref2.png"
            ref1.parent.mkdir(parents=True, exist_ok=True)
            _ = ref1.write_bytes(b"png")
            _ = ref2.write_bytes(b"png")
            output_path = root / "exports" / "scene-01.png"
            request_payload = {
                "payload": {
                    "prompt": "scene one",
                    "asset_root": str(asset_root.resolve()),
                    "ref_img_1": "images/ref1.png",
                    "ref_img_2": "images/ref2.png",
                }
            }
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"png")

            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "stdout", '{"ok":true}')
            setattr(completed, "stderr", "")

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli._attach_stage2_ref_images",
                ) as attach_mock,
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", return_value=completed),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.SUCCESS)
            attach_mock.assert_called_once()
            self.assertEqual(
                attach_mock.call_args.kwargs["file_paths"],
                [str(ref1.resolve()), str(ref2.resolve())],
            )
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                evidence["ref_images_requested"], ["images/ref1.png", "images/ref2.png"]
            )
            self.assertEqual(
                evidence["ref_images_resolved"],
                [str(ref1.resolve()), str(ref2.resolve())],
            )
            self.assertTrue(bool(evidence["ref_images_attach_attempted"]))

    def test_stage2_adapter_child_normalizes_genspark_target_matcher(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"
            captured_expected: list[str] = []
            responses: list[object] = []
            for payload in [
                '{"ok":true,"src":"https://www.genspark.ai/api/files/example.png"}',
                '{"ok":true}',
            ]:
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", payload)
                setattr(completed, "stderr", "")
                responses.append(completed)

            def fake_run(*args_: object, **kwargs: object) -> object:
                _ = args_
                _ = kwargs
                if responses:
                    return responses.pop(0)
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", '{"ok":true}')
                setattr(completed, "stderr", "")
                return completed

            def fake_verify(job: JobContract, artifact_root: Path) -> dict[str, object]:
                _ = artifact_root
                payload = cast(dict[str, object], job.payload)
                captured_expected.append(str(payload.get("expected_url_substring", "")))
                return {"status": "ok"}

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch("runtime_v2.cli.sleep"),
                patch("runtime_v2.cli._close_genspark_result_tabs"),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    side_effect=fake_verify,
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        self.assertTrue(captured_expected)
        self.assertTrue(
            all(
                value == "genspark.ai/agents?type=image_generation_agent"
                for value in captured_expected
            )
        )

    def test_stage2_adapter_child_closes_existing_genspark_result_tabs_first(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch("runtime_v2.cli.sleep"),
                patch("runtime_v2.cli._close_genspark_result_tabs") as close_mock,
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run") as run_mock,
            ):
                completed = cast(object, type("Completed", (), {})())
                setattr(
                    completed,
                    "stdout",
                    '{"ok":true,"src":"https://www.genspark.ai/api/files/example.png"}',
                )
                setattr(completed, "stderr", "")
                run_mock.return_value = completed
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        close_mock.assert_called_once_with(9333)

    def test_stage2_adapter_child_requests_new_genspark_session_before_prompt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"
            captured_actions: list[dict[str, object]] = []
            responses: list[object] = []
            for payload in [
                '{"ok":true,"src":"https://www.genspark.ai/api/files/example.png"}',
                '{"ok":true}',
            ]:
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", payload)
                setattr(completed, "stderr", "")
                responses.append(completed)

            def fake_run(*args_: object, **kwargs: object) -> object:
                _ = args_
                _ = kwargs
                if responses:
                    return responses.pop(0)
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", '{"ok":true}')
                setattr(completed, "stderr", "")
                return completed

            def fake_verify(job: JobContract, artifact_root: Path) -> dict[str, object]:
                _ = artifact_root
                payload = cast(dict[str, object], job.payload)
                captured_actions.extend(
                    cast(list[dict[str, object]], payload.get("actions", []))
                )
                return {"status": "ok"}

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch("runtime_v2.cli.sleep"),
                patch("runtime_v2.cli._close_genspark_result_tabs"),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    side_effect=fake_verify,
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        scripts = [str(action.get("script", "")) for action in captured_actions]
        self.assertTrue(any("selected_new_session" in script for script in scripts))

    def test_attach_stage2_ref_images_uses_genspark_filechooser_helper(self) -> None:
        with patch(
            "runtime_v2.cli._attach_genspark_ref_images_via_filechooser"
        ) as attach_mock:
            _attach_stage2_ref_images(
                port=9333,
                expected_url_substring="genspark.ai/agents?type=image_generation_agent",
                file_paths=[r"D:\tmp\ref1.png", r"D:\tmp\ref2.png"],
            )

        attach_mock.assert_called_once_with(
            port=9333,
            file_paths=[r"D:\tmp\ref1.png", r"D:\tmp\ref2.png"],
        )

    def test_stage2_adapter_child_fails_closed_when_ref_image_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            asset_root = root / "assets"
            asset_root.mkdir(parents=True, exist_ok=True)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {
                "payload": {
                    "prompt": "scene one",
                    "asset_root": str(asset_root.resolve()),
                    "ref_img_1": "images/missing-ref.png",
                }
            }
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "seaart"
            args.port = 9444
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "seaart.ai"
            args.expected_title_substring = "SeaArt"

            with patch("runtime_v2.cli.Path.cwd", return_value=root):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["error_code"], "REF_IMAGE_UPLOAD_FAILED")
            self.assertEqual(
                evidence["ref_upload_error_code"], "REF_IMAGE_UPLOAD_FAILED"
            )
            self.assertTrue(bool(evidence["ref_images_attach_attempted"]))

    def test_stage2_adapter_child_fails_closed_when_genspark_ref_upload_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            asset_root = root / "assets"
            asset_root.mkdir(parents=True, exist_ok=True)
            ref1 = asset_root / "images" / "ref1.png"
            ref2 = asset_root / "images" / "ref2.png"
            ref1.parent.mkdir(parents=True, exist_ok=True)
            _ = ref1.write_bytes(b"png")
            _ = ref2.write_bytes(b"png")
            output_path = root / "exports" / "scene-01.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _ = output_path.write_bytes(b"png")
            request_payload = {
                "payload": {
                    "prompt": "scene one",
                    "asset_root": str(asset_root.resolve()),
                    "ref_img_1": "images/ref1.png",
                    "ref_img_2": "images/ref2.png",
                }
            }
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "stdout", '{"ok":true}')
            setattr(completed, "stderr", "")
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli._attach_stage2_ref_images",
                    side_effect=RuntimeError("NO_FILE_INPUT"),
                ),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "genspark", "sha256": "ok"},
                ),
                patch("runtime_v2.cli.subprocess.run", return_value=completed),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(
                evidence["ref_upload_error_code"], "REF_IMAGE_UPLOAD_FAILED"
            )
            self.assertTrue(bool(evidence["ref_images_attach_attempted"]))

    def test_attach_genspark_ref_images_supports_image_generation_agent_page(
        self,
    ) -> None:
        class _Chooser:
            def __init__(self) -> None:
                self.files: list[str] = []

            def set_files(self, files: list[str]) -> None:
                self.files = files

        class _ChooserContext:
            def __init__(self, chooser: _Chooser) -> None:
                self.value = chooser

            def __enter__(self) -> "_ChooserContext":
                return self

            def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
                _ = (exc_type, exc, tb)
                return False

        class _Locator:
            @property
            def first(self) -> "_Locator":
                return self

            def click(self) -> None:
                return None

        class _Page:
            def __init__(self, chooser: _Chooser) -> None:
                self.url = "https://www.genspark.ai/agents?type=image_generation_agent"
                self._chooser = chooser

            def bring_to_front(self) -> None:
                return None

            def expect_file_chooser(self, timeout: int = 5000) -> _ChooserContext:
                _ = timeout
                return _ChooserContext(self._chooser)

            def locator(self, selector: str) -> _Locator:
                _ = selector
                return _Locator()

            def get_by_text(self, text: str, exact: bool = False) -> _Locator:
                _ = (text, exact)
                return _Locator()

        class _Context:
            def __init__(self, page: _Page) -> None:
                self.pages = [page]

        class _Browser:
            def __init__(self, context: _Context) -> None:
                self.contexts = [context]

            def close(self) -> None:
                return None

        class _Chromium:
            def __init__(self, browser: _Browser) -> None:
                self._browser = browser

            def connect_over_cdp(self, endpoint: str) -> _Browser:
                _ = endpoint
                return self._browser

        class _Playwright:
            def __init__(self, chromium: _Chromium) -> None:
                self.chromium = chromium

        class _PlaywrightContext:
            def __init__(self, playwright: _Playwright) -> None:
                self._playwright = playwright

            def __enter__(self) -> _Playwright:
                return self._playwright

            def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
                _ = (exc_type, exc, tb)
                return False

        chooser = _Chooser()
        page = _Page(chooser)
        browser = _Browser(_Context(page))
        playwright_context = _PlaywrightContext(_Playwright(_Chromium(browser)))

        with patch(
            "playwright.sync_api.sync_playwright", return_value=playwright_context
        ):
            _attach_genspark_ref_images_via_filechooser(
                port=9333,
                file_paths=[r"D:\tmp\ref1.png", r"D:\tmp\ref2.png"],
            )

        self.assertEqual(
            chooser.files,
            [
                str(Path(r"D:\tmp\ref1.png").resolve()),
                str(Path(r"D:\tmp\ref2.png").resolve()),
            ],
        )

    def test_attach_genspark_ref_images_skips_when_upload_ui_missing(self) -> None:
        class _Page:
            url = "https://www.genspark.ai/agents?type=image_generation_agent"

            def bring_to_front(self) -> None:
                return None

            def expect_file_chooser(self, timeout: int = 5000) -> object:
                _ = timeout
                raise RuntimeError("unexpected")

            def locator(self, selector: str) -> object:
                _ = selector

                class _Locator:
                    @property
                    def first(self) -> "_Locator":
                        return self

                    def click(self) -> None:
                        return None

                return _Locator()

            def get_by_text(self, text: str, exact: bool = False) -> object:
                _ = (text, exact)

                class _Locator:
                    @property
                    def first(self) -> "_Locator":
                        return self

                    def click(self) -> None:
                        return None

                return _Locator()

        class _Context:
            def __init__(self) -> None:
                self.pages = [_Page()]

        class _Browser:
            def __init__(self) -> None:
                self.contexts = [_Context()]

            def close(self) -> None:
                return None

        class _Chromium:
            def connect_over_cdp(self, endpoint: str) -> _Browser:
                _ = endpoint
                return _Browser()

        class _Playwright:
            chromium = _Chromium()

        class _PlaywrightContext:
            def __enter__(self) -> _Playwright:
                return _Playwright()

            def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
                _ = (exc_type, exc, tb)
                return False

        with patch(
            "playwright.sync_api.sync_playwright", return_value=_PlaywrightContext()
        ):
            _attach_genspark_ref_images_via_filechooser(
                port=9333,
                file_paths=[r"D:\tmp\ref1.png"],
            )

    def test_attach_seaart_ref_images_uses_playwright_input_files(self) -> None:
        class _Locator:
            def __init__(self) -> None:
                self.files: list[str] = []

            @property
            def first(self) -> "_Locator":
                return self

            def set_input_files(self, files: list[str]) -> None:
                self.files = files

        class _Page:
            def __init__(self, locator: _Locator) -> None:
                self.url = "https://www.seaart.ai/ko/create/image?id=abc"
                self._locator = locator

            def bring_to_front(self) -> None:
                return None

            def locator(self, selector: str) -> _Locator:
                _ = selector
                return self._locator

        class _Context:
            def __init__(self, page: _Page) -> None:
                self.pages = [page]

        class _Browser:
            def __init__(self, context: _Context) -> None:
                self.contexts = [context]

            def close(self) -> None:
                return None

        class _Chromium:
            def __init__(self, browser: _Browser) -> None:
                self._browser = browser

            def connect_over_cdp(self, endpoint: str) -> _Browser:
                _ = endpoint
                return self._browser

        class _Playwright:
            def __init__(self, chromium: _Chromium) -> None:
                self.chromium = chromium

        class _PlaywrightContext:
            def __init__(self, playwright: _Playwright) -> None:
                self._playwright = playwright

            def __enter__(self) -> _Playwright:
                return self._playwright

            def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
                _ = (exc_type, exc, tb)
                return False

        locator = _Locator()
        page = _Page(locator)
        browser = _Browser(_Context(page))
        playwright_context = _PlaywrightContext(_Playwright(_Chromium(browser)))

        with patch(
            "playwright.sync_api.sync_playwright", return_value=playwright_context
        ):
            _attach_seaart_ref_images_via_playwright(
                port=9444,
                file_paths=[r"D:\tmp\ref1.png", r"D:\tmp\ref2.png"],
            )

        self.assertEqual(
            locator.files,
            [
                str(Path(r"D:\tmp\ref1.png").resolve()),
                str(Path(r"D:\tmp\ref2.png").resolve()),
            ],
        )

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

    def test_stage2_adapter_child_records_pre_action_exception_details(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "scene-01.png"
            request_payload = {"payload": {"prompt": "scene one"}}
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "genspark"
            args.port = 9333
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "genspark.ai"
            args.expected_title_substring = "Genspark"

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch("runtime_v2.cli._close_genspark_result_tabs"),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    side_effect=TypeError("unexpected parser shape"),
                ),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            details = cast(dict[object, object], evidence["details"])
            self.assertEqual(
                evidence["error_code"], "AGENT_BROWSER_PRE_ACTION_EXCEPTION"
            )
            self.assertEqual(str(details["exception_type"]), "TypeError")
            self.assertIn("unexpected parser shape", str(details["exception"]))

    def test_stage2_adapter_child_records_debug_state_on_genspark_capture_failure(
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
            completed = cast(object, type("Completed", (), {})())
            setattr(completed, "stdout", '{"ok":true}')
            setattr(completed, "stderr", "")

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch("runtime_v2.cli.subprocess.run", return_value=completed),
                patch("runtime_v2.cli.sleep"),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    side_effect=RuntimeError("capture-failed"),
                ),
                patch(
                    "runtime_v2.cli.collect_browser_debug_state",
                    return_value={
                        "selected_target": {
                            "url": "https://www.genspark.ai/agents?id=fresh"
                        }
                    },
                ),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            details = cast(dict[object, object], evidence["details"])
            debug_state_path = Path(str(details["debug_state_path"]))
            retry_trace_path = Path(str(details["retry_trace_path"]))
            self.assertTrue(debug_state_path.exists())
            self.assertTrue(retry_trace_path.exists())
            debug_payload = json.loads(debug_state_path.read_text(encoding="utf-8"))
            retry_payload = json.loads(retry_trace_path.read_text(encoding="utf-8"))
            self.assertEqual(
                cast(dict[object, object], debug_payload["selected_target"])["url"],
                "https://www.genspark.ai/agents?id=fresh",
            )
            entries = cast(list[object], retry_payload["entries"])
            self.assertGreaterEqual(len(entries), 1)

    def test_stage2_adapter_child_persists_retry_trace_entries_on_genspark_failure(
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

            responses: list[object] = []
            for payload in [
                '{"ok":false,"error":"GENSPARK_IMAGE_NOT_READY"}',
                '{"ok":false,"reason":"FOLLOWUP_ALREADY_SENT"}',
                '{"ok":false,"reason":"NO_REGENERATE_BUTTON"}',
                '{"ok":false,"error":"GENSPARK_IMAGE_NOT_READY"}',
            ]:
                completed = cast(object, type("Completed", (), {})())
                setattr(completed, "stdout", payload)
                setattr(completed, "stderr", "stderr-" + payload)
                setattr(completed, "returncode", 0)
                responses.append(completed)

            def fake_run(*args_: object, **kwargs: object) -> object:
                _ = kwargs
                if responses:
                    return responses.pop(0)
                completed = cast(object, type("Completed", (), {})())
                setattr(
                    completed, "stdout", '{"ok":false,"reason":"FOLLOWUP_ALREADY_SENT"}'
                )
                setattr(completed, "stderr", "")
                setattr(completed, "returncode", 0)
                return completed

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch("runtime_v2.cli.sleep"),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    side_effect=RuntimeError("capture-failed"),
                ),
                patch(
                    "runtime_v2.cli.collect_browser_debug_state",
                    return_value={
                        "selected_target": {
                            "url": "https://www.genspark.ai/agents?id=fresh"
                        }
                    },
                ),
                patch("runtime_v2.cli.subprocess.run", side_effect=fake_run),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )
            details = cast(dict[object, object], evidence["details"])
            retry_trace_path = Path(str(details["retry_trace_path"]))
            retry_payload = json.loads(retry_trace_path.read_text(encoding="utf-8"))
            entries = cast(list[object], retry_payload["entries"])
            self.assertGreaterEqual(len(entries), 4)
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
                    evidence = json.loads(
                        (root / "attach_evidence.json").read_text(encoding="utf-8")
                    )

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        evidence_mock.assert_called_once()
        self.assertEqual(evidence["service"], "canva")
        self.assertEqual(evidence["status"], "ok")
        self.assertFalse(bool(evidence["placeholder_artifact"]))

    def test_stage2_adapter_child_builds_full_canva_legacy_sequence_actions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "THUMB.png"
            (root / "thumb_data.json").write_text(
                json.dumps(
                    {
                        "bg_prompt": "legacy background",
                        "line1": "Legacy",
                        "line2": "Thumb",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            request_payload = {
                "payload": {"prompt": "scene one", "ref_img": "D:/ref.png"}
            }
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "canva"
            args.port = 9666
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "canva.com"
            args.expected_title_substring = "Canva"
            captured_actions: list[dict[str, object]] = []

            def fake_verify(job: JobContract, artifact_root: Path) -> dict[str, object]:
                _ = artifact_root
                payload = cast(dict[str, object], job.payload)
                captured_actions.extend(
                    cast(list[dict[str, object]], payload.get("actions", []))
                )
                return {"status": "ok"}

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    side_effect=fake_verify,
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    return_value={"service": "canva", "sha256": "ok"},
                ),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        scripts = [str(action.get("script", "")) for action in captured_actions]
        uploads = [
            action for action in captured_actions if action.get("type") == "upload"
        ]
        self.assertTrue(
            any("submitted_background_generate" in script for script in scripts)
        )
        self.assertTrue(
            any("clicked_remove_background" in script for script in scripts)
        )
        self.assertTrue(any("set_image_position" in script for script in scripts))
        self.assertTrue(any("edited_thumbnail_text" in script for script in scripts))
        self.assertTrue(any("clicked_download_execute" in script for script in scripts))
        self.assertTrue(
            any("cleanup_deleted_created_page" in script for script in scripts)
        )
        self.assertTrue(any("prepared_upload_input" in script for script in scripts))
        self.assertTrue(any("placed_uploaded_image" in script for script in scripts))
        self.assertTrue(
            any("__runtime_v2_canva_before_upload" in script for script in scripts)
        )
        self.assertEqual(len(uploads), 1)
        self.assertEqual(
            uploads[0]["selector"], "input[data-runtime-v2-canva-upload='ready']"
        )
        self.assertEqual(uploads[0]["files"], ["D:/ref.png"])

    def test_stage2_adapter_child_fail_closes_when_functional_capture_fails(
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

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    side_effect=RuntimeError("capture failed"),
                ),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

            evidence = json.loads(
                (root / "attach_evidence.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, exit_codes.BROWSER_UNHEALTHY)
        self.assertEqual(evidence["status"], "ok")
        self.assertTrue(bool(evidence["placeholder_artifact"]))

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
            self.assertTrue(bool(evidence["placeholder_artifact"]))
            self.assertFalse(output_path.exists())

    def test_stage2_adapter_child_succeeds_for_geminigen_with_truthful_artifact(
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

            def fake_bundle(**kwargs: object) -> dict[str, object]:
                target = Path(str(kwargs["service_artifact_path"]))
                target.parent.mkdir(parents=True, exist_ok=True)
                _ = target.write_bytes(b"mp4")
                return {"service": "geminigen", "sha256": "ok"}

            with (
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    return_value={"status": "ok"},
                ),
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    side_effect=fake_bundle,
                ) as evidence_mock,
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)
                evidence = json.loads(
                    (root / "attach_evidence.json").read_text(encoding="utf-8")
                )
                self.assertEqual(exit_code, exit_codes.SUCCESS)
                evidence_mock.assert_called_once()
                self.assertEqual(evidence["service"], "geminigen")
                self.assertEqual(evidence["status"], "ok")
                self.assertFalse(bool(evidence["placeholder_artifact"]))
                self.assertTrue(output_path.exists())

    def test_stage2_adapter_child_builds_geminigen_legacy_upload_actions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "geminigen-scene-01.mp4"
            first_frame = root / "assets" / "frame.png"
            first_frame.parent.mkdir(parents=True, exist_ok=True)
            _ = first_frame.write_bytes(b"png")
            request_payload = {
                "payload": {
                    "prompt": "video prompt one",
                    "first_frame_path": str(first_frame.resolve()),
                }
            }
            (root / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=True), encoding="utf-8"
            )
            args = CliArgs()
            args.service = "geminigen"
            args.port = 9555
            args.service_artifact_path = str(output_path)
            args.expected_url_substring = "geminigen.ai"
            args.expected_title_substring = "Gemini"
            captured_actions: list[dict[str, object]] = []

            def fake_verify(job: JobContract, artifact_root: Path) -> dict[str, object]:
                _ = artifact_root
                payload = cast(dict[str, object], job.payload)
                captured_actions.extend(
                    cast(list[dict[str, object]], payload.get("actions", []))
                )
                return {"status": "ok"}

            def fake_bundle(**kwargs: object) -> dict[str, object]:
                target = Path(str(kwargs["service_artifact_path"]))
                target.parent.mkdir(parents=True, exist_ok=True)
                _ = target.write_bytes(b"mp4")
                return {"service": "geminigen", "sha256": "ok"}

            with (
                patch("runtime_v2.cli.Path.cwd", return_value=root),
                patch(
                    "runtime_v2.cli.run_agent_browser_verify_job",
                    side_effect=fake_verify,
                ),
                patch(
                    "runtime_v2.cli.write_functional_evidence_bundle",
                    side_effect=fake_bundle,
                ),
            ):
                exit_code = _run_agent_browser_stage2_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        uploads = [
            action for action in captured_actions if action.get("type") == "upload"
        ]
        scripts = [str(action.get("script", "")) for action in captured_actions]
        self.assertEqual(len(uploads), 2)
        self.assertEqual(
            uploads[0]["selector"], "input[data-runtime-v2-geminigen-upload='first']"
        )
        self.assertEqual(
            uploads[1]["selector"], "input[data-runtime-v2-geminigen-upload='last']"
        )
        self.assertEqual(uploads[0]["files"], [str(first_frame.resolve())])
        self.assertEqual(uploads[1]["files"], [str(first_frame.resolve())])
        self.assertTrue(
            any("prepared_geminigen_upload_inputs" in script for script in scripts)
        )
        self.assertTrue(any("selected_create_new" in script for script in scripts))
        self.assertTrue(any("clicked_generate" in script for script in scripts))

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
            output_path = root / "exports" / "speech.flac"
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
            output_path = root / "exports" / "speech.flac"
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
            args.service_artifact_path = str(root / "exports" / "speech.flac")

            exit_code = _run_qwen3_adapter_child(args)

        self.assertEqual(exit_code, exit_codes.CLI_USAGE)

    def test_qwen3_adapter_child_returns_canonical_failure_code_on_subprocess_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            output_path = root / "exports" / "speech.flac"
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

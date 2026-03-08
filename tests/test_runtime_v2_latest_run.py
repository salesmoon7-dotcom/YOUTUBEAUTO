from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.config import RuntimeConfig
from runtime_v2.control_plane import run_control_loop_once, seed_control_job
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.bootstrap import ensure_runtime_bootstrap
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status
from runtime_v2.latest_run import load_joined_latest_run, write_runtime_snapshot


def _latest_run_config(root: Path) -> RuntimeConfig:
    return RuntimeConfig(
        gui_status_file=root / "health" / "gui_status.json",
        result_router_file=root / "evidence" / "result.json",
        control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
        latest_active_run_file=root / "latest_active_run.json",
        latest_completed_run_file=root / "latest_completed_run.json",
    )


class RuntimeV2LatestRunTests(unittest.TestCase):
    def test_only_single_runtime_api_updates_latest_and_result_snapshots(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _latest_run_config(root)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")

            gui_payload = build_gui_status_payload(
                {"status": "ok", "code": "OK", "queue_status": "completed"},
                run_id="runtime-run-1",
                mode="control_loop",
                stage="finished",
                exit_code=0,
            )
            artifact_path = root / "artifacts" / "result.mp4"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            _ = artifact_path.write_bytes(b"mp4")

            _ = write_runtime_snapshot(
                config,
                run_id="runtime-run-1",
                mode="control_loop",
                status="ok",
                code="OK",
                debug_log=str(root / "debug.jsonl"),
                gui_payload=gui_payload,
                artifacts=[artifact_path],
                metadata={"run_id": "runtime-run-1", "code": "OK"},
                write_completed=True,
                artifact_root=root,
            )

            latest_join = load_joined_latest_run(config, completed=True)

        self.assertFalse(bool(latest_join["out_of_sync"]))
        pointer = cast(dict[object, object], latest_join["pointer"])
        gui_status = cast(dict[object, object], latest_join["gui_status"])
        result_metadata = cast(dict[object, object], latest_join["result_metadata"])
        self.assertEqual(str(pointer["run_id"]), "runtime-run-1")
        self.assertEqual(str(gui_status["run_id"]), "runtime-run-1")
        self.assertEqual(str(result_metadata["run_id"]), "runtime-run-1")
        self.assertEqual(str(result_metadata["code"]), "OK")

    def test_control_plane_uses_runtime_snapshot_api_without_direct_result_router_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig.from_root(root)
            seed_control_job(
                JobContract(
                    job_id="single-writer-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:single-writer-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )
            runtime_result: dict[str, object] = {
                "status": "ok",
                "code": "OK",
                "worker_result": {
                    "status": "ok",
                    "stage": "synthesize_audio",
                    "error_code": "",
                    "retryable": False,
                    "artifacts": [],
                    "next_jobs": [],
                    "completion": {
                        "state": "completed",
                        "final_output": True,
                        "final_artifact": "speech.wav",
                        "final_artifact_path": str(
                            root
                            / "artifacts"
                            / "qwen3_tts"
                            / "single-writer-job"
                            / "speech.wav"
                        ),
                    },
                },
            }

            with (
                patch(
                    "runtime_v2.control_plane.run_gated", return_value=runtime_result
                ),
                patch(
                    "runtime_v2.control_plane.write_result_router",
                    side_effect=AssertionError(
                        "control_plane must not write result_router directly"
                    ),
                ),
            ):
                result = run_control_loop_once(
                    owner="runtime_v2",
                    config=config,
                    run_id="control-run-single-writer",
                )

            joined = load_joined_latest_run(config, completed=True)

        self.assertEqual(str(result["status"]), "ok")
        self.assertFalse(bool(joined["out_of_sync"]))

    def test_load_joined_latest_run_uses_pointer_specific_paths(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _latest_run_config(root)
            pointer_gui_path = root / "temp" / "gui_status.pointer.json"
            pointer_result_path = root / "temp" / "result.pointer.json"
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            pointer_gui_path.parent.mkdir(parents=True, exist_ok=True)
            pointer_result_path.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "failed", "code": "BROWSER_UNHEALTHY"},
                    run_id="canonical-gui-run",
                    mode="control_loop",
                    stage="finished",
                    exit_code=1,
                ),
                config.gui_status_file,
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "canonical-result-run",
                            "code": "GPT_FLOOR_FAIL",
                        },
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="pointer-run",
                    mode="once",
                    stage="finished",
                    exit_code=0,
                ),
                pointer_gui_path,
            )
            _ = pointer_result_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "artifacts": [],
                        "metadata": {"run_id": "pointer-run", "code": "OK"},
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.latest_completed_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "run_id": "pointer-run",
                        "gui_status_path": str(pointer_gui_path),
                        "result_path": str(pointer_result_path),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            latest_join = load_joined_latest_run(config, completed=True)

        self.assertFalse(bool(latest_join["out_of_sync"]))
        pointer = cast(dict[object, object], latest_join["pointer"])
        gui_status = cast(dict[object, object], latest_join["gui_status"])
        result_metadata = cast(dict[object, object], latest_join["result_metadata"])
        self.assertEqual(str(pointer["run_id"]), "pointer-run")
        self.assertEqual(str(gui_status["run_id"]), "pointer-run")
        self.assertEqual(str(result_metadata["run_id"]), "pointer-run")
        self.assertEqual(str(result_metadata["code"]), "OK")

    def test_latest_join_flags_out_of_sync_when_gui_and_result_run_ids_diverge(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _latest_run_config(root)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "failed", "code": "BROWSER_UNHEALTHY"},
                    run_id="gui-run",
                    mode="control_loop",
                    stage="finished",
                    exit_code=1,
                ),
                config.gui_status_file,
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "artifacts": [],
                        "metadata": {"run_id": "result-run", "code": "GPT_FLOOR_FAIL"},
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.latest_completed_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "run_id": "result-run",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            latest_join = load_joined_latest_run(config, completed=True)

        self.assertTrue(bool(latest_join["out_of_sync"]))
        reasons = cast(list[object], latest_join["reasons"])
        self.assertIn("gui_run_id_mismatch", [str(reason) for reason in reasons])

    def test_latest_join_flags_out_of_sync_when_pointer_run_id_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _latest_run_config(root)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="gui-run",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "artifacts": [],
                        "metadata": {"run_id": "result-run", "code": "OK"},
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.latest_completed_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "run_id": "",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            latest_join = load_joined_latest_run(config, completed=True)

        self.assertTrue(bool(latest_join["out_of_sync"]))
        reasons = cast(list[object], latest_join["reasons"])
        self.assertIn("pointer_run_id_missing", [str(reason) for reason in reasons])

    def test_bootstrap_does_not_overwrite_existing_latest_completed_pointer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _latest_run_config(root)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "failed", "code": "native_genspark_not_implemented"},
                    run_id="existing-run",
                    mode="control_loop",
                    stage="finished",
                    exit_code=1,
                ),
                config.gui_status_file,
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "existing-run",
                            "code": "native_genspark_not_implemented",
                        },
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.latest_completed_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "run_id": "existing-run",
                        "mode": "control_loop",
                        "status": "failed",
                        "code": "native_genspark_not_implemented",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            ensure_runtime_bootstrap(
                config, run_id="control-bootstrap", mode="control_loop"
            )
            latest_join = load_joined_latest_run(config, completed=True)

        pointer = cast(dict[object, object], latest_join["pointer"])
        self.assertEqual(str(pointer["run_id"]), "existing-run")
        self.assertFalse(bool(latest_join["out_of_sync"]))


if __name__ == "__main__":
    _ = unittest.main()

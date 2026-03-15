from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from time import time
from typing import cast
from unittest.mock import patch

from runtime_v2.config import RuntimeConfig
from runtime_v2.evidence import (
    load_latest_result_metadata,
    load_runtime_readiness,
    resolve_snapshot_run_id,
)
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status


def _evidence_config(root: Path) -> RuntimeConfig:
    return RuntimeConfig(
        gui_status_file=root / "health" / "gui_status.json",
        browser_health_file=root / "health" / "browser_health.json",
        browser_registry_file=root / "health" / "browser_session_registry.json",
        lease_file=root / "health" / "gpu_scheduler_health.json",
        gpt_status_file=root / "health" / "gpt_status.json",
        worker_registry_file=root / "health" / "worker_registry.json",
        result_router_file=root / "evidence" / "result.json",
        control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
        latest_active_run_file=root / "latest_active_run.json",
        latest_completed_run_file=root / "latest_completed_run.json",
        artifact_root=root / "artifacts",
    )


def _write_ready_gpu_and_worker_state(
    config: RuntimeConfig, *, checked_at: float
) -> None:
    config.lease_file.parent.mkdir(parents=True, exist_ok=True)
    _ = config.lease_file.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "runtime": "runtime_v2",
                "workload": "qwen3_tts",
                "lock_key": "lock:qwen3_tts",
                "event": "acquired",
                "checked_at": checked_at,
                "lease": None,
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    config.worker_registry_file.parent.mkdir(parents=True, exist_ok=True)
    _ = config.worker_registry_file.write_text(
        json.dumps(
            {
                "qwen3_tts": {
                    "workload": "qwen3_tts",
                    "state": "idle",
                    "run_id": "run-1",
                    "last_seen": checked_at,
                    "progress_ts": checked_at,
                }
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


class RuntimeV2EvidenceTests(unittest.TestCase):
    def test_load_latest_result_metadata_uses_runtime_config_default_when_unspecified(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.result_router_file.write_text(
                json.dumps(
                    {"code": "OK", "metadata": {"run_id": "runtime-run-1"}},
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with patch("runtime_v2.evidence.RuntimeConfig", return_value=config):
                metadata = load_latest_result_metadata()

        self.assertEqual(metadata["run_id"], "runtime-run-1")
        self.assertEqual(metadata["code"], "OK")

    def test_resolve_snapshot_run_id_prefers_result_metadata_over_pointer(self) -> None:
        latest_join = cast(
            dict[str, object],
            {
                "pointer": {"run_id": "pointer-run"},
                "gui_status": {"run_id": "gui-run"},
            },
        )
        result_metadata = cast(
            dict[str, object],
            {
                "run_id": "result-run",
                "canonical_handoff": {"run_id": "handoff-run"},
            },
        )

        run_id, source = resolve_snapshot_run_id(latest_join, result_metadata)

        self.assertEqual(run_id, "result-run")
        self.assertEqual(source, "result_metadata.run_id")

    def test_readiness_reports_single_snapshot_run_id_even_when_latest_is_drifted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.parent.mkdir(
                parents=True, exist_ok=True
            )
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
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "gui-run",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "gui-run",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "result-run",
                            "code": "OK",
                            "canonical_handoff": {"run_id": "result-run"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "pointer-run",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)

            readiness = load_runtime_readiness(config, completed=True)

        self.assertFalse(bool(readiness["ready"]))
        self.assertEqual(readiness["snapshot_run_id"], "result-run")
        self.assertEqual(readiness["snapshot_run_id_source"], "result_metadata.run_id")

    def test_readiness_blocks_when_latest_pointer_run_id_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.parent.mkdir(
                parents=True, exist_ok=True
            )
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
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "gui-run",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "gui-run",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {"name": "default", "status": "OK", "last_seen_at": 1.0e12}
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
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
                        "checked_at": fresh_checked_at,
                        "run_id": "",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)

            readiness = load_runtime_readiness(config, completed=True)

        self.assertFalse(bool(readiness["ready"]))
        blockers = cast(list[object], readiness["blockers"])
        self.assertIsInstance(blockers, list)
        blocker_codes: set[str] = set()
        for item in blockers:
            if not isinstance(item, dict):
                continue
            blocker = cast(dict[object, object], item)
            blocker_codes.add(str(blocker["code"]))
        self.assertIn("LATEST_RUN_POINTER_INVALID", blocker_codes)

    def test_readiness_fail_closes_when_gpt_min_ok_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.parent.mkdir(
                parents=True, exist_ok=True
            )
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 0,
                        "min_ok": "bad-min-ok",
                        "floor_breached": True,
                        "breach_started_at": 1.0,
                        "breach_sec": 1,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": True,
                        "warning_active": True,
                        "last_warning_at": 1.0,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 1,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {"name": "default", "status": "FAILED", "last_seen_at": 1.0}
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)

            readiness = load_runtime_readiness(config, completed=True)

        self.assertFalse(bool(readiness["ready"]))
        blockers = cast(list[object], readiness["blockers"])
        blocker_codes: set[str] = set()
        for item in blockers:
            if not isinstance(item, dict):
                continue
            blocker = cast(dict[object, object], item)
            blocker_codes.add(str(blocker["code"]))
        self.assertIn("GPT_FLOOR_FAIL", blocker_codes)

    def test_readiness_treats_restart_exhausted_latest_result_as_blocker(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.gui_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "status": "blocked",
                        "code": "BROWSER_RESTART_EXHAUSTED",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "floor_breached": False,
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "run-1",
                            "code": "BROWSER_RESTART_EXHAUSTED",
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)

            readiness = load_runtime_readiness(config, completed=True)

        self.assertFalse(bool(readiness["ready"]))
        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertIn("BROWSER_RESTART_EXHAUSTED", blocker_codes)

    def test_readiness_marks_latest_result_mismatch_warning_in_details(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.gui_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "status": "blocked",
                        "code": "BROWSER_RESTART_EXHAUSTED",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "floor_breached": False,
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "run-1",
                            "code": "BROWSER_RESTART_EXHAUSTED",
                            "canonical_handoff": {
                                "warning_worker_error_code_mismatch": "worker_error_code=BROWSER_BLOCKED error_code=BROWSER_RESTART_EXHAUSTED"
                            },
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        latest_result_blockers = [
            cast(dict[object, object], item)
            for item in blockers
            if isinstance(item, dict) and item.get("axis") == "latest_result"
        ]
        self.assertEqual(len(latest_result_blockers), 1)
        details = cast(dict[object, object], latest_result_blockers[0]["details"])
        self.assertTrue(bool(details["warning_worker_error_code_mismatch"]))

    def test_readiness_ignores_stale_restart_exhausted_latest_result(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            now_value = round(time(), 3)
            stale_checked_at = now_value - 301.0
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.gui_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": now_value,
                        "status": "ok",
                        "code": "OK",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": now_value,
                        "healthy_count": 1,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": now_value,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": now_value,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": stale_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "run-1",
                            "code": "BROWSER_RESTART_EXHAUSTED",
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
                        "checked_at": now_value,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=now_value)

            readiness = load_runtime_readiness(config, completed=True)

        self.assertTrue(bool(readiness["ready"]))
        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertNotIn("BROWSER_RESTART_EXHAUSTED", blocker_codes)

    def test_readiness_fail_closes_when_gpt_status_is_stale(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.parent.mkdir(
                parents=True, exist_ok=True
            )
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 1,
                        "healthy_count": 1,
                        "unhealthy_count": 0,
                        "sessions": [
                            {
                                "service": "chatgpt",
                                "group": "llm",
                                "healthy": True,
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 1,
                        "sessions": [{"service": "chatgpt", "group": "llm"}],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": 1.0,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)

            readiness = load_runtime_readiness(config, completed=True)

        self.assertFalse(bool(readiness["ready"]))
        blockers = cast(list[object], readiness["blockers"])
        blocker_codes: set[str] = set()
        for item in blockers:
            if not isinstance(item, dict):
                continue
            blocker = cast(dict[object, object], item)
            blocker_codes.add(str(blocker["code"]))
        self.assertIn("GPT_STATUS_STALE", blocker_codes)

    def test_readiness_allows_fresh_gpt_status_when_floor_is_healthy(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.parent.mkdir(
                parents=True, exist_ok=True
            )
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 1,
                        "healthy_count": 1,
                        "unhealthy_count": 0,
                        "sessions": [
                            {
                                "service": "chatgpt",
                                "group": "llm",
                                "healthy": True,
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 1,
                        "sessions": [{"service": "chatgpt", "group": "llm"}],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)

            readiness = load_runtime_readiness(config, completed=True)

        self.assertTrue(bool(readiness["ready"]))
        self.assertEqual(str(readiness["code"]), "OK")

    def test_readiness_blocks_when_gpu_health_is_stale(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            stale_checked_at = fresh_checked_at - float(config.running_stale_sec + 10)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.lease_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "workload": "qwen3_tts",
                        "lock_key": "lock:qwen3_tts",
                        "event": "acquired",
                        "checked_at": stale_checked_at,
                        "lease": None,
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.worker_registry_file.write_text(
                json.dumps(
                    {
                        "qwen3_tts": {
                            "workload": "qwen3_tts",
                            "state": "idle",
                            "run_id": "run-1",
                            "last_seen": fresh_checked_at,
                            "progress_ts": fresh_checked_at,
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertIn("GPU_HEALTH_STALE", blocker_codes)

    def test_readiness_allows_stale_idle_gpu_health_without_lease(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            stale_checked_at = fresh_checked_at - float(config.running_stale_sec + 10)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.lease_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "workload": "qwen3_tts",
                        "lock_key": "lock:qwen3_tts",
                        "event": "idle",
                        "checked_at": stale_checked_at,
                        "lease": None,
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.worker_registry_file.write_text(
                json.dumps({}, ensure_ascii=True), encoding="utf-8"
            )

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertNotIn("GPU_HEALTH_STALE", blocker_codes)

    def test_readiness_allows_stale_released_gpu_health_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            stale_checked_at = fresh_checked_at - float(config.running_stale_sec + 10)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.lease_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "workload": "qwen3_tts",
                        "lock_key": "lock:qwen3_tts",
                        "event": "lock_release",
                        "checked_at": stale_checked_at,
                        "lease": {
                            "key": "lock:qwen3_tts",
                            "owner": "runtime_v2",
                            "token": 1,
                            "expires_at": stale_checked_at,
                            "run_id": "run-1",
                            "pid": 1234,
                            "started_at": stale_checked_at,
                            "host": "test-host",
                        },
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.worker_registry_file.write_text(
                json.dumps({}, ensure_ascii=True), encoding="utf-8"
            )

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertNotIn("GPU_HEALTH_STALE", blocker_codes)

    def test_readiness_blocks_when_worker_registry_has_stalled_workload(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            stale_progress = fresh_checked_at - float(
                config.progress_stall_timeout_sec + 10
            )
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)
            _ = config.worker_registry_file.write_text(
                json.dumps(
                    {
                        "qwen3_tts": {
                            "workload": "qwen3_tts",
                            "state": "running",
                            "run_id": "run-1",
                            "last_seen": fresh_checked_at,
                            "progress_ts": stale_progress,
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertIn("WORKER_STALL_DETECTED", blocker_codes)

    def test_readiness_does_not_treat_idle_worker_entries_as_stalled(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            stale_progress = fresh_checked_at - float(
                config.progress_stall_timeout_sec + 10
            )
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {"run_id": "run-1", "code": "OK"},
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)
            _ = config.worker_registry_file.write_text(
                json.dumps(
                    {
                        "qwen3_tts": {
                            "workload": "qwen3_tts",
                            "state": "idle",
                            "run_id": "run-1",
                            "last_seen": fresh_checked_at,
                            "progress_ts": stale_progress,
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertNotIn("WORKER_STALL_DETECTED", blocker_codes)

    def test_readiness_blocks_when_promotion_gate_d_is_missing_final_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)
            asset_root = root / "artifacts" / "render" / "render-run-1"
            qwen_audio = (
                config.artifact_root / "qwen3_tts" / "qwen3-run-1" / "speech.flac"
            )
            qwen_audio.parent.mkdir(parents=True, exist_ok=True)
            qwen_audio.write_bytes(b"wav")
            asset_root.mkdir(parents=True, exist_ok=True)
            _ = (asset_root / "asset_manifest.json").write_text(
                json.dumps(
                    {
                        "roles": {
                            "image_primary": "D:/img.png",
                            "thumb_primary": "D:/thumb.png",
                            "voice_json": "D:/voice.json",
                            "stage2.scene_01.genspark": "D:/img.png",
                            "stage2.scene_02.geminigen": "D:/video.mp4",
                            "stage2.scene_00.kenburns": "D:/ken.mp4",
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "run-1",
                            "code": "OK",
                            "final_output": False,
                            "final_artifact_path": "",
                            "asset_manifest_path": str(
                                (asset_root / "asset_manifest.json").resolve()
                            ),
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertIn("PROMOTION_GATE_D_FAIL", blocker_codes)

    def test_readiness_exposes_promotion_gates_when_all_gate_inputs_are_present(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)
            asset_root = root / "artifacts" / "render" / "render-run-1"
            output_dir = asset_root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            final_artifact = output_dir / "render_final.mp4"
            final_artifact.write_bytes(b"mp4")
            qwen_audio = (
                config.artifact_root / "qwen3_tts" / "qwen3-run-1" / "speech.flac"
            )
            qwen_audio.parent.mkdir(parents=True, exist_ok=True)
            qwen_audio.write_bytes(b"wav")
            _ = (asset_root / "asset_manifest.json").write_text(
                json.dumps(
                    {
                        "roles": {
                            "image_primary": "D:/img.png",
                            "thumb_primary": "D:/thumb.png",
                            "voice_json": "D:/voice.json",
                            "stage2.scene_01.genspark": "D:/img.png",
                            "stage2.scene_02.geminigen": "D:/video.mp4",
                            "stage2.scene_00.kenburns": "D:/ken.mp4",
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "run-1",
                            "code": "OK",
                            "final_output": True,
                            "final_artifact_path": str(final_artifact.resolve()),
                            "asset_manifest_path": str(
                                (asset_root / "asset_manifest.json").resolve()
                            ),
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            readiness = load_runtime_readiness(config, completed=True)

        gates = cast(
            dict[object, object],
            cast(dict[object, object], readiness["promotion_gates"])["gates"],
        )
        self.assertTrue(bool(cast(dict[object, object], gates["A"])["passed"]))
        self.assertTrue(bool(cast(dict[object, object], gates["B"])["passed"]))
        self.assertTrue(bool(cast(dict[object, object], gates["C"])["passed"]))
        self.assertTrue(bool(cast(dict[object, object], gates["D"])["passed"]))

    def test_readiness_blocks_when_gate_c_has_empty_kenburns_role(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)
            asset_root = root / "artifacts" / "render" / "render-run-1"
            output_dir = asset_root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            final_artifact = output_dir / "render_final.mp4"
            final_artifact.write_bytes(b"mp4")
            qwen_audio = (
                config.artifact_root / "qwen3_tts" / "qwen3-run-1" / "speech.flac"
            )
            qwen_audio.parent.mkdir(parents=True, exist_ok=True)
            qwen_audio.write_bytes(b"wav")
            _ = (asset_root / "asset_manifest.json").write_text(
                json.dumps(
                    {
                        "roles": {
                            "image_primary": "D:/img.png",
                            "thumb_primary": "D:/thumb.png",
                            "voice_json": "D:/voice.json",
                            "stage2.scene_01.genspark": "D:/img.png",
                            "stage2.scene_02.geminigen": "D:/video.mp4",
                            "stage2.scene_00.kenburns": "",
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "run-1",
                            "code": "OK",
                            "final_output": True,
                            "final_artifact_path": str(final_artifact.resolve()),
                            "asset_manifest_path": str(
                                (asset_root / "asset_manifest.json").resolve()
                            ),
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            readiness = load_runtime_readiness(config, completed=True)

        blockers = cast(list[object], readiness["blockers"])
        blocker_codes = {
            str(cast(dict[object, object], item)["code"])
            for item in blockers
            if isinstance(item, dict)
        }
        self.assertIn("PROMOTION_GATE_C_FAIL", blocker_codes)

    def test_readiness_blocks_when_gate_c_has_no_current_session_audio(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _evidence_config(root)
            fresh_checked_at = round(time(), 3)
            config.gui_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_health_file.parent.mkdir(parents=True, exist_ok=True)
            config.browser_registry_file.parent.mkdir(parents=True, exist_ok=True)
            config.gpt_status_file.parent.mkdir(parents=True, exist_ok=True)
            config.result_router_file.parent.mkdir(parents=True, exist_ok=True)
            config.latest_completed_run_file.parent.mkdir(parents=True, exist_ok=True)
            config.control_plane_events_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.control_plane_events_file.write_text("", encoding="utf-8")
            _ = write_gui_status(
                build_gui_status_payload(
                    {"status": "ok", "code": "OK"},
                    run_id="run-1",
                    mode="control_loop",
                    stage="finished",
                    exit_code=0,
                ),
                config.gui_status_file,
            )
            _ = config.browser_health_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "healthy_count": 0,
                        "unhealthy_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.browser_registry_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "run_id": "run-1",
                        "checked_at": fresh_checked_at,
                        "session_count": 0,
                        "sessions": [],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.gpt_status_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "ok_count": 1,
                        "min_ok": 1,
                        "floor_breached": False,
                        "breach_started_at": None,
                        "breach_sec": 0,
                        "pending_boot": 0,
                        "last_spawn_at": None,
                        "spawn_fail_count": 0,
                        "spawn_needed": False,
                        "warning_active": False,
                        "last_warning_at": None,
                        "cooldown_sec": 300,
                        "cooldown_elapsed_sec": 300,
                        "hourly_spawn_count": 0,
                        "spawn_history": [],
                        "endpoints": [
                            {
                                "name": "chatgpt",
                                "status": "OK",
                                "last_seen_at": fresh_checked_at,
                            }
                        ],
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _write_ready_gpu_and_worker_state(config, checked_at=fresh_checked_at)
            asset_root = root / "artifacts" / "render" / "render-run-1"
            output_dir = asset_root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            final_artifact = output_dir / "render_final.mp4"
            final_artifact.write_bytes(b"mp4")
            _ = (asset_root / "asset_manifest.json").write_text(
                json.dumps(
                    {
                        "roles": {
                            "image_primary": "D:/img.png",
                            "thumb_primary": "D:/thumb.png",
                            "voice_json": "D:/voice.json",
                            "stage2.scene_01.genspark": "D:/img.png",
                            "stage2.scene_02.geminigen": "D:/video.mp4",
                            "stage2.scene_00.kenburns": "D:/ken.mp4",
                        }
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            _ = config.result_router_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "runtime": "runtime_v2",
                        "checked_at": fresh_checked_at,
                        "artifacts": [],
                        "metadata": {
                            "run_id": "run-1",
                            "code": "OK",
                            "final_output": True,
                            "final_artifact_path": str(final_artifact.resolve()),
                            "asset_manifest_path": str(
                                (asset_root / "asset_manifest.json").resolve()
                            ),
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
                        "checked_at": fresh_checked_at,
                        "run_id": "run-1",
                        "gui_status_path": str(config.gui_status_file),
                        "result_path": str(config.result_router_file),
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            readiness = load_runtime_readiness(config, completed=True)

        gates = cast(
            dict[object, object],
            cast(dict[object, object], readiness["promotion_gates"])["gates"],
        )
        self.assertFalse(bool(cast(dict[object, object], gates["C"])["passed"]))
        self.assertEqual(
            cast(dict[object, object], gates["C"])["reason"],
            "missing_voice_json_audio_or_kenburns_role",
        )


if __name__ == "__main__":
    _ = unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.evidence import load_runtime_readiness
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status


def _evidence_config(root: Path) -> RuntimeConfig:
    return RuntimeConfig(
        gui_status_file=root / "health" / "gui_status.json",
        browser_health_file=root / "health" / "browser_health.json",
        browser_registry_file=root / "health" / "browser_session_registry.json",
        gpt_status_file=root / "health" / "gpt_status.json",
        result_router_file=root / "evidence" / "result.json",
        control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
        latest_active_run_file=root / "latest_active_run.json",
        latest_completed_run_file=root / "latest_completed_run.json",
    )


class RuntimeV2EvidenceTests(unittest.TestCase):
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

            readiness = load_runtime_readiness(config, completed=True)

        self.assertTrue(bool(readiness["ready"]))
        self.assertEqual(str(readiness["code"]), "OK")


if __name__ == "__main__":
    _ = unittest.main()

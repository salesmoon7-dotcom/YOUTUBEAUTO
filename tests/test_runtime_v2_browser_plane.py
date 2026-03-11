from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from time import time
from typing import cast
from unittest.mock import patch

from runtime_v2.browser.manager import (
    BrowserManager,
    BrowserSession,
    _launch_debug_browser,
    _manager_owns_browser,
    _refresh_session_ready_marker,
    _start_url_for_service,
    acquire_profile_lock,
    build_browser_inventory,
    build_profile_storage_report,
    default_browser_sessions_by_service,
    open_browser_for_login,
)
from runtime_v2.config import RuntimeConfig, browser_session_root
from runtime_v2.browser.registry import load_browser_registry
from runtime_v2.browser.supervisor import BrowserSupervisor, _prune_restart_history
from runtime_v2.evidence import load_latest_result_metadata
from runtime_v2.supervisor import run_once


class RuntimeV2BrowserPlaneTests(unittest.TestCase):
    def test_browser_inventory_matches_runtime_browser_contracts(self) -> None:
        inventory = build_browser_inventory()
        self.assertIn("geminigen", inventory)
        self.assertEqual(inventory["geminigen"]["browser"], "uc")
        self.assertEqual(inventory["genspark"]["browser"], "edge")

    def test_service_start_urls_follow_runtime_defaults(self) -> None:
        self.assertEqual(_start_url_for_service("chatgpt"), "https://chatgpt.com/")
        self.assertEqual(_start_url_for_service("genspark"), "https://www.genspark.ai/")
        self.assertEqual(
            _start_url_for_service("seaart"),
            "https://www.seaart.ai/ko/create/image?id=d4kssode878c7387fae0&model_ver_no=ef24b47a8d618127c9342fd0635aedb9",
        )
        self.assertEqual(
            _start_url_for_service("geminigen"), "https://geminigen.ai/app/video-gen"
        )
        self.assertEqual(
            _start_url_for_service("canva"),
            "https://www.canva.com/design/DAHAnm1uUBA/-FWB5gw_ir1U7Ls0ZHF9Ig/edit",
        )

    def test_launch_debug_browser_uses_service_start_url(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            session = BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str((Path(tmp_dir) / "chatgpt-primary").resolve()),
                status="stopped",
            )

            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port",
                    side_effect=[False, True],
                ),
                patch(
                    "runtime_v2.browser.manager._resolve_browser_executable",
                    return_value=Path(r"C:\\Chrome\\chrome.exe"),
                ),
                patch("runtime_v2.browser.manager.subprocess.Popen") as popen,
            ):
                launched = _launch_debug_browser(session)

        self.assertTrue(launched)
        command = popen.call_args.args[0]
        self.assertEqual(command[-1], "https://chatgpt.com/")

    def test_launch_debug_browser_keeps_profile_lock_with_browser_pid(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            session = BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str(profile_dir.resolve()),
                status="stopped",
            )

            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port",
                    side_effect=[False, True],
                ),
                patch(
                    "runtime_v2.browser.manager._resolve_browser_executable",
                    return_value=Path(r"C:\\Chrome\\chrome.exe"),
                ),
                patch("runtime_v2.browser.manager.subprocess.Popen") as popen,
            ):
                popen.return_value.configure_mock(pid=54321)
                launched = _launch_debug_browser(session)

            lock_file = profile_dir / ".runtime_v2.profile.lock"
            self.assertTrue(launched)
            self.assertTrue(lock_file.exists())
            lock_payload = cast(
                dict[object, object],
                json.loads(lock_file.read_text(encoding="utf-8")),
            )
            self.assertEqual(int(cast(int, lock_payload["pid"])), 54321)
            self.assertEqual(int(cast(int, lock_payload["browser_pid"])), 54321)

    def test_second_acquire_sees_busy_lock_after_successful_launch(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            session = BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str(profile_dir.resolve()),
                status="stopped",
            )

            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port",
                    side_effect=[False, True, True],
                ),
                patch(
                    "runtime_v2.browser.manager._resolve_browser_executable",
                    return_value=Path(r"C:\\Chrome\\chrome.exe"),
                ),
                patch("runtime_v2.browser.manager._pid_is_running", return_value=True),
                patch("runtime_v2.browser.manager.subprocess.Popen") as popen,
            ):
                popen.return_value.configure_mock(pid=54321)
                launched = _launch_debug_browser(session)
                second = acquire_profile_lock(
                    str(profile_dir.resolve()),
                    service="chatgpt",
                    session_id="primary",
                    port=9222,
                )

        self.assertTrue(launched)
        self.assertFalse(bool(second["locked"]))
        self.assertEqual(str(second["lock_state"]), "busy")

    def test_default_browser_sessions_uses_runtime_port_and_profile_overrides(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            config_path = Path(tmp_dir) / "app_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sessions": {
                            "edge_debug": "C:/edge_debug",
                            "seaart_chrome": "C:/chrome_seaart",
                            "geminigen_chrome_userdata": "D:/profiles/geminigen",
                            "canva_chrome": "C:/chrome_canva",
                        },
                        "ports": {
                            "genspark_edge": 9230,
                            "seaart_chrome": 9225,
                            "geminigen_uc": 9556,
                            "canva_chrome": 9227,
                        },
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"RUNTIME_V2_APP_CONFIG": str(config_path.resolve())},
                clear=False,
            ):
                sessions = BrowserManager().sessions

        session_map = {session.service: session for session in sessions}
        self.assertEqual(session_map["genspark"].port, 9230)
        self.assertEqual(session_map["seaart"].port, 9225)
        self.assertEqual(session_map["canva"].port, 9227)
        self.assertEqual(
            session_map["genspark"].profile_dir, str(Path("C:/edge_debug").resolve())
        )
        self.assertEqual(
            session_map["seaart"].profile_dir, str(Path("C:/chrome_seaart").resolve())
        )
        self.assertEqual(
            session_map["canva"].profile_dir, str(Path("C:/chrome_canva").resolve())
        )
        self.assertEqual(
            session_map["geminigen"].profile_dir,
            str(Path("D:/profiles/geminigen").resolve()),
        )
        self.assertEqual(session_map["geminigen"].port, 9556)

    def test_geminigen_uses_uc_browser_contract(self) -> None:
        session = default_browser_sessions_by_service()["geminigen"]
        self.assertEqual(session.browser_family, "uc")

    def test_manager_owns_geminigen_browser_session(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            lock_file = Path(tmp_dir) / "browser_plane.lock"
            now = round(time(), 3)
            _ = lock_file.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "acquired_at": now,
                        "last_heartbeat_at": now,
                        "run_id": "geminigen-owned-test",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"RUNTIME_V2_BROWSER_PLANE_LOCK": str(lock_file.resolve())},
                clear=False,
            ):
                self.assertTrue(_manager_owns_browser("geminigen"))

    def test_refresh_session_ready_marker_creates_marker_for_ready_tab(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "seaart-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            session = BrowserSession(
                service="seaart",
                group="image",
                session_id="primary",
                port=9225,
                profile_dir=str(profile_dir.resolve()),
                status="running",
            )

            with patch(
                "runtime_v2.browser.manager._list_debug_tabs",
                return_value=[
                    {
                        "url": "https://www.seaart.ai/ko/create/image?id=d4kssode878c7387fae0&model_ver_no=ef24b47a8d618127c9342fd0635aedb9",
                        "title": "Seaart",
                    }
                ],
            ):
                ready = _refresh_session_ready_marker(session)
            self.assertTrue(ready)
            self.assertTrue((profile_dir / "session_ready.json").exists())

    def test_manual_login_open_marks_session_ready_after_expected_tab_detected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            session = BrowserSession(
                service="seaart",
                group="image",
                session_id="primary",
                port=9225,
                profile_dir=str((Path(tmp_dir) / "seaart-primary").resolve()),
                status="stopped",
            )
            manager = BrowserManager(sessions=[session])

            with patch(
                "runtime_v2.browser.manager._launch_debug_browser", return_value=True
            ):
                result = open_browser_for_login("seaart", manager=manager)

        self.assertEqual(result["service"], "seaart")
        self.assertTrue(bool(result["profile_dir"]))
        self.assertEqual(result["start_url"], _start_url_for_service("seaart"))

    def test_refresh_session_ready_marker_removes_marker_for_login_page(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "canva-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            ready_file = profile_dir / "session_ready.json"
            _ = ready_file.write_text('{"ready": true}', encoding="utf-8")
            session = BrowserSession(
                service="canva",
                group="design",
                session_id="primary",
                port=9227,
                profile_dir=str(profile_dir.resolve()),
                status="running",
            )

            with patch(
                "runtime_v2.browser.manager._list_debug_tabs",
                return_value=[
                    {
                        "url": "https://www.canva.com/ko_kr/login/?redirect=%2Fdesign%2FDAHAnm1uUBA%2F-FWB5gw_ir1U7Ls0ZHF9Ig%2Fedit",
                        "title": "Canva login",
                    }
                ],
            ):
                ready = _refresh_session_ready_marker(session)
            self.assertFalse(ready)
            self.assertFalse(ready_file.exists())

    def test_chatgpt_login_page_removes_ready_marker(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            ready_file = profile_dir / "session_ready.json"
            _ = ready_file.write_text('{"ready": true}', encoding="utf-8")
            session = BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str(profile_dir.resolve()),
                status="running",
            )

            with patch(
                "runtime_v2.browser.manager._list_debug_tabs",
                return_value=[
                    {"url": "https://chatgpt.com/auth/login", "title": "ChatGPT login"}
                ],
            ):
                ready = _refresh_session_ready_marker(session)

        self.assertFalse(ready)
        self.assertFalse(ready_file.exists())

    def test_browser_health_marks_login_page_as_login_required_without_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "genspark-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            session = BrowserSession(
                service="genspark",
                group="llm",
                session_id="primary",
                port=9230,
                profile_dir=str(profile_dir.resolve()),
                status="running",
            )
            manager = BrowserManager(sessions=[session])
            manager.running = True
            supervisor = BrowserSupervisor(manager)

            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port", return_value=True
                ),
                patch(
                    "runtime_v2.browser.manager._list_debug_tabs",
                    return_value=[
                        {"url": "https://www.genspark.ai/login", "title": "login"}
                    ],
                ),
                patch(
                    "runtime_v2.browser.manager._launch_debug_browser",
                    return_value=True,
                ) as launch_browser,
            ):
                result = supervisor.tick(
                    registry_file=Path(tmp_dir) / "browser_session_registry.json",
                    health_file=Path(tmp_dir) / "browser_health.json",
                    run_id="browser-run-login-required",
                    recover_unhealthy=True,
                    restart_threshold=1,
                    cooldown_sec=0,
                )

        self.assertEqual(result["restarted_services"], [])
        launch_browser.assert_not_called()

    def test_supervisor_writes_blocked_browser_event_for_login_required(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "genspark-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            session = BrowserSession(
                service="genspark",
                group="llm",
                session_id="primary",
                port=9230,
                profile_dir=str(profile_dir.resolve()),
                status="running",
            )
            manager = BrowserManager(sessions=[session])
            manager.running = True
            supervisor = BrowserSupervisor(manager)
            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port", return_value=True
                ),
                patch(
                    "runtime_v2.browser.manager._list_debug_tabs",
                    return_value=[
                        {"url": "https://www.genspark.ai/login", "title": "login"}
                    ],
                ),
            ):
                result = supervisor.tick(
                    registry_file=Path(tmp_dir) / "browser_session_registry.json",
                    health_file=Path(tmp_dir) / "browser_health.json",
                    run_id="browser-run-event-login-required",
                    recover_unhealthy=True,
                    restart_threshold=1,
                    cooldown_sec=0,
                )

            event_rows = cast(list[object], result["events"])
            latest = cast(dict[object, object], event_rows[-1])

        self.assertEqual(str(latest["event"]), "browser_supervisor_status")
        self.assertEqual(str(latest["status"]), "login_required")
        self.assertEqual(str(latest["action_result"]), "blocked")
        self.assertEqual(str(latest["tick_id"]), "browser-run-event-login-required")
        self.assertEqual(str(latest["error"]), "")

    def test_supervisor_writes_recovery_event_for_stale_lock_recovery(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            session = BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str(profile_dir.resolve()),
                status="unhealthy",
                consecutive_failures=1,
                lock_state="stale",
                lock_recovered=True,
            )
            manager = BrowserManager(sessions=[session])
            manager.running = True
            supervisor = BrowserSupervisor(manager)
            with (
                patch.object(
                    manager,
                    "session_snapshots",
                    return_value=[session.to_dict(healthy=False)],
                ),
                patch.object(manager, "restart"),
            ):
                result = supervisor.tick(
                    registry_file=Path(tmp_dir) / "browser_session_registry.json",
                    health_file=Path(tmp_dir) / "browser_health.json",
                    run_id="browser-run-event-stale-recovered",
                    recover_unhealthy=True,
                    restart_threshold=1,
                    cooldown_sec=0,
                )

            event_lines = cast(list[object], result["events"])
            recovery_events = [
                cast(dict[object, object], entry)
                for entry in event_lines
                if isinstance(entry, dict)
                and entry.get("event") == "browser_supervisor_recovery"
            ]

        self.assertEqual(len(recovery_events), 1)
        self.assertEqual(str(recovery_events[0]["status"]), "stale_lock_recovered")
        self.assertEqual(str(recovery_events[0]["action"]), "clear_lock")
        self.assertEqual(str(recovery_events[0]["action_result"]), "ok")

    def test_manager_skips_launch_when_fresh_foreign_browser_owner_exists(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            lock_file = Path(tmp_dir) / "browser_plane.lock"
            _ = lock_file.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "acquired_at": round(time(), 3),
                        "last_heartbeat_at": round(time(), 3),
                        "run_id": "foreign-run",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            manager = BrowserManager()

            with (
                patch.dict(
                    os.environ,
                    {"RUNTIME_V2_BROWSER_PLANE_LOCK": str(lock_file.resolve())},
                    clear=False,
                ),
                patch("runtime_v2.browser.manager._pid_is_running", return_value=True),
                patch(
                    "runtime_v2.browser.manager._launch_debug_browser"
                ) as launch_browser,
            ):
                manager.start()

        launch_browser.assert_not_called()
        self.assertTrue(
            all(session.status == "external" for session in manager.sessions)
        )

    def test_manager_takes_over_dead_browser_owner_without_waiting_for_lock_age(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            lock_file = Path(tmp_dir) / "browser_plane.lock"
            _ = lock_file.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "acquired_at": round(time(), 3),
                        "last_heartbeat_at": round(time(), 3),
                        "run_id": "dead-owner",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            manager = BrowserManager(
                sessions=[
                    BrowserSession(
                        service="chatgpt",
                        group="llm",
                        session_id="primary",
                        port=9222,
                        profile_dir=str((Path(tmp_dir) / "chatgpt-primary").resolve()),
                        status="stopped",
                    )
                ]
            )

            with (
                patch.dict(
                    os.environ,
                    {"RUNTIME_V2_BROWSER_PLANE_LOCK": str(lock_file.resolve())},
                    clear=False,
                ),
                patch("runtime_v2.browser.manager._pid_is_running", return_value=False),
                patch(
                    "runtime_v2.browser.manager._launch_debug_browser",
                    return_value=True,
                ) as launch_browser,
            ):
                manager.start()

        launch_browser.assert_called_once()
        self.assertEqual(manager.sessions[0].status, "running")

    def test_supervisor_takes_over_stale_browser_owner_and_emits_event(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            lock_file = Path(tmp_dir) / "browser_plane.lock"
            _ = lock_file.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "acquired_at": 1.0,
                        "last_heartbeat_at": 1.0,
                        "run_id": "stale-owner",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            manager = BrowserManager()
            supervisor = BrowserSupervisor(manager)

            with (
                patch.dict(
                    os.environ,
                    {"RUNTIME_V2_BROWSER_PLANE_LOCK": str(lock_file.resolve())},
                    clear=False,
                ),
                patch("runtime_v2.browser.manager._pid_is_running", return_value=False),
                patch(
                    "runtime_v2.browser.manager._launch_debug_browser",
                    return_value=False,
                ),
            ):
                result = supervisor.tick(
                    registry_file=Path(tmp_dir) / "browser_session_registry.json",
                    health_file=Path(tmp_dir) / "browser_health.json",
                    run_id="browser-owner-takeover",
                    recover_unhealthy=False,
                )

            event_lines = cast(list[object], result["events"])
            ownership_events = [
                cast(dict[object, object], entry)
                for entry in event_lines
                if isinstance(entry, dict)
                and entry.get("event") == "browser_plane_ownership"
            ]

        self.assertEqual(len(ownership_events), 1)
        self.assertEqual(
            str(ownership_events[0]["action_result"]), "ownership_stale_takeover"
        )

    def test_supervisor_escalates_long_lived_busy_lock(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            session = BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str(profile_dir.resolve()),
                status="busy_lock",
                lock_state="busy",
                lock_pid_alive=True,
                lock_age_sec=180.0,
            )
            manager = BrowserManager(sessions=[session])
            manager.running = True
            supervisor = BrowserSupervisor(manager)
            with patch.object(
                manager,
                "session_snapshots",
                return_value=[session.to_dict(healthy=False)],
            ):
                result = supervisor.tick(
                    registry_file=Path(tmp_dir) / "browser_session_registry.json",
                    health_file=Path(tmp_dir) / "browser_health.json",
                    run_id="browser-run-event-busy-lock",
                    recover_unhealthy=True,
                    restart_threshold=1,
                    cooldown_sec=60,
                )

            event_lines = cast(list[object], result["events"])
            escalation_events = [
                cast(dict[object, object], entry)
                for entry in event_lines
                if isinstance(entry, dict)
                and entry.get("event") == "browser_supervisor_escalation"
            ]

        self.assertEqual(len(escalation_events), 1)
        self.assertEqual(str(escalation_events[0]["status"]), "busy_lock")
        self.assertEqual(str(escalation_events[0]["action"]), "escalate")
        self.assertEqual(str(escalation_events[0]["action_result"]), "blocked")

    def test_supervisor_blocks_restart_when_budget_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            session = BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str(profile_dir.resolve()),
                status="unhealthy",
                consecutive_failures=1,
                restart_history=[100.0, 200.0, 250.0],
            )
            manager = BrowserManager(sessions=[session])
            manager.running = True
            supervisor = BrowserSupervisor(manager)
            with (
                patch.object(
                    manager,
                    "session_snapshots",
                    side_effect=[
                        [session.to_dict(healthy=False)],
                        [session.to_dict(healthy=False)],
                    ],
                ),
                patch.object(manager, "restart") as restart,
            ):
                result = supervisor.tick(
                    registry_file=Path(tmp_dir) / "browser_session_registry.json",
                    health_file=Path(tmp_dir) / "browser_health.json",
                    run_id="browser-run-restart-budget",
                    recover_unhealthy=True,
                    restart_threshold=1,
                    cooldown_sec=0,
                    restart_budget=3,
                    restart_window_sec=300,
                    now_fn=lambda: 300.0,
                )

            restart.assert_not_called()
            sessions = cast(list[dict[object, object]], result["sessions"])
            self.assertEqual(str(sessions[0]["status"]), "restart_exhausted")
            self.assertEqual(
                str(sessions[0]["blocked_reason"]), "restart_budget_exhausted"
            )
            event_lines = cast(list[object], result["events"])
            exhausted_events = [
                cast(dict[object, object], entry)
                for entry in event_lines
                if isinstance(entry, dict)
                and entry.get("event") == "browser_restart_budget_exhausted"
            ]
            self.assertEqual(len(exhausted_events), 1)
            self.assertEqual(str(exhausted_events[0]["status"]), "restart_exhausted")
            self.assertEqual(str(exhausted_events[0]["action_result"]), "blocked")

    def test_restart_window_boundary_keeps_exact_cutoff_and_excludes_older_entry(
        self,
    ) -> None:
        retained = _prune_restart_history(
            [299.999, 300.0, 300.001],
            now=600.0,
            window_sec=300,
        )

        self.assertEqual(retained, [300.0, 300.001])

    def test_restart_guard_skips_duplicate_same_session_restart(self) -> None:
        session = BrowserSession(
            service="chatgpt",
            group="llm",
            session_id="primary",
            port=9222,
            profile_dir=str(
                (Path("runtime_v2") / "sessions" / "chatgpt-primary").resolve()
            ),
            status="unhealthy",
        )
        manager = BrowserManager(sessions=[session])
        supervisor = BrowserSupervisor(manager)
        restart_started = threading.Event()
        release_restart = threading.Event()
        calls: list[str] = []

        def slow_restart(service: str) -> None:
            calls.append(service)
            restart_started.set()
            release_restart.wait(timeout=2)

        with patch.object(manager, "restart", side_effect=slow_restart):
            first_result: list[bool] = []

            def run_first() -> None:
                first_result.append(
                    supervisor._restart_session(session.service, session.session_id)
                )

            first_thread = threading.Thread(target=run_first)
            first_thread.start()
            self.assertTrue(restart_started.wait(timeout=2))

            second_result = supervisor._restart_session(
                session.service, session.session_id
            )
            release_restart.set()
            first_thread.join(timeout=2)

        self.assertEqual(calls, ["chatgpt"])
        self.assertEqual(first_result, [True])
        self.assertFalse(second_result)

    def test_same_profile_is_not_opened_by_two_browser_processes(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = str((Path(tmp_dir) / "chrome_seaart").resolve())
            first = acquire_profile_lock(
                profile_dir, service="seaart", session_id="primary", port=9225
            )
            second = acquire_profile_lock(
                profile_dir, service="canva", session_id="primary", port=9227
            )

        self.assertTrue(bool(first["locked"]))
        self.assertFalse(bool(second["locked"]))

    def test_same_service_lock_is_not_reused_by_different_process(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            first = acquire_profile_lock(
                str(profile_dir.resolve()),
                service="chatgpt",
                session_id="primary",
                port=9222,
            )
            lock_file = profile_dir / ".runtime_v2.profile.lock"
            lock_payload = json.loads(lock_file.read_text(encoding="utf-8"))
            lock_payload["pid"] = 999999
            _ = lock_file.write_text(
                json.dumps(lock_payload, ensure_ascii=True), encoding="utf-8"
            )

            second = acquire_profile_lock(
                str(profile_dir.resolve()),
                service="chatgpt",
                session_id="primary",
                port=9222,
            )

        self.assertTrue(bool(first["locked"]))
        self.assertFalse(bool(second["locked"]))

    def test_stale_profile_lock_is_recovered_when_owner_dead_and_port_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            first = acquire_profile_lock(
                str(profile_dir.resolve()),
                service="chatgpt",
                session_id="primary",
                port=9222,
            )
            lock_file = profile_dir / ".runtime_v2.profile.lock"
            lock_payload = json.loads(lock_file.read_text(encoding="utf-8"))
            lock_payload["pid"] = 999999
            _ = lock_file.write_text(
                json.dumps(lock_payload, ensure_ascii=True), encoding="utf-8"
            )

            with (
                patch("runtime_v2.browser.manager._pid_is_running", return_value=False),
                patch(
                    "runtime_v2.browser.manager._probe_local_port", return_value=False
                ),
            ):
                second = acquire_profile_lock(
                    str(profile_dir.resolve()),
                    service="chatgpt",
                    session_id="primary",
                    port=9222,
                )

        self.assertTrue(bool(first["locked"]))
        self.assertTrue(bool(second["locked"]))
        self.assertEqual(str(second["lock_state"]), "stale")
        self.assertTrue(bool(second["recovered"]))

    def test_busy_profile_lock_is_not_recovered_when_owner_still_alive(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            first = acquire_profile_lock(
                str(profile_dir.resolve()),
                service="chatgpt",
                session_id="primary",
                port=9222,
            )
            lock_file = profile_dir / ".runtime_v2.profile.lock"
            lock_payload = json.loads(lock_file.read_text(encoding="utf-8"))
            lock_payload["pid"] = 999999
            _ = lock_file.write_text(
                json.dumps(lock_payload, ensure_ascii=True), encoding="utf-8"
            )

            with patch("runtime_v2.browser.manager._pid_is_running", return_value=True):
                second = acquire_profile_lock(
                    str(profile_dir.resolve()),
                    service="chatgpt",
                    session_id="primary",
                    port=9222,
                )

        self.assertTrue(bool(first["locked"]))
        self.assertFalse(bool(second["locked"]))
        self.assertEqual(str(second["lock_state"]), "busy")
        self.assertFalse(bool(second.get("recovered", False)))

    def test_unknown_profile_lock_metadata_fail_closes(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            lock_file = profile_dir / ".runtime_v2.profile.lock"
            _ = lock_file.write_text('{"service": "chatgpt"}', encoding="utf-8")

            second = acquire_profile_lock(
                str(profile_dir.resolve()),
                service="chatgpt",
                session_id="primary",
                port=9222,
            )

        self.assertFalse(bool(second["locked"]))
        self.assertEqual(str(second["lock_state"]), "unknown")
        self.assertFalse(bool(second.get("metadata_valid", True)))

    def test_browser_health_requires_ready_marker_not_just_open_port(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            profile_dir = Path(tmp_dir) / "chatgpt-primary"
            profile_dir.mkdir(parents=True, exist_ok=True)
            manager = BrowserManager(
                sessions=[
                    BrowserSession(
                        service="chatgpt",
                        group="llm",
                        session_id="primary",
                        port=9222,
                        profile_dir=str(profile_dir.resolve()),
                        status="running",
                    )
                ]
            )
            manager.running = True

            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port", return_value=True
                ),
                patch("runtime_v2.browser.manager._list_debug_tabs", return_value=[]),
            ):
                snapshots = manager.session_snapshots()

        session = cast(dict[object, object], snapshots[0])
        self.assertFalse(bool(session["healthy"]))

    def test_run_once_blocks_browser_workload_when_login_is_required(self) -> None:
        browser_runtime = {
            "sessions": [
                {
                    "service": "chatgpt",
                    "healthy": False,
                    "status": "login_required",
                    "lock_state": "free",
                }
            ]
        }
        with patch("runtime_v2.supervisor.BrowserManager.start"):
            with patch(
                "runtime_v2.supervisor.BrowserSupervisor.tick",
                return_value=browser_runtime,
            ):
                result = run_once(
                    owner="runtime_v2",
                    run_id="chatgpt-run-login-required",
                    workload="chatgpt",
                    config=RuntimeConfig(),
                    worker_runner=lambda: {"status": "ok"},
                )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BROWSER_BLOCKED")

    def test_run_once_marks_browser_unhealthy_as_failed_not_blocked(self) -> None:
        browser_runtime = {
            "sessions": [
                {
                    "service": "chatgpt",
                    "healthy": False,
                    "status": "unhealthy",
                    "lock_state": "free",
                }
            ]
        }
        with patch("runtime_v2.supervisor.BrowserManager.start"):
            with patch(
                "runtime_v2.supervisor.BrowserSupervisor.tick",
                return_value=browser_runtime,
            ):
                result = run_once(
                    owner="runtime_v2",
                    run_id="chatgpt-run-browser-unhealthy",
                    workload="chatgpt",
                    config=RuntimeConfig(),
                    worker_runner=lambda: {"status": "ok"},
                )

        worker_result = cast(dict[object, object], result["worker_result"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_UNHEALTHY")
        self.assertEqual(str(worker_result["stage"]), "runtime_preflight")
        self.assertEqual(str(worker_result["error_code"]), "BROWSER_UNHEALTHY")
        self.assertNotIn("completion", worker_result)

    def test_run_once_blocks_browser_workload_when_restart_budget_is_exhausted(
        self,
    ) -> None:
        browser_runtime = {
            "sessions": [
                {
                    "service": "chatgpt",
                    "healthy": False,
                    "status": "restart_exhausted",
                    "lock_state": "free",
                    "blocked_reason": "restart_budget_exhausted",
                }
            ]
        }
        with patch("runtime_v2.supervisor.BrowserManager.start"):
            with patch(
                "runtime_v2.supervisor.BrowserSupervisor.tick",
                return_value=browser_runtime,
            ):
                result = run_once(
                    owner="runtime_v2",
                    run_id="chatgpt-run-restart-exhausted",
                    workload="chatgpt",
                    config=RuntimeConfig(),
                    worker_runner=lambda: {"status": "ok"},
                )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BROWSER_RESTART_EXHAUSTED")
        worker_result = cast(dict[object, object], result["worker_result"])
        details = cast(dict[object, object], worker_result["details"])
        self.assertEqual(details["blocked_services"], ["chatgpt"])
        self.assertEqual(str(worker_result["error_code"]), "restart_exhausted")

    def test_profile_storage_policy_reports_in_project_vs_external_paths(self) -> None:
        policy = build_profile_storage_report()
        self.assertEqual(policy["chatgpt"]["location_type"], "project_subfolder")
        self.assertEqual(policy["seaart"]["location_type"], "external")

    def test_default_browser_sessions_prefers_external_root_when_present(self) -> None:
        external_chatgpt = browser_session_root() / "chatgpt-primary"
        legacy_chatgpt = (Path("runtime_v2") / "sessions" / "chatgpt-primary").resolve()
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            temp_root = Path(tmp_dir)
            external_dir = temp_root / "external-sessions"
            legacy_dir = temp_root / "legacy-sessions"
            (external_dir / "chatgpt-primary").mkdir(parents=True, exist_ok=True)
            (legacy_dir / "chatgpt-primary").mkdir(parents=True, exist_ok=True)
            with (
                patch(
                    "runtime_v2.browser.manager.browser_session_root",
                    return_value=external_dir,
                ),
                patch("runtime_v2.browser.manager.LEGACY_SESSION_ROOT", legacy_dir),
            ):
                sessions = default_browser_sessions_by_service()

        self.assertNotEqual(external_chatgpt, legacy_chatgpt)
        self.assertEqual(
            sessions["chatgpt"].profile_dir,
            str((external_dir / "chatgpt-primary").resolve()),
        )

    def test_default_browser_sessions_falls_back_to_legacy_root_when_external_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            temp_root = Path(tmp_dir)
            external_dir = temp_root / "external-sessions"
            legacy_dir = temp_root / "legacy-sessions"
            (legacy_dir / "chatgpt-primary").mkdir(parents=True, exist_ok=True)
            with (
                patch(
                    "runtime_v2.browser.manager.browser_session_root",
                    return_value=external_dir,
                ),
                patch("runtime_v2.browser.manager.LEGACY_SESSION_ROOT", legacy_dir),
            ):
                sessions = default_browser_sessions_by_service()

        self.assertEqual(
            sessions["chatgpt"].profile_dir,
            str((legacy_dir / "chatgpt-primary").resolve()),
        )

    def test_supervisor_reconciles_registry_sessions_with_code_defaults(self) -> None:
        registry_session = BrowserSession(
            service="seaart",
            group="image",
            session_id="primary",
            port=9999,
            profile_dir="runtime_v2/sessions/wrong-seaart",
            status="running",
        )
        payload = {
            "schema_version": "1.0",
            "runtime": "runtime_v2",
            "run_id": "browser-run-reconcile",
            "checked_at": 1.0,
            "session_count": 1,
            "sessions": [registry_session.to_dict(healthy=True)],
        }
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            registry_path = Path(tmp_dir) / "browser_session_registry.json"
            health_path = Path(tmp_dir) / "browser_health.json"
            _ = registry_path.write_text(
                json.dumps(payload, ensure_ascii=True), encoding="utf-8"
            )
            manager = BrowserManager()
            default_map = {session.service: session for session in manager.sessions}
            supervisor = BrowserSupervisor(manager)
            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port", return_value=False
                ),
                patch(
                    "runtime_v2.browser.manager._launch_debug_browser",
                    return_value=False,
                ),
            ):
                result = supervisor.tick(
                    registry_file=registry_path,
                    health_file=health_path,
                    run_id="browser-run-reconcile",
                    recover_unhealthy=False,
                )

        sessions = cast(list[dict[object, object]], result["sessions"])
        session_map = {str(item["service"]): item for item in sessions}
        self.assertEqual(
            int(str(session_map["seaart"]["port"])), default_map["seaart"].port
        )
        self.assertEqual(
            str(session_map["seaart"]["profile_dir"]),
            default_map["seaart"].profile_dir,
        )

    def test_supervisor_recovers_only_unhealthy_session(self) -> None:
        sessions = [
            BrowserSession(
                service="chatgpt",
                group="llm",
                session_id="primary",
                port=9222,
                profile_dir=str(
                    (Path("runtime_v2") / "sessions" / "chatgpt-primary").resolve()
                ),
                status="running",
            ),
            BrowserSession(
                service="seaart",
                group="image",
                session_id="primary",
                port=9225,
                profile_dir=str(
                    (Path("runtime_v2") / "sessions" / "seaart-primary").resolve()
                ),
                status="running",
            ),
        ]
        manager = BrowserManager(sessions=sessions)
        manager.running = True
        supervisor = BrowserSupervisor(manager)
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for session in sessions:
                profile_dir = Path(session.profile_dir)
                profile_dir.mkdir(parents=True, exist_ok=True)
                _ = (profile_dir / "session_ready.json").write_text(
                    '{"ready": true}', encoding="utf-8"
                )

            def debug_tabs_for(session: BrowserSession) -> list[dict[str, str]]:
                if session.service == "chatgpt":
                    return [{"url": "https://chatgpt.com/", "title": "ChatGPT"}]
                return [
                    {
                        "url": "https://www.seaart.ai/ko/create/image?id=d4kssode878c7387fae0&model_ver_no=ef24b47a8d618127c9342fd0635aedb9",
                        "title": "SeaArt",
                    }
                ]

            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port", return_value=True
                ),
                patch(
                    "runtime_v2.browser.manager._launch_debug_browser",
                    return_value=True,
                ),
                patch(
                    "runtime_v2.browser.manager._list_debug_tabs",
                    side_effect=debug_tabs_for,
                ),
            ):
                result = supervisor.tick(
                    registry_file=root / "browser_session_registry.json",
                    health_file=root / "browser_health.json",
                    run_id="browser-run-1",
                    force_unhealthy_service="chatgpt",
                    recover_unhealthy=True,
                    restart_threshold=2,
                    cooldown_sec=0,
                )

        self.assertEqual(result["restarted_services"], ["chatgpt"])
        final_summary_obj = result["final_summary"]
        self.assertIsInstance(final_summary_obj, dict)
        if not isinstance(final_summary_obj, dict):
            self.fail("final_summary missing")
        final_sessions_obj = result["sessions"]
        self.assertIsInstance(final_sessions_obj, list)
        if not isinstance(final_sessions_obj, list):
            self.fail("sessions missing")
        snapshots: dict[str, dict[object, object]] = {}
        final_sessions = cast(list[object], final_sessions_obj)
        for item in final_sessions:
            if isinstance(item, dict):
                typed_item = cast(dict[object, object], item)
                snapshots[str(typed_item["service"])] = typed_item
        self.assertTrue(bool(snapshots["chatgpt"]["healthy"]))
        self.assertTrue(bool(snapshots["seaart"]["healthy"]))

    def test_supervisor_tick_returns_health_state_not_policy_contract(self) -> None:
        session = BrowserSession(
            service="chatgpt",
            group="llm",
            session_id="primary",
            port=9222,
            profile_dir=str(
                (Path("runtime_v2") / "sessions" / "chatgpt-primary").resolve()
            ),
            status="running",
        )
        manager = BrowserManager(sessions=[session])
        manager.running = True
        supervisor = BrowserSupervisor(manager)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with (
                patch(
                    "runtime_v2.browser.manager._probe_local_port", return_value=False
                ),
                patch(
                    "runtime_v2.browser.manager._launch_debug_browser",
                    return_value=False,
                ),
            ):
                result = supervisor.tick(
                    registry_file=root / "browser_session_registry.json",
                    health_file=root / "browser_health.json",
                    run_id="browser-run-owner-freeze",
                    recover_unhealthy=False,
                )

        self.assertEqual(
            set(result.keys()),
            {
                "restarted_services",
                "initial_summary",
                "final_summary",
                "sessions",
                "events",
            },
        )
        self.assertNotIn("retryable", result)
        self.assertNotIn("next_jobs", result)
        self.assertNotIn("completion", result)

    def test_registry_load_normalizes_profile_dir_to_absolute_path(self) -> None:
        session = BrowserSession(
            service="chatgpt",
            group="llm",
            session_id="primary",
            port=9222,
            profile_dir="runtime_v2/sessions/chatgpt-primary",
            status="running",
        )
        payload = {
            "schema_version": "1.0",
            "runtime": "runtime_v2",
            "run_id": "browser-run-1",
            "checked_at": 1.0,
            "session_count": 1,
            "sessions": [session.to_dict(healthy=True)],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry_path = Path(tmp_dir) / "browser_session_registry.json"
            _ = registry_path.write_text(
                json.dumps(payload, ensure_ascii=True), encoding="utf-8"
            )
            loaded = load_browser_registry(registry_path)

        self.assertEqual(len(loaded), 1)
        self.assertTrue(Path(loaded[0].profile_dir).is_absolute())

    def test_stage5_latest_run_has_interpretable_failure_or_success_evidence(
        self,
    ) -> None:
        metadata = load_latest_result_metadata()
        self.assertIn(
            str(metadata["code"]),
            {
                "OK",
                "GPT_FLOOR_FAIL",
                "BROWSER_UNHEALTHY",
                "native_genspark_not_implemented",
            },
        )


if __name__ == "__main__":
    _ = unittest.main()

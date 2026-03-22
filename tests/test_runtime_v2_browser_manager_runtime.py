from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_v2.browser.manager as browser_manager
from runtime_v2.browser.manager import BrowserSession
from runtime_v2.browser.manager import BrowserManager
from runtime_v2.browser.supervisor import BrowserSupervisor


class RuntimeV2BrowserManagerRuntimeTests(unittest.TestCase):
    def test_launch_debug_browser_waits_for_debug_endpoint_ready(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            session = BrowserSession(
                service="genspark",
                group="llm",
                session_id="primary",
                port=9333,
                profile_dir=str(Path(tmp_dir) / "profile"),
                status="stopped",
                browser_family="edge",
            )

            readiness = iter([False, False, True])

            with (
                patch(
                    "runtime_v2.browser.manager._resolve_browser_executable",
                    return_value=Path(
                        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
                    ),
                ),
                patch(
                    "runtime_v2.browser.manager.acquire_profile_lock",
                    return_value={"locked": True, "lock_state": "owned"},
                ),
                patch(
                    "runtime_v2.browser.manager._debug_endpoint_ready",
                    side_effect=lambda service, port: next(readiness),
                ) as ready_mock,
                patch("runtime_v2.browser.manager.subprocess.Popen") as popen_mock,
                patch("runtime_v2.browser.manager.sleep"),
            ):
                popen_mock.return_value.pid = 12345
                ok = browser_manager._launch_debug_browser(session)

        self.assertTrue(ok)
        self.assertEqual(ready_mock.call_count, 3)

    def test_session_snapshots_exposes_cdp_endpoint_truth(self) -> None:
        manager = BrowserManager()
        manager.running = True
        manager.sessions = [
            BrowserSession(
                service="genspark",
                group="llm",
                session_id="primary",
                port=9333,
                profile_dir=r"D:\YOUTUBEAUTO_RUNTIME\sessions\genspark-primary",
                status="running",
                browser_family="edge",
            )
        ]

        with (
            patch("runtime_v2.browser.manager._probe_local_port", return_value=True),
            patch(
                "runtime_v2.browser.manager._debug_endpoint_ready", return_value=False
            ),
            patch(
                "runtime_v2.browser.manager._list_debug_tabs",
                return_value=[
                    {
                        "url": "https://www.genspark.ai/agents?type=image_generation_agent"
                    }
                ],
            ),
        ):
            snapshots = manager.session_snapshots()

        self.assertEqual(len(snapshots), 1)
        snapshot = snapshots[0]
        self.assertFalse(bool(snapshot["healthy"]))
        self.assertFalse(bool(snapshot["cdp_endpoint_ready"]))

    def test_browser_manager_restart_returns_launch_result(self) -> None:
        manager = BrowserManager(
            sessions=[
                BrowserSession(
                    service="genspark",
                    group="llm",
                    session_id="primary",
                    port=9333,
                    profile_dir=r"D:\YOUTUBEAUTO_RUNTIME\sessions\genspark-primary",
                    status="stopped",
                    browser_family="edge",
                )
            ]
        )

        with (
            patch(
                "runtime_v2.browser.manager.ensure_browser_plane_ownership",
                return_value={"owned": True},
            ),
            patch(
                "runtime_v2.browser.manager._launch_debug_browser",
                return_value=False,
            ),
        ):
            ok = manager.restart("genspark")

        self.assertFalse(ok)

    def test_browser_supervisor_restart_session_respects_failed_launch(self) -> None:
        supervisor = BrowserSupervisor(BrowserManager())

        with patch.object(
            supervisor.manager,
            "restart",
            return_value=False,
        ):
            ok = supervisor._restart_session("genspark", "primary")

        self.assertFalse(ok)


if __name__ == "__main__":
    _ = unittest.main()

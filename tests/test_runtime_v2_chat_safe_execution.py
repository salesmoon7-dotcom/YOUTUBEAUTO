from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from runtime_v2 import exit_codes
from runtime_v2.browser import manager as browser_manager
from runtime_v2.cli import (
    _copy_legacy_sessions,
    exit_code_from_readiness,
    exit_code_from_status,
    _spawn_detached_probe,
    _write_detached_summary,
    CliArgs,
)
from runtime_v2.config import RuntimeConfig, runtime_state_root
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.job_runtime import prepare_workspace


class RuntimeV2ChatSafeExecutionTests(unittest.TestCase):
    def test_exit_code_from_status_maps_stage6_gpu_blockers(self) -> None:
        self.assertEqual(
            exit_code_from_status("GPU_HEALTH_STALE"), exit_codes.LEASE_BUSY
        )
        self.assertEqual(
            exit_code_from_status("GPU_LEASE_RENEW_FAILED"), exit_codes.LEASE_BUSY
        )

    def test_exit_code_from_readiness_maps_worker_stall_blocker(self) -> None:
        readiness: dict[str, object] = {
            "ready": False,
            "blockers": [
                {
                    "axis": "worker_registry",
                    "code": "WORKER_STALL_DETECTED",
                    "reason": "stalled_workloads_present",
                }
            ],
        }

        self.assertEqual(exit_code_from_readiness(readiness), exit_codes.SELFTEST_FAIL)

    def test_prepare_workspace_defaults_to_runtime_config_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            artifact_root = Path(tmp_dir) / "external-artifacts"
            job = JobContract(
                job_id="chat-safe-workspace",
                workload="qwen3_tts",
                checkpoint_key="seed:chat-safe-workspace",
                payload={},
            )

            with patch(
                "runtime_v2.workers.job_runtime.RuntimeConfig"
            ) as runtime_config:
                runtime_config.return_value = RuntimeConfig(artifact_root=artifact_root)
                workspace = prepare_workspace(job)

        self.assertEqual(workspace, artifact_root / job.workload / job.job_id)
        self.assertNotIn(r"D:\YOUTUBEAUTO\system\runtime_v2\artifacts", str(workspace))

    def test_default_runtime_config_uses_external_runtime_state_root(self) -> None:
        config = RuntimeConfig()
        state_root = runtime_state_root()

        self.assertEqual(
            config.queue_store_file, state_root / "state" / "job_queue.json"
        )
        self.assertEqual(
            config.gui_status_file, state_root / "health" / "gui_status.json"
        )
        self.assertEqual(config.artifact_root, state_root / "artifacts")
        self.assertEqual(config.debug_log_root, state_root / "logs")
        self.assertNotIn(
            r"D:\YOUTUBEAUTO\system\runtime_v2", str(config.queue_store_file)
        )

    def test_runtime_config_from_root_preserves_explicit_root_layout(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir) / "runtime"
            config = RuntimeConfig.from_root(root)

        self.assertEqual(
            config.queue_store_file, root.resolve() / "state" / "job_queue.json"
        )
        self.assertEqual(config.artifact_root, root.resolve() / "artifacts")
        self.assertEqual(config.debug_log_root, root.resolve() / "logs")

    def test_copy_legacy_sessions_copies_missing_directories(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            legacy_root = root / "legacy"
            external_root = root / "external"
            (legacy_root / "chatgpt-primary").mkdir(parents=True)
            (legacy_root / "chatgpt-primary" / "marker.txt").write_text(
                "ok", encoding="utf-8"
            )
            (external_root / "seaart-primary").mkdir(parents=True)

            report = _copy_legacy_sessions(legacy_root, external_root)

        self.assertTrue(bool(report["ok"]))
        self.assertEqual(report["migrated"], ["chatgpt-primary"])
        self.assertEqual(report["skipped_existing"], [])

    def test_write_detached_summary_writes_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            out_root = Path(tmp_dir) / "probe"
            summary_file = _write_detached_summary(
                out_root=out_root,
                kind="pytest",
                target="tests/test_runtime_v2_browser_plane.py",
                exit_code=0,
                payload={"status": "ok"},
            )
            payload = json.loads(summary_file.read_text(encoding="utf-8"))

        self.assertEqual(payload["kind"], "pytest")
        self.assertEqual(payload["target"], "tests/test_runtime_v2_browser_plane.py")
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["out_root"], str(out_root))

    def test_spawn_detached_probe_writes_spawn_summary(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            args = CliArgs()
            args.probe_root = str(root / "probe")
            popen_result = MagicMock()
            popen_result.pid = 24680

            with patch("runtime_v2.cli.subprocess.Popen", return_value=popen_result):
                exit_code = _spawn_detached_probe(args, mode="selftest")

            payload = json.loads(
                (root / "probe" / "summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        self.assertEqual(payload["status"], "spawned")
        self.assertEqual(payload["kind"], "selftest")
        self.assertEqual(payload["exit_code"], exit_codes.SUCCESS)

    def test_default_session_profile_dir_uses_legacy_only_when_explicitly_allowed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            legacy_root = root / "legacy"
            external_root = root / "external"
            (legacy_root / "chatgpt-primary").mkdir(parents=True)

            with (
                patch.object(browser_manager, "LEGACY_SESSION_ROOT", legacy_root),
                patch(
                    "runtime_v2.browser.manager.browser_session_root",
                    return_value=external_root,
                ),
                patch.dict(os.environ, {}, clear=False),
            ):
                blocked = browser_manager._default_session_profile_dir(
                    "chatgpt-primary"
                )

            with (
                patch.object(browser_manager, "LEGACY_SESSION_ROOT", legacy_root),
                patch(
                    "runtime_v2.browser.manager.browser_session_root",
                    return_value=external_root,
                ),
                patch.dict(
                    os.environ,
                    {"RUNTIME_V2_ALLOW_LEGACY_SESSION_ROOT": "1"},
                    clear=False,
                ),
            ):
                allowed = browser_manager._default_session_profile_dir(
                    "chatgpt-primary"
                )

        self.assertEqual(blocked, str((external_root / "chatgpt-primary").resolve()))
        self.assertEqual(allowed, str((legacy_root / "chatgpt-primary").resolve()))


if __name__ == "__main__":
    _ = unittest.main()

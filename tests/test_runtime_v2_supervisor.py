from __future__ import annotations

import tempfile
import traceback
import unittest
from pathlib import Path
from time import time

from runtime_v2.config import RuntimeConfig
from runtime_v2.gpu.lease import Lease, LeaseStore
from runtime_v2.supervisor import _run_worker_with_lease_heartbeat


def _runtime_config(root: Path) -> RuntimeConfig:
    return RuntimeConfig.from_root(root)


def _lease() -> Lease:
    started_at = time()
    return Lease(
        key="lock:qwen3_tts",
        owner="runtime_v2",
        token=1,
        expires_at=started_at + 30.0,
        run_id="lease-run-1",
        pid=1234,
        started_at=started_at,
        host="localhost",
    )


class RuntimeV2SupervisorTests(unittest.TestCase):
    def test_worker_heartbeat_reraises_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = _runtime_config(Path(tmp_dir))

            def worker_runner() -> dict[str, object]:
                raise RuntimeError("boom")

            with self.assertRaises(RuntimeError):
                _ = _run_worker_with_lease_heartbeat(
                    LeaseStore(),
                    "lock:qwen3_tts",
                    _lease(),
                    owner="runtime_v2",
                    workload="qwen3_tts",
                    config=config,
                    worker_runner=worker_runner,
                )

    def test_worker_heartbeat_reraises_system_exit(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = _runtime_config(Path(tmp_dir))

            def worker_runner() -> dict[str, object]:
                raise SystemExit(7)

            with self.assertRaises(SystemExit) as raised:
                _ = _run_worker_with_lease_heartbeat(
                    LeaseStore(),
                    "lock:qwen3_tts",
                    _lease(),
                    owner="runtime_v2",
                    workload="qwen3_tts",
                    config=config,
                    worker_runner=worker_runner,
                )

        self.assertEqual(raised.exception.code, 7)

    def test_worker_heartbeat_reraises_keyboard_interrupt(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = _runtime_config(Path(tmp_dir))

            def worker_runner() -> dict[str, object]:
                raise KeyboardInterrupt()

            with self.assertRaises(KeyboardInterrupt):
                _ = _run_worker_with_lease_heartbeat(
                    LeaseStore(),
                    "lock:qwen3_tts",
                    _lease(),
                    owner="runtime_v2",
                    workload="qwen3_tts",
                    config=config,
                    worker_runner=worker_runner,
                )

    def test_worker_heartbeat_preserves_original_traceback_site(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            config = _runtime_config(Path(tmp_dir))

            def worker_runner() -> dict[str, object]:
                raise RuntimeError("traceback-check")

            captured: RuntimeError | None = None
            try:
                _ = _run_worker_with_lease_heartbeat(
                    LeaseStore(),
                    "lock:qwen3_tts",
                    _lease(),
                    owner="runtime_v2",
                    workload="qwen3_tts",
                    config=config,
                    worker_runner=worker_runner,
                )
            except RuntimeError as exc:
                captured = exc

        if captured is None:
            self.fail("RuntimeError was not re-raised")
        formatted = "".join(traceback.format_tb(captured.__traceback__))
        self.assertIn("worker_runner", formatted)


if __name__ == "__main__":
    _ = unittest.main()

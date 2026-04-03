from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2.result_router import _ensure_checked_at, write_result_router


class RuntimeV2ResultRouterTests(unittest.TestCase):
    def test_result_router_checked_at_guard_adds_missing_timestamp(self) -> None:
        payload = _ensure_checked_at({"runtime": "runtime_v2"}, now_fn=lambda: 123.4567)

        self.assertEqual(payload["checked_at"], 123.457)

    def test_result_router_checked_at_guard_preserves_existing_timestamp(self) -> None:
        payload = _ensure_checked_at(
            {"runtime": "runtime_v2", "checked_at": 111.2222},
            now_fn=lambda: 999.9999,
        )

        self.assertEqual(payload["checked_at"], 111.222)

    def test_result_router_checked_at_guard_replaces_non_finite_timestamp(self) -> None:
        payload = _ensure_checked_at(
            {"runtime": "runtime_v2", "checked_at": float("nan")},
            now_fn=lambda: 222.3333,
        )

        self.assertEqual(payload["checked_at"], 222.333)

    def test_result_router_checked_at_guard_replaces_infinite_timestamp(self) -> None:
        positive = _ensure_checked_at(
            {"runtime": "runtime_v2", "checked_at": float("inf")},
            now_fn=lambda: 333.4444,
        )
        negative = _ensure_checked_at(
            {"runtime": "runtime_v2", "checked_at": -float("inf")},
            now_fn=lambda: 444.5555,
        )

        self.assertEqual(positive["checked_at"], 333.444)
        self.assertEqual(negative["checked_at"], 444.555)

    def test_result_router_checked_at_guard_treats_bool_as_invalid(self) -> None:
        payload = _ensure_checked_at(
            {"runtime": "runtime_v2", "checked_at": True},
            now_fn=lambda: 555.6666,
        )

        self.assertEqual(payload["checked_at"], 555.667)

    def test_write_result_router_emits_top_level_checked_at(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            artifact_root.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_root / "sample.json"
            artifact_path.write_text('{"ok": true}', encoding="utf-8")
            output_file = root / "result.json"

            write_result_router(
                [artifact_path],
                artifact_root,
                output_file,
                metadata={"debug_log": str((root / "logs" / "run.jsonl").resolve())},
            )

            payload = json.loads(output_file.read_text(encoding="utf-8"))

        self.assertIsInstance(payload["checked_at"], float)

    def test_write_result_router_retries_winerror_5_on_replace(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            artifact_root = root / "artifacts"
            artifact_root.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_root / "sample.json"
            artifact_path.write_text('{"ok": true}', encoding="utf-8")
            output_file = root / "result.json"
            replace_calls = {"count": 0}
            original_replace = Path.replace

            def flaky_replace(self: Path, target: Path) -> Path:
                if self.suffix == ".tmp" and replace_calls["count"] < 2:
                    replace_calls["count"] += 1
                    error = PermissionError("locked")
                    error.winerror = 5
                    raise error
                return original_replace(self, target)

            with patch("runtime_v2.result_router.Path.replace", new=flaky_replace):
                written = write_result_router(
                    [artifact_path], artifact_root, output_file
                )
                contents = output_file.read_text(encoding="utf-8")

        self.assertEqual(written, output_file)
        self.assertIn('"path":', contents)


if __name__ == "__main__":
    _ = unittest.main()

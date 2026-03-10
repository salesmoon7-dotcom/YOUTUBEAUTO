from __future__ import annotations

import unittest

from runtime_v2_manager_gui import _display_worker_error_code


class RuntimeV2ManagerGuiTests(unittest.TestCase):
    def test_display_worker_error_code_expands_restart_exhausted(self) -> None:
        self.assertEqual(
            _display_worker_error_code("BROWSER_RESTART_EXHAUSTED"),
            "BROWSER_RESTART_EXHAUSTED(restart budget exhausted)",
        )

    def test_display_worker_error_code_preserves_other_codes(self) -> None:
        self.assertEqual(
            _display_worker_error_code("BROWSER_BLOCKED"),
            "BROWSER_BLOCKED",
        )


if __name__ == "__main__":
    _ = unittest.main()

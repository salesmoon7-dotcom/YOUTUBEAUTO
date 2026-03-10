from __future__ import annotations

import unittest

from runtime_v2_manager_gui import (
    _display_worker_error_code,
    _worker_error_code_mismatch_warning,
)


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

    def test_worker_error_code_mismatch_warning_reads_canonical_handoff(self) -> None:
        self.assertEqual(
            _worker_error_code_mismatch_warning(
                {
                    "metadata": {
                        "canonical_handoff": {
                            "warning_worker_error_code_mismatch": (
                                "worker_error_code=BROWSER_RESTART_EXHAUSTED "
                                "error_code=BROWSER_BLOCKED"
                            )
                        }
                    }
                }
            ),
            "worker_error_code=BROWSER_RESTART_EXHAUSTED error_code=BROWSER_BLOCKED",
        )

    def test_worker_error_code_mismatch_warning_returns_blank_without_field(
        self,
    ) -> None:
        self.assertEqual(_worker_error_code_mismatch_warning(None), "")
        self.assertEqual(_worker_error_code_mismatch_warning({}), "")


if __name__ == "__main__":
    _ = unittest.main()

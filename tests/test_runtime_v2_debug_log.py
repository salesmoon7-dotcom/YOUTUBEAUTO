from __future__ import annotations

import unittest

from runtime_v2.debug_log import summarize_runtime_result


class RuntimeV2DebugLogTests(unittest.TestCase):
    def test_summarize_runtime_result_exposes_raw_error_code_from_worker_result(
        self,
    ) -> None:
        summary = summarize_runtime_result(
            {
                "status": "failed",
                "code": "BROWSER_RESTART_EXHAUSTED",
                "worker_result": {
                    "status": "blocked",
                    "stage": "browser_preflight",
                    "error_code": "-",
                },
            }
        )

        self.assertEqual(summary["error_code"], "-")
        self.assertEqual(summary["raw_error_code"], "-")

    def test_summarize_runtime_result_exposes_raw_error_code_from_resolved_result(
        self,
    ) -> None:
        summary = summarize_runtime_result(
            {
                "status": "failed",
                "code": "BROWSER_BLOCKED",
                "error_code": "BROWSER_BLOCKED",
            }
        )

        self.assertEqual(summary["error_code"], "BROWSER_BLOCKED")
        self.assertEqual(summary["raw_error_code"], "BROWSER_BLOCKED")


if __name__ == "__main__":
    _ = unittest.main()

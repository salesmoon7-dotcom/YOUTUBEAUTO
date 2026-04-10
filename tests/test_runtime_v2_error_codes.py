from __future__ import annotations

import unittest

from runtime_v2.error_codes import (
    normalize_error_code,
    runtime_preflight_contract,
    select_worker_error_code,
)


class RuntimeV2ErrorCodesTests(unittest.TestCase):
    def test_runtime_preflight_contract_marks_restart_exhausted_terminal(self) -> None:
        contract = runtime_preflight_contract("restart_exhausted")

        self.assertEqual(contract["error_code"], "BROWSER_RESTART_EXHAUSTED")
        self.assertEqual(contract["status"], "failed")
        self.assertFalse(bool(contract["retryable"]))
        self.assertEqual(contract["completion_state"], "failed")
        self.assertTrue(bool(contract["terminal"]))

    def test_runtime_preflight_contract_keeps_blocked_paths_retryable(self) -> None:
        browser_blocked = runtime_preflight_contract("browser_side_effects_disabled")
        gpu_blocked = runtime_preflight_contract("GPU_LEASE_BUSY")
        gpt_blocked = runtime_preflight_contract("GPT_FLOOR_FAIL")
        browser_verify_blocked = runtime_preflight_contract(
            "BROWSER_BLOCKED", workload="agent_browser_verify"
        )

        self.assertEqual(browser_blocked["error_code"], "BROWSER_BLOCKED")
        self.assertEqual(browser_blocked["status"], "blocked")
        self.assertTrue(bool(browser_blocked["retryable"]))
        self.assertEqual(browser_blocked["completion_state"], "blocked")
        self.assertFalse(bool(browser_blocked["terminal"]))
        self.assertEqual(gpu_blocked["status"], "blocked")
        self.assertTrue(bool(gpu_blocked["retryable"]))
        self.assertEqual(gpt_blocked["status"], "blocked")
        self.assertTrue(bool(gpt_blocked["retryable"]))
        self.assertEqual(browser_verify_blocked["status"], "failed")
        self.assertFalse(bool(browser_verify_blocked["retryable"]))
        self.assertEqual(browser_verify_blocked["completion_state"], "failed")

    def test_select_worker_error_code_prefers_explicit_worker_code(self) -> None:
        selected = select_worker_error_code(
            {
                "worker_error_code": "BROWSER_RESTART_EXHAUSTED",
                "error_code": "BROWSER_BLOCKED",
            }
        )

        self.assertEqual(selected, "BROWSER_RESTART_EXHAUSTED")

    def test_select_worker_error_code_falls_back_to_error_code_when_blank(self) -> None:
        selected = select_worker_error_code(
            {
                "worker_error_code": "   ",
                "error_code": "BROWSER_RESTART_EXHAUSTED",
            }
        )

        self.assertEqual(selected, "BROWSER_RESTART_EXHAUSTED")

    def test_select_worker_error_code_ignores_placeholder_values(self) -> None:
        self.assertEqual(
            select_worker_error_code(
                {
                    "worker_error_code": "-",
                    "error_code": "BROWSER_RESTART_EXHAUSTED",
                }
            ),
            "BROWSER_RESTART_EXHAUSTED",
        )

    def test_error_code_selection_normalizes_runtime_aliases(self) -> None:
        self.assertEqual(
            normalize_error_code("restart_exhausted"), "BROWSER_RESTART_EXHAUSTED"
        )
        self.assertEqual(
            select_worker_error_code(
                {
                    "worker_error_code": "browser_side_effects_disabled",
                    "error_code": "BROWSER_BLOCKED",
                }
            ),
            "BROWSER_BLOCKED",
        )
        self.assertEqual(
            select_worker_error_code(
                {
                    "worker_error_code": "gpu_lease_renew_failed",
                    "error_code": "GPU_LEASE_RENEW_FAILED",
                }
            ),
            "GPU_LEASE_RENEW_FAILED",
        )
        self.assertEqual(
            select_worker_error_code(
                {
                    "worker_error_code": " failed ",
                    "error_code": "BROWSER_RESTART_EXHAUSTED",
                }
            ),
            "BROWSER_RESTART_EXHAUSTED",
        )
        self.assertEqual(
            select_worker_error_code(
                {
                    "worker_error_code": "Unknown",
                    "error_code": "BROWSER_RESTART_EXHAUSTED",
                }
            ),
            "BROWSER_RESTART_EXHAUSTED",
        )


if __name__ == "__main__":
    _ = unittest.main()

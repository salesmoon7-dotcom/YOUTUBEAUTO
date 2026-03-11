from __future__ import annotations

import unittest

from runtime_v2_manager_gui import (
    _display_worker_error_code,
    _format_seed_summary,
    _format_terminal_evidence_summary,
    _readiness_blocker_messages,
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

    def test_readiness_blocker_messages_surface_gpt_and_browser_stop_conditions(
        self,
    ) -> None:
        self.assertEqual(
            _readiness_blocker_messages(
                {
                    "blockers": [
                        {
                            "axis": "gpt_floor",
                            "code": "GPT_FLOOR_FAIL",
                            "reason": "ok_count_below_min",
                        },
                        {
                            "axis": "browser_health",
                            "code": "BROWSER_UNHEALTHY",
                            "reason": "unhealthy_sessions_present",
                        },
                    ]
                }
            ),
            [
                "gpt_floor:GPT_FLOOR_FAIL(ok_count_below_min)",
                "browser_health:BROWSER_UNHEALTHY(unhealthy_sessions_present)",
            ],
        )

    def test_format_seed_summary_reports_seeded_row_and_job(self) -> None:
        self.assertEqual(
            _format_seed_summary(
                {
                    "status": "seeded",
                    "job_id": "chatgpt-sheet1-2",
                    "topic_spec": {"row_ref": "Sheet1!row2"},
                },
                excel_path="D:/YOUTUBEAUTO/4 머니.xlsx",
                sheet_name="Sheet1",
                row_index=1,
            ),
            "seed: seeded row=Sheet1!row2 job=chatgpt-sheet1-2",
        )

    def test_format_terminal_evidence_summary_prefers_final_output_path(self) -> None:
        self.assertEqual(
            _format_terminal_evidence_summary(
                {
                    "metadata": {
                        "run_id": "run-123",
                        "final_output": True,
                        "final_artifact_path": "D:/out/final.mp4",
                    }
                },
                None,
            ),
            "run_id=run-123 final_output=true path=D:/out/final.mp4",
        )

    def test_format_terminal_evidence_summary_reports_failure_summary_when_present(
        self,
    ) -> None:
        self.assertEqual(
            _format_terminal_evidence_summary(
                {
                    "metadata": {
                        "run_id": "run-456",
                        "final_output": False,
                        "failure_summary_path": "D:/runtime/failure_summary.json",
                    }
                },
                None,
            ),
            "run_id=run-456 failure_summary=D:/runtime/failure_summary.json",
        )


if __name__ == "__main__":
    _ = unittest.main()

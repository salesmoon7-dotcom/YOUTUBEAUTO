from __future__ import annotations

import unittest

from runtime_v2.gui_adapter import build_gui_status_payload


class RuntimeV2GuiAdapterTests(unittest.TestCase):
    def test_build_gui_status_payload_uses_canonical_worker_error_code(self) -> None:
        payload = build_gui_status_payload(
            {
                "status": "blocked",
                "code": "BROWSER_RESTART_EXHAUSTED",
                "worker_error_code": "-",
                "error_code": "BROWSER_RESTART_EXHAUSTED",
            },
            run_id="run-1",
            mode="browser_recover",
            stage="finished",
            exit_code=1,
        )

        self.assertEqual(payload["worker_error_code"], "BROWSER_RESTART_EXHAUSTED")


if __name__ == "__main__":
    _ = unittest.main()

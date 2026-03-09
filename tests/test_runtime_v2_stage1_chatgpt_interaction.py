from __future__ import annotations

import json
import unittest

from runtime_v2.stage1.chatgpt_interaction import generate_gpt_response_text


class RuntimeV2Stage1ChatgptInteractionTests(unittest.TestCase):
    def test_generate_gpt_response_text_submits_and_waits_for_stable_text(self) -> None:
        responses = iter(
            [
                json.dumps(
                    {
                        "ok": True,
                        "inputSelector": "#prompt-textarea",
                        "sendClicked": True,
                    }
                ),
                json.dumps(
                    {
                        "has_stop": True,
                        "assistant_block_count": 1,
                        "assistant_text": "draft",
                    }
                ),
                json.dumps(
                    {
                        "has_stop": False,
                        "assistant_block_count": 1,
                        "assistant_text": "final json",
                    }
                ),
                json.dumps(
                    {
                        "has_stop": False,
                        "assistant_block_count": 1,
                        "assistant_text": "final json",
                    }
                ),
            ]
        )

        def fake_runner(command: list[str], timeout_sec: int) -> str:
            return next(responses)

        result = generate_gpt_response_text(
            prompt="test prompt",
            port=9222,
            poll_interval_sec=0.01,
            command_runner=fake_runner,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response_text"], "final json")


if __name__ == "__main__":
    _ = unittest.main()

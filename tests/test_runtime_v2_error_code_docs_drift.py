from __future__ import annotations

import unittest
from pathlib import Path

from runtime_v2.error_codes import (
    ERROR_CODE_GUARDRAIL_DOC_PATH,
    ERROR_CODE_SEMANTICS_DOC_PATH,
    iter_documented_error_code_ids,
)


class RuntimeV2ErrorCodeDocsDriftTests(unittest.TestCase):
    def test_documented_error_code_ids_exist_in_both_canonical_docs(self) -> None:
        semantics_text = Path(ERROR_CODE_SEMANTICS_DOC_PATH).read_text(encoding="utf-8")
        guardrail_text = Path(ERROR_CODE_GUARDRAIL_DOC_PATH).read_text(encoding="utf-8")

        missing_in_semantics = [
            code
            for code in iter_documented_error_code_ids()
            if code not in semantics_text
        ]
        missing_in_guardrails = [
            code
            for code in iter_documented_error_code_ids()
            if code not in guardrail_text
        ]

        self.assertEqual(
            missing_in_semantics,
            [],
            (
                "Missing code IDs in "
                f"{ERROR_CODE_SEMANTICS_DOC_PATH}: {missing_in_semantics}"
            ),
        )
        self.assertEqual(
            missing_in_guardrails,
            [],
            (
                "Missing code IDs in "
                f"{ERROR_CODE_GUARDRAIL_DOC_PATH}: {missing_in_guardrails}"
            ),
        )


if __name__ == "__main__":
    _ = unittest.main()

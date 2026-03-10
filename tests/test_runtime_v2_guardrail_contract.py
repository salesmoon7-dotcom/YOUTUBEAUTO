from __future__ import annotations

import unittest
from pathlib import Path

from runtime_v2.error_codes import (
    ERROR_CODE_GUARDRAIL_DOC_PATH,
    ERROR_CODE_SEMANTICS_DOC_PATH,
)


REQUIRED_GUARDRAIL_PHRASES: tuple[str, ...] = (
    "- owner:",
    "- failure mode:",
    "- removal:",
)


class RuntimeV2GuardrailContractTests(unittest.TestCase):
    def test_canonical_guardrail_docs_define_addition_contract(self) -> None:
        docs = {
            ERROR_CODE_GUARDRAIL_DOC_PATH: Path(ERROR_CODE_GUARDRAIL_DOC_PATH)
            .read_text(encoding="utf-8")
            .lower(),
            ERROR_CODE_SEMANTICS_DOC_PATH: Path(ERROR_CODE_SEMANTICS_DOC_PATH)
            .read_text(encoding="utf-8")
            .lower(),
        }

        for doc_path, text in docs.items():
            missing_phrases = [
                phrase for phrase in REQUIRED_GUARDRAIL_PHRASES if phrase not in text
            ]
            self.assertEqual(
                missing_phrases,
                [],
                f"Missing guardrail contract phrases in {doc_path}: {missing_phrases}",
            )


if __name__ == "__main__":
    _ = unittest.main()

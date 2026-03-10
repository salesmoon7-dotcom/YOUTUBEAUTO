from __future__ import annotations


def select_worker_error_code(metadata: dict[str, object]) -> str:
    explicit_worker_error_code = str(metadata.get("worker_error_code", "")).strip()
    normalized_worker_error_code = explicit_worker_error_code.lower()
    meaningless_worker_codes = {
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "null",
        "unknown",
        "failed",
        "error",
        "undefined",
    }
    if (
        explicit_worker_error_code
        and normalized_worker_error_code not in meaningless_worker_codes
    ):
        return explicit_worker_error_code
    return str(metadata.get("error_code", "")).strip()

from __future__ import annotations


ERROR_CODE_SEMANTICS_DOC_PATH = "docs/reference/error-code-semantics.md"
ERROR_CODE_GUARDRAIL_DOC_PATH = "docs/sop/SOP_runtime_v2_development_guardrails.md"

DOCUMENTED_ERROR_CODE_IDS: tuple[str, ...] = (
    "OK",
    "BROWSER_BLOCKED",
    "BROWSER_RESTART_EXHAUSTED",
    "BROWSER_UNHEALTHY",
    "GPU_LEASE_BUSY",
    "GPT_FLOOR_FAIL",
    "QUEUE_STORE_INVALID",
    "GPT_STATUS_MISSING",
    "GPT_STATUS_INVALID",
    "GPT_STATUS_STALE",
    "BROWSER_HEALTH_MISSING",
    "BROWSER_HEALTH_INVALID",
    "BROWSER_REGISTRY_MISSING",
    "BROWSER_REGISTRY_INVALID",
    "BROWSER_REGISTRY_DRIFT",
)


def iter_documented_error_code_ids() -> tuple[str, ...]:
    return DOCUMENTED_ERROR_CODE_IDS


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

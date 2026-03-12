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
    "GPU_HEALTH_MISSING",
    "GPU_HEALTH_INVALID",
    "GPU_HEALTH_STALE",
    "GPU_LEASE_RENEW_FAILED",
    "WORKER_REGISTRY_MISSING",
    "WORKER_REGISTRY_INVALID",
    "WORKER_STALL_DETECTED",
)

ERROR_CODE_ALIASES: dict[str, str] = {
    "restart_exhausted": "BROWSER_RESTART_EXHAUSTED",
    "browser_side_effects_disabled": "BROWSER_BLOCKED",
    "gpu_lease_renew_failed": "GPU_LEASE_RENEW_FAILED",
}


def iter_documented_error_code_ids() -> tuple[str, ...]:
    return DOCUMENTED_ERROR_CODE_IDS


def normalize_error_code(raw_code: object) -> str:
    code = str(raw_code).strip()
    if not code:
        return ""
    return ERROR_CODE_ALIASES.get(code.lower(), code)


def select_worker_error_code(metadata: dict[str, object]) -> str:
    explicit_worker_error_code = normalize_error_code(
        metadata.get("worker_error_code", "")
    )
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
    return normalize_error_code(metadata.get("error_code", ""))

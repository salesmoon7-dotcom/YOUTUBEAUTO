from __future__ import annotations


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "": {"OK", "partial", "failed"},
    "OK": {"Image OK", "partial", "failed"},
    "Image OK": {"Thumb OK", "Video OK", "partial", "failed"},
    "Thumb OK": {"Video OK", "partial", "failed"},
    "Video OK": {"Voice OK", "Done", "partial", "failed"},
    "Voice OK": {"Done", "partial", "failed"},
    "partial": {"OK", "Image OK", "Video OK", "Voice OK", "failed"},
    "failed": {"partial"},
}

TERMINAL_STATUSES = {"done"}


def can_transition_excel_status(current_status: str, next_status: str) -> bool:
    normalized = current_status.strip()
    return next_status in ALLOWED_STATUS_TRANSITIONS.get(normalized, set())

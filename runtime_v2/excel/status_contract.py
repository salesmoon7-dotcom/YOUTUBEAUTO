from __future__ import annotations


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "": {"seeded", "running", "ok", "partial", "failed"},
    "seeded": {"running", "ok", "partial", "failed"},
    "running": {
        "ok",
        "image ok",
        "thumb ok",
        "video ok",
        "voice ok",
        "done",
        "partial",
        "failed",
    },
    "ok": {"image ok", "partial", "failed"},
    "image ok": {"thumb ok", "video ok", "partial", "failed"},
    "thumb ok": {"video ok", "partial", "failed"},
    "video ok": {"voice ok", "done", "partial", "failed"},
    "voice ok": {"done", "partial", "failed"},
    "partial": {
        "seeded",
        "running",
        "ok",
        "image ok",
        "video ok",
        "voice ok",
        "failed",
    },
    "failed": {"seeded", "running", "partial"},
}

TERMINAL_STATUSES = {"done"}


def can_transition_excel_status(current_status: str, next_status: str) -> bool:
    normalized_current = current_status.strip().lower()
    normalized_next = next_status.strip().lower()
    return normalized_next in ALLOWED_STATUS_TRANSITIONS.get(normalized_current, set())

from __future__ import annotations


def build_agent_browser_evidence(worker_result: dict[str, object]) -> dict[str, object]:
    details_obj = worker_result.get("details", {})
    details = details_obj if isinstance(details_obj, dict) else {}
    return {
        "service": str(details.get("service", "")),
        "port": details.get("port", 0),
        "current_url": str(details.get("current_url", "")),
        "current_title": str(details.get("current_title", "")),
        "transcript_path": str(details.get("transcript_path", "")),
    }

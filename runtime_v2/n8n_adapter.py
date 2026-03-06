from __future__ import annotations


def build_n8n_webhook_response(status: dict[str, str], callback_url: str) -> dict[str, object]:
    """Remote n8n webhook payload contract for orchestration server."""
    return {
        "execution_env": "remote_n8n",
        "callback_url": callback_url,
        "ok": status.get("status") == "ok",
        "runtime": "runtime_v2",
        "status": status,
    }

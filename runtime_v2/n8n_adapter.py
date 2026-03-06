from __future__ import annotations

import json
from pathlib import Path


def build_n8n_webhook_response(
    status: dict[str, object],
    callback_url: str,
    run_id: str,
    mode: str,
    exit_code: int,
) -> dict[str, object]:
    """Remote n8n webhook payload contract for orchestration server."""
    return {
        "schema_version": "1.0",
        "execution_env": "remote_n8n",
        "callback_url": callback_url,
        "run_id": run_id,
        "mode": mode,
        "exit_code": exit_code,
        "ok": status.get("status") == "ok",
        "runtime": "runtime_v2",
        "status": status,
    }


def write_mock_callback(payload: dict[str, object], output_file: str) -> None:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

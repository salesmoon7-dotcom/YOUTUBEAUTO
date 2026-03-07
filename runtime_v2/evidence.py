from __future__ import annotations

import json
from pathlib import Path


def load_latest_result_metadata(
    result_file: str | Path = "system/runtime_v2/evidence/result.json",
) -> dict[str, object]:
    path = Path(result_file)
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        return {"code": "UNKNOWN"}
    metadata = raw_payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return {"code": str(raw_payload.get("code", "UNKNOWN"))}
    typed_metadata = {str(key): metadata[key] for key in metadata}
    if "code" not in typed_metadata:
        typed_metadata["code"] = str(raw_payload.get("code", "UNKNOWN"))
    return typed_metadata

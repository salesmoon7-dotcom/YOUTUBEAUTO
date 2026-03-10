from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import Callable

from runtime_v2.contracts.artifact_contract import artifact_record


def _ensure_checked_at(
    payload: dict[str, object], *, now_fn: Callable[[], float] = time
) -> dict[str, object]:
    checked_at = payload.get("checked_at")
    if isinstance(checked_at, (int, float)):
        payload["checked_at"] = round(float(checked_at), 3)
        return payload
    payload["checked_at"] = round(now_fn(), 3)
    return payload


def write_result_router(
    artifacts: list[Path],
    artifact_root: Path,
    output_file: Path,
    metadata: dict[str, object] | None = None,
) -> Path:
    metadata_payload: dict[str, object] = {} if metadata is None else dict(metadata)
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "runtime": "runtime_v2",
        "artifacts": [artifact_record(path, artifact_root) for path in artifacts],
        "metadata": metadata_payload,
    }
    payload = _ensure_checked_at(payload)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_file.parent,
        prefix=f"{output_file.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(output_file)
    return output_file


def attach_failure_summary(
    metadata: dict[str, object], failure_summary_path: str
) -> dict[str, object]:
    payload = dict(metadata)
    payload["failure_summary_path"] = failure_summary_path
    return payload

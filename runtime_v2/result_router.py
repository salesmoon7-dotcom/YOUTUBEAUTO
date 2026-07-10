from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from time import sleep
from time import time
from typing import Callable

from runtime_v2.contracts.artifact_contract import artifact_record


_RESULT_ROUTER_REPLACE_RETRY_DELAYS = (0.05, 0.1, 0.2)


def _ensure_checked_at(
    payload: dict[str, object], *, now_fn: Callable[[], float] = time
) -> dict[str, object]:
    checked_at = payload.get("checked_at")
    if not isinstance(checked_at, bool) and isinstance(checked_at, (int, float)):
        numeric_checked_at = float(checked_at)
        if math.isfinite(numeric_checked_at):
            payload["checked_at"] = round(numeric_checked_at, 3)
            return payload
    fallback_checked_at = float(now_fn())
    payload["checked_at"] = round(fallback_checked_at, 3)
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
    payload_text = json.dumps(payload, ensure_ascii=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_file.parent,
        prefix=f"{output_file.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(payload_text)
        temp_path = Path(handle.name)
    last_error: PermissionError | None = None
    for delay in (*_RESULT_ROUTER_REPLACE_RETRY_DELAYS, None):
        try:
            _ = temp_path.replace(output_file)
            break
        except PermissionError as exc:
            last_error = exc
            if getattr(exc, "winerror", None) != 5 or delay is None:
                if getattr(exc, "winerror", None) == 5 and delay is None:
                    output_file.write_text(payload_text, encoding="utf-8")
                    temp_path.unlink(missing_ok=True)
                    break
                raise
            sleep(delay)
    if last_error is not None and not output_file.exists():
        raise last_error
    return output_file


def attach_failure_summary(
    metadata: dict[str, object], failure_summary_path: str
) -> dict[str, object]:
    payload = dict(metadata)
    payload["failure_summary_path"] = failure_summary_path
    return payload

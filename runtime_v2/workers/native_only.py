from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from runtime_v2.workers.job_runtime import finalize_worker_result, write_json_atomic


JsonLike = str | int | float | bool | None | dict[str, "JsonLike"] | list["JsonLike"]


def sanitize_worker_payload(payload: Mapping[str, object]) -> dict[str, JsonLike]:
    sanitized: dict[str, JsonLike] = {}
    for key, value in payload.items():
        sanitized[str(key)] = _sanitize_value(value)
    return sanitized


def _sanitize_value(value: object) -> JsonLike:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        sanitized: dict[str, JsonLike] = {}
        for raw_key, nested_value in cast(Mapping[object, object], value).items():
            key = str(raw_key)
            sanitized[str(key)] = _sanitize_value(nested_value)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_value(item) for item in value]
    return str(value)


def write_native_request(
    workspace: Path,
    payload: Mapping[str, object],
    *,
    file_name: str = "request.json",
) -> Path:
    return write_json_atomic(
        workspace / file_name,
        {"payload": sanitize_worker_payload(payload)},
    )


def native_not_implemented_result(
    workspace: Path,
    *,
    workload: str,
    stage: str,
    artifacts: list[Path],
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload_details = sanitize_worker_payload(details or {})
    payload_details.update(
        {
            "execution_mode": "native_only",
            "external_execution": "disabled",
            "workload": workload,
        }
    )
    details_payload: dict[str, object] = dict(payload_details)
    return finalize_worker_result(
        workspace,
        status="failed",
        stage=stage,
        artifacts=artifacts,
        error_code=f"native_{workload}_not_implemented",
        retryable=False,
        details=details_payload,
        completion={"state": "failed", "final_output": False},
    )

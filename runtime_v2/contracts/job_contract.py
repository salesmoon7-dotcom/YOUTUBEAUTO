from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import cast

from runtime_v2.config import WorkloadName, allowed_workloads


EXPLICIT_CONTRACT_NAME = "runtime_v2_inbox_job"
EXPLICIT_CONTRACT_VERSION = "1.0"


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return 0


def _to_float(value: object, default: float) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    return default


def workload_from_value(value: object) -> WorkloadName | None:
    workload_value = str(value).strip()
    for allowed in allowed_workloads():
        if workload_value == allowed:
            return allowed
    return None


def build_explicit_job_contract(
    *,
    job_id: str,
    workload: WorkloadName,
    checkpoint_key: str,
    payload: dict[str, object],
    chain_step: int | None = None,
    parent_job_id: str = "",
) -> dict[str, object]:
    contract: dict[str, object] = {
        "contract": EXPLICIT_CONTRACT_NAME,
        "contract_version": EXPLICIT_CONTRACT_VERSION,
        "local_only": True,
        "job": {
            "job_id": job_id,
            "worker": workload,
            "checkpoint_key": checkpoint_key,
            "payload": payload,
        },
    }
    chain: dict[str, object] = {}
    if chain_step is not None:
        chain["step"] = chain_step
    if parent_job_id:
        chain["parent_job_id"] = parent_job_id
    if chain:
        contract["chain"] = chain
    return contract


@dataclass(slots=True)
class JobContract:
    job_id: str
    workload: WorkloadName
    status: str = "queued"
    attempts: int = 0
    checkpoint_key: str = ""
    payload: dict[str, object] = field(default_factory=dict)
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "workload": self.workload,
            "status": self.status,
            "attempts": self.attempts,
            "checkpoint_key": self.checkpoint_key,
            "payload": self.payload,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "JobContract":
        workload = workload_from_value(payload.get("workload", "qwen3_tts")) or "qwen3_tts"
        raw_payload = payload.get("payload", {})
        typed_payload: dict[str, object] = {}
        if isinstance(raw_payload, dict):
            raw_payload_dict = cast(dict[object, object], raw_payload)
            for raw_key in raw_payload_dict:
                typed_payload[str(raw_key)] = raw_payload_dict[raw_key]
        now = time()
        return cls(
            job_id=str(payload.get("job_id", "unknown")),
            workload=workload,
            status=str(payload.get("status", "queued")),
            attempts=_to_int(payload.get("attempts", 0)),
            checkpoint_key=str(payload.get("checkpoint_key", "")),
            payload=typed_payload,
            created_at=_to_float(payload.get("created_at", now), now),
            updated_at=_to_float(payload.get("updated_at", now), now),
        )

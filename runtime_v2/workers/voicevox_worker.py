from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.qwen3_worker import run_qwen3_job


def run_voicevox_job(job: JobContract, *, artifact_root: Path) -> dict[str, object]:
    return run_qwen3_job(job, artifact_root=artifact_root)

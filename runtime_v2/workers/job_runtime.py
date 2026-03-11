from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.config import RuntimeConfig, external_runtime_root


REPO_ROOT = Path(__file__).resolve().parents[2]


def prepare_workspace(job: JobContract, artifact_root: Path | None = None) -> Path:
    resolved_root = artifact_root or RuntimeConfig().artifact_root
    workspace = resolved_root / job.workload / job.job_id
    workspace.mkdir(parents=True, exist_ok=True)
    _ = write_json_atomic(workspace / "job.json", job.to_dict())
    return workspace


def write_json_atomic(path: Path, payload: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True, indent=2))
        temp_path = Path(handle.name)
    _ = temp_path.replace(path)
    return path


def resolve_local_input(raw_path: str) -> Path | None:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    allowed_roots = {REPO_ROOT.resolve(), external_runtime_root().resolve()}
    if not any(
        candidate == root or root in candidate.parents for root in allowed_roots
    ):
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def stage_local_input(
    workspace: Path, source: Path, target_name: str | None = None
) -> Path:
    name = target_name or source.name
    target = workspace / name
    _ = shutil.copy2(source, target)
    return target


def finalize_worker_result(
    workspace: Path,
    *,
    status: str,
    stage: str,
    artifacts: list[Path],
    error_code: str = "",
    retryable: bool = False,
    details: dict[str, object] | None = None,
    next_jobs: list[dict[str, object]] | None = None,
    completion: dict[str, object] | None = None,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "workspace": str(workspace.resolve()),
        "artifacts": [str(path.resolve()) for path in artifacts],
        "relative_artifacts": [path.name for path in artifacts],
    }
    result: dict[str, object] = {
        "status": status,
        "stage": stage,
        "error_code": error_code,
        "retryable": retryable,
        "manifest_path": str((workspace / "manifest.json").resolve()),
        "details": details or {},
        "next_jobs": next_jobs or [],
        "completion": completion or {},
    }
    _ = write_json_atomic(workspace / "manifest.json", manifest)
    _ = write_json_atomic(workspace / "result.json", result)
    payload: dict[str, object] = {
        "status": status,
        "stage": stage,
        "artifacts": [str(path.resolve()) for path in artifacts],
        "manifest_path": str((workspace / "manifest.json").resolve()),
        "result_path": str((workspace / "result.json").resolve()),
        "retryable": retryable,
    }
    if error_code:
        payload["error_code"] = error_code
    if details:
        payload["details"] = details
    if next_jobs:
        payload["next_jobs"] = next_jobs
    if completion:
        payload["completion"] = completion
    return payload

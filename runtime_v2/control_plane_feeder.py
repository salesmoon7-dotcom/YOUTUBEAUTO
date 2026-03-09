from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.config import RuntimeConfig, allowed_workloads
from runtime_v2.contracts.job_contract import (
    EXPLICIT_CONTRACT_NAME,
    EXPLICIT_CONTRACT_VERSION,
    JobContract,
    workload_from_value,
)
from runtime_v2.queue_store import QueueStore

ALLOWED_WORKLOADS = set(allowed_workloads())
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_EXTENSIONS = {".wav", ".mp3", ".flac", ".mp4", ".mov", ".mkv", ".avi"}
MAX_CONTRACT_BYTES = 262144
REPO_ROOT = Path(__file__).resolve().parents[1]


def seed_local_jobs(config: RuntimeConfig | None = None) -> list[JobContract]:
    runtime_config = config or RuntimeConfig()
    queue_store = QueueStore(runtime_config.queue_store_file)
    existing_jobs = queue_store.load()
    known_keys = {job.checkpoint_key for job in existing_jobs if job.checkpoint_key}
    feeder_state = _load_feeder_state(runtime_config.feeder_state_file)
    known_keys.update(feeder_state)
    seeded: list[JobContract] = []
    for job in _discover_explicit_contract_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    for job in _discover_qwen_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    for job in _discover_kenburns_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    for job in _discover_rvc_jobs(runtime_config, known_keys):
        _ = queue_store.upsert(job)
        known_keys.add(job.checkpoint_key)
        feeder_state[job.checkpoint_key] = {
            "job_id": job.job_id,
            "created_at": job.created_at,
        }
        seeded.append(job)
    _ = _save_feeder_state(runtime_config.feeder_state_file, feeder_state)
    return seeded


def job_from_explicit_payload(
    payload: dict[str, object], *, source_hint: str
) -> tuple[JobContract | None, dict[str, object] | None]:
    if str(payload.get("contract", "")) != EXPLICIT_CONTRACT_NAME:
        return None, {"code": "invalid_contract", "message": "contract name mismatch"}
    if str(payload.get("contract_version", "")) != EXPLICIT_CONTRACT_VERSION:
        return None, {
            "code": "invalid_contract_version",
            "message": "unsupported contract_version",
        }
    if bool(payload.get("local_only", False)) is not True:
        return None, {"code": "not_local_only", "message": "local_only must be true"}
    raw_job = payload.get("job")
    job_block = _mapping_from_obj(raw_job)
    if job_block is None:
        return None, {"code": "missing_job", "message": "job block missing"}
    job_id = str(job_block.get("job_id", "")).strip()
    workload = workload_from_value(
        job_block.get("worker", job_block.get("workload", ""))
    )
    if not job_id or workload is None or workload not in ALLOWED_WORKLOADS:
        return None, {"code": "invalid_job", "message": "job_id or workload invalid"}
    typed_payload: dict[str, object] = {}
    raw_payload_block = job_block.get("payload", {})
    raw_payload_dict = _mapping_from_obj(raw_payload_block)
    if raw_payload_dict is not None:
        for raw_key, raw_value in raw_payload_dict.items():
            typed_payload[str(raw_key)] = raw_value
    raw_args_block = job_block.get("args", {})
    raw_args_dict = _mapping_from_obj(raw_args_block)
    if raw_args_dict is not None:
        for raw_key, raw_value in raw_args_dict.items():
            typed_payload[str(raw_key)] = raw_value
    raw_inputs = job_block.get("inputs", [])
    if isinstance(raw_inputs, list):
        for raw_entry in cast(list[object], raw_inputs):
            entry = _mapping_from_obj(raw_entry)
            if entry is None:
                continue
            name = str(entry.get("name", "")).strip()
            path_value = str(entry.get("path", "")).strip()
            if name and path_value:
                typed_payload[name] = path_value
    raw_chain = payload.get("chain")
    chain_block = _mapping_from_obj(raw_chain)
    if chain_block is not None:
        typed_payload["chain_depth"] = _to_int(
            chain_block.get("step", chain_block.get("chain_depth", 0))
        )
        parent_job_id = str(chain_block.get("parent_job_id", "")).strip()
        if parent_job_id:
            typed_payload["routed_from"] = parent_job_id
    if not payload_paths_are_local(typed_payload):
        return None, {
            "code": "non_local_path",
            "message": "payload paths must stay inside workspace",
        }
    checkpoint_key = str(job_block.get("checkpoint_key", f"explicit:{source_hint}"))
    return (
        JobContract(
            job_id=job_id,
            workload=workload,
            checkpoint_key=checkpoint_key,
            payload=typed_payload,
        ),
        None,
    )


def payload_paths_are_local(payload: dict[str, object]) -> bool:
    for key in ("source_path", "audio_path", "image_path"):
        raw_value = payload.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            if _normalize_local_path(raw_value) is None:
                return False
    return True


def _discover_explicit_contract_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    inbox_root = config.input_root
    if not inbox_root.exists():
        return []
    jobs: list[JobContract] = []
    for contract_file in sorted(inbox_root.rglob("*.job.json")):
        if not contract_file.is_file() or not _is_stable_file(
            contract_file, age_sec=config.stable_file_age_sec
        ):
            continue
        if _is_explicit_contract_archived(inbox_root, contract_file):
            continue
        if not _is_allowed_explicit_contract_path(inbox_root, contract_file):
            _ = _archive_explicit_contract(
                inbox_root,
                contract_file,
                accepted=False,
                invalid_reason={
                    "code": "invalid_contract_path",
                    "message": "explicit contract must stay inside allowed inbox subdirectories",
                },
            )
            continue
        explicit_job, invalid_reason = _job_from_explicit_contract(contract_file)
        if explicit_job is None:
            _ = _archive_explicit_contract(
                inbox_root, contract_file, accepted=False, invalid_reason=invalid_reason
            )
            continue
        if explicit_job.checkpoint_key in known_keys:
            _ = _archive_explicit_contract(inbox_root, contract_file, accepted=True)
            continue
        jobs.append(explicit_job)
        _ = _archive_explicit_contract(inbox_root, contract_file, accepted=True)
    return jobs


def _job_from_explicit_contract(
    contract_file: Path,
) -> tuple[JobContract | None, dict[str, object] | None]:
    try:
        if contract_file.stat().st_size > MAX_CONTRACT_BYTES:
            return None, {
                "code": "contract_too_large",
                "message": "explicit contract exceeds size limit",
            }
        raw_payload = cast(
            object, json.loads(contract_file.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError):
        return None, {
            "code": "invalid_json",
            "message": "explicit contract is not valid JSON",
        }
    payload = _mapping_from_obj(raw_payload)
    if payload is None:
        return None, {
            "code": "invalid_contract",
            "message": "explicit contract root must be object",
        }
    return job_from_explicit_payload(payload, source_hint=str(contract_file))


def _is_explicit_contract_archived(inbox_root: Path, contract_file: Path) -> bool:
    archived_roots = {inbox_root / "accepted", inbox_root / "invalid"}
    return any(
        root == contract_file.parent or root in contract_file.parents
        for root in archived_roots
    )


def _is_allowed_explicit_contract_path(inbox_root: Path, contract_file: Path) -> bool:
    allowed_roots = {
        (inbox_root / "qwen3_tts").resolve(),
        (inbox_root / "chatgpt").resolve(),
        (inbox_root / "genspark").resolve(),
        (inbox_root / "seaart").resolve(),
        (inbox_root / "geminigen").resolve(),
        (inbox_root / "canva").resolve(),
        (inbox_root / "render").resolve(),
        (inbox_root / "kenburns").resolve(),
        (inbox_root / "rvc" / "source").resolve(),
        (inbox_root / "rvc" / "audio").resolve(),
    }
    contract_parent = contract_file.resolve().parent
    return contract_parent in allowed_roots


def _archive_explicit_contract(
    inbox_root: Path,
    contract_file: Path,
    *,
    accepted: bool,
    invalid_reason: dict[str, object] | None = None,
) -> Path:
    archive_root = inbox_root / ("accepted" if accepted else "invalid")
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / contract_file.name
    if target.exists():
        target = (
            archive_root
            / f"{contract_file.name.removesuffix('.job.json')}.{int(time())}.job.json"
        )
    _ = contract_file.replace(target)
    if invalid_reason is not None:
        reason_file = target.with_suffix(target.suffix + ".reason.json")
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=reason_file.parent,
            prefix=f"{reason_file.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            _ = handle.write(json.dumps(invalid_reason, ensure_ascii=True, indent=2))
            temp_path = Path(handle.name)
        _ = temp_path.replace(reason_file)
    return target


def _discover_qwen_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    inbox = config.input_root / "qwen3_tts"
    image_inbox = config.input_root / "kenburns"
    if not inbox.exists():
        return []
    jobs: list[JobContract] = []
    for text_file in sorted(inbox.glob("*.txt")):
        if not _is_stable_file(text_file, age_sec=config.stable_file_age_sec):
            continue
        checkpoint_key = f"qwen3_tts:{text_file.resolve()}"
        if checkpoint_key in known_keys:
            continue
        script_text = text_file.read_text(encoding="utf-8").strip()
        if not script_text:
            continue
        payload: dict[str, object] = {"script_text": script_text}
        image_path = _matching_image_path(
            image_inbox, text_file.stem, age_sec=config.stable_file_age_sec
        )
        if image_path is not None:
            payload["image_path"] = str(image_path.resolve())
        if not payload_paths_are_local(payload):
            continue
        jobs.append(
            JobContract(
                job_id=f"qwen3_tts-{text_file.stem}",
                workload="qwen3_tts",
                checkpoint_key=checkpoint_key,
                payload=payload,
            )
        )
    return jobs


def _discover_kenburns_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    inbox = config.input_root / "kenburns"
    if not inbox.exists():
        return []
    jobs: list[JobContract] = []
    for source_file in sorted(inbox.iterdir()):
        if (
            not source_file.is_file()
            or source_file.suffix.lower() not in IMAGE_EXTENSIONS
        ):
            continue
        if not _is_stable_file(source_file, age_sec=config.stable_file_age_sec):
            continue
        checkpoint_key = f"kenburns:{source_file.resolve()}"
        if checkpoint_key in known_keys:
            continue
        jobs.append(
            JobContract(
                job_id=f"kenburns-{source_file.stem}",
                workload="kenburns",
                checkpoint_key=checkpoint_key,
                payload={
                    "source_path": str(source_file.resolve()),
                    "duration_sec": 8,
                    "chain_depth": 0,
                },
            )
        )
    return jobs


def _discover_rvc_jobs(
    config: RuntimeConfig, known_keys: set[str]
) -> list[JobContract]:
    source_root = config.input_root / "rvc" / "source"
    audio_root = config.input_root / "rvc" / "audio"
    if not source_root.exists():
        return []
    jobs: list[JobContract] = []
    audio_candidates = _audio_map(audio_root)
    for source_file in sorted(source_root.iterdir()):
        if (
            not source_file.is_file()
            or source_file.suffix.lower() not in MEDIA_EXTENSIONS
        ):
            continue
        if not _is_stable_file(source_file, age_sec=config.stable_file_age_sec):
            continue
        checkpoint_key = f"rvc:{source_file.resolve()}"
        if checkpoint_key in known_keys:
            continue
        payload: dict[str, object] = {"source_path": str(source_file.resolve())}
        audio_match = audio_candidates.get(source_file.stem)
        if audio_match is not None:
            payload["audio_path"] = str(audio_match.resolve())
        if not payload_paths_are_local(payload):
            continue
        jobs.append(
            JobContract(
                job_id=f"rvc-{source_file.stem}",
                workload="rvc",
                checkpoint_key=checkpoint_key,
                payload=payload,
            )
        )
    return jobs


def _audio_map(audio_root: Path) -> dict[str, Path]:
    if not audio_root.exists():
        return {}
    mapping: dict[str, Path] = {}
    for audio_file in sorted(audio_root.iterdir()):
        if (
            not audio_file.is_file()
            or audio_file.suffix.lower() not in MEDIA_EXTENSIONS
        ):
            continue
        mapping[audio_file.stem] = audio_file
    return mapping


def _matching_image_path(image_root: Path, stem: str, *, age_sec: int) -> Path | None:
    if not image_root.exists():
        return None
    for extension in sorted(IMAGE_EXTENSIONS):
        candidate = image_root / f"{stem}{extension}"
        if (
            candidate.exists()
            and candidate.is_file()
            and _is_stable_file(candidate, age_sec=age_sec)
        ):
            return candidate
    return None


def _is_stable_file(path: Path, age_sec: int = 3) -> bool:
    try:
        modified_age = time() - path.stat().st_mtime
    except OSError:
        return False
    return modified_age >= age_sec


def _load_feeder_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        raw_payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_payload, dict):
        return {}
    source_payload = cast(dict[object, object], raw_payload)
    state: dict[str, dict[str, object]] = {}
    for raw_key, raw_value in source_payload.items():
        if isinstance(raw_key, str) and isinstance(raw_value, dict):
            raw_mapping = cast(dict[object, object], raw_value)
            state[raw_key] = {str(key): value for key, value in raw_mapping.items()}
    return state


def _save_feeder_state(path: Path, payload: dict[str, dict[str, object]]) -> Path:
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


def archived_contract_counts(inbox_root: Path) -> tuple[int, int]:
    accepted_root = inbox_root / "accepted"
    invalid_root = inbox_root / "invalid"
    accepted_count = _archived_contract_count(accepted_root)
    invalid_count = _archived_contract_count(invalid_root)
    return accepted_count, invalid_count


def invalid_reason_summary(inbox_root: Path) -> str:
    invalid_root = inbox_root / "invalid"
    if not invalid_root.exists():
        return ""
    reason_files = sorted(
        invalid_root.glob("*.reason.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reason_files:
        return ""
    latest = reason_files[0]
    try:
        raw_payload = cast(object, json.loads(latest.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return latest.name
    if not isinstance(raw_payload, dict):
        return latest.name
    payload = cast(dict[object, object], raw_payload)
    code = str(payload.get("code", "invalid"))
    message = str(payload.get("message", ""))
    return f"{code}:{message}" if message else code


def _archived_contract_count(root: Path) -> int:
    if not root.exists():
        return 0
    exact = list(root.glob("*.job.json"))
    alternate = [
        path
        for path in root.glob("*.job.*.json")
        if not path.name.endswith(".reason.json")
    ]
    return len(exact) + len(alternate)


def _mapping_from_obj(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw_value = cast(dict[object, object], value)
    return {str(key): item for key, item in raw_value.items()}


def _normalize_local_path(raw_path: str) -> Path | None:
    if "://" in raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
        return None
    return candidate


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0

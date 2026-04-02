from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.stage2.router import route_video_plan


_BOUNDARY_PROMPT_PLACEHOLDERS = {
    "test",
    "test.",
    "test prompt",
    "\u30c6\u30b9\u30c8\u3067\u3059\u3002",
    "\ud14c\uc2a4\ud2b8\uc785\ub2c8\ub2e4.",
}


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw = cast(dict[object, object], value)
    return {str(key): raw[key] for key in raw}


def _load_json_mapping(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_boundary_source")
    return _mapping(payload) or {}


def load_stage1_handoff_contract(path: str | Path) -> dict[str, object]:
    payload = _load_json_mapping(path)
    contract = _mapping(payload.get("contract"))
    if contract is not None:
        return contract
    return payload


def load_video_plan(path: str | Path) -> dict[str, object]:
    return _load_json_mapping(path)


def _artifact_root_from_path(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    for parent in resolved.parents:
        if parent.name.lower() == "artifacts":
            return parent
    if resolved.parent.name.lower().startswith("stage1-"):
        probe_parent = resolved.parent.parent
        if probe_parent.name.lower() == "probe":
            assets_root = resolved.parent / "assets"
            if assets_root.exists() and assets_root.is_dir():
                return assets_root.resolve()
            return resolved.parent
    raise ValueError("missing_artifact_root_ancestor")


def _select_boundary_voice_texts(
    voice_texts: list[dict[str, object]],
) -> list[dict[str, object]]:
    for entry in voice_texts:
        if str(entry.get("col", "")).strip() == "#01":
            return [entry]
    return [voice_texts[0]]


def _boundary_prompt_is_placeholder(value: object) -> bool:
    normalized = str(value).strip().lower()
    if not normalized:
        return True
    return normalized in _BOUNDARY_PROMPT_PLACEHOLDERS


def _job_id_is_ref_boundary(job_id: str) -> bool:
    normalized = job_id.strip().lower()
    return normalized.endswith("-ref-1") or normalized.endswith("-ref-2")


def build_qwen_boundary_contract(
    *, stage1_handoff_path: str | Path, model_name: str = "voice-model-a"
) -> dict[str, object]:
    contract = load_stage1_handoff_contract(stage1_handoff_path)
    run_id = str(contract.get("run_id", "")).strip()
    row_ref = str(contract.get("row_ref", "")).strip()
    topic = str(contract.get("topic", "")).strip()
    raw_voice_texts = contract.get("voice_texts", [])
    if not isinstance(raw_voice_texts, list) or not raw_voice_texts:
        raise ValueError("missing_voice_texts")
    artifact_root = _artifact_root_from_path(stage1_handoff_path)
    voice_texts: list[dict[str, object]] = []
    for entry in cast(list[object], raw_voice_texts):
        item = _mapping(entry)
        if item is None:
            continue
        text = str(item.get("text", "")).strip()
        col = str(item.get("col", "")).strip()
        if not text or not col:
            continue
        voice_texts.append(
            {
                "col": col,
                "text": text,
                "original_voices": item.get("original_voices", []),
            }
        )
    if not voice_texts:
        raise ValueError("missing_voice_texts")
    boundary_voice_texts = _select_boundary_voice_texts(voice_texts)
    boundary_suffix = run_id or row_ref or "boundary"
    boundary_suffix = boundary_suffix.replace("!", "-").replace(":", "-")
    job_id = f"qwen3-boundary-{boundary_suffix}"
    service_artifact_path = (
        artifact_root
        / "qwen3_tts"
        / f"qwen3-{run_id or boundary_suffix}"
        / "speech.flac"
    ).resolve()
    return build_explicit_job_contract(
        job_id=job_id,
        workload="qwen3_tts",
        checkpoint_key=f"boundary:qwen3_tts:{row_ref or run_id or 'boundary'}",
        payload={
            "run_id": run_id,
            "row_ref": row_ref,
            "topic": topic,
            "voice_texts": boundary_voice_texts,
            "model_name": model_name,
            "service_artifact_path": str(service_artifact_path),
            "chain_depth": 0,
        },
    )


def build_stage2_boundary_contract(
    *,
    video_plan_path: str | Path,
    workload: str,
    scene_index: int | None = None,
    ref_id: str = "",
) -> dict[str, object]:
    video_plan = load_video_plan(video_plan_path)
    jobs, _ = route_video_plan(video_plan)
    target_ref = ref_id.strip().lower()
    for job in jobs:
        typed_job = _mapping(job)
        if typed_job is None:
            continue
        inner_job = _mapping(typed_job.get("job"))
        if inner_job is None:
            continue
        if str(inner_job.get("worker", "")).strip() != workload:
            continue
        job_id = str(inner_job.get("job_id", "")).strip().lower()
        payload = _mapping(inner_job.get("payload")) or {}
        job_scene_index = payload.get("scene_index")
        if target_ref:
            if job_id.endswith(target_ref):
                return typed_job
            continue
        if scene_index is None:
            if _boundary_prompt_is_placeholder(payload.get("prompt", "")):
                raise ValueError("boundary_prompt_placeholder")
            return typed_job
        if _job_id_is_ref_boundary(job_id):
            continue
        if isinstance(job_scene_index, int):
            parsed_scene_index = job_scene_index
        elif isinstance(job_scene_index, float):
            parsed_scene_index = int(job_scene_index)
        elif isinstance(job_scene_index, str):
            try:
                parsed_scene_index = int(job_scene_index.strip())
            except ValueError:
                continue
        else:
            continue
        if parsed_scene_index == scene_index:
            if _boundary_prompt_is_placeholder(payload.get("prompt", "")):
                raise ValueError("boundary_prompt_placeholder")
            return typed_job
    raise ValueError("boundary_job_not_found")


def write_boundary_contract(
    contract: dict[str, object], output_path: str | Path
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contract, ensure_ascii=True, indent=2), encoding="utf-8")
    return path

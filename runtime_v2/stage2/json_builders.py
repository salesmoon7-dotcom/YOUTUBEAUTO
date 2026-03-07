from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.config import WorkloadName
from runtime_v2.contracts.job_contract import build_explicit_job_contract
from runtime_v2.contracts.render_spec import build_render_spec
from runtime_v2.contracts.stage2_contracts import build_stage2_payload


def ensure_common_asset_root(asset_root: str | Path) -> Path:
    root = Path(asset_root)
    if not root.exists() or not root.is_dir():
        raise ValueError("missing_common_asset_root")
    return root


def _scene_index_from_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return 0


def _service_output_name(workload: WorkloadName, run_id: str, scene_index: int) -> str:
    if workload == "geminigen":
        return f"video/#{scene_index:02d}_GEMI.mp4"
    if workload == "canva":
        return f"thumbs/canva-{run_id}-{scene_index}.png"
    return f"images/{workload}-{run_id}-{scene_index}.png"


def _build_voice_json(scene_plan: list[object]) -> dict[str, object]:
    voice_texts: list[dict[str, object]] = []
    for raw_scene in scene_plan:
        if not isinstance(raw_scene, dict):
            continue
        scene = cast(dict[str, object], raw_scene)
        scene_index = _scene_index_from_value(scene.get("scene_index", 0))
        prompt = str(scene.get("prompt", "")).strip()
        if scene_index <= 0 or not prompt:
            continue
        voice_texts.append(
            {
                "col": f"#{scene_index:02d}",
                "text": prompt,
                "original_voices": [scene_index],
            }
        )
    return {"voice_texts": voice_texts}


def build_stage2_jobs(video_plan: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object]]:
    asset_plan_raw = video_plan.get("asset_plan", {})
    if not isinstance(asset_plan_raw, dict):
        raise ValueError("artifact_invalid")
    asset_plan = cast(dict[str, object], asset_plan_raw)
    asset_root = ensure_common_asset_root(str(asset_plan.get("common_asset_folder", asset_plan.get("asset_root", ""))))
    run_id = str(video_plan.get("run_id", ""))
    row_ref = str(video_plan.get("row_ref", ""))
    scene_plan_raw = video_plan.get("scene_plan", [])
    jobs: list[dict[str, object]] = []
    workloads: list[WorkloadName] = ["genspark", "seaart", "geminigen", "canva"]
    typed_scene_plan = cast(list[object], scene_plan_raw) if isinstance(scene_plan_raw, list) else []
    asset_refs: list[str] = []
    timeline: list[dict[str, object]] = []
    thumbnail_refs: list[str] = []
    for scene_offset, raw_scene in enumerate(typed_scene_plan):
        if not isinstance(raw_scene, dict):
            continue
        scene = cast(dict[str, object], raw_scene)
        workload = workloads[scene_offset % len(workloads)]
        scene_index = _scene_index_from_value(scene.get("scene_index", 0))
        prompt = str(scene.get("prompt", "")).strip()
        service_artifact_path = (asset_root / _service_output_name(workload, run_id, scene_index)).resolve()
        payload = build_stage2_payload(
            run_id=run_id,
            row_ref=row_ref,
            scene_index=scene_index,
            prompt=prompt,
            asset_root=str(asset_root.resolve()),
            reason_code=str(video_plan.get("reason_code", "ok")),
        )
        payload["service_artifact_path"] = str(service_artifact_path)
        jobs.append(
            build_explicit_job_contract(
                job_id=f"{workload}-{run_id}-{scene_index}",
                workload=workload,
                checkpoint_key=f"stage2:{workload}:{row_ref}:{scene_index}",
                payload=payload,
            )
        )
        if workload == "canva":
            thumbnail_refs.append(str(service_artifact_path))
            continue
        asset_refs.append(str(service_artifact_path))
        timeline.append(
            {
                "scene_index": scene_index,
                "asset_path": str(service_artifact_path),
                "workload": workload,
            }
        )

    voice_json_path = (asset_root / "voice.json").resolve()
    render_spec = build_render_spec(
        run_id=run_id,
        row_ref=row_ref,
        asset_refs=asset_refs,
        timeline=timeline,
        audio_refs=[str(voice_json_path)],
        thumbnail_refs=thumbnail_refs,
        reason_code=str(video_plan.get("reason_code", "ok")),
    )
    render_payload: dict[str, object] = {
        "run_id": run_id,
        "row_ref": row_ref,
        "reason_code": str(video_plan.get("reason_code", "ok")),
        "render_folder_path": str(asset_root.resolve()),
        "voice_json_path": str(voice_json_path),
        "render_spec": render_spec,
        "voice_json": _build_voice_json(typed_scene_plan),
    }
    jobs.append(
        build_explicit_job_contract(
            job_id=f"render-{run_id}",
            workload="render",
            checkpoint_key=f"render:{row_ref}:{run_id}",
            payload=render_payload,
        )
    )
    return jobs, render_spec

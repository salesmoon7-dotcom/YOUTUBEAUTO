from __future__ import annotations

from pathlib import Path
import re
from typing import cast

from runtime_v2.config import WorkloadName
from runtime_v2.contracts.job_contract import build_explicit_job_contract
from runtime_v2.contracts.render_spec import build_render_spec
from runtime_v2.contracts.stage2_contracts import build_stage2_payload

LEGACY_IMAGE_CATEGORY_WORKLOADS: dict[str, WorkloadName] = {
    "인물": "genspark",
    "식품": "genspark",
    "글자": "genspark",
    "도표": "genspark",
    "도표-슬라이드": "genspark",
    "person": "genspark",
    "food": "genspark",
    "text": "genspark",
    "chart": "genspark",
    "chart-slide": "genspark",
    "chart slide": "genspark",
    "concept": "seaart",
    "place": "seaart",
    "object": "seaart",
    "hand": "seaart",
    "life": "seaart",
    "landscape": "seaart",
    "개념": "seaart",
    "장소": "seaart",
    "사물": "seaart",
    "손": "seaart",
    "생활": "seaart",
    "풍경": "seaart",
}
LEGACY_CATEGORY_PREFIX = re.compile(r"^\[(?P<label>[^\]]+)\]\s*(?P<body>.*)$")


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


def _legacy_scene_workload(prompt: str) -> tuple[WorkloadName | None, str, str]:
    normalized_prompt = str(prompt).strip()
    if not normalized_prompt:
        return None, "", ""
    matched = LEGACY_CATEGORY_PREFIX.match(normalized_prompt)
    if not matched:
        return None, "", normalized_prompt
    label_raw = str(matched.group("label") or "").strip()
    label = label_raw.lower()
    cleaned_prompt = str(matched.group("body") or "").strip()
    workload = LEGACY_IMAGE_CATEGORY_WORKLOADS.get(label)
    if workload is None:
        return None, "", normalized_prompt
    return workload, label_raw, cleaned_prompt or normalized_prompt


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


def _stage1_contract(video_plan: dict[str, object]) -> dict[str, object] | None:
    handoff = video_plan.get("stage1_handoff")
    if not isinstance(handoff, dict):
        return None
    contract = handoff.get("contract")
    if not isinstance(contract, dict):
        return None
    return cast(dict[str, object], contract)


def _build_thumb_data(
    *, prompt: str, stage1_contract: dict[str, object] | None
) -> dict[str, object]:
    title_for_thumb = ""
    if stage1_contract is not None:
        title_for_thumb = str(stage1_contract.get("title_for_thumb", "")).strip()
    line1 = title_for_thumb
    line2 = ""
    if "\n" in title_for_thumb:
        parts = [part.strip() for part in title_for_thumb.splitlines() if part.strip()]
        if parts:
            line1 = parts[0]
            line2 = parts[1] if len(parts) > 1 else ""
    return {
        "bg_prompt": prompt,
        "line1": line1,
        "line2": line2,
    }


def _select_ref_img(timeline: list[dict[str, object]]) -> str:
    for preferred_workload in ("genspark", "seaart"):
        for entry in timeline:
            if str(entry.get("workload", "")) != preferred_workload:
                continue
            candidate = str(entry.get("asset_path", "")).strip()
            if candidate:
                return candidate
    return ""


def _select_ref_img_from_stage1(stage1_contract: dict[str, object] | None) -> str:
    if stage1_contract is None:
        return ""
    for key in ("ref_img_1", "ref_img_2"):
        candidate = str(stage1_contract.get(key, "")).strip()
        if candidate:
            return candidate
    return ""


def _select_ref_images_from_stage1(
    stage1_contract: dict[str, object] | None,
) -> tuple[str, str]:
    if stage1_contract is None:
        return "", ""
    ref_img_1 = str(stage1_contract.get("ref_img_1", "")).strip()
    ref_img_2 = str(stage1_contract.get("ref_img_2", "")).strip()
    return ref_img_1, ref_img_2


def _build_ref_jobs(
    *,
    run_id: str,
    row_ref: str,
    asset_root: Path,
    stage1_handoff: dict[str, object] | None,
    stage1_contract: dict[str, object] | None,
    reason_code: str,
    agent_browser_services: set[str],
) -> tuple[list[dict[str, object]], str, str]:
    ref_jobs: list[dict[str, object]] = []
    ref_img_1_prompt, ref_img_2_prompt = _select_ref_images_from_stage1(stage1_contract)
    ref_img_1_path = ""
    ref_img_2_path = ""
    refs = [
        (ref_img_1_prompt, "genspark", 1, "ref-1"),
        (ref_img_2_prompt, "seaart", 2, "ref-2"),
    ]
    for prompt, workload, scene_index, ref_id in refs:
        if not prompt:
            continue
        service_artifact_path = (asset_root / f"images/{ref_id}-{run_id}.png").resolve()
        payload = build_stage2_payload(
            run_id=run_id,
            row_ref=row_ref,
            scene_index=scene_index,
            prompt=prompt,
            asset_root=str(asset_root.resolve()),
            reason_code=reason_code,
        )
        payload["service_artifact_path"] = str(service_artifact_path)
        if isinstance(stage1_handoff, dict):
            payload["stage1_handoff"] = stage1_handoff
        if workload in agent_browser_services:
            payload["use_agent_browser"] = True
        ref_jobs.append(
            build_explicit_job_contract(
                job_id=f"{workload}-{run_id}-{ref_id}",
                workload=cast(WorkloadName, workload),
                checkpoint_key=f"stage2:{workload}:{row_ref}:{ref_id}",
                payload=payload,
            )
        )
        if ref_id == "ref-1":
            ref_img_1_path = str(service_artifact_path)
        else:
            ref_img_2_path = str(service_artifact_path)
    return ref_jobs, ref_img_1_path, ref_img_2_path


def build_stage2_jobs(
    video_plan: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    asset_plan_raw = video_plan.get("asset_plan", {})
    if not isinstance(asset_plan_raw, dict):
        raise ValueError("artifact_invalid")
    asset_plan = cast(dict[str, object], asset_plan_raw)
    asset_root = ensure_common_asset_root(
        str(asset_plan.get("common_asset_folder", asset_plan.get("asset_root", "")))
    )
    run_id = str(video_plan.get("run_id", ""))
    row_ref = str(video_plan.get("row_ref", ""))
    scene_plan_raw = video_plan.get("scene_plan", [])
    jobs: list[dict[str, object]] = []
    workloads: list[WorkloadName] = ["genspark", "seaart", "geminigen", "canva"]
    typed_scene_plan = (
        cast(list[object], scene_plan_raw) if isinstance(scene_plan_raw, list) else []
    )
    asset_refs: list[str] = []
    timeline: list[dict[str, object]] = []
    thumbnail_refs: list[str] = []
    raw_agent_browser_services = video_plan.get("use_agent_browser_services", [])
    agent_browser_services = (
        {
            str(item).strip()
            for item in cast(list[object], raw_agent_browser_services)
            if str(item).strip()
        }
        if isinstance(raw_agent_browser_services, list)
        else set()
    )
    stage1_handoff = video_plan.get("stage1_handoff")
    stage1_contract = _stage1_contract(video_plan)
    ref_jobs, ref_img_1_path, ref_img_2_path = _build_ref_jobs(
        run_id=run_id,
        row_ref=row_ref,
        asset_root=asset_root,
        stage1_handoff=cast(dict[str, object], stage1_handoff)
        if isinstance(stage1_handoff, dict)
        else None,
        stage1_contract=stage1_contract,
        reason_code=str(video_plan.get("reason_code", "ok")),
        agent_browser_services=agent_browser_services,
    )
    jobs.extend(ref_jobs)
    for scene_offset, raw_scene in enumerate(typed_scene_plan):
        if not isinstance(raw_scene, dict):
            continue
        scene = cast(dict[str, object], raw_scene)
        scene_index = _scene_index_from_value(scene.get("scene_index", 0))
        prompt = str(scene.get("prompt", "")).strip()
        legacy_workload, legacy_category, cleaned_prompt = _legacy_scene_workload(
            prompt
        )
        workload = legacy_workload or workloads[scene_offset % len(workloads)]
        service_artifact_path = (
            asset_root / _service_output_name(workload, run_id, scene_index)
        ).resolve()
        payload = build_stage2_payload(
            run_id=run_id,
            row_ref=row_ref,
            scene_index=scene_index,
            prompt=cleaned_prompt,
            asset_root=str(asset_root.resolve()),
            reason_code=str(video_plan.get("reason_code", "ok")),
            ref_img_1=ref_img_1_path if workload in {"genspark", "seaart"} else "",
            ref_img_2=ref_img_2_path if workload in {"genspark", "seaart"} else "",
        )
        if legacy_category:
            payload["legacy_category"] = legacy_category
        payload["service_artifact_path"] = str(service_artifact_path)
        if isinstance(stage1_handoff, dict):
            payload["stage1_handoff"] = stage1_handoff
        if workload == "canva":
            payload["thumb_data"] = _build_thumb_data(
                prompt=prompt, stage1_contract=stage1_contract
            )
            ref_img = _select_ref_img_from_stage1(stage1_contract)
            if not ref_img:
                ref_img = _select_ref_img(timeline)
            if ref_img:
                payload["ref_img"] = ref_img
        if workload == "geminigen":
            ref_img = _select_ref_img_from_stage1(stage1_contract)
            if not ref_img:
                ref_img = _select_ref_img(timeline)
            if ref_img:
                payload["first_frame_path"] = ref_img
        if workload in agent_browser_services:
            payload["use_agent_browser"] = True
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
    if isinstance(stage1_handoff, dict):
        render_payload["stage1_handoff"] = stage1_handoff
    jobs.append(
        build_explicit_job_contract(
            job_id=f"render-{run_id}",
            workload="render",
            checkpoint_key=f"render:{row_ref}:{run_id}",
            payload=render_payload,
        )
    )
    return jobs, render_spec

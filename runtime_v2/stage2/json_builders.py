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
KENBURNS_PAN_DIRECTIONS: tuple[str, ...] = ("left", "right", "up", "down")
KENBURNS_ZOOM_MODES: tuple[str, ...] = ("in", "out")
KENBURNS_PAN_PCT = 0.05
KENBURNS_ZOOM_PCT = 0.40
DEFAULT_REAL_ROW_AGENT_BROWSER_SERVICES: set[str] = {
    "genspark",
    "seaart",
    "canva",
    "geminigen",
}


def _promotion_gate_for_workload(workload: WorkloadName) -> str:
    if workload in {"genspark", "seaart"}:
        return "A"
    if workload in {"canva", "geminigen"}:
        return "B"
    if workload in {"qwen3_tts", "rvc", "kenburns"}:
        return "C"
    if workload == "render":
        return "D"
    return ""


def ensure_common_asset_root(asset_root: str | Path) -> Path:
    root = Path(asset_root)
    if not root.exists() or not root.is_dir():
        raise ValueError("missing_common_asset_root")
    return root


def _scene_index_from_value(value: object) -> int:
    if isinstance(value, int):
        return int(str(value))
    if isinstance(value, float):
        return int(str(value))
    if isinstance(value, str):
        return int(value.strip())
    return 0


def _timeline_scene_indices(timeline: list[dict[str, object]]) -> list[int]:
    return [_scene_index_from_value(entry.get("scene_index", 0)) for entry in timeline]


def _build_kenburns_bundle_contract(
    *,
    run_id: str,
    row_ref: str,
    asset_root: Path,
    timeline: list[dict[str, object]],
    reason_code: str,
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    bundle_entries: list[dict[str, object]] = []
    kenburns_timeline: list[dict[str, object]] = []
    for entry in timeline:
        workload = str(entry.get("workload", "")).strip()
        if workload != "genspark" and workload != "seaart":
            if workload == "geminigen":
                kenburns_timeline.append(dict(entry))
            continue
        scene_index = _scene_index_from_value(entry.get("scene_index", 0))
        bundle_output_path = (
            asset_root / f"video/#{scene_index:02d}_KEN.mp4"
        ).resolve()
        bundle_entries.append(
            {
                "scene_key": f"scene_{scene_index:02d}",
                "scene_index": scene_index,
                "source_path": str(entry.get("asset_path", "")),
                "output_path": str(bundle_output_path),
                "duration_sec": 8,
                "pan_direction": KENBURNS_PAN_DIRECTIONS[
                    len(bundle_entries) % len(KENBURNS_PAN_DIRECTIONS)
                ],
                "pan_pct": KENBURNS_PAN_PCT,
                "zoom_mode": KENBURNS_ZOOM_MODES[
                    len(bundle_entries) % len(KENBURNS_ZOOM_MODES)
                ],
                "zoom_pct": KENBURNS_ZOOM_PCT,
            }
        )
        kenburns_timeline.append(
            {
                "scene_index": scene_index,
                "asset_path": str(bundle_output_path),
                "workload": "kenburns",
                "asset_kind": "video",
                "duration_sec": 8,
            }
        )
    if not bundle_entries:
        return None, timeline
    payload: dict[str, object] = {
        "run_id": run_id,
        "row_ref": row_ref,
        "reason_code": reason_code,
        "scene_bundle_map": {"scenes": bundle_entries},
        "service_artifact_path": str(
            (asset_root / "video" / f"kenburns-{run_id}.json").resolve()
        ),
        "promotion_gate": _promotion_gate_for_workload("kenburns"),
    }
    contract = build_explicit_job_contract(
        job_id=f"kenburns-{run_id}",
        workload="kenburns",
        checkpoint_key=f"kenburns:{row_ref}:{run_id}",
        payload=payload,
    )
    return contract, kenburns_timeline


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


def _stage1_videos(
    video_plan: dict[str, object], stage1_contract: dict[str, object] | None
) -> list[str]:
    for source in (
        video_plan.get("videos", []),
        [] if stage1_contract is None else stage1_contract.get("videos", []),
    ):
        if not isinstance(source, list):
            continue
        videos = [
            str(item).strip()
            for item in cast(list[object], source)
            if str(item).strip()
        ]
        if videos:
            return videos
    return []


def _build_thumb_data(
    *, prompt: str, stage1_contract: dict[str, object] | None
) -> dict[str, object]:
    title_for_thumb = ""
    if stage1_contract is not None:
        title_for_thumb = str(stage1_contract.get("title_for_thumb", "")).strip()
    bg_prompt = prompt
    line1 = title_for_thumb
    line2 = ""
    if title_for_thumb:
        parts = [part.strip() for part in title_for_thumb.splitlines() if part.strip()]
        if parts and any(part.startswith("Line 1:") for part in parts):
            preface = [part for part in parts if not part.startswith("Line ")]
            bg_prompt = preface[0] if preface else prompt
            for part in parts:
                if part.startswith("Line 1:"):
                    line1 = part.removeprefix("Line 1:").strip()
                elif part.startswith("Line 2:"):
                    line2 = part.removeprefix("Line 2:").strip()
        elif "\n" in title_for_thumb:
            if parts:
                line1 = parts[0]
                line2 = parts[1] if len(parts) > 1 else ""
    return {
        "bg_prompt": bg_prompt,
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


def _resolve_ref_input_as_file(candidate: str, asset_root: Path) -> str:
    text = candidate.strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        path = (asset_root / path).resolve()
    else:
        path = path.resolve()
    if path.exists() and path.is_file():
        return str(path)
    return ""


def _select_ref_img_from_stage1(
    stage1_contract: dict[str, object] | None, asset_root: Path
) -> str:
    if stage1_contract is None:
        return ""
    for key in ("ref_img_1", "ref_img_2"):
        candidate = str(stage1_contract.get(key, "")).strip()
        resolved = _resolve_ref_input_as_file(candidate, asset_root)
        if resolved:
            return resolved
    return ""


def _select_ref_images_from_stage1(
    stage1_contract: dict[str, object] | None,
) -> tuple[str, str]:
    if stage1_contract is None:
        return "", ""
    ref_img_1 = str(stage1_contract.get("ref_img_1", "")).strip()
    ref_img_2 = str(stage1_contract.get("ref_img_2", "")).strip()
    return ref_img_1, ref_img_2


def _sanitize_ref_job_prompt(prompt: str) -> str:
    text = prompt.strip()
    prefixes = [
        "Refer to attached character image.",
        "Refer to attached background image.",
        "Use attached images as reference.",
    ]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix) :].lstrip()
                changed = True
    return text


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
    ref_img_1_spec, ref_img_2_spec = _select_ref_images_from_stage1(stage1_contract)
    ref_img_1_path = ""
    ref_img_2_path = ""
    refs = [
        (ref_img_1_spec, "genspark", 1, "ref-1"),
        (ref_img_2_spec, "seaart", 2, "ref-2"),
    ]
    for ref_input, workload, scene_index, ref_id in refs:
        if not ref_input:
            continue
        resolved_file = _resolve_ref_input_as_file(ref_input, asset_root)
        if resolved_file:
            if ref_id == "ref-1":
                ref_img_1_path = resolved_file
            else:
                ref_img_2_path = resolved_file
            continue
        service_artifact_path = (asset_root / f"images/{ref_id}-{run_id}.png").resolve()
        payload = build_stage2_payload(
            run_id=run_id,
            row_ref=row_ref,
            scene_index=scene_index,
            prompt=_sanitize_ref_job_prompt(ref_input),
            asset_root=str(asset_root.resolve()),
            reason_code=reason_code,
        )
        payload["service_artifact_path"] = str(service_artifact_path)
        payload["promotion_gate"] = _promotion_gate_for_workload(
            cast(WorkloadName, workload)
        )
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


def _build_geminigen_jobs(
    *,
    run_id: str,
    row_ref: str,
    asset_root: Path,
    stage1_handoff: dict[str, object] | None,
    stage1_contract: dict[str, object] | None,
    reason_code: str,
    videos: list[str],
    scene_index_start: int,
    agent_browser_services: set[str],
) -> tuple[list[dict[str, object]], list[str], list[dict[str, object]]]:
    if not videos:
        return [], [], []
    geminigen_jobs: list[dict[str, object]] = []
    asset_refs: list[str] = []
    timeline: list[dict[str, object]] = []
    ref_img = _select_ref_img_from_stage1(stage1_contract, asset_root)
    for offset, video_prompt in enumerate(videos, start=1):
        scene_index = scene_index_start + offset
        service_artifact_path = (
            asset_root / _service_output_name("geminigen", run_id, scene_index)
        ).resolve()
        payload = build_stage2_payload(
            run_id=run_id,
            row_ref=row_ref,
            scene_index=scene_index,
            prompt=video_prompt,
            asset_root=str(asset_root.resolve()),
            reason_code=reason_code,
        )
        payload["service_artifact_path"] = str(service_artifact_path)
        payload["promotion_gate"] = _promotion_gate_for_workload("geminigen")
        if ref_img:
            payload["first_frame_path"] = ref_img
        if "geminigen" in agent_browser_services:
            payload["use_agent_browser"] = True
        if isinstance(stage1_handoff, dict):
            payload["stage1_handoff"] = stage1_handoff
        geminigen_jobs.append(
            build_explicit_job_contract(
                job_id=f"geminigen-{run_id}-{scene_index}",
                workload="geminigen",
                checkpoint_key=f"stage2:geminigen:{row_ref}:{scene_index}",
                payload=payload,
            )
        )
        asset_refs.append(str(service_artifact_path))
        timeline.append(
            {
                "scene_index": scene_index,
                "asset_path": str(service_artifact_path),
                "workload": "geminigen",
                "asset_kind": "video",
                "duration_sec": 8,
            }
        )
    return geminigen_jobs, asset_refs, timeline


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
    if not agent_browser_services and isinstance(stage1_handoff, dict):
        agent_browser_services = set(DEFAULT_REAL_ROW_AGENT_BROWSER_SERVICES)
    stage1_contract = _stage1_contract(video_plan)
    stage1_videos = _stage1_videos(video_plan, stage1_contract)
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
    scene_workloads: list[WorkloadName]
    if stage1_videos:
        scene_workloads = ["genspark", "seaart", "canva"]
    else:
        scene_workloads = workloads
    for scene_offset, raw_scene in enumerate(typed_scene_plan):
        if not isinstance(raw_scene, dict):
            continue
        scene = cast(dict[str, object], raw_scene)
        scene_index = _scene_index_from_value(scene.get("scene_index", 0))
        prompt = str(scene.get("prompt", "")).strip()
        legacy_workload, legacy_category, cleaned_prompt = _legacy_scene_workload(
            prompt
        )
        workload = (
            legacy_workload or scene_workloads[scene_offset % len(scene_workloads)]
        )
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
        payload["promotion_gate"] = _promotion_gate_for_workload(workload)
        if isinstance(stage1_handoff, dict):
            payload["stage1_handoff"] = stage1_handoff
        if workload == "canva":
            payload["thumb_data"] = _build_thumb_data(
                prompt=prompt, stage1_contract=stage1_contract
            )
            ref_img = _select_ref_img_from_stage1(stage1_contract, asset_root)
            if not ref_img:
                ref_img = _select_ref_img(timeline)
            if ref_img:
                payload["ref_img"] = ref_img
        if workload == "geminigen":
            ref_img = _select_ref_img_from_stage1(stage1_contract, asset_root)
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
                "asset_kind": "video" if workload == "geminigen" else "image",
                "duration_sec": 8,
            }
        )

    kenburns_contract, timeline = _build_kenburns_bundle_contract(
        run_id=run_id,
        row_ref=row_ref,
        asset_root=asset_root,
        timeline=timeline,
        reason_code=str(video_plan.get("reason_code", "ok")),
    )
    if kenburns_contract is not None:
        jobs.append(kenburns_contract)
        asset_refs = [str(entry.get("asset_path", "")) for entry in timeline]

    geminigen_jobs, geminigen_asset_refs, geminigen_timeline = _build_geminigen_jobs(
        run_id=run_id,
        row_ref=row_ref,
        asset_root=asset_root,
        stage1_handoff=cast(dict[str, object], stage1_handoff)
        if isinstance(stage1_handoff, dict)
        else None,
        stage1_contract=stage1_contract,
        reason_code=str(video_plan.get("reason_code", "ok")),
        videos=stage1_videos,
        scene_index_start=max([0, *_timeline_scene_indices(timeline)]),
        agent_browser_services=agent_browser_services,
    )
    jobs.extend(geminigen_jobs)
    asset_refs.extend(geminigen_asset_refs)
    timeline.extend(geminigen_timeline)

    voice_json_path = (asset_root / "voice.json").resolve()
    render_spec = build_render_spec(
        run_id=run_id,
        row_ref=row_ref,
        asset_refs=asset_refs,
        timeline=timeline,
        audio_refs=[],
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
        "promotion_gate": _promotion_gate_for_workload("render"),
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

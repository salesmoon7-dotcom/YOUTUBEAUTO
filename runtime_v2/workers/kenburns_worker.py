from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from runtime_v2.config import external_runtime_root
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
    write_json_atomic,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

PanDirection = Literal["left", "right", "up", "down"]
ZoomMode = Literal["in", "out"]
EffectType = Literal[
    "zoom_in_center",
    "zoom_out_center",
    "pan_left_to_right",
    "pan_right_to_left",
    "zoom_in_top_left",
    "zoom_in_bottom_right",
    "pan_up_to_down",
    "pan_down_to_up",
]

OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
OUTPUT_FPS = 60
UPSCALE_WIDTH = 8000
DEFAULT_PAN_PCT = 0.40
DEFAULT_ZOOM_PCT = 0.13
PAN_DIRECTION_SEQUENCE: tuple[PanDirection, ...] = ("left", "right", "up", "down")
ZOOM_MODE_SEQUENCE: tuple[ZoomMode, ...] = ("in", "out")
EFFECT_SEQUENCE: tuple[EffectType, ...] = (
    "zoom_in_center",
    "pan_left_to_right",
    "zoom_out_center",
    "pan_right_to_left",
    "zoom_in_top_left",
    "pan_up_to_down",
    "zoom_in_bottom_right",
    "pan_down_to_up",
)


def run_kenburns_job(
    job: JobContract | None = None, artifact_root: Path | None = None
) -> dict[str, object]:
    if job is None:
        return {"worker": "kenburns", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    bundle_map_path, bundle_entries = _load_scene_bundle_entries(workspace, job.payload)
    if bundle_entries is not None:
        return _run_kenburns_bundle_job(
            workspace=workspace,
            payload=job.payload,
            bundle_map_path=bundle_map_path,
            bundle_entries=bundle_entries,
        )
    raw_source = job.payload.get("source_path", "")
    source = (
        resolve_local_input(str(raw_source))
        if isinstance(raw_source, str) and raw_source.strip()
        else None
    )
    if source is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_source_path",
            retryable=False,
        )
    duration_value = job.payload.get("duration_sec", 12)
    duration_sec = (
        int(duration_value) if isinstance(duration_value, (int, float, str)) else 12
    )
    duration_sec = max(1, duration_sec)
    motion = _resolve_motion_settings(job.payload, scene_index=1)
    staged_input = stage_local_input(
        workspace, source, target_name=f"source{source.suffix.lower()}"
    )
    silent_output_path = workspace / "kenburns_silent.mp4"
    command = _silent_kenburns_command(
        staged_input,
        silent_output_path,
        duration_sec,
        motion=motion,
    )
    process_result = run_external_process(command, cwd=workspace)
    exit_code = process_result.get("exit_code", 1)
    exit_code_int = int(exit_code) if isinstance(exit_code, (int, float, str)) else 1
    if exit_code_int != 0 or not silent_output_path.exists():
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render_video",
            artifacts=[staged_input] if staged_input.exists() else [],
            error_code="ffmpeg_failed",
            retryable=True,
            details={
                "stdout": process_result.get("stdout", ""),
                "stderr": process_result.get("stderr", ""),
            },
            completion={
                "state": "failed",
                "final_output": False,
            },
        )
    output_path = silent_output_path
    raw_audio_path = job.payload.get("audio_path", "")
    if isinstance(raw_audio_path, str) and raw_audio_path.strip():
        audio_source = resolve_local_input(raw_audio_path)
        if audio_source is not None:
            staged_audio = stage_local_input(
                workspace,
                audio_source,
                target_name=f"audio{audio_source.suffix.lower()}",
            )
            muxed_output_path = workspace / "kenburns.mp4"
            mux_result = run_external_process(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(silent_output_path.resolve()),
                    "-i",
                    str(staged_audio.resolve()),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(muxed_output_path.resolve()),
                ],
                cwd=workspace,
            )
            mux_exit_code = mux_result.get("exit_code", 1)
            mux_exit_int = (
                int(mux_exit_code)
                if isinstance(mux_exit_code, (int, float, str))
                else 1
            )
            if mux_exit_int == 0 and muxed_output_path.exists():
                output_path = muxed_output_path
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="render_video",
        artifacts=[
            path
            for path in (staged_input, silent_output_path, output_path)
            if path.exists()
        ],
        retryable=False,
        details={
            "stdout": process_result.get("stdout", ""),
            "stderr": process_result.get("stderr", ""),
        },
        completion={
            "state": "succeeded",
            "final_output": True,
            "final_artifact": output_path.name,
            "final_artifact_path": str(output_path.resolve()),
        },
    )


def _run_kenburns_bundle_job(
    *,
    workspace: Path,
    payload: dict[str, object],
    bundle_map_path: Path | None,
    bundle_entries: list[dict[str, object]],
) -> dict[str, object]:
    if not bundle_entries:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[] if bundle_map_path is None else [bundle_map_path],
            error_code="invalid_scene_bundle_map",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    artifacts: list[Path] = [] if bundle_map_path is None else [bundle_map_path]
    bundle_manifest_path, manifest_error = _resolve_bundle_manifest_path(
        workspace, payload
    )
    if manifest_error:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=artifacts,
            error_code=manifest_error,
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )
    scene_outputs: list[dict[str, object]] = []
    for index, entry in enumerate(bundle_entries, start=1):
        scene_key = _scene_key(entry, index)
        resolved_output_path: Path | None = None
        raw_source = entry.get("source_path", entry.get("image_path", ""))
        source_path = (
            resolve_local_input(str(raw_source).strip())
            if str(raw_source).strip()
            else None
        )
        if source_path is None:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="validate_input",
                artifacts=artifacts,
                error_code="missing_source_path",
                retryable=False,
                details={"scene_key": scene_key},
                completion={"state": "failed", "final_output": False},
            )
        duration_sec = _duration_sec(entry.get("duration_sec", 8))
        motion = _resolve_motion_settings(entry, scene_index=index)
        staged_input = stage_local_input(
            workspace,
            source_path,
            target_name=f"{scene_key}_source{source_path.suffix.lower()}",
        )
        artifacts.append(staged_input)
        output_path_override = str(entry.get("output_path", "")).strip()
        if output_path_override:
            resolved_output_path = _resolve_local_output_path(
                output_path_override, base_dir=workspace
            )
            if resolved_output_path is None:
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="validate_input",
                    artifacts=artifacts,
                    error_code="invalid_output_path",
                    retryable=False,
                    details={
                        "scene_key": scene_key,
                        "output_path": output_path_override,
                    },
                    completion={"state": "failed", "final_output": False},
                )
            resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
            silent_output_path = resolved_output_path.with_name(
                f"{resolved_output_path.stem}_silent.mp4"
            )
        else:
            silent_output_path = workspace / f"{scene_key}_silent.mp4"
        process_result = run_external_process(
            _silent_kenburns_command(
                staged_input,
                silent_output_path,
                duration_sec,
                motion=motion,
            ),
            cwd=workspace,
        )
        exit_code = process_result.get("exit_code", 1)
        exit_code_int = (
            int(exit_code) if isinstance(exit_code, (int, float, str)) else 1
        )
        if exit_code_int != 0 or not silent_output_path.exists():
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="render_video",
                artifacts=artifacts,
                error_code="ffmpeg_failed",
                retryable=True,
                details={
                    "scene_key": scene_key,
                    "stdout": process_result.get("stdout", ""),
                    "stderr": process_result.get("stderr", ""),
                },
                completion={"state": "failed", "final_output": False},
            )
        artifacts.append(silent_output_path)
        output_path = silent_output_path
        raw_audio = str(entry.get("audio_path", "")).strip()
        if raw_audio:
            audio_source = resolve_local_input(raw_audio)
            if audio_source is not None:
                staged_audio = stage_local_input(
                    workspace,
                    audio_source,
                    target_name=f"{scene_key}_audio{audio_source.suffix.lower()}",
                )
                artifacts.append(staged_audio)
                if output_path_override:
                    if resolved_output_path is None:
                        return finalize_worker_result(
                            workspace,
                            status="failed",
                            stage="validate_input",
                            artifacts=artifacts,
                            error_code="invalid_output_path",
                            retryable=False,
                            details={
                                "scene_key": scene_key,
                                "output_path": output_path_override,
                            },
                            completion={"state": "failed", "final_output": False},
                        )
                    assert resolved_output_path is not None
                    muxed_output_path = resolved_output_path
                else:
                    muxed_output_path = workspace / f"{scene_key}.mp4"
                mux_result = run_external_process(
                    _audio_mux_command(
                        silent_output_path, staged_audio, muxed_output_path
                    ),
                    cwd=workspace,
                )
                mux_exit_code = mux_result.get("exit_code", 1)
                mux_exit_int = (
                    int(mux_exit_code)
                    if isinstance(mux_exit_code, (int, float, str))
                    else 1
                )
                if mux_exit_int != 0 or not muxed_output_path.exists():
                    return finalize_worker_result(
                        workspace,
                        status="failed",
                        stage="render_video",
                        artifacts=artifacts,
                        error_code="ffmpeg_failed",
                        retryable=True,
                        details={
                            "scene_key": scene_key,
                            "stdout": mux_result.get("stdout", ""),
                            "stderr": mux_result.get("stderr", ""),
                        },
                        completion={"state": "failed", "final_output": False},
                    )
                artifacts.append(muxed_output_path)
                output_path = muxed_output_path
        elif output_path_override:
            if resolved_output_path is None:
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="validate_input",
                    artifacts=artifacts,
                    error_code="invalid_output_path",
                    retryable=False,
                    details={
                        "scene_key": scene_key,
                        "output_path": output_path_override,
                    },
                    completion={"state": "failed", "final_output": False},
                )
            assert resolved_output_path is not None
            final_output_path = resolved_output_path
            final_output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path = final_output_path
            if silent_output_path.resolve() != final_output_path:
                _ = silent_output_path.replace(final_output_path)
        scene_outputs.append(
            {
                "scene_key": scene_key,
                "source_path": str(source_path.resolve()),
                "output_path": str(output_path.resolve()),
                "duration_sec": duration_sec,
                "audio_path": raw_audio,
                "effect_type": motion["effect_type"],
                "pan_direction": motion["pan_direction"],
                "pan_pct": motion["pan_pct"],
                "zoom_mode": motion["zoom_mode"],
                "zoom_pct": motion["zoom_pct"],
            }
        )
    bundle_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_manifest_path = write_json_atomic(
        bundle_manifest_path,
        {
            "scene_count": len(scene_outputs),
            "scenes": scene_outputs,
        },
    )
    artifacts.append(bundle_manifest_path)
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="render_video",
        artifacts=artifacts,
        retryable=False,
        details={
            "bundle_mode": "scene_bundle_map",
            "scene_count": len(scene_outputs),
            "bundle_manifest_path": str(bundle_manifest_path.resolve()),
        },
        completion={
            "state": "succeeded",
            "final_output": True,
            "final_artifact": bundle_manifest_path.name,
            "final_artifact_path": str(bundle_manifest_path.resolve()),
        },
    )


def _load_scene_bundle_entries(
    workspace: Path,
    payload: dict[str, object],
) -> tuple[Path | None, list[dict[str, object]] | None]:
    raw_bundle_path = str(payload.get("scene_bundle_map_path", "")).strip()
    if raw_bundle_path:
        resolved_path = resolve_local_input(raw_bundle_path)
        if resolved_path is None:
            return None, []
        staged_bundle_path = stage_local_input(
            workspace,
            resolved_path,
            target_name="scene_bundle_map.json",
        )
        try:
            raw_payload = cast(
                object, json.loads(staged_bundle_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError):
            return staged_bundle_path, []
        return staged_bundle_path, _normalize_scene_bundle_entries(raw_payload)
    raw_bundle = payload.get("scene_bundle_map")
    if raw_bundle is None:
        return None, None
    staged_bundle_path = write_json_atomic(
        workspace / "scene_bundle_map.json",
        {"scenes": raw_bundle},
    )
    return staged_bundle_path, _normalize_scene_bundle_entries(raw_bundle)


def _normalize_scene_bundle_entries(raw_bundle: object) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    if isinstance(raw_bundle, list):
        for raw_entry in cast(list[object], raw_bundle):
            if isinstance(raw_entry, dict):
                typed_entry = cast(dict[object, object], raw_entry)
                entries.append({str(key): value for key, value in typed_entry.items()})
        return entries
    if isinstance(raw_bundle, dict):
        typed_bundle = cast(dict[object, object], raw_bundle)
        scenes = typed_bundle.get("scenes")
        if isinstance(scenes, list):
            return _normalize_scene_bundle_entries(cast(object, scenes))
        for raw_key, raw_value in typed_bundle.items():
            if not isinstance(raw_value, dict):
                continue
            typed_entry = {
                str(key): value
                for key, value in cast(dict[object, object], raw_value).items()
            }
            _ = typed_entry.setdefault("scene_key", str(raw_key))
            entries.append(typed_entry)
    return entries


def _scene_key(entry: dict[str, object], index: int) -> str:
    raw_key = str(entry.get("scene_key", "")).strip()
    if not raw_key:
        raw_key = f"scene_{index:02d}"
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw_key)


def _duration_sec(value: object) -> int:
    duration_sec = int(value) if isinstance(value, (int, float, str)) else 12
    return max(1, duration_sec)


def _resolve_bundle_manifest_path(
    workspace: Path, payload: dict[str, object]
) -> tuple[Path, str]:
    raw_target = str(payload.get("service_artifact_path", "")).strip()
    if not raw_target:
        return workspace / "scene_bundle_manifest.json", ""
    resolved_target = _resolve_local_output_path(raw_target, base_dir=workspace)
    if resolved_target is None:
        return workspace / "scene_bundle_manifest.json", "invalid_service_artifact_path"
    return resolved_target, ""


def _resolve_local_output_path(raw_path: str, *, base_dir: Path) -> Path | None:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    allowed_roots = {REPO_ROOT.resolve(), external_runtime_root().resolve()}
    if not any(
        candidate == root or root in candidate.parents for root in allowed_roots
    ):
        return None
    return candidate


def _resolve_motion_settings(
    payload: dict[str, object], *, scene_index: int
) -> dict[str, object]:
    effect_type = _normalize_effect_type(
        payload.get("effect_type"),
        fallback=EFFECT_SEQUENCE[(max(scene_index, 1) - 1) % len(EFFECT_SEQUENCE)],
    )
    pan_direction = _normalize_pan_direction(
        payload.get("pan_direction"),
        fallback=PAN_DIRECTION_SEQUENCE[
            (max(scene_index, 1) - 1) % len(PAN_DIRECTION_SEQUENCE)
        ],
    )
    zoom_mode = _normalize_zoom_mode(
        payload.get("zoom_mode"),
        fallback=ZOOM_MODE_SEQUENCE[
            (max(scene_index, 1) - 1) % len(ZOOM_MODE_SEQUENCE)
        ],
    )
    pan_pct = _normalize_percentage(payload.get("pan_pct"), DEFAULT_PAN_PCT)
    zoom_pct = _normalize_percentage(payload.get("zoom_pct"), DEFAULT_ZOOM_PCT)
    return {
        "effect_type": effect_type,
        "pan_direction": pan_direction,
        "zoom_mode": zoom_mode,
        "pan_pct": pan_pct,
        "zoom_pct": zoom_pct,
    }


def _normalize_effect_type(value: object, *, fallback: EffectType) -> EffectType:
    normalized = str(value).strip().lower()
    if normalized in set(EFFECT_SEQUENCE):
        return cast(EffectType, normalized)
    return fallback


def _normalize_pan_direction(value: object, *, fallback: PanDirection) -> PanDirection:
    normalized = str(value).strip().lower()
    if normalized in {"left", "right", "up", "down"}:
        return cast(PanDirection, normalized)
    return fallback


def _normalize_zoom_mode(value: object, *, fallback: ZoomMode) -> ZoomMode:
    normalized = str(value).strip().lower()
    if normalized in {"in", "out"}:
        return cast(ZoomMode, normalized)
    return fallback


def _normalize_percentage(value: object, default: float) -> float:
    if isinstance(value, str):
        candidate_text = value.strip()
        if not candidate_text:
            return default
        candidate = float(candidate_text)
    elif isinstance(value, (int, float)):
        candidate = float(value)
    else:
        return default
    if candidate > 1.0:
        candidate = candidate / 100.0
    if candidate < 0:
        return 0.0
    return min(candidate, 0.95)


def _silent_kenburns_command(
    source: Path,
    output: Path,
    duration_sec: int,
    *,
    motion: dict[str, object],
) -> list[str]:
    frame_count = max(1, duration_sec * OUTPUT_FPS)
    filter_chain = _build_kenburns_filter(frame_count=frame_count, motion=motion)
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(source.resolve()),
        "-vf",
        filter_chain,
        "-t",
        str(duration_sec),
        "-r",
        str(OUTPUT_FPS),
        str(output.resolve()),
    ]


def _build_kenburns_filter(*, frame_count: int, motion: dict[str, object]) -> str:
    progress = "if(eq(duration,1),0,on/(duration-1))"
    effect_type = cast(EffectType, motion["effect_type"])
    pan_direction = cast(PanDirection, motion["pan_direction"])
    zoom_mode = cast(ZoomMode, motion["zoom_mode"])
    pan_pct = cast(float, motion["pan_pct"])
    zoom_pct = cast(float, motion["zoom_pct"])
    if effect_type in {
        "pan_left_to_right",
        "pan_right_to_left",
        "pan_up_to_down",
        "pan_down_to_up",
    }:
        ease_expr = f"({progress}*{progress}*(3-2*{progress}))"
        zoom_expr = "1.1"
        travel_x = "(iw-iw/zoom)"
        travel_y = "(ih-ih/zoom)"
        if effect_type == "pan_left_to_right":
            x_expr = f"{travel_x}*{pan_pct:.4f}*{ease_expr}"
            y_expr = "ih/2-(ih/zoom/2)"
        elif effect_type == "pan_right_to_left":
            x_expr = f"{travel_x}*(1-{pan_pct:.4f}*{ease_expr})"
            y_expr = "ih/2-(ih/zoom/2)"
        elif effect_type == "pan_up_to_down":
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"{travel_y}*{pan_pct:.4f}*{ease_expr}"
        else:
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"{travel_y}*(1-{pan_pct:.4f}*{ease_expr})"
        return (
            f"scale={UPSCALE_WIDTH}:-2,"
            f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
            f"d={frame_count}:fps={OUTPUT_FPS}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT},"
            "format=yuv420p"
        )
    if effect_type == "zoom_in_top_left":
        pan_direction = "left"
    elif effect_type == "zoom_in_bottom_right":
        pan_direction = "right"
    max_zoom = 1.0 + zoom_pct
    if zoom_mode == "out":
        zoom_expr = f"max({max_zoom:.4f}-{zoom_pct:.4f}*{progress},1.0)"
    else:
        zoom_expr = f"min(1.0+{zoom_pct:.4f}*{progress},{max_zoom:.4f})"
    travel_x = "(iw-iw/zoom)"
    travel_y = "(ih-ih/zoom)"
    center_x = f"({travel_x}/2)"
    center_y = f"({travel_y}/2)"
    pan_ratio = f"{pan_pct:.4f}"
    if pan_direction == "left":
        x_expr = f"max({center_x}-{travel_x}*{pan_ratio}*{progress},0)"
        y_expr = center_y
    elif pan_direction == "right":
        x_expr = f"min({center_x}+{travel_x}*{pan_ratio}*{progress},{travel_x})"
        y_expr = center_y
    elif pan_direction == "up":
        x_expr = center_x
        y_expr = f"max({center_y}-{travel_y}*{pan_ratio}*{progress},0)"
    else:
        x_expr = center_x
        y_expr = f"min({center_y}+{travel_y}*{pan_ratio}*{progress},{travel_y})"
    return (
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        f"scale={UPSCALE_WIDTH}:-2,"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frame_count}:fps={OUTPUT_FPS}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT},"
        "format=yuv420p"
    )


def _audio_mux_command(video: Path, audio: Path, output: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(video.resolve()),
        "-i",
        str(audio.resolve()),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output.resolve()),
    ]

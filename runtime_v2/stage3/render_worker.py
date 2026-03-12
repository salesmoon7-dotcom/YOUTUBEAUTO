from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import cast

from runtime_v2.config import external_runtime_root
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import (
    REPO_ROOT,
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
    write_json_atomic,
)


def _resolve_local_directory(raw_path: str) -> Path | None:
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
    if not candidate.exists() or not candidate.is_dir():
        return None
    return candidate


def _load_render_spec_payload(render_spec_path: Path) -> dict[str, object] | None:
    try:
        raw_payload = cast(
            object, json.loads(render_spec_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    typed_payload = cast(dict[object, object], raw_payload)
    return {str(key): value for key, value in typed_payload.items()}


def _missing_render_paths(render_spec: dict[str, object]) -> list[str]:
    missing_paths: list[str] = []

    def collect_paths(entries: object) -> None:
        if not isinstance(entries, list):
            return
        for entry in cast(list[object], entries):
            if (
                isinstance(entry, str)
                and entry.strip()
                and resolve_local_input(entry) is None
            ):
                missing_paths.append(entry)

    collect_paths(render_spec.get("asset_refs", []))
    collect_paths(render_spec.get("audio_refs", []))
    collect_paths(render_spec.get("thumbnail_refs", []))

    raw_timeline = render_spec.get("timeline", [])
    if isinstance(raw_timeline, list):
        for raw_entry in cast(list[object], raw_timeline):
            if not isinstance(raw_entry, dict):
                continue
            timeline_entry = cast(dict[object, object], raw_entry)
            asset_path = str(timeline_entry.get("asset_path", "")).strip()
            if asset_path and resolve_local_input(asset_path) is None:
                missing_paths.append(asset_path)

    return sorted(set(missing_paths))


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}


def _render_output_path(render_folder: Path) -> Path:
    return (render_folder / "output" / "render_final.mp4").resolve()


def _silent_render_output_path(render_folder: Path) -> Path:
    return (render_folder / "output" / "render_silent.mp4").resolve()


def _collect_render_assets(render_spec: dict[str, object]) -> list[Path]:
    candidates: list[Path] = []

    raw_timeline = render_spec.get("timeline", [])
    if isinstance(raw_timeline, list):
        for raw_entry in cast(list[object], raw_timeline):
            if not isinstance(raw_entry, dict):
                continue
            timeline_entry = cast(dict[object, object], raw_entry)
            asset_path = str(timeline_entry.get("asset_path", "")).strip()
            resolved = resolve_local_input(asset_path) if asset_path else None
            if resolved is not None:
                candidates.append(resolved)

    raw_asset_refs = render_spec.get("asset_refs", [])
    if isinstance(raw_asset_refs, list):
        for raw_entry in cast(list[object], raw_asset_refs):
            if not isinstance(raw_entry, str) or not raw_entry.strip():
                continue
            resolved = resolve_local_input(raw_entry)
            if resolved is not None:
                candidates.append(resolved)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        deduped.append(resolved)
        seen.add(resolved)
    return deduped


def _int_from_object(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return int(str(value))
    if isinstance(value, float):
        return int(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        return int(float(text))
    return default


def _render_timeline_entries(render_spec: dict[str, object]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    raw_timeline = render_spec.get("timeline", [])
    if not isinstance(raw_timeline, list):
        return entries
    for raw_entry in cast(list[object], raw_timeline):
        if not isinstance(raw_entry, dict):
            continue
        timeline_entry = cast(dict[object, object], raw_entry)
        asset_path = str(timeline_entry.get("asset_path", "")).strip()
        resolved = resolve_local_input(asset_path) if asset_path else None
        if resolved is None:
            continue
        asset_kind = str(timeline_entry.get("asset_kind", "")).strip().lower()
        if asset_kind not in {"image", "video"}:
            asset_kind = (
                "video" if resolved.suffix.lower() in VIDEO_EXTENSIONS else "image"
            )
        raw_duration = timeline_entry.get("duration_sec", 8)
        duration_sec = max(1, _int_from_object(raw_duration, 8))
        raw_scene_index = timeline_entry.get("scene_index", len(entries) + 1)
        scene_index = _int_from_object(raw_scene_index, len(entries) + 1)
        entries.append(
            {
                "scene_index": scene_index,
                "asset_path": str(resolved.resolve()),
                "asset_kind": asset_kind,
                "duration_sec": duration_sec,
            }
        )
    return entries


def _canonical_audio_candidates(run_id: str, artifact_root: Path) -> list[Path]:
    if not run_id.strip():
        return []
    return [
        (artifact_root / "rvc" / f"rvc-qwen3-{run_id}" / "speech_rvc.wav").resolve(),
        (artifact_root / "qwen3_tts" / f"qwen3-{run_id}" / "speech.wav").resolve(),
    ]


def _select_primary_audio(
    render_spec: dict[str, object], artifact_root: Path
) -> Path | None:
    candidates: list[Path] = []
    raw_audio_refs = render_spec.get("audio_refs", [])
    if isinstance(raw_audio_refs, list):
        for raw_entry in cast(list[object], raw_audio_refs):
            if not isinstance(raw_entry, str) or not raw_entry.strip():
                continue
            resolved = resolve_local_input(raw_entry)
            if resolved is not None and resolved.suffix.lower() in AUDIO_EXTENSIONS:
                candidates.append(resolved.resolve())
    candidates.extend(
        _canonical_audio_candidates(
            str(render_spec.get("run_id", "")).strip(), artifact_root
        )
    )
    for candidate in candidates:
        if (
            candidate.exists()
            and candidate.is_file()
            and candidate.suffix.lower() in AUDIO_EXTENSIONS
        ):
            return candidate.resolve()
    return None


def _select_primary_render_asset(
    render_spec: dict[str, object],
) -> tuple[Path | None, str]:
    assets = _collect_render_assets(render_spec)
    for candidate in assets:
        if candidate.suffix.lower() in VIDEO_EXTENSIONS:
            return candidate, "video_copy"
    for candidate in assets:
        if candidate.suffix.lower() in IMAGE_EXTENSIONS:
            return candidate, "image_ffmpeg"
    return None, ""


def _render_from_image(source_image: Path, output_path: Path) -> dict[str, object]:
    return _render_image_clip(source_image, output_path, duration_sec=8)


def _render_image_clip(
    source_image: Path, output_path: Path, *, duration_sec: int
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(source_image.resolve()),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-t",
        str(duration_sec),
        "-r",
        "30",
        str(output_path.resolve()),
    ]
    return run_external_process(command, cwd=output_path.parent)


def _render_video_clip(
    source_video: Path, output_path: Path, *, duration_sec: int
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video.resolve()),
        "-t",
        str(duration_sec),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-r",
        "30",
        str(output_path.resolve()),
    ]
    return run_external_process(command, cwd=output_path.parent)


def _concat_scene_clips(
    scene_clips: list[Path], output_path: Path
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output_path.parent / "render_concat.txt"
    concat_text = "".join(
        f"file '{str(path.resolve()).replace("'", "''")}'\n" for path in scene_clips
    )
    concat_file.write_text(concat_text, encoding="utf-8")
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file.resolve()),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path.resolve()),
    ]
    return run_external_process(command, cwd=output_path.parent)


def _mux_render_audio(
    video_path: Path, audio_path: Path, output_path: Path
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path.resolve()),
        "-i",
        str(audio_path.resolve()),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path.resolve()),
    ]
    return run_external_process(command, cwd=output_path.parent)


def run_render_job(job: JobContract, artifact_root: Path) -> dict[str, object]:
    workspace = prepare_workspace(job, artifact_root)
    try:
        render_spec_path = workspace / "render_spec.json"
        raw_render_spec_path = str(job.payload.get("render_spec_path", "")).strip()
        if raw_render_spec_path:
            source_render_spec = resolve_local_input(raw_render_spec_path)
            if source_render_spec is None:
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="render",
                    artifacts=[],
                    error_code="missing_render_spec",
                    retryable=True,
                    completion={"state": "blocked", "final_output": False},
                )
            staged_render_spec = stage_local_input(
                workspace, source_render_spec, target_name="render_spec.json"
            )
        else:
            render_spec_payload = job.payload.get(
                "render_spec", {"payload": job.payload}
            )
            typed_render_spec: dict[str, object]
            if isinstance(render_spec_payload, dict):
                typed_render_spec = cast(dict[str, object], render_spec_payload)
            else:
                typed_render_spec = {"payload": job.payload}
            staged_render_spec = write_json_atomic(render_spec_path, typed_render_spec)

        raw_render_folder_path = str(job.payload.get("render_folder_path", "")).strip()
        raw_voice_json_path = str(job.payload.get("voice_json_path", "")).strip()
        render_folder = (
            _resolve_local_directory(raw_render_folder_path)
            if raw_render_folder_path
            else None
        )
        voice_json_path = (
            resolve_local_input(raw_voice_json_path) if raw_voice_json_path else None
        )
        if voice_json_path is None:
            voice_json_payload = job.payload.get("voice_json", {})
            if isinstance(voice_json_payload, dict):
                voice_json_path = write_json_atomic(
                    workspace / "voice.json",
                    cast(dict[str, object], voice_json_payload),
                )
    except OSError as exc:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[],
            error_code="render_io_failed",
            retryable=False,
            completion={"state": "failed", "final_output": False},
            details={"exception": str(exc)},
        )
    if render_folder is None or voice_json_path is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[staged_render_spec],
            error_code="missing_render_inputs",
            retryable=True,
            completion={"state": "blocked", "final_output": False},
            details={
                "render_folder_path": raw_render_folder_path,
                "voice_json_path": raw_voice_json_path,
            },
        )

    render_spec_payload = _load_render_spec_payload(staged_render_spec)
    if render_spec_payload is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[staged_render_spec, voice_json_path],
            error_code="invalid_render_spec",
            retryable=False,
            completion={"state": "failed", "final_output": False},
        )

    missing_paths = _missing_render_paths(render_spec_payload)
    if missing_paths:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[staged_render_spec, voice_json_path],
            error_code="render_inputs_not_ready",
            retryable=True,
            completion={"state": "blocked", "final_output": False},
            details={
                "render_folder_path": str(render_folder.resolve()),
                "missing_paths": missing_paths,
            },
        )

    try:
        final_output_path = _render_output_path(render_folder)
        final_output_path.parent.mkdir(parents=True, exist_ok=True)
        if final_output_path.exists() and final_output_path.is_file():
            return finalize_worker_result(
                workspace,
                status="ok",
                stage="render",
                artifacts=[staged_render_spec, voice_json_path, final_output_path],
                retryable=False,
                details={
                    "render_folder_path": str(render_folder.resolve()),
                    "voice_json_path": str(voice_json_path.resolve()),
                    "service_artifact_path": str(final_output_path.resolve()),
                    "render_mode": "reused",
                    "reused": True,
                    "reason_code": str(render_spec_payload.get("reason_code", "ok")),
                },
                completion={
                    "state": "succeeded",
                    "final_output": True,
                    "final_artifact": final_output_path.name,
                    "final_artifact_path": str(final_output_path.resolve()),
                    "reused": True,
                },
            )

        timeline_entries = _render_timeline_entries(render_spec_payload)
        if not timeline_entries:
            source_asset, render_mode = _select_primary_render_asset(
                render_spec_payload
            )
            if source_asset is None:
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="render",
                    artifacts=[staged_render_spec, voice_json_path],
                    error_code="render_asset_unsupported",
                    retryable=False,
                    completion={"state": "failed", "final_output": False},
                    details={
                        "render_folder_path": str(render_folder.resolve()),
                        "voice_json_path": str(voice_json_path.resolve()),
                        "reason_code": str(
                            render_spec_payload.get("reason_code", "ok")
                        ),
                    },
                )
            timeline_entries = [
                {
                    "scene_index": 1,
                    "asset_path": str(source_asset.resolve()),
                    "asset_kind": "video" if render_mode == "video_copy" else "image",
                    "duration_sec": 8,
                }
            ]

        scene_clips: list[Path] = []
        process_details = {"stdout": "", "stderr": ""}
        audio_source = _select_primary_audio(render_spec_payload, artifact_root)
        if (
            len(timeline_entries) == 1
            and str(timeline_entries[0]["asset_kind"]) == "video"
            and audio_source is None
        ):
            source_asset = Path(str(timeline_entries[0]["asset_path"]))
            _ = shutil.copy2(source_asset, final_output_path)
            return finalize_worker_result(
                workspace,
                status="ok",
                stage="render",
                artifacts=[staged_render_spec, voice_json_path, final_output_path],
                retryable=False,
                details={
                    "render_folder_path": str(render_folder.resolve()),
                    "voice_json_path": str(voice_json_path.resolve()),
                    "source_asset_path": str(source_asset.resolve()),
                    "audio_source_path": "",
                    "service_artifact_path": str(final_output_path.resolve()),
                    "render_mode": "video_copy",
                    "reused": False,
                    "reason_code": str(render_spec_payload.get("reason_code", "ok")),
                    "stdout": "",
                    "stderr": "",
                },
                completion={
                    "state": "succeeded",
                    "final_output": True,
                    "final_artifact": final_output_path.name,
                    "final_artifact_path": str(final_output_path.resolve()),
                    "reused": False,
                },
            )
        for entry in timeline_entries:
            scene_index = _int_from_object(entry.get("scene_index"), 1)
            asset_path = Path(str(entry["asset_path"]))
            asset_kind = str(entry["asset_kind"])
            duration_sec = _int_from_object(entry.get("duration_sec"), 8)
            scene_output = render_folder / "output" / f"scene_{scene_index:02d}.mp4"
            if asset_kind == "video":
                process_result = _render_video_clip(
                    asset_path, scene_output, duration_sec=duration_sec
                )
            else:
                process_result = _render_image_clip(
                    asset_path, scene_output, duration_sec=duration_sec
                )
            exit_code = process_result.get("exit_code", 1)
            exit_code_int = (
                int(exit_code) if isinstance(exit_code, (int, float, str)) else 1
            )
            if (
                exit_code_int != 0
                or not scene_output.exists()
                or not scene_output.is_file()
            ):
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="render",
                    artifacts=[staged_render_spec, voice_json_path, *scene_clips],
                    error_code="ffmpeg_failed",
                    retryable=True,
                    completion={"state": "failed", "final_output": False},
                    details={
                        "render_folder_path": str(render_folder.resolve()),
                        "voice_json_path": str(voice_json_path.resolve()),
                        "source_asset_path": str(asset_path.resolve()),
                        "stdout": str(process_result.get("stdout", "")),
                        "stderr": str(process_result.get("stderr", "")),
                        "reason_code": str(
                            render_spec_payload.get("reason_code", "ok")
                        ),
                    },
                )
            scene_clips.append(scene_output.resolve())
            process_details = {
                "stdout": str(
                    process_result.get("stdout", process_details.get("stdout", ""))
                ),
                "stderr": str(
                    process_result.get("stderr", process_details.get("stderr", ""))
                ),
            }

        silent_output_path = _silent_render_output_path(render_folder)
        if len(scene_clips) == 1:
            _ = shutil.copy2(scene_clips[0], silent_output_path)
        else:
            concat_result = _concat_scene_clips(scene_clips, silent_output_path)
            concat_exit = concat_result.get("exit_code", 1)
            concat_exit_int = (
                int(concat_exit) if isinstance(concat_exit, (int, float, str)) else 1
            )
            if (
                concat_exit_int != 0
                or not silent_output_path.exists()
                or not silent_output_path.is_file()
            ):
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="render",
                    artifacts=[staged_render_spec, voice_json_path, *scene_clips],
                    error_code="ffmpeg_failed",
                    retryable=True,
                    completion={"state": "failed", "final_output": False},
                    details={
                        "render_folder_path": str(render_folder.resolve()),
                        "voice_json_path": str(voice_json_path.resolve()),
                        "stdout": str(concat_result.get("stdout", "")),
                        "stderr": str(concat_result.get("stderr", "")),
                        "reason_code": str(
                            render_spec_payload.get("reason_code", "ok")
                        ),
                    },
                )
            process_details = {
                "stdout": str(
                    concat_result.get("stdout", process_details.get("stdout", ""))
                ),
                "stderr": str(
                    concat_result.get("stderr", process_details.get("stderr", ""))
                ),
            }

        if audio_source is not None:
            mux_result = _mux_render_audio(
                silent_output_path, audio_source, final_output_path
            )
            mux_exit = mux_result.get("exit_code", 1)
            mux_exit_int = (
                int(mux_exit) if isinstance(mux_exit, (int, float, str)) else 1
            )
            if (
                mux_exit_int != 0
                or not final_output_path.exists()
                or not final_output_path.is_file()
            ):
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="render",
                    artifacts=[
                        staged_render_spec,
                        voice_json_path,
                        *scene_clips,
                        silent_output_path,
                    ],
                    error_code="ffmpeg_failed",
                    retryable=True,
                    completion={"state": "failed", "final_output": False},
                    details={
                        "render_folder_path": str(render_folder.resolve()),
                        "voice_json_path": str(voice_json_path.resolve()),
                        "audio_source_path": str(audio_source.resolve()),
                        "stdout": str(mux_result.get("stdout", "")),
                        "stderr": str(mux_result.get("stderr", "")),
                        "reason_code": str(
                            render_spec_payload.get("reason_code", "ok")
                        ),
                    },
                )
            process_details = {
                "stdout": str(
                    mux_result.get("stdout", process_details.get("stdout", ""))
                ),
                "stderr": str(
                    mux_result.get("stderr", process_details.get("stderr", ""))
                ),
            }
            render_mode = "timeline_ffmpeg_audio"
        else:
            _ = shutil.copy2(silent_output_path, final_output_path)
            render_mode = "timeline_ffmpeg"

        source_asset = scene_clips[0] if scene_clips else final_output_path

        if not final_output_path.exists() or not final_output_path.is_file():
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="render",
                artifacts=[staged_render_spec, voice_json_path, *scene_clips],
                error_code="render_output_missing",
                retryable=False,
                completion={"state": "failed", "final_output": False},
                details={
                    "render_folder_path": str(render_folder.resolve()),
                    "voice_json_path": str(voice_json_path.resolve()),
                    "source_asset_path": str(source_asset.resolve()),
                    "render_mode": render_mode,
                    "reason_code": str(render_spec_payload.get("reason_code", "ok")),
                },
            )

        return finalize_worker_result(
            workspace,
            status="ok",
            stage="render",
            artifacts=[
                staged_render_spec,
                voice_json_path,
                *scene_clips,
                final_output_path,
            ],
            retryable=False,
            details={
                "render_folder_path": str(render_folder.resolve()),
                "voice_json_path": str(voice_json_path.resolve()),
                "source_asset_path": str(source_asset.resolve()),
                "audio_source_path": ""
                if audio_source is None
                else str(audio_source.resolve()),
                "service_artifact_path": str(final_output_path.resolve()),
                "render_mode": render_mode,
                "reused": False,
                "reason_code": str(render_spec_payload.get("reason_code", "ok")),
                **process_details,
            },
            completion={
                "state": "succeeded",
                "final_output": True,
                "final_artifact": final_output_path.name,
                "final_artifact_path": str(final_output_path.resolve()),
                "reused": False,
            },
        )
    except OSError as exc:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="render",
            artifacts=[staged_render_spec, voice_json_path],
            error_code="render_io_failed",
            retryable=False,
            completion={"state": "failed", "final_output": False},
            details={
                "render_folder_path": str(render_folder.resolve()),
                "voice_json_path": str(voice_json_path.resolve()),
                "reason_code": str(render_spec_payload.get("reason_code", "ok")),
                "exception": str(exc),
            },
        )

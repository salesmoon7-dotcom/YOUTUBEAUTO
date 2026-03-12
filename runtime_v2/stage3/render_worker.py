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


def _render_output_path(render_folder: Path) -> Path:
    return (render_folder / "output" / "render_final.mp4").resolve()


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
        "8",
        "-r",
        "30",
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

        source_asset, render_mode = _select_primary_render_asset(render_spec_payload)
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
                    "reason_code": str(render_spec_payload.get("reason_code", "ok")),
                },
            )

        if render_mode == "video_copy":
            _ = shutil.copy2(source_asset, final_output_path)
            process_details = {"stdout": "", "stderr": ""}
        else:
            process_result = _render_from_image(source_asset, final_output_path)
            exit_code = process_result.get("exit_code", 1)
            exit_code_int = (
                int(exit_code) if isinstance(exit_code, (int, float, str)) else 1
            )
            if (
                exit_code_int != 0
                or not final_output_path.exists()
                or not final_output_path.is_file()
            ):
                return finalize_worker_result(
                    workspace,
                    status="failed",
                    stage="render",
                    artifacts=[staged_render_spec, voice_json_path],
                    error_code="ffmpeg_failed",
                    retryable=True,
                    completion={"state": "failed", "final_output": False},
                    details={
                        "render_folder_path": str(render_folder.resolve()),
                        "voice_json_path": str(voice_json_path.resolve()),
                        "source_asset_path": str(source_asset.resolve()),
                        "stdout": str(process_result.get("stdout", "")),
                        "stderr": str(process_result.get("stderr", "")),
                        "reason_code": str(
                            render_spec_payload.get("reason_code", "ok")
                        ),
                    },
                )
            process_details = {
                "stdout": str(process_result.get("stdout", "")),
                "stderr": str(process_result.get("stderr", "")),
            }

        if not final_output_path.exists() or not final_output_path.is_file():
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="render",
                artifacts=[staged_render_spec, voice_json_path],
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
            artifacts=[staged_render_spec, voice_json_path, final_output_path],
            retryable=False,
            details={
                "render_folder_path": str(render_folder.resolve()),
                "voice_json_path": str(voice_json_path.resolve()),
                "source_asset_path": str(source_asset.resolve()),
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

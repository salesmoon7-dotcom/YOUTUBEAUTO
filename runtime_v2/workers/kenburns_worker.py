from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
    stage_local_input,
    write_json_atomic,
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
    duration_value = job.payload.get("duration_sec", 8)
    duration_sec = (
        int(duration_value) if isinstance(duration_value, (int, float, str)) else 8
    )
    duration_sec = max(1, duration_sec)
    staged_input = stage_local_input(
        workspace, source, target_name=f"source{source.suffix.lower()}"
    )
    silent_output_path = workspace / "kenburns_silent.mp4"
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(staged_input.resolve()),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-t",
        str(duration_sec),
        "-r",
        "30",
        str(silent_output_path.resolve()),
    ]
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
    scene_outputs: list[dict[str, object]] = []
    for index, entry in enumerate(bundle_entries, start=1):
        scene_key = _scene_key(entry, index)
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
        staged_input = stage_local_input(
            workspace,
            source_path,
            target_name=f"{scene_key}_source{source_path.suffix.lower()}",
        )
        artifacts.append(staged_input)
        silent_output_path = workspace / f"{scene_key}_silent.mp4"
        process_result = run_external_process(
            _silent_kenburns_command(staged_input, silent_output_path, duration_sec),
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
        scene_outputs.append(
            {
                "scene_key": scene_key,
                "source_path": str(source_path.resolve()),
                "output_path": str(output_path.resolve()),
                "duration_sec": duration_sec,
                "audio_path": raw_audio,
            }
        )
    bundle_manifest_path = write_json_atomic(
        workspace / "scene_bundle_manifest.json",
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
    duration_sec = int(value) if isinstance(value, (int, float, str)) else 8
    return max(1, duration_sec)


def _silent_kenburns_command(
    source: Path, output: Path, duration_sec: int
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(source.resolve()),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-t",
        str(duration_sec),
        "-r",
        "30",
        str(output.resolve()),
    ]


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

from __future__ import annotations

from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.stage2.legacy_executor import LEGACY_ROOT, int_value, load_legacy_result_json, resolve_output_from_result, script_command, stage_output
from runtime_v2.workers.external_process import run_external_process
from runtime_v2.workers.job_runtime import finalize_worker_result, prepare_workspace, write_json_atomic


def run_qwen3_job(job: JobContract | None = None, artifact_root: Path | None = None) -> dict[str, object]:
    if job is None:
        return {"worker": "qwen3_tts", "status": "failed", "error_code": "missing_job"}
    workspace = prepare_workspace(job, artifact_root=artifact_root)
    raw_text = job.payload.get("script_text", "")
    script_text = str(raw_text).strip() if isinstance(raw_text, str) else ""
    if not script_text:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_script_text",
            retryable=False,
        )

    project_root = workspace / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    prompt_payload = {
        "channel": int_value(job.payload.get("channel", 0), 0),
        "rows": [
            {
                "row_index": 0,
                "channel": int_value(job.payload.get("channel", 0), 0),
                "topic": str(job.payload.get("topic", job.job_id)),
                "no": str(job.payload.get("episode_no", "1")),
                "folder_path": str(project_root.resolve()),
                "voice_texts": [{"col": "#01", "text": script_text}],
            }
        ],
    }
    request_file = write_json_atomic(workspace / "request.json", {"payload": job.payload})
    prompt_file = write_json_atomic(workspace / "qwen_prompt.json", prompt_payload)
    result_json_path = workspace / "legacy_result.json"
    command = script_command("qwen3_tts_automation.py") + [
        "--prompt-file",
        str(prompt_file.resolve()),
        "--row-index",
        "0",
        "--result-json",
        str(result_json_path.resolve()),
    ]
    process_result = cast(dict[str, object], run_external_process(command, cwd=LEGACY_ROOT))
    exit_code = int_value(process_result.get("exit_code", 1), 1)
    if exit_code != 0 or not result_json_path.exists():
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="qwen3_tts",
            artifacts=[request_file, prompt_file],
            error_code="legacy_executor_failed",
            retryable=True,
            details={"process_result": process_result},
            completion={"state": "blocked", "final_output": False},
        )

    parsed_result = load_legacy_result_json(
        workspace,
        stage="qwen3_tts",
        result_json_path=result_json_path,
        artifacts=[request_file, prompt_file, result_json_path],
        process_result=process_result,
    )
    if parsed_result.get("status") == "failed":
        return parsed_result

    result_payload = cast(dict[str, object], parsed_result)
    output_path = resolve_output_from_result(result_payload)
    if output_path is None:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="qwen3_tts",
            artifacts=[request_file, prompt_file, result_json_path],
            error_code="missing_legacy_outputs",
            retryable=True,
            details={"legacy_result": result_payload, "process_result": process_result},
            completion={"state": "blocked", "final_output": False},
        )

    staged_output = stage_output(workspace, output_path, fallback_name="speech.flac")
    chain_depth_value = job.payload.get("chain_depth", 0)
    chain_depth = int(chain_depth_value) if isinstance(chain_depth_value, (int, float, str)) else 0
    next_payload: dict[str, object] = {
        "source_path": str(staged_output.resolve()),
        "chain_depth": chain_depth + 1,
    }
    image_path = str(job.payload.get("image_path", "")).strip()
    if image_path:
        next_payload["image_path"] = image_path
    model_name = str(job.payload.get("model_name", "")).strip()
    if model_name:
        next_payload["model_name"] = model_name
    next_jobs: list[dict[str, object]] = [
        build_explicit_job_contract(
            job_id=f"rvc-{job.job_id}",
            workload="rvc",
            checkpoint_key=f"derived:rvc:{job.job_id}",
            payload=next_payload,
            parent_job_id=job.job_id,
            chain_step=chain_depth + 1,
        )
    ]
    return finalize_worker_result(
        workspace,
        status="ok",
        stage="qwen3_tts",
        artifacts=[request_file, prompt_file, result_json_path, staged_output],
        retryable=False,
        details={
            "legacy_result": result_payload,
            "tts_backend": "legacy_qwen3_tts",
            "service_artifact_path": str(output_path.resolve()),
        },
        next_jobs=next_jobs,
        completion={
            "state": "routed",
            "final_output": False,
        },
    )

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.stage2.request_builders import (
    build_canva_thumb_file,
    channel_from_payload,
    row_index_from_payload,
)
from runtime_v2.workers.job_runtime import (
    finalize_worker_result,
    prepare_workspace,
    resolve_local_input,
)
from runtime_v2.workers.native_only import (
    native_not_implemented_result,
    write_native_request,
)


def run_canva_job(
    job: JobContract, artifact_root: Path, registry_file: Path | None = None
) -> dict[str, object]:
    _ = registry_file
    workspace = prepare_workspace(job, artifact_root)
    prompt = str(job.payload.get("prompt", "")).strip()
    if not prompt:
        return finalize_worker_result(
            workspace,
            status="failed",
            stage="validate_input",
            artifacts=[],
            error_code="missing_prompt",
            retryable=False,
            completion={"state": "blocked", "final_output": False},
        )
    request_path = write_native_request(workspace, job.payload)
    thumb_data_path = build_canva_thumb_file(workspace, job.payload)
    ref_img = str(job.payload.get("ref_img", "")).strip()
    adapter_command_raw = job.payload.get("adapter_command")
    if isinstance(adapter_command_raw, list) and adapter_command_raw:
        adapter_command_items = cast(list[object], adapter_command_raw)
        adapter_command = [str(item) for item in adapter_command_items]
        completed = subprocess.run(
            adapter_command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )
        stdout_path = workspace / "adapter_stdout.log"
        stderr_path = workspace / "adapter_stderr.log"
        _ = stdout_path.write_text(completed.stdout, encoding="utf-8")
        _ = stderr_path.write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="canva_adapter",
                artifacts=[request_path, thumb_data_path, stdout_path, stderr_path],
                error_code="canva_adapter_failed",
                retryable=False,
                details={"returncode": completed.returncode},
                completion={"state": "blocked", "final_output": False},
            )

        service_artifact_path = str(
            job.payload.get("service_artifact_path", "")
        ).strip()
        verified_output = resolve_local_input(service_artifact_path)
        if verified_output is None:
            return finalize_worker_result(
                workspace,
                status="failed",
                stage="canva_verify_output",
                artifacts=[request_path, thumb_data_path, stdout_path, stderr_path],
                error_code="missing_service_artifact_path",
                retryable=False,
                completion={"state": "blocked", "final_output": False},
            )

        return finalize_worker_result(
            workspace,
            status="ok",
            stage="canva",
            artifacts=[
                request_path,
                thumb_data_path,
                stdout_path,
                stderr_path,
                verified_output,
            ],
            retryable=False,
            details={
                "channel": channel_from_payload(job.payload),
                "row_index": row_index_from_payload(job.payload),
                "save_path": str(verified_output.resolve()),
                "ref_img": ref_img,
                "service_artifact_path": str(verified_output.resolve()),
                "adapter_mode": "command",
            },
            completion={
                "state": "succeeded",
                "final_output": True,
                "final_artifact": verified_output.name,
                "final_artifact_path": str(verified_output.resolve()),
            },
        )

    return native_not_implemented_result(
        workspace,
        workload="canva",
        stage="canva",
        artifacts=[request_path, thumb_data_path],
        details={
            "channel": channel_from_payload(job.payload),
            "row_index": row_index_from_payload(job.payload),
            "save_path": str((workspace / "thumbnail.png").resolve()),
            "ref_img": ref_img,
            "service_artifact_path": str(job.payload.get("service_artifact_path", "")),
        },
    )

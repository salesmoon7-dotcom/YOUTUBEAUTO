from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from time import sleep, time
from typing import cast
from uuid import uuid4

from runtime_v2 import exit_codes
from runtime_v2.bootstrap import ensure_runtime_bootstrap
from runtime_v2.boundary_jobs import (
    build_qwen_boundary_contract,
    build_stage2_boundary_contract,
    write_boundary_contract,
)
from runtime_v2.browser.manager import (
    BrowserManager,
    expected_url_substring_for_service,
    open_browser_for_login,
)
from runtime_v2.browser.supervisor import BrowserSupervisor
from runtime_v2.config import (
    GpuWorkload,
    RuntimeConfig,
    WorkloadName,
    browser_session_root,
    probe_runtime_root,
    runtime_state_root,
)
from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.control_plane import run_control_loop_once
from runtime_v2.control_plane import run_worker
from runtime_v2.contracts.json_contract import (
    emit_event,
    final_report,
    now_ts,
    validate_contract,
)
from runtime_v2.debug_log import (
    append_debug_event,
    debug_log_path,
    exception_payload,
    summarize_cli_report,
    summarize_runtime_result,
)
from runtime_v2.evidence import load_runtime_readiness
from runtime_v2.gpt_pool_monitor import tick_gpt_status
from runtime_v2.gui_adapter import build_gui_status_payload
from runtime_v2.latest_run import write_cli_runtime_snapshot
from runtime_v2.manager import mark_excel_row_running, seed_excel_row
from runtime_v2.excel.selector import select_pending_row_indexes
from runtime_v2.excel.source import read_excel_row
from runtime_v2.control_plane_feeder import job_from_explicit_payload
from runtime_v2.n8n_adapter import (
    build_n8n_webhook_response,
    post_callback,
    write_mock_callback,
)
from runtime_v2.preflight import write_preflight_report
from runtime_v2.soak_report import (
    append_soak_event,
    build_soak_snapshot,
    write_soak_report,
)
from runtime_v2.stage2.canva_worker import run_canva_job
from runtime_v2.stage2.geminigen_worker import run_geminigen_job
from runtime_v2.stage2.agent_browser_adapter import (
    stage2_attach_verify_succeeded,
    write_stage2_attach_evidence,
)
from runtime_v2.agent_browser.cdp_capture import (
    collect_browser_debug_state,
    write_functional_evidence_bundle,
)
from runtime_v2.agent_browser.cdp_capture import _cdp_command, _select_page_target
from runtime_v2.stage2.genspark_worker import run_genspark_job
from runtime_v2.stage2.json_builders import build_stage2_jobs
from runtime_v2.stage2.seaart_worker import run_seaart_job
from runtime_v2.supervisor import run_once, run_selftest
from runtime_v2.supervisor import run_gated
from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job


class CliArgs(argparse.Namespace):
    owner: str
    once: bool
    control_once: bool
    control_once_detached: bool
    control_once_probe_child: bool
    excel_once: bool
    excel_batch: bool
    excel_path: str
    sheet_name: str
    row_index: int
    accepted_statuses: str
    job_contract_path: str
    emit_boundary_contract_path: str
    stage1_handoff_path: str
    video_plan_path: str
    boundary_workload: str
    boundary_scene_index: int
    boundary_ref_id: str
    batch_count: int
    max_control_ticks: int
    selftest: bool
    selftest_detached: bool
    selftest_probe_child: bool
    browser_recover_detached: bool
    browser_recover_probe_child: bool
    agent_browser_stage2_adapter_child: bool
    qwen3_adapter_child: bool
    rvc_adapter_child: bool
    stage2_row1_detached: bool
    stage2_row1_probe_child: bool
    stage5_row1_detached: bool
    stage5_row1_probe_child: bool
    stage5b_5row_detached: bool
    stage5b_5row_probe_child: bool
    callback_url: str
    callback_mock_out: str
    gui_status_out: str
    probe_root: str
    seed_mock_chain: bool
    selftest_force_browser_fail: bool
    selftest_force_gpt_fail: bool
    open_browser_login: str
    readiness_check: bool
    soak_report: bool
    soak_24h: bool
    runtime_root: str
    ref_audio: str
    service: str
    port: int
    service_artifact_path: str
    expected_url_substring: str
    expected_title_substring: str
    stage2_agent_browser_services: str
    migrate_sessions: bool
    allow_legacy_session_root: bool

    def __init__(self) -> None:
        super().__init__()
        self.owner = "runtime_v2"
        self.once = False
        self.control_once = False
        self.control_once_detached = False
        self.control_once_probe_child = False
        self.excel_once = False
        self.excel_batch = False
        self.excel_path = ""
        self.sheet_name = "Sheet1"
        self.row_index = 0
        self.accepted_statuses = ""
        self.job_contract_path = ""
        self.emit_boundary_contract_path = ""
        self.stage1_handoff_path = ""
        self.video_plan_path = ""
        self.boundary_workload = ""
        self.boundary_scene_index = 0
        self.boundary_ref_id = ""
        self.batch_count = 5
        self.max_control_ticks = 50
        self.selftest = False
        self.selftest_detached = False
        self.selftest_probe_child = False
        self.browser_recover_detached = False
        self.browser_recover_probe_child = False
        self.agent_browser_stage2_adapter_child = False
        self.qwen3_adapter_child = False
        self.rvc_adapter_child = False
        self.stage2_row1_detached = False
        self.stage2_row1_probe_child = False
        self.stage5_row1_detached = False
        self.stage5_row1_probe_child = False
        self.stage5b_5row_detached = False
        self.stage5b_5row_probe_child = False
        self.callback_url = ""
        self.callback_mock_out = ""
        self.gui_status_out = "system/runtime_v2/health/gui_status.json"
        self.probe_root = ""
        self.seed_mock_chain = False
        self.selftest_force_browser_fail = False
        self.selftest_force_gpt_fail = False
        self.open_browser_login = ""
        self.readiness_check = False
        self.soak_report = False
        self.soak_24h = False
        self.runtime_root = ""
        self.ref_audio = ""
        self.service = ""
        self.port = 0
        self.service_artifact_path = ""
        self.expected_url_substring = ""
        self.expected_title_substring = ""
        self.stage2_agent_browser_services = "genspark"
        self.migrate_sessions = False
        self.allow_legacy_session_root = False


def exit_code_from_status(code: str) -> int:
    mapping = {
        "OK": exit_codes.SUCCESS,
        "NO_JOB": exit_codes.SUCCESS,
        "SEEDED_JOB": exit_codes.SUCCESS,
        "NO_WORK": exit_codes.SUCCESS,
        "CONTROL_BUSY": exit_codes.SUCCESS,
        "GPU_LEASE_BUSY": exit_codes.LEASE_BUSY,
        "BROWSER_UNHEALTHY": exit_codes.BROWSER_UNHEALTHY,
        "BROWSER_BLOCKED": exit_codes.BROWSER_BLOCKED,
        "BROWSER_RESTART_EXHAUSTED": exit_codes.BROWSER_BLOCKED,
        "GPU_HEALTH_MISSING": exit_codes.LEASE_BUSY,
        "GPU_HEALTH_INVALID": exit_codes.LEASE_BUSY,
        "GPU_HEALTH_STALE": exit_codes.LEASE_BUSY,
        "GPU_LEASE_RENEW_FAILED": exit_codes.LEASE_BUSY,
        "WORKER_REGISTRY_MISSING": exit_codes.SELFTEST_FAIL,
        "WORKER_REGISTRY_INVALID": exit_codes.SELFTEST_FAIL,
        "WORKER_STALL_DETECTED": exit_codes.SELFTEST_FAIL,
        "GPT_FLOOR_FAIL": exit_codes.GPT_FLOOR_FAIL,
        "SELFTEST_FAIL": exit_codes.SELFTEST_FAIL,
        "CALLBACK_FAIL": exit_codes.CALLBACK_FAIL,
    }
    return mapping.get(code, exit_codes.CLI_USAGE)


def exit_code_from_readiness(readiness: dict[str, object]) -> int:
    if bool(readiness.get("ready", False)):
        return exit_codes.SUCCESS
    blockers = readiness.get("blockers")
    if isinstance(blockers, list):
        typed_blockers = cast(list[object], blockers)
        for blocker_obj in typed_blockers:
            blocker = (
                cast(dict[object, object], blocker_obj)
                if isinstance(blocker_obj, dict)
                else None
            )
            if not isinstance(blocker, dict):
                continue
            mapped = exit_code_from_status(str(blocker.get("code", "CLI_USAGE")))
            if mapped != exit_codes.CLI_USAGE:
                return mapped
    primary_code = str(readiness.get("code", "CLI_USAGE"))
    mapped_primary = exit_code_from_status(primary_code)
    if mapped_primary != exit_codes.CLI_USAGE:
        return mapped_primary
    return exit_codes.BROWSER_BLOCKED


def _terminal_excel_status(status: object) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in {"done", "partial", "failed"}


def _int_value(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return int(str(value))
    if isinstance(value, float):
        return int(str(value))
    if isinstance(value, str):
        text = value.strip()
        if text:
            return int(text)
    return default


def _parse_accepted_statuses(raw: str) -> set[str] | None:
    tokens = [token.strip().lower() for token in raw.split(",") if token.strip()]
    return set(tokens) if tokens else None


def _load_job_contract(path: str) -> JobContract:
    contract_path = Path(path)
    raw_payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError("invalid_job_contract_json")
    payload = cast(dict[str, object], raw_payload)
    parsed_job, invalid = job_from_explicit_payload(
        payload, source_hint=str(contract_path.resolve())
    )
    if parsed_job is None:
        error_code = str((invalid or {}).get("code", "invalid_job_contract"))
        raise ValueError(error_code or "invalid_job_contract")
    return parsed_job


def _emit_boundary_contract(args: CliArgs) -> Path:
    workload = args.boundary_workload.strip()
    if not workload:
        raise ValueError("missing_boundary_workload")
    if workload == "qwen3_tts":
        if not args.stage1_handoff_path.strip():
            raise ValueError("missing_stage1_handoff_path")
        contract = build_qwen_boundary_contract(
            stage1_handoff_path=args.stage1_handoff_path,
        )
    else:
        if not args.video_plan_path.strip():
            raise ValueError("missing_video_plan_path")
        scene_index = (
            args.boundary_scene_index if args.boundary_scene_index > 0 else None
        )
        contract = build_stage2_boundary_contract(
            video_plan_path=args.video_plan_path,
            workload=workload,
            scene_index=scene_index,
            ref_id=args.boundary_ref_id,
        )
    return write_boundary_contract(contract, args.emit_boundary_contract_path)


def _job_contract_artifacts(result: dict[str, object]) -> list[Path]:
    worker_result = cast(
        dict[str, object],
        result.get("worker_result", {})
        if isinstance(result.get("worker_result", {}), dict)
        else {},
    )
    artifacts: list[Path] = []
    for raw_path in cast(list[object], worker_result.get("artifacts", [])):
        path_text = str(raw_path).strip()
        if path_text:
            artifacts.append(Path(path_text))
    completion = cast(
        dict[str, object],
        worker_result.get("completion", {})
        if isinstance(worker_result.get("completion", {}), dict)
        else {},
    )
    final_artifact_path = str(completion.get("final_artifact_path", "")).strip()
    if final_artifact_path:
        final_path = Path(final_artifact_path)
        if all(
            str(existing.resolve()) != str(final_path.resolve())
            for existing in artifacts
        ):
            artifacts.append(final_path)
    return artifacts


def _run_explicit_job_contract(
    *, owner: str, config: RuntimeConfig, run_id: str, job: JobContract
) -> dict[str, object]:
    result = run_gated(
        owner=owner,
        execute=lambda: run_worker(
            job,
            config.artifact_root,
            registry_file=config.worker_registry_file,
        ),
        workload=job.workload,
        config=config,
        run_id=run_id,
        require_browser_healthy=True,
        allow_runtime_side_effects=True,
    )
    result["job"] = job.to_dict()
    return result


def _run_excel_batch_mode(
    *,
    owner: str,
    config: RuntimeConfig,
    run_id: str,
    excel_path: str,
    sheet_name: str,
    batch_count: int,
    max_control_ticks: int,
) -> dict[str, object]:
    selected_rows = select_pending_row_indexes(
        excel_path,
        sheet_name=sheet_name,
        limit=batch_count,
    )
    if not selected_rows:
        return {"status": "no_work", "code": "NO_WORK", "selected_rows": []}
    seeded_runs: list[dict[str, object]] = []
    for offset, row_index in enumerate(selected_rows, start=1):
        row_run_id = f"{run_id}-row{offset:02d}"
        seeded = seed_excel_row(
            config=config,
            run_id=row_run_id,
            excel_path=excel_path,
            sheet_name=sheet_name,
            row_index=row_index,
        )
        if str(seeded.get("status", "")) == "seeded":
            running_updated = mark_excel_row_running(
                excel_path=excel_path,
                sheet_name=sheet_name,
                row_index=row_index,
            )
            if not running_updated:
                return {
                    "status": "failed",
                    "code": "EXCEL_STATUS_UPDATE_FAILED",
                    "selected_rows": seeded_runs,
                    "failed_row_index": row_index,
                }
            seeded_runs.append(
                {
                    "row_index": row_index,
                    "run_id": row_run_id,
                    "job_id": str(seeded.get("job_id", "")),
                }
            )
        elif str(seeded.get("status", "")) == "failed":
            return {
                "status": "failed",
                "code": str(seeded.get("code", "EXCEL_STATUS_UPDATE_FAILED")),
                "selected_rows": seeded_runs,
                "failed_row_index": row_index,
            }
    if not seeded_runs:
        return {"status": "no_work", "code": "NO_WORK", "selected_rows": []}
    control_results: list[dict[str, object]] = []
    for _ in range(max_control_ticks):
        control_result = run_control_loop_once(
            owner=owner, config=config, run_id=run_id
        )
        control_results.append(control_result)
        pending_rows = []
        for seeded in seeded_runs:
            row_map = read_excel_row(
                excel_path,
                sheet_name=sheet_name,
                row_index=_int_value(seeded["row_index"], -1),
            )
            if not _terminal_excel_status(row_map.get("Status", "")):
                pending_rows.append(_int_value(seeded["row_index"], -1))
        if not pending_rows:
            return {
                "status": "ok",
                "code": "OK",
                "selected_rows": seeded_runs,
                "ticks": len(control_results),
                "control_results": control_results,
            }
    return {
        "status": "failed",
        "code": "BATCH_TIMEOUT",
        "selected_rows": seeded_runs,
        "ticks": len(control_results),
        "control_results": control_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--owner", default="runtime_v2")
    _ = parser.add_argument("--once", action="store_true")
    _ = parser.add_argument("--control-once", action="store_true")
    _ = parser.add_argument("--control-once-detached", action="store_true")
    _ = parser.add_argument(
        "--control-once-probe-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument("--excel-once", action="store_true")
    _ = parser.add_argument("--excel-batch", action="store_true")
    _ = parser.add_argument("--excel-path", default="")
    _ = parser.add_argument("--sheet-name", default="Sheet1")
    _ = parser.add_argument("--row-index", type=int, default=0)
    _ = parser.add_argument("--accepted-statuses", default="")
    _ = parser.add_argument("--job-contract-path", default="")
    _ = parser.add_argument("--emit-boundary-contract-path", default="")
    _ = parser.add_argument("--stage1-handoff-path", default="")
    _ = parser.add_argument("--video-plan-path", default="")
    _ = parser.add_argument("--boundary-workload", default="")
    _ = parser.add_argument("--boundary-scene-index", type=int, default=0)
    _ = parser.add_argument("--boundary-ref-id", default="")
    _ = parser.add_argument("--batch-count", type=int, default=5)
    _ = parser.add_argument("--max-control-ticks", type=int, default=50)
    _ = parser.add_argument("--selftest", action="store_true")
    _ = parser.add_argument("--selftest-detached", action="store_true")
    _ = parser.add_argument(
        "--selftest-probe-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument("--browser-recover-detached", action="store_true")
    _ = parser.add_argument(
        "--browser-recover-probe-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument(
        "--agent-browser-stage2-adapter-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    _ = parser.add_argument(
        "--qwen3-adapter-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument(
        "--rvc-adapter-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument("--stage2-row1-detached", action="store_true")
    _ = parser.add_argument(
        "--stage2-row1-probe-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument("--stage5-row1-detached", action="store_true")
    _ = parser.add_argument(
        "--stage5-row1-probe-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument("--stage5b-5row-detached", action="store_true")
    _ = parser.add_argument(
        "--stage5b-5row-probe-child", action="store_true", help=argparse.SUPPRESS
    )
    _ = parser.add_argument("--callback-url", default="")
    _ = parser.add_argument("--callback-mock-out", default="")
    _ = parser.add_argument("--gui-status-out", default="")
    _ = parser.add_argument("--probe-root", default="")
    _ = parser.add_argument("--seed-mock-chain", action="store_true")
    _ = parser.add_argument("--selftest-force-browser-fail", action="store_true")
    _ = parser.add_argument("--selftest-force-gpt-fail", action="store_true")
    _ = parser.add_argument("--open-browser-login", default="")
    _ = parser.add_argument("--readiness-check", action="store_true")
    _ = parser.add_argument("--soak-report", action="store_true")
    _ = parser.add_argument("--soak-24h", action="store_true")
    _ = parser.add_argument("--runtime-root", default="")
    _ = parser.add_argument("--ref-audio", default="", help=argparse.SUPPRESS)
    _ = parser.add_argument("--service", default="")
    _ = parser.add_argument("--port", type=int, default=0)
    _ = parser.add_argument("--service-artifact-path", default="")
    _ = parser.add_argument("--expected-url-substring", default="")
    _ = parser.add_argument("--expected-title-substring", default="")
    _ = parser.add_argument(
        "--stage2-agent-browser-services",
        default="genspark",
    )
    _ = parser.add_argument("--migrate-sessions", action="store_true")
    _ = parser.add_argument("--allow-legacy-session-root", action="store_true")
    args = parser.parse_args(namespace=CliArgs())
    if args.allow_legacy_session_root:
        os.environ["RUNTIME_V2_ALLOW_LEGACY_SESSION_ROOT"] = "1"

    selected_modes = [
        flag
        for flag in (
            args.once,
            args.control_once,
            args.control_once_detached,
            args.control_once_probe_child,
            args.excel_once,
            args.excel_batch,
            bool(args.job_contract_path.strip()),
            bool(args.emit_boundary_contract_path.strip()),
            args.selftest,
            args.selftest_detached,
            args.selftest_probe_child,
            args.browser_recover_detached,
            args.browser_recover_probe_child,
            args.agent_browser_stage2_adapter_child,
            args.qwen3_adapter_child,
            args.rvc_adapter_child,
            args.stage2_row1_detached,
            args.stage2_row1_probe_child,
            args.stage5_row1_detached,
            args.stage5_row1_probe_child,
            args.stage5b_5row_detached,
            args.stage5b_5row_probe_child,
            bool(args.open_browser_login.strip()),
            args.readiness_check,
            args.soak_report,
            args.soak_24h,
            args.migrate_sessions,
        )
        if flag
    ]
    if len(selected_modes) > 1:
        return exit_codes.CLI_USAGE
    if len(selected_modes) == 0:
        return exit_codes.CLI_USAGE
    if (args.selftest_force_browser_fail or args.selftest_force_gpt_fail) and not (
        args.selftest or args.selftest_detached or args.selftest_probe_child
    ):
        return exit_codes.CLI_USAGE
    if args.seed_mock_chain and not (
        args.control_once_detached or args.control_once_probe_child
    ):
        return exit_codes.CLI_USAGE
    if args.excel_once and args.row_index < 0:
        return exit_codes.CLI_USAGE
    if args.excel_batch and (args.batch_count <= 0 or args.max_control_ticks <= 0):
        return exit_codes.CLI_USAGE
    config = _build_runtime_config(args)
    try:
        _ = write_preflight_report(config)
    except Exception as exc:
        print(f"warning: preflight report write failed: {exc}", file=sys.stderr)
    if args.open_browser_login.strip():
        payload = open_browser_for_login(args.open_browser_login.strip())
        print(json.dumps(payload, ensure_ascii=True))
        return exit_codes.SUCCESS
    if args.readiness_check:
        readiness = load_runtime_readiness(config, completed=True)
        print(json.dumps(readiness, ensure_ascii=True))
        return exit_code_from_readiness(readiness)
    if args.soak_report:
        report_path = write_soak_report(config)
        report = {"status": "ok", "code": "OK", "report_path": str(report_path)}
        print(final_report(report))
        return exit_codes.SUCCESS
    if args.migrate_sessions:
        report = _migrate_legacy_sessions()
        print(json.dumps(report, ensure_ascii=True))
        return (
            exit_codes.SUCCESS
            if bool(report.get("ok", False))
            else exit_codes.CLI_USAGE
        )

    if args.browser_recover_detached:
        return _spawn_detached_probe(args, mode="browser_recover")
    if args.stage2_row1_detached:
        return _spawn_detached_probe(args, mode="stage2_row1")
    if args.stage5_row1_detached:
        return _spawn_detached_probe(args, mode="stage5_row1")
    if args.stage5b_5row_detached:
        return _spawn_detached_probe(args, mode="stage5b_5row")

    if args.agent_browser_stage2_adapter_child:
        return _run_agent_browser_stage2_adapter_child(args)
    if args.qwen3_adapter_child:
        return _run_qwen3_adapter_child(args)
    if args.rvc_adapter_child:
        return _run_rvc_adapter_child(args)

    if args.selftest_detached:
        return _spawn_detached_probe(args, mode="selftest")
    if args.control_once_detached:
        return _spawn_detached_probe(args, mode="control_once")

    if args.selftest or args.selftest_probe_child:
        mode = "selftest"
    elif args.browser_recover_probe_child:
        mode = "browser_recover"
    elif args.stage2_row1_probe_child:
        mode = "stage2_row1"
    elif args.stage5_row1_probe_child:
        mode = "stage5_row1"
    elif args.stage5b_5row_probe_child:
        mode = "stage5b_5row"
    elif args.control_once or args.control_once_probe_child or args.excel_once:
        mode = "control_once"
    elif args.excel_batch:
        mode = "excel_batch"
    elif args.job_contract_path.strip():
        mode = "job_contract"
    elif args.emit_boundary_contract_path.strip():
        mode = "emit_boundary_contract"
    elif args.soak_24h:
        mode = "soak_24h"
    else:
        mode = "once"
    explicit_job: JobContract | None = None
    if args.emit_boundary_contract_path.strip():
        try:
            output_path = _emit_boundary_contract(args)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(
                final_report(
                    {
                        "run_id": "",
                        "status": "failed",
                        "code": str(exc) or "boundary_contract_failed",
                    }
                )
            )
            return exit_codes.CLI_USAGE
        print(
            final_report(
                {
                    "run_id": "",
                    "status": "ok",
                    "code": "OK",
                    "boundary_contract_path": str(output_path.resolve()),
                }
            )
        )
        return exit_codes.SUCCESS
    if args.job_contract_path.strip():
        try:
            explicit_job = _load_job_contract(args.job_contract_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(
                final_report(
                    {
                        "run_id": "",
                        "status": "failed",
                        "code": str(exc) or "invalid_job_contract",
                    }
                )
            )
            return exit_codes.CLI_USAGE
    run_id = (
        str(explicit_job.payload.get("run_id", explicit_job.job_id)).strip()
        if explicit_job is not None
        else str(uuid4())
    )
    if args.browser_recover_probe_child:
        report = _run_browser_recovery_probe(
            config=config,
            probe_root=_probe_root_path(args.probe_root),
            run_id=run_id,
        )
        _ = _write_detached_summary(
            out_root=_probe_root_path(args.probe_root),
            kind="browser_recover",
            target="runtime_v2.cli --browser-recover-probe-child",
            exit_code=exit_code_from_status(str(report.get("code", "CLI_USAGE"))),
            payload=report,
        )
        print(final_report(report))
        return exit_code_from_status(str(report.get("code", "CLI_USAGE")))
    if args.stage2_row1_probe_child:
        report = _run_stage2_row1_probe(
            config=config,
            probe_root=_probe_root_path(args.probe_root),
            run_id=run_id,
            agent_browser_services=_parse_stage2_agent_browser_services(
                args.stage2_agent_browser_services
            ),
        )
        _ = _write_detached_summary(
            out_root=_probe_root_path(args.probe_root),
            kind="stage2_row1",
            target="runtime_v2.cli --stage2-row1-probe-child",
            exit_code=exit_code_from_status(str(report.get("code", "CLI_USAGE"))),
            payload=report,
        )
        print(final_report(report))
        return exit_code_from_status(str(report.get("code", "CLI_USAGE")))
    if args.stage5_row1_probe_child:
        report = _run_stage5_row1_probe(
            owner=args.owner,
            config=config,
            probe_root=_probe_root_path(args.probe_root),
            run_id=run_id,
            excel_path=args.excel_path,
            sheet_name=args.sheet_name,
            row_index=args.row_index,
            max_control_ticks=args.max_control_ticks,
        )
        _ = _write_detached_summary(
            out_root=_probe_root_path(args.probe_root),
            kind="stage5_row1",
            target="runtime_v2.cli --stage5-row1-probe-child",
            exit_code=exit_code_from_status(str(report.get("code", "CLI_USAGE"))),
            payload=report,
        )
        print(final_report(report))
        return exit_code_from_status(str(report.get("code", "CLI_USAGE")))
    if args.stage5b_5row_probe_child:
        report = _run_stage5b_5row_probe(
            owner=args.owner,
            config=config,
            probe_root=_probe_root_path(args.probe_root),
            run_id=run_id,
            excel_path=args.excel_path,
            sheet_name=args.sheet_name,
            batch_count=args.batch_count,
            max_control_ticks=args.max_control_ticks,
        )
        _ = _write_detached_summary(
            out_root=_probe_root_path(args.probe_root),
            kind="stage5b_5row",
            target="runtime_v2.cli --stage5b-5row-probe-child",
            exit_code=exit_code_from_status(str(report.get("code", "CLI_USAGE"))),
            payload=report,
        )
        print(final_report(report))
        return exit_code_from_status(str(report.get("code", "CLI_USAGE")))
    bootstrap_workload: str = "qwen3_tts"
    if explicit_job is not None and explicit_job.workload in {
        "qwen3_tts",
        "rvc",
        "kenburns",
    }:
        bootstrap_workload = explicit_job.workload
    ensure_runtime_bootstrap(
        config,
        workload=cast(GpuWorkload, bootstrap_workload),
        run_id=run_id,
        mode=mode,
    )
    seed_result: dict[str, object] | None = None
    if args.excel_once:
        seed_result = seed_excel_row(
            config=config,
            run_id=run_id,
            excel_path=args.excel_path,
            sheet_name=args.sheet_name,
            row_index=args.row_index,
            accepted_statuses=_parse_accepted_statuses(args.accepted_statuses),
        )
    if args.excel_batch:
        batch_result = _run_excel_batch_mode(
            owner=args.owner,
            config=config,
            run_id=run_id,
            excel_path=args.excel_path,
            sheet_name=args.sheet_name,
            batch_count=args.batch_count,
            max_control_ticks=args.max_control_ticks,
        )
        print(final_report(batch_result))
        return exit_code_from_status(str(batch_result.get("code", "CLI_USAGE")))
    if args.seed_mock_chain and args.control_once_probe_child:
        _ = seed_mock_chain_probe(config.input_root)

    debug_log = debug_log_path(config.debug_log_root, run_id)
    start_event = {
        "run_id": run_id,
        "event": "run_started",
        "ts": now_ts(),
        "mode": mode,
        "debug_log": str(debug_log),
    }
    ok, missing = validate_contract(start_event)
    if not ok:
        print(
            final_report(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "code": "CLI_USAGE",
                    "missing": missing,
                }
            )
        )
        return exit_codes.CLI_USAGE

    print(emit_event(start_event))
    _ = append_debug_event(debug_log, event="cli_start", payload=start_event)

    try:
        if args.selftest or args.selftest_probe_child:
            result = run_selftest(
                owner=args.owner,
                run_id=run_id,
                config=config,
                inject_browser_fail=args.selftest_force_browser_fail,
                inject_gpt_fail=args.selftest_force_gpt_fail,
            )
        elif explicit_job is not None:
            result = _run_explicit_job_contract(
                owner=args.owner,
                config=config,
                run_id=run_id,
                job=explicit_job,
            )
        elif (
            args.excel_once
            and seed_result is not None
            and str(seed_result.get("status", "")) in {"no_work", "seeded"}
            and config.stable_file_age_sec > 0
        ):
            result = seed_result
        elif args.control_once_probe_child and args.seed_mock_chain:
            result = _run_control_probe_until_terminal(
                owner=args.owner, config=config, run_id=run_id
            )
        elif args.control_once or args.control_once_probe_child or args.excel_once:
            result = run_control_loop_once(
                owner=args.owner, config=config, run_id=run_id
            )
        else:
            result = run_once(owner=args.owner, run_id=run_id, config=config)
    except Exception as exc:
        _ = append_debug_event(
            debug_log,
            event="cli_exception",
            level="ERROR",
            payload={
                "run_id": run_id,
                "mode": mode,
                **exception_payload(exc),
            },
        )
        failure_report = {
            "run_id": run_id,
            "event": "run_finished",
            "ts": now_ts(),
            "mode": mode,
            "status": "failed",
            "code": "UNHANDLED_EXCEPTION",
            "exit_code": exit_codes.CLI_USAGE,
        }
        print(final_report(summarize_cli_report(failure_report, debug_log)))
        return exit_codes.CLI_USAGE
    summary = summarize_runtime_result(result)
    code = str(summary.get("code", result.get("code", "CLI_USAGE")))
    if (
        not code.strip()
        and str(summary.get("status", result.get("status", ""))).strip() == "ok"
    ):
        code = "OK"
    exit_code = exit_code_from_status(code)
    callback_result: dict[str, object] | None = None
    _ = append_debug_event(
        debug_log,
        event="cli_result",
        payload={
            "run_id": run_id,
            "mode": mode,
            "result": result,
            "summary": summary,
        },
    )

    if args.callback_url:
        callback_payload = build_n8n_webhook_response(
            result,
            callback_url=args.callback_url,
            run_id=run_id,
            mode=mode,
            exit_code=exit_code,
        )
        callback_result = post_callback(
            callback_payload,
            timeout_sec=config.callback_timeout_sec,
            max_attempts=config.callback_max_attempts,
            backoff_sec=config.callback_backoff_sec,
        )
        print(
            emit_event(
                {
                    "run_id": run_id,
                    "event": "callback_result",
                    "ts": now_ts(),
                    "ok": bool(callback_result.get("ok", False)),
                    "debug_log": str(debug_log),
                }
            )
        )
        _ = append_debug_event(
            debug_log,
            event="callback_result",
            payload={
                "run_id": run_id,
                "mode": mode,
                "callback_result": callback_result,
            },
            level="ERROR" if not bool(callback_result.get("ok", False)) else "INFO",
        )
        if not bool(callback_result.get("ok", False)):
            exit_code = exit_codes.CALLBACK_FAIL
        if args.callback_mock_out:
            try:
                write_mock_callback(callback_payload, args.callback_mock_out)
            except OSError:
                exit_code = exit_codes.CALLBACK_FAIL

    if args.soak_24h:
        soak_snapshot = build_soak_snapshot(config)
        _ = append_soak_event(
            config,
            run_id=run_id,
            mode=mode,
            status=str(summary.get("status", result.get("status", "unknown"))),
            code=code,
            exit_code=exit_code,
            debug_log=str(debug_log),
            summary={**summary, "soak_snapshot": soak_snapshot},
        )
        _ = write_soak_report(config)

    if not args.control_once:
        gui_status_input = dict(result)
        gui_status_input.update(summary)
        gui_status_input["debug_log"] = str(debug_log)
        snapshot_artifacts = _job_contract_artifacts(result)
        gui_payload = build_gui_status_payload(
            gui_status_input,
            run_id=run_id,
            mode=mode,
            stage="finished",
            exit_code=exit_code,
        )
        print(
            emit_event(
                {
                    "run_id": run_id,
                    "event": "gui_status",
                    "ts": now_ts(),
                    "status": str(
                        summary.get("status", result.get("status", "unknown"))
                    ),
                    "code": code,
                    "exit_code": exit_code,
                    "debug_log": str(debug_log),
                }
            )
        )
        _ = append_debug_event(
            debug_log,
            event="gui_status_snapshot",
            payload={
                "run_id": run_id,
                "mode": mode,
                "gui_payload": gui_payload,
            },
        )
        write_cli_runtime_snapshot(
            config,
            run_id=run_id,
            mode=mode,
            status=str(summary.get("status", result.get("status", "failed"))),
            code=code,
            debug_log=str(debug_log),
            gui_payload=gui_payload,
            metadata={
                "run_id": run_id,
                "mode": mode,
                "status": str(summary.get("status", result.get("status", "failed"))),
                "code": code,
                "exit_code": exit_code,
                "job_id": str(summary.get("job_id", "")),
                "workload": str(summary.get("workload", "")),
                "queue_status": str(summary.get("queue_status", "")),
                "stage": str(summary.get("stage", "")),
                "error_code": str(summary.get("error_code", "")),
                "manifest_path": str(summary.get("manifest_path", "")),
                "result_path": str(summary.get("result_path", "")),
                "completion_state": str(summary.get("completion_state", "")),
                "final_output": bool(summary.get("final_output", False)),
                "final_artifact": str(summary.get("final_artifact", "")),
                "final_artifact_path": str(summary.get("final_artifact_path", "")),
                "debug_log": str(debug_log),
                "ts": now_ts(),
            },
            artifacts=snapshot_artifacts,
        )

    report = {
        "run_id": run_id,
        "event": "run_finished",
        "ts": now_ts(),
        "mode": mode,
        "status": result.get("status", "failed"),
        "code": code,
        "exit_code": exit_code,
        "result": result,
    }
    if callback_result is not None:
        report["callback_result"] = callback_result
    _ = append_debug_event(debug_log, event="cli_report", payload=report)
    if args.selftest_probe_child or args.control_once_probe_child:
        _ = _write_probe_result(
            _probe_root_path(args.probe_root),
            {
                "run_id": run_id,
                "mode": mode,
                "status": str(report.get("status", "unknown")),
                "code": code,
                "exit_code": exit_code,
                "debug_log": str(debug_log),
                "result": result,
                "summary": summary,
            },
        )
        _ = _write_detached_summary(
            out_root=_probe_root_path(args.probe_root),
            kind="selftest" if args.selftest_probe_child else "control_once",
            target=(
                "runtime_v2.cli --selftest-probe-child"
                if args.selftest_probe_child
                else "runtime_v2.cli --control-once-probe-child"
            ),
            exit_code=exit_code,
            payload={
                "run_id": run_id,
                "status": str(report.get("status", "unknown")),
                "code": code,
                "probe_result": str(
                    _probe_root_path(args.probe_root) / "probe_result.json"
                ),
                "debug_log": str(debug_log),
            },
        )
    print(final_report(summarize_cli_report(report, debug_log)))
    return exit_code


def _run_control_probe_until_terminal(
    *, owner: str, config: RuntimeConfig, run_id: str, max_passes: int = 8
) -> dict[str, object]:
    last_result: dict[str, object] = {
        "status": "failed",
        "code": "CONTROL_PROBE_NO_RESULT",
    }
    for _ in range(max(1, max_passes)):
        last_result = run_control_loop_once(owner=owner, config=config, run_id=run_id)
        if _result_has_final_output(last_result):
            return last_result
        result_code = _result_code(last_result)
        if result_code in {
            "NO_JOB",
            "BROWSER_UNHEALTHY",
            "GPT_FLOOR_FAIL",
            "GPU_LEASE_BUSY",
            "GPU_LEASE_RENEW_FAILED",
        }:
            return last_result
        if str(last_result.get("status", "")) in {"failed", "blocked"}:
            return last_result
    return last_result


def _result_code(result: dict[str, object]) -> str:
    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        return str(nested_result.get("code", result.get("code", "")))
    return str(result.get("code", ""))


def _result_has_final_output(result: dict[str, object]) -> bool:
    worker_result = result.get("worker_result")
    if not isinstance(worker_result, dict):
        return False
    completion = worker_result.get("completion")
    if not isinstance(completion, dict):
        return False
    return bool(completion.get("final_output", False))


def _build_runtime_config(args: CliArgs) -> RuntimeConfig:
    runtime_root = _runtime_root_path(args.runtime_root)
    if runtime_root is not None:
        return RuntimeConfig.from_root(runtime_root)
    if args.probe_root.strip() and (
        args.selftest_probe_child
        or args.control_once_probe_child
        or args.stage2_row1_probe_child
        or args.stage5_row1_probe_child
        or args.stage5b_5row_probe_child
        or args.readiness_check
    ):
        root = _probe_root_path(args.probe_root)
        return RuntimeConfig.from_root(root).replace(
            allow_mock_chain=bool(
                args.seed_mock_chain and args.control_once_probe_child
            )
        )
    config = RuntimeConfig()
    if args.gui_status_out.strip():
        return config.replace(gui_status_file=Path(args.gui_status_out))
    return config


def _spawn_detached_probe(args: CliArgs, *, mode: str) -> int:
    probe_root = _probe_root_path(args.probe_root)
    for directory in (
        probe_root,
        probe_root / "health",
        probe_root / "evidence",
        probe_root / "state",
        probe_root / "artifacts",
        probe_root / "inbox",
        probe_root / "inbox" / "qwen3_tts",
        probe_root / "inbox" / "kenburns",
        probe_root / "inbox" / "rvc" / "source",
        probe_root / "inbox" / "rvc" / "audio",
        probe_root / "locks",
        probe_root / "logs",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    seeded_contract: Path | None = None
    if mode == "control_once" and args.seed_mock_chain:
        seeded_contract = seed_mock_chain_probe(probe_root / "inbox")

    stdout_path = probe_root / "logs" / f"{mode}_stdout.log"
    stderr_path = probe_root / "logs" / f"{mode}_stderr.log"
    child_flag = {
        "selftest": "--selftest-probe-child",
        "control_once": "--control-once-probe-child",
        "browser_recover": "--browser-recover-probe-child",
        "stage2_row1": "--stage2-row1-probe-child",
        "stage5_row1": "--stage5-row1-probe-child",
        "stage5b_5row": "--stage5b-5row-probe-child",
    }[mode]
    command = [
        sys.executable,
        "-u",
        "-m",
        "runtime_v2.cli",
        child_flag,
        "--owner",
        args.owner,
        "--probe-root",
        str(probe_root),
    ]
    if mode == "selftest" and args.selftest_force_browser_fail:
        command.append("--selftest-force-browser-fail")
    if mode == "selftest" and args.selftest_force_gpt_fail:
        command.append("--selftest-force-gpt-fail")
    if mode == "control_once" and args.seed_mock_chain:
        command.append("--seed-mock-chain")
    if mode == "stage2_row1":
        command.extend(
            [
                "--stage2-agent-browser-services",
                args.stage2_agent_browser_services,
            ]
        )
    if mode == "stage5_row1":
        command.extend(
            [
                "--excel-path",
                args.excel_path,
                "--sheet-name",
                args.sheet_name,
                "--row-index",
                str(args.row_index),
                "--max-control-ticks",
                str(args.max_control_ticks),
            ]
        )
    if mode == "stage5b_5row":
        command.extend(
            [
                "--excel-path",
                args.excel_path,
                "--sheet-name",
                args.sheet_name,
                "--batch-count",
                str(args.batch_count),
                "--max-control-ticks",
                str(args.max_control_ticks),
            ]
        )
    if args.runtime_root.strip():
        command.extend(["--runtime-root", args.runtime_root.strip()])

    creationflags = 0
    creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    creationflags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
    creationflags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_handle,
        stderr_path.open("w", encoding="utf-8") as stderr_handle,
    ):
        child = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=creationflags,
        )

    report = {
        "run_id": f"detached-{uuid4()}",
        "event": "probe_spawned",
        "ts": now_ts(),
        "mode": f"{mode}_detached",
        "status": "spawned",
        "code": "PROBE_RUNNING",
        "exit_code": exit_codes.SUCCESS,
        "probe_root": str(probe_root),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "probe_result": str(probe_root / "probe_result.json"),
        "pid": child.pid,
    }
    if seeded_contract is not None:
        report["seeded_contract"] = str(seeded_contract)
    _ = _write_detached_summary(
        out_root=probe_root,
        kind=mode,
        target=child_flag,
        exit_code=exit_codes.SUCCESS,
        payload={
            "status": "spawned",
            "code": "PROBE_RUNNING",
            "pid": child.pid,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "probe_result": str(probe_root / "probe_result.json"),
        },
    )
    print(final_report(report))
    return exit_codes.SUCCESS


def _probe_root_path(raw_probe_root: str) -> Path:
    probe_root = raw_probe_root.strip()
    if probe_root:
        return Path(probe_root)
    return probe_runtime_root() / str(uuid4())


def _legacy_session_root() -> Path:
    return (Path(__file__).resolve().parent / "sessions").resolve()


def _copy_legacy_sessions(legacy_root: Path, external_root: Path) -> dict[str, object]:
    external_root.mkdir(parents=True, exist_ok=True)
    migrated: list[str] = []
    skipped_existing: list[str] = []
    if not legacy_root.exists():
        return {
            "ok": True,
            "legacy_root": str(legacy_root),
            "external_root": str(external_root),
            "migrated": migrated,
            "skipped_existing": skipped_existing,
            "missing": ["legacy_root_missing"],
        }
    for child in sorted(legacy_root.iterdir()):
        if not child.is_dir():
            continue
        target = external_root / child.name
        if target.exists():
            skipped_existing.append(child.name)
            continue
        shutil.copytree(child, target)
        migrated.append(child.name)
    return {
        "ok": True,
        "legacy_root": str(legacy_root),
        "external_root": str(external_root),
        "migrated": migrated,
        "skipped_existing": skipped_existing,
    }


def _migrate_legacy_sessions() -> dict[str, object]:
    return _copy_legacy_sessions(_legacy_session_root(), browser_session_root())


def _write_detached_summary(
    *,
    out_root: Path,
    kind: str,
    target: str,
    exit_code: int,
    payload: dict[str, object],
) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    summary_file = out_root / "summary.json"
    summary_payload = {
        "started_at": round(time(), 3),
        "finished_at": round(time(), 3),
        "command": list(sys.argv),
        "exit_code": exit_code,
        "kind": kind,
        "target": target,
        "out_root": str(out_root),
        **payload,
    }
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=out_root,
        prefix="summary.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(
            json.dumps(_json_safe_mapping(summary_payload), ensure_ascii=True)
        )
        temp_path = Path(handle.name)
    _ = temp_path.replace(summary_file)
    return summary_file


def _runtime_root_path(raw_runtime_root: str) -> Path | None:
    runtime_root = raw_runtime_root.strip()
    if not runtime_root:
        return None
    return Path(runtime_root)


def _runtime_root_for_config(config: RuntimeConfig) -> Path:
    return config.result_router_file.parent.parent.resolve()


def _parse_stage2_agent_browser_services(raw: str) -> list[str]:
    services: list[str] = []
    for item in raw.split(","):
        service = item.strip()
        if service:
            services.append(service)
    return services


def _load_optional_json_dict(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_payload, dict):
        return {}
    return {str(key): value for key, value in raw_payload.items()}


def _stage2_transcript_items(result: dict[str, object]) -> list[dict[str, object]]:
    transcript_items = result.get("transcript", [])
    if isinstance(transcript_items, list):
        normalized = [item for item in transcript_items if isinstance(item, dict)]
        if normalized:
            return cast(list[dict[str, object]], normalized)
    details_raw = result.get("details", {})
    details = details_raw if isinstance(details_raw, dict) else {}
    transcript_path = Path(str(details.get("transcript_path", "")).strip())
    if not transcript_path.exists():
        return []
    transcript_payload = _load_optional_json_dict(transcript_path)
    steps = transcript_payload.get("steps", [])
    if not isinstance(steps, list):
        return []
    normalized_steps = [item for item in steps if isinstance(item, dict)]
    return cast(list[dict[str, object]], normalized_steps)


def _stage2_result_by_step(result: dict[str, object]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for item in _stage2_transcript_items(result):
        raw_output = item.get("result", item.get("output", ""))
        try:
            parsed = json.loads(str(raw_output))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError:
                continue
        if not isinstance(parsed, dict):
            continue
        step = str(parsed.get("step", "")).strip()
        if step:
            mapped[step] = {str(key): value for key, value in parsed.items()}
    return mapped


def _stage2_runner_for_service(service: str):
    mapping = {
        "genspark": run_genspark_job,
        "seaart": run_seaart_job,
        "geminigen": run_geminigen_job,
        "canva": run_canva_job,
    }
    return mapping[service]


def _is_stage2_probe_service(service: str) -> bool:
    return service in {"genspark", "seaart", "geminigen", "canva"}


def _build_stage2_row1_video_plan(
    *, asset_root: Path, run_id: str, agent_browser_services: list[str]
) -> dict[str, object]:
    return {
        "contract": "video_plan",
        "contract_version": "1.0",
        "run_id": run_id,
        "row_ref": "Sheet1!row1",
        "topic": "Stage2 row1 auto probe",
        "scene_plan": [
            {"scene_index": 1, "prompt": "scene one"},
            {"scene_index": 2, "prompt": "scene two"},
            {"scene_index": 3, "prompt": "scene three"},
            {"scene_index": 4, "prompt": "scene four"},
        ],
        "asset_plan": {
            "asset_root": str(asset_root.resolve()),
            "common_asset_folder": str(asset_root.resolve()),
        },
        "voice_plan": {"mapping_source": "excel_scene", "scene_count": 4, "groups": []},
        "reason_code": "ok",
        "evidence": {"source": "stage2_row1_detached"},
        "use_agent_browser_services": agent_browser_services,
    }


def _build_stage2_placeholder_adapter_command(target_path: Path) -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            f"p=Path(r'{str(target_path)}'); "
            "p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_bytes(b'placeholder')"
        ),
    ]


def _run_stage2_row1_probe(
    *,
    config: RuntimeConfig,
    probe_root: Path,
    run_id: str,
    agent_browser_services: list[str],
) -> dict[str, object]:
    asset_root = config.artifact_root / "stage2_row1_assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    video_plan = _build_stage2_row1_video_plan(
        asset_root=asset_root,
        run_id=run_id,
        agent_browser_services=agent_browser_services,
    )
    jobs, render_spec = build_stage2_jobs(video_plan)
    stage2_results: list[dict[str, object]] = []
    overall_ok = True
    failure_code = "OK"
    placeholder_services: list[str] = []
    live_ready_services: list[str] = []
    for raw in jobs[:-1]:
        typed = cast(dict[str, object], raw)
        job_payload = cast(dict[str, object], typed["job"])
        service = str(job_payload["worker"])
        if not _is_stage2_probe_service(service):
            continue
        payload = cast(dict[str, object], job_payload["payload"])
        payload["runtime_root"] = str(config.result_router_file.parent.parent.resolve())
        if service not in agent_browser_services:
            payload["adapter_command"] = _build_stage2_placeholder_adapter_command(
                Path(str(payload.get("service_artifact_path", "")))
            )
        contract = JobContract(
            job_id=str(job_payload["job_id"]),
            workload=cast(WorkloadName, service),
            checkpoint_key=str(job_payload["checkpoint_key"]),
            payload=payload,
        )
        runner = _stage2_runner_for_service(service)
        result = runner(contract, config.artifact_root)
        fallback_used = False
        attach_attempt_failed = str(result.get("status", "")) != "ok"
        if attach_attempt_failed and service in agent_browser_services:
            fallback_payload = dict(payload)
            fallback_payload.pop("use_agent_browser", None)
            fallback_payload["adapter_command"] = (
                _build_stage2_placeholder_adapter_command(
                    Path(str(payload.get("service_artifact_path", "")))
                )
            )
            fallback_contract = JobContract(
                job_id=str(job_payload["job_id"]),
                workload=cast(WorkloadName, service),
                checkpoint_key=str(job_payload["checkpoint_key"]),
                payload=fallback_payload,
            )
            result = runner(fallback_contract, config.artifact_root)
            fallback_used = True
        if fallback_used or service not in agent_browser_services:
            placeholder_services.append(service)
        elif str(result.get("status", "")) == "ok":
            live_ready_services.append(service)
        stage2_results.append(
            {
                "service": service,
                "status": str(result.get("status", "")),
                "error_code": str(result.get("error_code", "")),
                "details": result.get("details", {}),
                "completion": result.get("completion", {}),
                "fallback_used": fallback_used,
                "attach_attempt_failed": attach_attempt_failed,
            }
        )
        if str(result.get("status", "")) != "ok" and overall_ok:
            overall_ok = False
            failure_code = str(result.get("error_code", "BROWSER_BLOCKED"))
    report: dict[str, object] = {
        "run_id": run_id,
        "mode": "stage2_row1",
        "status": "ok" if overall_ok else "blocked",
        "code": "OK" if overall_ok else failure_code,
        "exit_code": exit_codes.SUCCESS
        if overall_ok
        else exit_code_from_status(failure_code),
        "agent_browser_services": agent_browser_services,
        "readiness_scope": "stage2_probe",
        "probe_success": overall_ok,
        "live_readiness": "full" if not placeholder_services else "partial",
        "placeholder_services": placeholder_services,
        "live_ready_services": live_ready_services,
        "video_plan": video_plan,
        "render_spec": render_spec,
        "results": stage2_results,
    }
    _ = _write_probe_result(probe_root, report)
    return report


def _run_stage5_row1_probe(
    *,
    owner: str,
    config: RuntimeConfig,
    probe_root: Path,
    run_id: str,
    excel_path: str,
    sheet_name: str,
    row_index: int,
    max_control_ticks: int,
) -> dict[str, object]:
    probe_config = config.replace(stable_file_age_sec=0)
    seed_result = seed_excel_row(
        config=probe_config,
        run_id=run_id,
        excel_path=excel_path,
        sheet_name=sheet_name,
        row_index=row_index,
        accepted_statuses={"", "partial", "failed", "nan", "ok", "seeded"},
    )
    if str(seed_result.get("status", "")) != "seeded":
        report: dict[str, object] = {
            "run_id": run_id,
            "mode": "stage5_row1",
            "status": str(seed_result.get("status", "failed")),
            "code": str(seed_result.get("code", "CLI_USAGE")),
            "exit_code": exit_code_from_status(
                str(seed_result.get("code", "CLI_USAGE"))
            ),
            "probe_success": False,
            "seed_result": seed_result,
            "ticks": 0,
            "control_results": [],
            "placeholder_services": [],
        }
        _ = _write_probe_result(probe_root, report)
        return report
    control_results: list[dict[str, object]] = []
    final_metadata: dict[str, object] = {}
    readiness_snapshot: dict[str, object] = {}
    for _ in range(max_control_ticks):
        result = run_control_loop_once(owner=owner, config=probe_config, run_id=run_id)
        control_results.append(result)
        latest_payload_path = probe_config.result_router_file
        if latest_payload_path.exists():
            latest_payload = json.loads(latest_payload_path.read_text(encoding="utf-8"))
            if isinstance(latest_payload, dict):
                metadata_obj = cast(
                    dict[str, object], latest_payload.get("metadata", {})
                )
                final_metadata = metadata_obj if isinstance(metadata_obj, dict) else {}
        latest_workload = str(final_metadata.get("workload", "")).strip()
        if (
            bool(final_metadata.get("final_output", False))
            and latest_workload == "render"
        ):
            readiness = load_runtime_readiness(config, completed=True)
            readiness_snapshot = {
                "ready": bool(readiness.get("ready", False)),
                "code": str(readiness.get("code", "CLI_USAGE")),
                "blockers": cast(list[object], readiness.get("blockers", []))
                if isinstance(readiness.get("blockers", []), list)
                else [],
                "promotion_gates": cast(
                    dict[str, object], readiness.get("promotion_gates", {})
                )
                if isinstance(readiness.get("promotion_gates", {}), dict)
                else {},
                "snapshot_run_id": str(readiness.get("snapshot_run_id", "")),
                "trace_paths": cast(dict[str, object], readiness.get("trace_paths", {}))
                if isinstance(readiness.get("trace_paths", {}), dict)
                else {},
            }
            if not bool(readiness_snapshot.get("ready", False)):
                report: dict[str, object] = {
                    "run_id": run_id,
                    "mode": "stage5_row1",
                    "status": "failed",
                    "code": str(readiness_snapshot.get("code", "CLI_USAGE")),
                    "exit_code": exit_code_from_status(
                        str(readiness_snapshot.get("code", "CLI_USAGE"))
                    ),
                    "probe_success": False,
                    "seed_result": seed_result,
                    "ticks": len(control_results),
                    "control_results": control_results,
                    "placeholder_services": [],
                    "final_artifact_path": str(
                        final_metadata.get("final_artifact_path", "")
                    ),
                    "readiness": readiness_snapshot,
                }
                _ = _write_probe_result(probe_root, report)
                return report
            report: dict[str, object] = {
                "run_id": run_id,
                "mode": "stage5_row1",
                "status": "ok",
                "code": "OK",
                "exit_code": exit_codes.SUCCESS,
                "probe_success": True,
                "seed_result": seed_result,
                "ticks": len(control_results),
                "control_results": control_results,
                "placeholder_services": [],
                "final_artifact_path": str(
                    final_metadata.get("final_artifact_path", "")
                ),
                "readiness": readiness_snapshot,
            }
            _ = _write_probe_result(probe_root, report)
            return report
        if str(result.get("status", "")) in {"failed", "blocked"}:
            report: dict[str, object] = {
                "run_id": run_id,
                "mode": "stage5_row1",
                "status": str(result.get("status", "failed")),
                "code": str(result.get("code", "CLI_USAGE")),
                "exit_code": exit_code_from_status(
                    str(result.get("code", "CLI_USAGE"))
                ),
                "probe_success": False,
                "seed_result": seed_result,
                "ticks": len(control_results),
                "control_results": control_results,
                "placeholder_services": [],
                "final_artifact_path": str(
                    final_metadata.get("final_artifact_path", "")
                ),
                "readiness": readiness_snapshot,
            }
            _ = _write_probe_result(probe_root, report)
            return report
    report: dict[str, object] = {
        "run_id": run_id,
        "mode": "stage5_row1",
        "status": "failed",
        "code": "BATCH_TIMEOUT",
        "exit_code": exit_code_from_status("BATCH_TIMEOUT"),
        "probe_success": False,
        "seed_result": seed_result,
        "ticks": len(control_results),
        "control_results": control_results,
        "placeholder_services": [],
        "final_artifact_path": str(final_metadata.get("final_artifact_path", "")),
        "readiness": readiness_snapshot,
    }
    _ = _write_probe_result(probe_root, report)
    return report


def _run_stage5b_5row_probe(
    *,
    owner: str,
    config: RuntimeConfig,
    probe_root: Path,
    run_id: str,
    excel_path: str,
    sheet_name: str,
    batch_count: int,
    max_control_ticks: int,
) -> dict[str, object]:
    selected_rows = select_pending_row_indexes(
        excel_path,
        sheet_name=sheet_name,
        limit=batch_count,
    )
    if not selected_rows:
        report: dict[str, object] = {
            "run_id": run_id,
            "mode": "stage5b_5row",
            "status": "no_work",
            "code": "NO_WORK",
            "exit_code": exit_codes.SUCCESS,
            "probe_success": False,
            "selected_rows": [],
            "row_reports": [],
        }
        _ = _write_probe_result(probe_root, report)
        return report
    row_reports: list[dict[str, object]] = []
    for offset, row_index in enumerate(selected_rows, start=1):
        row_report = _run_stage5_row1_probe(
            owner=owner,
            config=config,
            probe_root=probe_root / f"row_{offset:02d}",
            run_id=f"{run_id}-row{offset:02d}",
            excel_path=excel_path,
            sheet_name=sheet_name,
            row_index=row_index,
            max_control_ticks=max_control_ticks,
        )
        row_reports.append(row_report)
        if str(row_report.get("status", "")) != "ok":
            report: dict[str, object] = {
                "run_id": run_id,
                "mode": "stage5b_5row",
                "status": "failed",
                "code": str(row_report.get("code", "CLI_USAGE")),
                "exit_code": exit_code_from_status(
                    str(row_report.get("code", "CLI_USAGE"))
                ),
                "probe_success": False,
                "selected_rows": selected_rows,
                "row_reports": row_reports,
            }
            _ = _write_probe_result(probe_root, report)
            return report
    report = {
        "run_id": run_id,
        "mode": "stage5b_5row",
        "status": "ok",
        "code": "OK",
        "exit_code": exit_codes.SUCCESS,
        "probe_success": True,
        "selected_rows": selected_rows,
        "row_reports": row_reports,
    }
    _ = _write_probe_result(probe_root, cast(dict[str, object], report))
    return cast(dict[str, object], report)


def _run_browser_recovery_probe(
    *, config: RuntimeConfig, probe_root: Path, run_id: str
) -> dict[str, object]:
    browser_runtime = BrowserSupervisor(BrowserManager()).tick(
        registry_file=config.browser_registry_file,
        health_file=config.browser_health_file,
        events_file=config.control_plane_events_file,
        run_id=run_id,
        recover_unhealthy=True,
        restart_threshold=2,
        cooldown_sec=60,
    )
    gpt_status = tick_gpt_status(config.gpt_status_file, config)
    final_summary_raw = browser_runtime.get("final_summary", {})
    final_summary = (
        cast(dict[object, object], final_summary_raw)
        if isinstance(final_summary_raw, dict)
        else {}
    )
    all_healthy = bool(final_summary.get("all_healthy", False))
    distinct_code = "BROWSER_UNHEALTHY"
    blocked_services_raw = final_summary.get("blocked_services", [])
    blocked_services = (
        cast(list[object], blocked_services_raw)
        if isinstance(blocked_services_raw, list)
        else []
    )
    if any(str(service) for service in blocked_services):
        sessions_raw = browser_runtime.get("sessions", [])
        sessions = (
            cast(list[object], sessions_raw) if isinstance(sessions_raw, list) else []
        )
        for entry in sessions:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status", ""))
            blocked_reason = str(entry.get("blocked_reason", ""))
            if (
                status == "restart_exhausted"
                or blocked_reason == "restart_budget_exhausted"
            ):
                distinct_code = "BROWSER_RESTART_EXHAUSTED"
                break
    report = {
        "run_id": run_id,
        "mode": "browser_recover",
        "status": "ok" if all_healthy else "blocked",
        "code": "OK" if all_healthy else distinct_code,
        "exit_code": 0 if all_healthy else exit_code_from_status(distinct_code),
        "runtime_root": str(_runtime_root_for_config(config)),
        "restarted_services": browser_runtime.get("restarted_services", []),
        "initial_summary": browser_runtime.get("initial_summary", {}),
        "final_summary": final_summary,
        "gpt_status": gpt_status,
    }
    _ = _write_probe_result(probe_root, report)
    return report


def _run_agent_browser_stage2_adapter_child(args: CliArgs) -> int:
    service = args.service.strip()
    if not service:
        return exit_codes.CLI_USAGE
    service_artifact_path = args.service_artifact_path.strip()
    if not service_artifact_path:
        return exit_codes.CLI_USAGE
    target_path = Path(service_artifact_path)
    cwd_workspace = Path.cwd()
    workspace = (
        cwd_workspace
        if (cwd_workspace / "request.json").exists()
        or (cwd_workspace / "request_payload.json").exists()
        else (
            target_path.parent.parent
            if len(target_path.parents) >= 2
            else cwd_workspace
        )
    )
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_root = workspace / "agent_browser_adapter_artifacts"
    attach_evidence = workspace / "attach_evidence.json"
    if attach_evidence.exists():
        attach_evidence.unlink()

    pre_actions: list[dict[str, object]] = []
    actions: list[dict[str, object]] = []
    prompt_path = workspace / "request_payload.json"
    request_path = workspace / "request.json"
    prompt = ""
    ref_img_1 = ""
    ref_img_2 = ""
    ref_img = ""
    first_frame_path = ""
    ref_images_requested: list[str] = []
    ref_images_resolved: list[str] = []
    request_payload_obj: dict[str, object] = {}
    bg_prompt = ""
    line1 = ""
    line2 = ""
    canva_truth_gate_failed = False
    thumb_data = _load_optional_json_dict(workspace / "thumb_data.json")
    if request_path.exists():
        try:
            request_payload = json.loads(request_path.read_text(encoding="utf-8"))
            typed_request = cast(dict[str, object], request_payload)
            request_payload_obj = cast(
                dict[str, object], typed_request.get("payload", {})
            )
        except (OSError, json.JSONDecodeError):
            request_payload_obj = {}
    elif prompt_path.exists():
        try:
            request_payload = json.loads(prompt_path.read_text(encoding="utf-8"))
            request_payload_obj = cast(dict[str, object], request_payload)
        except (OSError, json.JSONDecodeError):
            request_payload_obj = {}

    if request_payload_obj:
        prompt = str(request_payload_obj.get("prompt", "")).strip()
        ref_img_1 = str(request_payload_obj.get("ref_img_1", "")).strip()
        ref_img_2 = str(request_payload_obj.get("ref_img_2", "")).strip()
        ref_img = str(request_payload_obj.get("ref_img", "")).strip()
        first_frame_path = str(request_payload_obj.get("first_frame_path", "")).strip()
        try:
            if service == "canva" and not ref_img:
                ref_images_requested, ref_images_resolved = [], []
            else:
                ref_images_requested, ref_images_resolved = (
                    _resolve_stage2_ref_image_paths(request_payload_obj)
                )
        except RuntimeError:
            write_stage2_attach_evidence(
                workspace=workspace,
                service=service,
                port=args.port,
                result={"status": "failed", "error_code": "REF_IMAGE_UPLOAD_FAILED"},
                probe_debug_only=True,
                recovery_attempted=False,
                placeholder_artifact=False,
                ref_images_requested=[ref_img_1, ref_img_2],
                ref_images_resolved=[],
                ref_images_attach_attempted=True,
                ref_upload_error_code="REF_IMAGE_UPLOAD_FAILED",
            )
            return exit_codes.BROWSER_UNHEALTHY
    canva_extra_details: dict[str, object] | None = None
    if prompt and service == "genspark":
        _close_genspark_result_tabs(args.port)
        effective_prompt = prompt
        pre_actions = [
            {
                "type": "eval",
                "script": "(() => { if (location.href !== 'https://www.genspark.ai/agents?type=image_generation_agent') { location.href = 'https://www.genspark.ai/agents?type=image_generation_agent'; return JSON.stringify({ok:true, step:'navigated_image_agent'}); } return JSON.stringify({ok:true, step:'already_on_image_agent'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const buttons = Array.from(document.querySelectorAll('button,[role=button],a')); const target = buttons.find(item => ((item.innerText || item.textContent || '').trim()).startsWith('New')); if (target instanceof HTMLElement) { target.click(); return JSON.stringify({ok:true, step:'selected_new_session'}); } return JSON.stringify({ok:true, step:'new_session_not_found'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const dismissLabels = ['나중에','Later','닫기','Close']; const buttons = Array.from(document.querySelectorAll('button')); for (const btn of buttons) { const text = (btn.innerText || btn.textContent || '').trim(); const aria = btn.getAttribute ? (btn.getAttribute('aria-label') || '') : ''; if (dismissLabels.includes(text) || dismissLabels.includes(aria)) { btn.click(); return JSON.stringify({ok:true, step:'dismissed_modal'}); } } return JSON.stringify({ok:true, step:'no_modal'}); })()",
            },
        ]
        actions = [
            {
                "type": "wait",
                "target": "textarea.j-search-input",
            },
            {
                "type": "eval",
                "script": "(() => { const textarea = document.querySelector('textarea.j-search-input'); if (!textarea) return JSON.stringify({ok:false,error:\"NO_INPUT\"}); const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set; textarea.focus(); if (setter) { setter.call(textarea, ''); } else { textarea.value=''; } textarea.dispatchEvent(new Event('input',{bubbles:true})); textarea.dispatchEvent(new Event('change',{bubbles:true})); if (setter) { setter.call(textarea, "
                + json.dumps(effective_prompt, ensure_ascii=True)
                + "); } else { textarea.value="
                + json.dumps(effective_prompt, ensure_ascii=True)
                + "; } textarea.dispatchEvent(new Event('input',{bubbles:true})); textarea.dispatchEvent(new Event('change',{bubbles:true})); return JSON.stringify({ok:true, step:'prompt_filled'}); })()",
            },
            {
                "type": "eval",
                "script": '(() => { const textarea = document.querySelector(\'textarea.j-search-input\'); const btn = document.querySelector(\'.enter-icon-wrapper\'); if (!textarea && !btn) return JSON.stringify({ok:false,error:"NO_BUTTON"}); if (textarea) { textarea.focus(); for (const type of ["keydown","keypress","keyup"]) { textarea.dispatchEvent(new KeyboardEvent(type, {key:"Enter", code:"Enter", keyCode:13, which:13, bubbles:true})); } } if (btn) { btn.click(); } return JSON.stringify({ok:true, step:"clicked_generate"}); })()',
            },
        ]
    elif prompt and service == "seaart":
        pre_actions = []
        actions = [
            {
                "type": "wait",
                "target": "textarea.el-textarea__inner",
            },
            {
                "type": "eval",
                "script": "(() => { const textarea = document.querySelector('textarea.el-textarea__inner'); if (!textarea) return JSON.stringify({ok:false,error:\"NO_INPUT\"}); textarea.focus(); textarea.value=''; textarea.dispatchEvent(new Event('input',{bubbles:true})); textarea.value="
                + json.dumps(prompt, ensure_ascii=True)
                + "; textarea.dispatchEvent(new Event('input',{bubbles:true})); return JSON.stringify({ok:true, step:'prompt_filled'}); })()",
            },
            {
                "type": "eval",
                "script": '(() => { const btn = document.querySelector(\'#generate-btn\'); if (!btn) return JSON.stringify({ok:false,error:"NO_BUTTON"}); btn.click(); return JSON.stringify({ok:true, step:"clicked_generate"}); })()',
            },
        ]
    elif service == "canva":
        bg_prompt = str(thumb_data.get("bg_prompt", prompt)).strip()
        line1 = str(thumb_data.get("line1", "")).strip()
        line2 = str(thumb_data.get("line2", "")).strip()
        pre_actions = []
        actions = [
            {
                "type": "eval",
                "script": _canva_page_count_script("page_count_before").replace(
                    "return JSON.stringify({ok:true, step:'page_count_before', count: totalPages});",
                    "window.__runtime_v2_canva_page_count_before = totalPages; return JSON.stringify({ok:true, step:'page_count_before', count: totalPages});",
                ),
            },
            {
                "type": "eval",
                "script": "(() => { document.body && document.body.click(); return JSON.stringify({ok:true, step:'body_focused'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const duplicateBtn = Array.from(document.querySelectorAll('button,[role=button]')).find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return text.includes('페이지 복제') || text.includes('Duplicate page'); }); if (duplicateBtn instanceof HTMLElement) { duplicateBtn.click(); window.__runtime_v2_canva_duplicated = true; return JSON.stringify({ok:true, step:'duplicated_template_page'}); } document.dispatchEvent(new KeyboardEvent('keydown', {key:'a', ctrlKey:true, bubbles:true})); document.dispatchEvent(new KeyboardEvent('keyup', {key:'a', ctrlKey:true, bubbles:true})); document.dispatchEvent(new KeyboardEvent('keydown', {key:'c', ctrlKey:true, bubbles:true})); document.dispatchEvent(new KeyboardEvent('keyup', {key:'c', ctrlKey:true, bubbles:true})); window.__runtime_v2_canva_duplicated = false; return JSON.stringify({ok:true, step:'copied_template'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { if (window.__runtime_v2_canva_duplicated) return JSON.stringify({ok:true, step:'add_page_optional'}); const labels=['페이지 추가','Add a new page']; const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text=((item.innerText||item.textContent||'')+' '+(item.getAttribute('aria-label')||'')).trim(); return labels.some(label => text.includes(label)); }); if (!btn) return JSON.stringify({ok:true, step:'add_page_optional'}); btn.click(); return JSON.stringify({ok:true, step:'clicked_add_page'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { if (window.__runtime_v2_canva_duplicated) return JSON.stringify({ok:true, step:'pasted_template_optional'}); document.dispatchEvent(new KeyboardEvent('keydown', {key:'v', ctrlKey:true, bubbles:true})); document.dispatchEvent(new KeyboardEvent('keyup', {key:'v', ctrlKey:true, bubbles:true})); return JSON.stringify({ok:true, step:'pasted_template'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const before = Number(window.__runtime_v2_canva_page_count_before || 0); const body = document.body && document.body.innerText ? document.body.innerText : ''; const match = body.match(/페이지\\s*(\\d+)\\s*\\/\\s*(\\d+)/) || body.match(/Page\\s*(\\d+)\\s*\\/\\s*(\\d+)/i); const fallback = document.querySelectorAll('button[aria-label=\"페이지 삭제\"], button[aria-label=\"Delete page\"]').length; const countPages = () => { const currentBody = document.body && document.body.innerText ? document.body.innerText : ''; const currentMatch = currentBody.match(/페이지\\s*(\\d+)\\s*\\/\\s*(\\d+)/) || currentBody.match(/Page\\s*(\\d+)\\s*\\/\\s*(\\d+)/i); const currentFallback = document.querySelectorAll('button[aria-label=\"페이지 삭제\"], button[aria-label=\"Delete page\"]').length; return currentMatch ? Number(currentMatch[2]) : currentFallback; }; const count = match ? Number(match[2]) : fallback; if (window.__runtime_v2_canva_duplicated && before > 0 && count <= before) { const labels=['페이지 추가','Add a new page']; const buttons = Array.from(document.querySelectorAll('button')); const addBtn = buttons.find(item => { const text=((item.innerText||item.textContent||'')+' '+(item.getAttribute('aria-label')||'')).trim(); return labels.some(label => text.includes(label)); }); if (addBtn instanceof HTMLElement) { addBtn.click(); document.dispatchEvent(new KeyboardEvent('keydown', {key:'v', ctrlKey:true, bubbles:true})); document.dispatchEvent(new KeyboardEvent('keyup', {key:'v', ctrlKey:true, bubbles:true})); const fallbackCount = countPages(); return JSON.stringify({ok:true, step:'page_count_after', count:fallbackCount, fallback_clicked_add_page:true, fallback_pasted_template:true}); } } return JSON.stringify({ok:true, step:'page_count_after', count}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const cardTexts = Array.from(document.querySelectorAll('div,button,[role=button]')).filter(node => node instanceof HTMLElement && (node.offsetWidth > 0 || node.offsetHeight > 0)).map(node => ({ node, text: (node.textContent || '').trim() })).filter(item => item.text.includes('페이지') && item.text.includes('페이지 제목 추가')); const target = cardTexts.length ? cardTexts[cardTexts.length - 1].node : null; if (!(target instanceof HTMLElement)) return JSON.stringify({ok:false,error:'NO_CREATED_PAGE_CARD'}); target.click(); return JSON.stringify({ok:true, step:'selected_created_page'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const targets = Array.from(document.querySelectorAll('div.fbzKiw')).filter(node => node instanceof HTMLElement && node.offsetWidth > 0 && node.offsetHeight > 0); const target = targets.length ? targets[targets.length - 1] : document.body; if (target instanceof HTMLElement) { target.click(); return JSON.stringify({ok:true, step:'focused_background_canvas'}); } return JSON.stringify({ok:false,error:'NO_BACKGROUND_CANVAS'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const labels = ['배경 생성', 'Create background', 'Background generator', 'Magic Background', 'Product Background']; const buttons = Array.from(document.querySelectorAll('button,[role=button],div')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return labels.some(label => text.includes(label)); }); if (!btn) return JSON.stringify({ok:false,error:'NO_BACKGROUND_GENERATE_BUTTON'}); if (btn instanceof HTMLElement) { btn.click(); return JSON.stringify({ok:true, step:'opened_background_generate_panel'}); } return JSON.stringify({ok:false,error:'NO_BACKGROUND_GENERATE_BUTTON'}); })()",
            },
            {
                "type": "eval",
                "script": '(() => { const selectors = [\'textarea[placeholder*="예시"]\',\'textarea[placeholder*="Describe"]\',\'textarea[placeholder*="prompt"]\',\'textarea[aria-label*="프롬프트"]\',\'textarea[aria-label*="Prompt"]\',\'div[role="dialog"] textarea\',\'div[contenteditable="true"][role="textbox"]\',\'div[contenteditable="true"][data-lexical-editor="true"]\',\'[role="textbox"][contenteditable="true"]\',\'textarea\']; const promptText = '
                + json.dumps(bg_prompt, ensure_ascii=True)
                + "; for (const selector of selectors) { const input = document.querySelector(selector); if (!(input instanceof HTMLElement)) continue; input.focus(); if ('value' in input) { const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set; if (setter && input instanceof HTMLTextAreaElement) { setter.call(input, promptText); } else { input.value = promptText; } input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return JSON.stringify({ok:true, step:'filled_background_prompt'}); } if (input.isContentEditable) { input.textContent = promptText; input.dispatchEvent(new InputEvent('input', {bubbles:true, data: promptText, inputType:'insertText'})); return JSON.stringify({ok:true, step:'filled_background_prompt'}); } } return JSON.stringify({ok:false,error:'NO_BACKGROUND_PROMPT_INPUT'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const beforeGenerated = Array.from(document.querySelectorAll('img,[role=img],div')).map(node => { if (!(node instanceof HTMLElement)) return ''; if (!(node.offsetWidth > 30 || node.offsetHeight > 30)) return ''; const style = window.getComputedStyle(node); const backgroundImage = style.backgroundImage || ''; const src = node instanceof HTMLImageElement ? (node.currentSrc || node.src || '') : ''; return src || backgroundImage; }).filter(Boolean); window.__runtime_v2_canva_generated_before = beforeGenerated; const labels = ['생성', 'Generate']; const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); if (!labels.some(label => text.includes(label))) return false; return !text.includes('배경 생성') && !text.includes('Create background') && !text.includes('Background generator'); }); if (!btn) return JSON.stringify({ok:false,error:'NO_BACKGROUND_EXECUTE_BUTTON'}); btn.click(); return JSON.stringify({ok:true, step:'submitted_background_generate'}); })()",
            },
            {
                "type": "eval",
                "script": "(async () => { const before = new Set(Array.isArray(window.__runtime_v2_canva_generated_before) ? window.__runtime_v2_canva_generated_before : []); const candidateKey = (node) => { if (!(node instanceof HTMLElement)) return ''; if (!(node.offsetWidth > 30 || node.offsetHeight > 30)) return ''; const style = window.getComputedStyle(node); const backgroundImage = style.backgroundImage || ''; const src = node instanceof HTMLImageElement ? (node.currentSrc || node.src || '') : ''; return src || backgroundImage; }; const deadline = Date.now() + 20000; while (Date.now() < deadline) { const candidates = Array.from(document.querySelectorAll('img,[role=img],div')); for (const node of candidates) { const key = candidateKey(node); if (!key || before.has(key)) continue; node.click(); await new Promise(resolve => setTimeout(resolve, 1500)); return JSON.stringify({ok:true, step:'selected_generated_background', key}); } await new Promise(resolve => setTimeout(resolve, 1000)); } return JSON.stringify({ok:true, step:'background_generate_result_optional'}); })()",
            },
            {
                "type": "eval",
                "script": "(() => { const labels = ['업로드 항목', '업로드', 'Uploads']; const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return labels.some(label => text.includes(label)); }); if (!btn) return JSON.stringify({ok:false,error:'NO_UPLOAD_TAB'}); btn.click(); return JSON.stringify({ok:true, step:'opened_upload_tab'}); })()",
            },
        ]
        if ref_img:
            actions.extend(
                [
                    {
                        "type": "eval",
                        "script": "(async () => { const before = new Set(Array.from(document.querySelectorAll('img,[role=img]')).map(node => { if (!(node instanceof HTMLElement)) return ''; if (node.offsetWidth < 30 || node.offsetHeight < 30) return ''; const style = window.getComputedStyle(node); const backgroundImage = style.backgroundImage || ''; const src = node instanceof HTMLImageElement ? (node.currentSrc || node.src || '') : ''; return src || backgroundImage; }).filter(Boolean)); const deadline = Date.now() + 15000; const candidateKey = (node) => { if (!(node instanceof HTMLElement)) return ''; if (node.offsetWidth < 30 || node.offsetHeight < 30) return ''; const style = window.getComputedStyle(node); const backgroundImage = style.backgroundImage || ''; const src = node instanceof HTMLImageElement ? (node.currentSrc || node.src || '') : ''; return src || backgroundImage; }; while (Date.now() < deadline) { const candidates = Array.from(document.querySelectorAll('img,[role=img]')); for (const node of candidates) { const key = candidateKey(node); if (!key || before.has(key)) continue; node.click(); await new Promise(resolve => setTimeout(resolve, 3000)); return JSON.stringify({ok:true, step:'placed_uploaded_image', key}); } await new Promise(resolve => setTimeout(resolve, 1000)); } return JSON.stringify({ok:false,error:'NO_UPLOADED_IMAGE_THUMB'}); })()",
                    },
                    {
                        "type": "eval",
                        "script": "(() => { const labels = ['배경 제거', 'Remove background']; const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return labels.some(label => text.includes(label)); }); if (!btn) return JSON.stringify({ok:true, step:'remove_background_optional'}); btn.click(); return JSON.stringify({ok:true, step:'clicked_remove_background'}); })()",
                    },
                    {
                        "type": "eval",
                        "script": "(() => { const labels = ['위치', 'Position']; const buttons = Array.from(document.querySelectorAll('button,[role=button],div')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return labels.some(label => text.includes(label)); }); if (!(btn instanceof HTMLElement)) return JSON.stringify({ok:true, step:'position_panel_optional'}); btn.click(); return JSON.stringify({ok:true, step:'opened_position_panel'}); })()",
                    },
                    {
                        "type": "eval",
                        "script": "(() => { const labels = ['정렬', 'Arrange']; const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return labels.some(label => text.includes(label)); }); if (!btn) return JSON.stringify({ok:true, step:'position_inputs_already_visible'}); btn.click(); return JSON.stringify({ok:true, step:'opened_arrange_tab'}); })()",
                    },
                    {
                        "type": "eval",
                        "script": "(() => { const values = ['1045','720','235','0']; const inputs = Array.from(document.querySelectorAll('input[inputmode=\"decimal\"]')).filter(node => node instanceof HTMLInputElement && node.offsetWidth > 0 && node.offsetHeight > 0); if (inputs.length < 4) return JSON.stringify({ok:true, step:'position_inputs_optional', count: inputs.length}); for (let index = 0; index < 4; index += 1) { const input = inputs[index]; input.focus(); input.value = values[index]; input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); } return JSON.stringify({ok:true, step:'set_image_position', values}); })()",
                    },
                ]
            )
        if line1 or line2:
            actions.append(
                {
                    "type": "eval",
                    "script": "(() => { const line1 = "
                    + json.dumps(line1, ensure_ascii=True)
                    + "; const line2 = "
                    + json.dumps(line2, ensure_ascii=True)
                    + "; const applied = []; const spans = Array.from(document.querySelectorAll('span[style*=\"color\"]')).filter(el => el instanceof HTMLElement && (el.offsetWidth > 0 || el.offsetHeight > 0)); const yellow = spans.find(el => String(el.getAttribute('style') || '').includes('rgb(255, 215, 0)')); const white = spans.find(el => String(el.getAttribute('style') || '').includes('rgb(255, 255, 255)')); if (yellow && line1) { yellow.textContent = line1; applied.push('rgb(255, 215, 0)'); } if (white && line2) { white.textContent = line2; applied.push('rgb(255, 255, 255)'); } if (applied.length === 0) { const nodes = Array.from(document.querySelectorAll('main div, main span, main p, main h1, main h2, main h3')).filter(el => el instanceof HTMLElement && (el.offsetWidth > 0 || el.offsetHeight > 0) && (el.textContent || '').trim().length >= 4 && (el.textContent || '').trim().length <= 120); const first = nodes[0]; const second = nodes[1]; if (first && line1 && line2 && !second) { first.textContent = line1 + ' / ' + line2; applied.push('fallback-combined'); } else { if (first && line1) { first.textContent = line1; applied.push('fallback-0'); } if (second && line2) { second.textContent = line2; applied.push('fallback-1'); } } } if (applied.length === 0) return JSON.stringify({ok:false,error:'NO_TEXT_TARGET'}); return JSON.stringify({ok:true, step:'edited_thumbnail_text', applied}); })()",
                }
            )
        actions.extend(
            [
                {
                    "type": "eval",
                    "script": "(() => { const labels = ['파일', 'File']; const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return labels.some(label => text === label || text.includes(label)); }); if (!btn) return JSON.stringify({ok:false,error:'NO_FILE_MENU'}); btn.click(); return JSON.stringify({ok:true, step:'opened_file_menu'}); })()",
                },
                {
                    "type": "eval",
                    "script": "(() => { const items = Array.from(document.querySelectorAll('button,[role=menuitem]')); const btn = items.find(item => { if (!(item instanceof HTMLElement)) return false; const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return text.includes('다운로드') || text.includes('Download') || text.includes('내보내기') || text.includes('Export') || text.includes('공유') || text.includes('Share'); }); if (!(btn instanceof HTMLElement)) return JSON.stringify({ok:false,error:'NO_DOWNLOAD_MENU'}); btn.click(); return JSON.stringify({ok:true, step:'opened_download_panel'}); })()",
                },
                {
                    "type": "eval",
                    "script": "(() => { const input = document.querySelector('input[placeholder*=\"페이지\"], input[placeholder*=\"page\"]'); if (!(input instanceof HTMLElement)) return JSON.stringify({ok:true, step:'page_picker_unavailable'}); input.click(); const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return text.includes('현재 페이지') || text.includes('Current page'); }); if (btn instanceof HTMLElement) { btn.click(); return JSON.stringify({ok:true, step:'selected_current_page'}); } const body = document.body && document.body.innerText ? document.body.innerText : ''; const match = body.match(/페이지\\s*(\\d+)\\s*\\/\\s*\\d+/) || body.match(/Page\\s*(\\d+)\\s*\\/\\s*\\d+/i); if ('value' in input && match && match[1]) { input.focus(); input.value = match[1]; input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); return JSON.stringify({ok:true, step:'typed_current_page', page: match[1]}); } return JSON.stringify({ok:false,error:'NO_CURRENT_PAGE_OPTION'}); })()",
                },
                {
                    "type": "eval",
                    "script": "(() => { const labels = ['완료', 'Done']; const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); return labels.some(label => text === label || text.includes(label)); }); if (!btn) return JSON.stringify({ok:true, step:'done_button_optional'}); btn.click(); return JSON.stringify({ok:true, step:'confirmed_download_options'}); })()",
                },
                {
                    "type": "eval",
                    "script": "(() => { const buttons = Array.from(document.querySelectorAll('button,[role=button],a')); const btn = buttons.find(item => { if (!(item instanceof HTMLElement)) return false; const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute('aria-label') || '')).trim(); const role = item.getAttribute('role') || ''; const disabled = item.getAttribute('aria-disabled') || ''; return (text.includes('다운로드') || text.includes('Download') || text.includes('저장') || text.includes('Save') || text.includes('내보내기') || text.includes('Export') || text.includes('공유') || text.includes('Share') || text.includes('PNG')) && role !== 'menuitem' && disabled !== 'true'; }); if (!(btn instanceof HTMLElement)) return JSON.stringify({ok:false,error:'NO_DOWNLOAD_EXECUTE_BUTTON'}); btn.click(); return JSON.stringify({ok:true, step:'clicked_download_execute'}); })()",
                },
                {
                    "type": "eval",
                    "script": "(() => { const buttons = Array.from(document.querySelectorAll('button[aria-label=\"페이지 삭제\"], button[aria-label=\"Delete page\"]')); if (buttons.length < 2) return JSON.stringify({ok:true, step:'cleanup_skipped_single_page'}); const btn = buttons[buttons.length - 1]; btn.click(); return JSON.stringify({ok:true, step:'cleanup_deleted_created_page'}); })()",
                },
            ]
        )
    elif prompt and service == "geminigen":
        pre_actions = [
            {
                "type": "wait",
                "target": "textarea[placeholder*='Describe the video']",
            },
            {
                "type": "eval",
                "script": "(() => { const createTabs = Array.from(document.querySelectorAll('[id*=\"trigger-create-new\"], button, [role=tab]')); const tab = createTabs.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute && (item.getAttribute('aria-label') || ''))).trim(); return text.includes('Create New'); }); if (tab instanceof HTMLElement) { tab.click(); return JSON.stringify({ok:true, step:'selected_create_new'}); } return JSON.stringify({ok:true, step:'create_new_already_selected'}); })()",
            },
        ]
        actions = []
        actions.extend(
            [
                {
                    "type": "eval",
                    "script": "(() => { const selectors = ['textarea[placeholder*=\"Describe the video\"]', '.base-prompt-input textarea']; for (const selector of selectors) { const textarea = document.querySelector(selector); if (!(textarea instanceof HTMLTextAreaElement)) continue; const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set; textarea.focus(); if (setter) { setter.call(textarea, ''); setter.call(textarea, "
                    + json.dumps(prompt, ensure_ascii=True)
                    + "); } else { textarea.value = "
                    + json.dumps(prompt, ensure_ascii=True)
                    + "; } textarea.dispatchEvent(new Event('input',{bubbles:true})); textarea.dispatchEvent(new Event('change',{bubbles:true})); return JSON.stringify({ok:true, step:'prompt_filled'}); } return JSON.stringify({ok:false,error:'NO_INPUT'}); })()",
                },
                {
                    "type": "eval",
                    "script": "(() => { const buttons = Array.from(document.querySelectorAll('button')); const btn = buttons.find(item => { const text = ((item.innerText || item.textContent || '') + ' ' + (item.getAttribute && (item.getAttribute('aria-label') || ''))).trim(); return text.includes('Generate Video') || text.includes('Generate with'); }); if (!(btn instanceof HTMLElement)) return JSON.stringify({ok:false,error:'NO_BUTTON'}); btn.click(); return JSON.stringify({ok:true, step:'clicked_generate'}); })()",
                },
            ]
        )
    expected_url_substring = args.expected_url_substring.strip()
    if service == "genspark":
        expected_url_substring = expected_url_substring_for_service("genspark")
    job = JobContract(
        job_id=f"agent-browser-stage2-{service}",
        workload="agent_browser_verify",
        checkpoint_key=f"agent-browser-stage2:{service}:{args.port}",
        payload={
            "service": service,
            "port": args.port,
            "expected_url_substring": expected_url_substring,
            "expected_title_substring": args.expected_title_substring.strip(),
            "actions": actions,
            "ref_img_1": ref_img_1,
            "ref_img_2": ref_img_2,
        },
    )
    if pre_actions:
        pre_job = JobContract(
            job_id=f"agent-browser-stage2-pre-{service}",
            workload="agent_browser_verify",
            checkpoint_key=f"agent-browser-stage2-pre:{service}:{args.port}",
            payload={
                "service": service,
                "port": args.port,
                "expected_url_substring": expected_url_substring,
                "expected_title_substring": args.expected_title_substring.strip(),
                "actions": pre_actions,
                "capture_snapshot": False,
            },
        )
        try:
            pre_result = run_agent_browser_verify_job(pre_job, artifact_root)
        except Exception as exc:
            write_stage2_attach_evidence(
                workspace=workspace,
                service=service,
                port=args.port,
                result={
                    "status": "failed",
                    "stage": "agent_browser_verify",
                    "error_code": "AGENT_BROWSER_PRE_ACTION_EXCEPTION",
                    "details": {"exception": str(exc)},
                },
                probe_debug_only=True,
                recovery_attempted=False,
                placeholder_artifact=False,
                ref_images_requested=ref_images_requested,
                ref_images_resolved=ref_images_resolved,
                extra_details={
                    "exception": str(exc),
                    "exception_type": exc.__class__.__name__,
                },
            )
            return exit_codes.BROWSER_UNHEALTHY
        if not stage2_attach_verify_succeeded(pre_result):
            write_stage2_attach_evidence(
                workspace=workspace,
                service=service,
                port=args.port,
                result=pre_result,
                probe_debug_only=True,
                recovery_attempted=False,
                placeholder_artifact=False,
                ref_images_requested=ref_images_requested,
                ref_images_resolved=ref_images_resolved,
            )
            return exit_codes.BROWSER_UNHEALTHY
    ref_upload_error_code = ""
    ref_images_attach_attempted = False
    if service in {"genspark", "seaart", "canva"} and (
        (service == "canva" and bool(ref_img))
        or (service != "canva" and bool(ref_img_1 or ref_img_2))
    ):
        try:
            ref_images_attach_attempted = True
            attach_paths = ref_images_resolved
            if service == "canva" and ref_img:
                attach_paths = [ref_img]
            _attach_stage2_ref_images(
                port=args.port,
                expected_url_substring=expected_url_substring,
                file_paths=attach_paths,
            )
        except Exception:
            ref_upload_error_code = "REF_IMAGE_UPLOAD_FAILED"
            write_stage2_attach_evidence(
                workspace=workspace,
                service=service,
                port=args.port,
                result={
                    "status": "failed",
                    "error_code": "REF_IMAGE_UPLOAD_FAILED",
                },
                probe_debug_only=True,
                recovery_attempted=False,
                placeholder_artifact=False,
                ref_images_requested=ref_images_requested,
                ref_images_resolved=ref_images_resolved,
                ref_images_attach_attempted=ref_images_attach_attempted,
                ref_upload_error_code=ref_upload_error_code,
            )
            return exit_codes.BROWSER_UNHEALTHY
    try:
        result = run_agent_browser_verify_job(job, artifact_root)
    except Exception as exc:
        write_stage2_attach_evidence(
            workspace=workspace,
            service=service,
            port=args.port,
            result={
                "status": "failed",
                "stage": "agent_browser_verify",
                "error_code": "AGENT_BROWSER_EXCEPTION",
                "details": {"exception": str(exc)},
            },
            probe_debug_only=True,
            recovery_attempted=False,
            placeholder_artifact=False,
            ref_images_requested=ref_images_requested,
            ref_images_resolved=ref_images_resolved,
            ref_images_attach_attempted=ref_images_attach_attempted,
        )
        return exit_codes.BROWSER_UNHEALTHY
    attach_ok = stage2_attach_verify_succeeded(result)
    if not attach_ok:
        write_stage2_attach_evidence(
            workspace=workspace,
            service=service,
            port=args.port,
            result=result,
            probe_debug_only=True,
            recovery_attempted=False,
            placeholder_artifact=False,
            ref_images_requested=ref_images_requested,
            ref_images_resolved=ref_images_resolved,
            ref_images_attach_attempted=ref_images_attach_attempted,
        )
        return exit_codes.BROWSER_UNHEALTHY
    write_stage2_attach_evidence(
        workspace=workspace,
        service=service,
        port=args.port,
        result=result,
        probe_debug_only=True,
        recovery_attempted=False,
        placeholder_artifact=False,
        ref_images_requested=ref_images_requested,
        ref_images_resolved=ref_images_resolved,
        ref_images_attach_attempted=ref_images_attach_attempted,
        ref_upload_error_code=ref_upload_error_code,
    )
    if service == "canva":
        step_results = _stage2_result_by_step(result)
        before_count = _int_value(
            step_results.get("page_count_before", {}).get("count", 0), default=0
        )
        after_count = _int_value(
            step_results.get("page_count_after", {}).get("count", 0), default=0
        )
        clone_ok = after_count > before_count
        canva_extra_details = {
            "page_count_before": before_count,
            "page_count_after": after_count,
            "clone_ok": clone_ok,
            "background_generate_ok": bool(
                step_results.get("submitted_background_generate", {}).get("ok", False)
            ),
            "upload_tab_ok": bool(
                step_results.get("opened_upload_tab", {}).get("ok", False)
            ),
            "ref_image_requested": ref_img,
            "ref_image_upload_ok": bool(ref_img)
            and bool(step_results.get("placed_uploaded_image", {}).get("ok", False)),
            "remove_background_ok": bool(ref_img)
            and bool(
                step_results.get("clicked_remove_background", {}).get("ok", False)
            ),
            "position_ok": bool(ref_img)
            and bool(step_results.get("set_image_position", {}).get("ok", False)),
            "text_edit_ok": bool(
                step_results.get("edited_thumbnail_text", {}).get("ok", False)
                and len(
                    cast(
                        list[object],
                        step_results.get("edited_thumbnail_text", {}).get(
                            "applied", []
                        ),
                    )
                )
                > 0
            )
            or not (line1 or line2),
            "current_page_selection_ok": bool(
                step_results.get("selected_current_page", {}).get("ok", False)
            )
            or bool(step_results.get("selected_created_page", {}).get("ok", False))
            or bool(step_results.get("typed_current_page", {}).get("ok", False))
            or bool(step_results.get("page_picker_unavailable", {}).get("ok", False)),
            "download_options_ok": bool(
                step_results.get("confirmed_download_options", {}).get("ok", False)
            )
            or bool(step_results.get("done_button_optional", {}).get("ok", False)),
            "download_sequence_ok": bool(
                step_results.get("clicked_download_execute", {}).get("ok", False)
            ),
            "cleanup_ok": bool(
                step_results.get("cleanup_deleted_created_page", {}).get("ok", False)
            )
            or bool(
                step_results.get("cleanup_skipped_single_page", {}).get("ok", False)
            ),
            "bg_prompt": bg_prompt,
            "line1": line1,
            "line2": line2,
            "transcript_path": str(
                cast(dict[str, object], result.get("details", {})).get(
                    "transcript_path", ""
                )
            ),
        }
        transcript_path = str(canva_extra_details["transcript_path"])
        canva_truth_gate_failed = transcript_path and not (
            canva_extra_details["clone_ok"]
            and canva_extra_details["text_edit_ok"]
            and canva_extra_details["current_page_selection_ok"]
            and canva_extra_details["download_sequence_ok"]
        )
    if service in {"seaart", "genspark", "canva", "geminigen"}:
        debug_state_path: Path | None = None
        retry_trace_path: Path | None = None
        retry_trace: list[dict[str, object]] = []
        ready_image_url = ""
        image_ready_script = ""
        needs_followup_script = ""
        followup_submit_script = ""
        interrupted_regenerate_script = ""
        action_delay_script = ""

        def _trace_eval(
            phase: str, attempt: int, script: str, *, timeout: int = 5
        ) -> subprocess.CompletedProcess[str] | None:
            try:
                result_local = _run_agent_browser_eval(
                    args.port, script, timeout=timeout
                )
            except Exception as exc:
                retry_trace.append(
                    {
                        "phase": phase,
                        "attempt": attempt,
                        "exception": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )
                return None
            _append_retry_trace(
                retry_trace,
                phase=phase,
                attempt=attempt,
                result=result_local,
            )
            return result_local

        try:
            if service == "genspark":
                image_ready_script = "(() => { const valid = (src) => !!src && (/^https?:/i.test(src) || /^blob:/i.test(src) || /^data:/i.test(src) || src.startsWith('/api/files/')); const sels = ['img[src*=\"/api/files/\"]', '.image-generated img', '.image-grid img', '.generated-images .image-container .image-grid > img:first-child']; for (const sel of sels) { const found = document.querySelector(sel); const src = found ? (found.currentSrc || found.src || '') : ''; const width = found ? (found.naturalWidth || 0) : 0; if (valid(src) && width >= 256 && !src.includes('/manual/icons/')) return JSON.stringify({ok:true, src}); } const fallback = Array.from(document.images).map(img => ({src: img.currentSrc || img.src || '', width: img.naturalWidth || 0})).find(item => valid(item.src) && item.width >= 256 && !item.src.includes('/manual/icons/')); if (fallback) return JSON.stringify({ok:true, src: fallback.src}); return JSON.stringify({ok:false,error:'GENSPARK_IMAGE_NOT_READY'}); })()"
                confirm_probe_script = "(() => { const body = (document.body.innerText || ''); const recent = body.slice(-600); const questionMarks = (recent.match(/[?]/g) || []).length; if (window.__stage2_confirm_sent) return JSON.stringify({ok:false, reason:'CONFIRM_ALREADY_SENT'}); return JSON.stringify({ok: questionMarks >= 2, question_marks: questionMarks}); })()"
                confirm_submit_script = "(() => { const textarea = document.querySelector('textarea.j-search-input'); const btn = document.querySelector('.enter-icon-wrapper'); if (!textarea) return JSON.stringify({ok:false,error:'NO_INPUT'}); const reply = '예'; const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set; textarea.focus(); if (setter) { setter.call(textarea, reply); } else { textarea.value = reply; } textarea.dispatchEvent(new Event('input',{bubbles:true})); textarea.dispatchEvent(new Event('change',{bubbles:true})); for (const type of ['keydown','keypress','keyup']) { textarea.dispatchEvent(new KeyboardEvent(type, {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true})); } if (btn) { btn.click(); } window.__stage2_confirm_sent = true; return JSON.stringify({ok:true, step:'confirm_submitted'}); })()"
                action_delay_script = (
                    "(() => JSON.stringify({ok:true, step:'pre_capture_wait'}))()"
                )

                for _attempt in range(90):
                    poll = _trace_eval(
                        "image_ready_poll", _attempt + 1, image_ready_script, timeout=10
                    )
                    if poll is None:
                        sleep(2)
                        continue
                    if '"ok":true' in (poll.stdout or ""):
                        try:
                            poll_payload = json.loads((poll.stdout or "").strip())
                        except json.JSONDecodeError:
                            poll_payload = {}
                        if isinstance(poll_payload, dict):
                            ready_image_url = str(poll_payload.get("src", "")).strip()
                        _ = _run_agent_browser_eval(
                            args.port, action_delay_script, timeout=5
                        )
                        sleep(15)
                        break
                    confirm_probe = _trace_eval(
                        "confirm_probe",
                        _attempt + 1,
                        confirm_probe_script,
                        timeout=10,
                    )
                    if confirm_probe is not None and '"ok":true' in (
                        confirm_probe.stdout or ""
                    ):
                        _ = _trace_eval(
                            "confirm_submit",
                            _attempt + 1,
                            confirm_submit_script,
                            timeout=10,
                        )
                        sleep(5)
                    sleep(2)
            capture_url = (
                str(
                    cast(dict[str, object], result.get("details", {})).get(
                        "current_url", expected_url_substring
                    )
                ).strip()
                or expected_url_substring
            )
            if service == "genspark":
                _ = write_functional_evidence_bundle(
                    workspace=workspace,
                    service=service,
                    port=args.port,
                    expected_url_substring=capture_url,
                    service_artifact_path=target_path,
                    image_url_override=ready_image_url,
                )
            else:
                _ = write_functional_evidence_bundle(
                    workspace=workspace,
                    service=service,
                    port=args.port,
                    expected_url_substring=capture_url,
                    service_artifact_path=target_path,
                )
            if service == "geminigen":
                if not (
                    target_path.exists()
                    and target_path.is_file()
                    and target_path.stat().st_size > 0
                ):
                    raise RuntimeError("GEMINIGEN_TRUTHFUL_ARTIFACT_MISSING")
            if service == "canva" and canva_truth_gate_failed:
                raise RuntimeError("CANVA_TRUTHFUL_ARTIFACT_GATE_FAILED")
            placeholder_artifact = False
        except Exception:
            if service == "genspark":
                debug_state_path = _write_stage2_adapter_debug_state(
                    workspace=workspace,
                    service=service,
                    port=args.port,
                    expected_url_substring=args.expected_url_substring.strip(),
                )
                retry_trace_path = _write_stage2_adapter_retry_trace(
                    workspace=workspace,
                    trace=retry_trace,
                )
            placeholder_artifact = not (
                target_path.exists()
                and target_path.is_file()
                and target_path.stat().st_size > 0
            )
            write_stage2_attach_evidence(
                workspace=workspace,
                service=service,
                port=args.port,
                result=result,
                probe_debug_only=True,
                recovery_attempted=False,
                placeholder_artifact=placeholder_artifact,
                ref_images_requested=ref_images_requested,
                ref_images_resolved=ref_images_resolved,
                ref_images_attach_attempted=bool(ref_images_requested),
                extra_details=(
                    {
                        key: value
                        for key, value in {
                            "debug_state_path": (
                                str(debug_state_path)
                                if debug_state_path is not None
                                else ""
                            ),
                            "retry_trace_path": (
                                str(retry_trace_path)
                                if retry_trace_path is not None
                                else ""
                            ),
                        }.items()
                        if value
                    }
                    if debug_state_path is not None or retry_trace_path is not None
                    else None
                ),
            )
            return exit_codes.BROWSER_UNHEALTHY
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _write_stage2_placeholder_artifact(target_path)
        placeholder_artifact = True
    write_stage2_attach_evidence(
        workspace=workspace,
        service=service,
        port=args.port,
        result=result,
        probe_debug_only=True,
        recovery_attempted=False,
        placeholder_artifact=placeholder_artifact,
        ref_images_requested=ref_images_requested,
        ref_images_resolved=ref_images_resolved,
        ref_images_attach_attempted=bool(ref_images_requested),
        ref_upload_error_code=ref_upload_error_code,
        extra_details=canva_extra_details if service == "canva" else None,
    )
    return exit_codes.SUCCESS


def _attach_stage2_ref_images(
    *, port: int, expected_url_substring: str, file_paths: list[str]
) -> None:
    if not file_paths:
        return
    if expected_url_substring == expected_url_substring_for_service("genspark"):
        _attach_genspark_ref_images_via_filechooser(port=port, file_paths=file_paths)
        return
    if expected_url_substring == expected_url_substring_for_service("seaart"):
        _attach_seaart_ref_images_via_playwright(port=port, file_paths=file_paths)
        return
    if expected_url_substring == expected_url_substring_for_service("canva"):
        _attach_canva_ref_images_via_playwright(port=port, file_paths=file_paths)
        return
    if expected_url_substring == expected_url_substring_for_service("geminigen"):
        _attach_geminigen_ref_images_via_playwright(port=port, file_paths=file_paths)
        return
    target = _select_page_target(port, expected_url_substring)
    eval_result = _cdp_command(
        target["webSocketDebuggerUrl"],
        method="Runtime.evaluate",
        params={
            "expression": "(() => document.querySelector('input[type=file]'))()",
            "returnByValue": False,
        },
    )
    remote_object = cast(
        dict[str, object],
        cast(dict[str, object], eval_result.get("result", {})).get("result", {}),
    )
    object_id = str(remote_object.get("objectId", "")).strip()
    if not object_id:
        raise RuntimeError("NO_FILE_INPUT")
    node_result = _cdp_command(
        target["webSocketDebuggerUrl"],
        method="DOM.requestNode",
        params={"objectId": object_id},
    )
    node_result_payload = cast(dict[str, object], node_result.get("result", {}))
    raw_node_id = node_result_payload.get("nodeId", 0)
    try:
        node_id = int(str(raw_node_id))
    except ValueError:
        node_id = 0
    if node_id <= 0:
        raise RuntimeError("NO_FILE_NODE")
    _cdp_command(
        target["webSocketDebuggerUrl"],
        method="DOM.setFileInputFiles",
        params={
            "nodeId": node_id,
            "files": [str(Path(path).resolve()) for path in file_paths],
        },
    )


def _attach_genspark_ref_images_via_filechooser(
    *, port: int, file_paths: list[str]
) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            page = None
            for context in browser.contexts:
                for candidate in context.pages:
                    if candidate.url.startswith(
                        "https://www.genspark.ai/agents?id="
                    ) or candidate.url.startswith(
                        "https://www.genspark.ai/agents?type=image_generation_agent"
                    ):
                        page = candidate
            if page is None:
                return
            page.bring_to_front()
            try:
                with page.expect_file_chooser(timeout=5000) as chooser_info:
                    page.locator("button.upload-button").first.click()
                    page.get_by_text("로컬 파일 찾기", exact=False).first.click()
            except (PlaywrightTimeoutError, RuntimeError):
                return
            chooser = chooser_info.value
            chooser.set_files([str(Path(path).resolve()) for path in file_paths])
        finally:
            browser.close()


def _attach_seaart_ref_images_via_playwright(
    *, port: int, file_paths: list[str]
) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            page = None
            for context in browser.contexts:
                for candidate in context.pages:
                    if candidate.url.startswith("https://www.seaart.ai/"):
                        page = candidate
                        break
                if page is not None:
                    break
            if page is None:
                raise RuntimeError("NO_UPLOAD_TARGET")
            page.bring_to_front()
            locator = page.locator("input.el-upload__input")
            count = locator.count()
            resolved_files = [str(Path(path).resolve()) for path in file_paths]
            if count <= 0:
                raise RuntimeError("NO_FILE_INPUT")
            if count == 1:
                locator.nth(0).set_input_files([resolved_files[0]])
                return
            for index, file_path in enumerate(resolved_files[:count]):
                locator.nth(index).set_input_files([file_path])
        finally:
            browser.close()


def _attach_geminigen_ref_images_via_playwright(
    *, port: int, file_paths: list[str]
) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            page = None
            for context in browser.contexts:
                for candidate in context.pages:
                    if "geminigen.ai" in candidate.url:
                        page = candidate
                        break
                if page is not None:
                    break
            if page is None:
                raise RuntimeError("NO_UPLOAD_TARGET")
            page.bring_to_front()
            try:
                with page.expect_file_chooser(timeout=5000) as chooser_info:
                    page.get_by_text("Select Image", exact=False).first.click()
            except (PlaywrightTimeoutError, RuntimeError):
                raise RuntimeError("NO_FILE_INPUT")
            chooser = chooser_info.value
            chooser.set_files([str(Path(file_paths[0]).resolve())])
        finally:
            browser.close()


def _attach_canva_ref_images_via_playwright(
    *, port: int, file_paths: list[str]
) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            page = None
            for context in browser.contexts:
                for candidate in context.pages:
                    if "canva.com" in candidate.url:
                        page = candidate
                        break
                if page is not None:
                    break
            if page is None:
                raise RuntimeError("NO_UPLOAD_TARGET")
            page.bring_to_front()
            locator = page.locator("input[type=file]")
            if locator.count() <= 0:
                raise RuntimeError("NO_FILE_INPUT")
            locator.nth(0).set_input_files([str(Path(file_paths[0]).resolve())])
        finally:
            browser.close()


def _close_genspark_result_tabs(port: int) -> None:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=10
    ) as response:
        payload = json.loads(response.read().decode("utf-8", "ignore"))
    pages = [
        cast(dict[str, object], item)
        for item in cast(list[object], payload)
        if isinstance(item, dict)
    ]
    for item in pages:
        if str(item.get("type", "")) != "page":
            continue
        url = str(item.get("url", ""))
        if not url.startswith("https://www.genspark.ai/agents?id="):
            continue
        target_id = str(item.get("id", "")).strip()
        if not target_id:
            continue
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/close/{target_id}", timeout=10
            ):
                pass
        except Exception:
            continue


def _resolve_stage2_ref_image_paths(
    payload: dict[str, object],
) -> tuple[list[str], list[str]]:
    requested = [
        str(payload.get("ref_img_1", "")).strip(),
        str(payload.get("ref_img_2", "")).strip(),
    ]
    requested = [item for item in requested if item]
    asset_root = str(payload.get("asset_root", "")).strip()
    asset_root_path = Path(asset_root).resolve() if asset_root else None
    resolved: list[str] = []
    for raw_path in requested:
        if not raw_path:
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            if asset_root_path is None:
                raise RuntimeError("REF_IMAGE_UPLOAD_FAILED")
            candidate = asset_root_path / candidate
        candidate = candidate.resolve()
        if not candidate.exists() or not candidate.is_file():
            raise RuntimeError("REF_IMAGE_UPLOAD_FAILED")
        resolved.append(str(candidate))
    return requested, resolved


def _canva_page_count_script(step_name: str) -> str:
    return (
        "(() => { "
        "const body = document.body && document.body.innerText ? document.body.innerText : ''; "
        "const match = body.match(/페이지\\s*(\\d+)\\s*\\/\\s*(\\d+)/) || body.match(/Page\\s*(\\d+)\\s*\\/\\s*(\\d+)/i); "
        'const fallback = document.querySelectorAll(\'button[aria-label="페이지 삭제"], button[aria-label="Delete page"]\').length; '
        "const totalPages = match ? Number(match[2]) : fallback; "
        f"return JSON.stringify({{ok:true, step:'{step_name}', count: totalPages}}); "
        "})()"
    )


def _run_qwen3_adapter_child(args: CliArgs) -> int:
    target_path = Path(args.service_artifact_path.strip())
    if not args.service_artifact_path.strip():
        return exit_codes.CLI_USAGE
    cwd_workspace = Path.cwd()
    workspace = cwd_workspace
    if not (cwd_workspace / "qwen_prompt.json").exists():
        workspace = (
            target_path.parent.parent
            if len(target_path.parents) >= 2
            else cwd_workspace
        )
    project_root = workspace / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    prompt_path = workspace / "qwen_prompt.json"
    if not prompt_path.exists():
        return exit_codes.CLI_USAGE
    prompt_payload = json.loads(prompt_path.read_text(encoding="utf-8"))
    rows = (
        cast(list[object], prompt_payload.get("rows", []))
        if isinstance(prompt_payload.get("rows", []), list)
        else []
    )
    if not rows:
        return exit_codes.CLI_USAGE
    row = cast(dict[str, object], rows[0])
    (project_root / "voice_texts.json").write_text(
        json.dumps(row.get("voice_texts", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result_path = workspace / "qwen3_result.json"
    command = [
        r"D:/qwen3_tts_env/Scripts/python.exe",
        r"D:/YOUTUBE_AUTO/scripts/qwen3_tts_automation.py",
        "--prompt-file",
        str(prompt_path.resolve()),
        "--row-index",
        "0",
        "--result-json",
        str(result_path.resolve()),
    ]
    if args.ref_audio.strip():
        command.extend(["--ref-audio", args.ref_audio.strip()])
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    (workspace / "qwen3_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (workspace / "qwen3_stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        return exit_codes.ADAPTER_FAIL
    voice_dir = project_root / "voice"
    candidates = sorted(
        list(voice_dir.glob("#*.flac"))
        + list(voice_dir.glob("#*.wav"))
        + list(voice_dir.glob("#*.mp3"))
    )
    candidates = [path for path in candidates if path.name != "#00.txt"]
    if not candidates:
        return exit_codes.ADAPTER_FAIL
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if len(candidates) == 1:
        target_path.write_bytes(candidates[0].read_bytes())
        return exit_codes.SUCCESS
    concat_list = workspace / "qwen3_concat.txt"
    concat_list.write_text(
        "".join(
            f"file '{str(path.resolve()).replace("'", "''")}'\n" for path in candidates
        ),
        encoding="utf-8",
    )
    ffmpeg_completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list.resolve()),
            "-c:a",
            "flac",
            str(target_path.resolve()),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (workspace / "qwen3_concat_stdout.log").write_text(
        ffmpeg_completed.stdout, encoding="utf-8"
    )
    (workspace / "qwen3_concat_stderr.log").write_text(
        ffmpeg_completed.stderr, encoding="utf-8"
    )
    if ffmpeg_completed.returncode != 0 or not target_path.exists():
        return exit_codes.ADAPTER_FAIL
    return exit_codes.SUCCESS


def _run_rvc_adapter_child(args: CliArgs) -> int:
    target_path = Path(args.service_artifact_path.strip())
    if not args.service_artifact_path.strip():
        return exit_codes.CLI_USAGE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cwd_workspace = Path.cwd()
    workspace = cwd_workspace
    if not (cwd_workspace / "rvc_request.json").exists():
        workspace = (
            target_path.parent.parent
            if len(target_path.parents) >= 2
            else cwd_workspace
        )
    request_path = workspace / "rvc_request.json"
    if not request_path.exists():
        return exit_codes.CLI_USAGE
    request = json.loads(request_path.read_text(encoding="utf-8"))
    config = json.loads(
        Path(r"D:/YOUTUBE_AUTO/system/config/rvc_config.json").read_text(
            encoding="utf-8"
        )
    )
    model = cast(
        dict[str, object],
        cast(dict[str, object], config["models"])[str(config["active_model"])],
    )
    inference = cast(dict[str, object], config.get("inference", {}))
    command = [
        str(config["applio_python"]),
        str(config["applio_core"]),
        "infer",
        "--input_path",
        str(request["source_path"]),
        "--output_path",
        str(target_path.resolve()),
        "--pth_path",
        str(model["pth"]),
        "--index_path",
        str(model.get("index", "")),
        "--sid",
        str(inference.get("sid", 0)),
        "--pitch",
        str(inference.get("pitch", 0)),
        "--index_rate",
        str(inference.get("index_rate", 0.65)),
        "--volume_envelope",
        str(inference.get("volume_envelope", 0.1)),
        "--protect",
        str(inference.get("protect", 0.45)),
        "--f0_method",
        str(inference.get("f0_method", "rmvpe")),
        "--clean_audio",
        str(inference.get("clean_audio", True)),
        "--clean_strength",
        str(inference.get("clean_strength", 0.6)),
        "--split_audio",
        str(inference.get("split_audio", True)),
        "--f0_autotune",
        str(inference.get("f0_autotune", False)),
        "--f0_autotune_strength",
        str(inference.get("f0_autotune_strength", 1.0)),
        "--proposed_pitch",
        str(inference.get("proposed_pitch", False)),
        "--proposed_pitch_threshold",
        str(
            int(cast(int | float | str, inference.get("proposed_pitch_threshold", 155)))
        ),
        "--export_format",
        str(inference.get("export_format", "FLAC")),
        "--embedder_model",
        str(inference.get("embedder_model", "japanese-hubert-base")),
        "--post_process",
        str(inference.get("post_process", True)),
    ]
    completed = subprocess.run(
        command,
        cwd=str(config["applio_dir"]),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (workspace / "rvc_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (workspace / "rvc_stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0 or not target_path.exists():
        return exit_codes.ADAPTER_FAIL
    return exit_codes.SUCCESS


def _write_stage2_placeholder_artifact(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        _ = path.write_bytes(b"agent-browser-stage2-placeholder\n")
        return
    if suffix == ".png":
        _ = path.write_bytes(b"agent-browser-stage2-placeholder\n")
        return
    _ = path.write_text("agent-browser-stage2-placeholder\n", encoding="utf-8")


def _write_probe_result(probe_root: Path, payload: dict[str, object]) -> Path:
    probe_root.mkdir(parents=True, exist_ok=True)
    output_file = probe_root / "probe_result.json"
    payload_with_contract = {
        "schema_version": "1.0",
        "runtime": "runtime_v2",
        "checked_at": round(time(), 3),
        **_json_safe_mapping(payload),
    }
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=probe_root,
        prefix="probe_result.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload_with_contract, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(output_file)
    return output_file


def _json_safe_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        raw = cast(dict[object, object], value)
        return {str(key): _json_safe_value(item) for key, item in raw.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    return value


def _json_safe_mapping(payload: dict[str, object]) -> dict[str, object]:
    return {str(key): _json_safe_value(value) for key, value in payload.items()}


def seed_mock_chain_probe(inbox_root: Path) -> Path:
    qwen_root = inbox_root / "qwen3_tts"
    seed_asset_root = inbox_root.parent / "seed_inputs"
    qwen_root.mkdir(parents=True, exist_ok=True)
    seed_asset_root.mkdir(parents=True, exist_ok=True)
    image_path = seed_asset_root / "mock-chain.png"
    contract_path = qwen_root / "mock-chain.job.json"
    _ = _write_text_file(image_path, "mock image placeholder\n")
    payload = build_explicit_job_contract(
        job_id="mock-chain-qwen3",
        workload="qwen3_tts",
        checkpoint_key="mock_chain:probe:mock-chain-qwen3",
        payload={
            "script_text": "runtime_v2 mock chain seed",
            "image_path": str(image_path.resolve()),
            "mock_chain": True,
        },
        chain_step=0,
    )
    _ = _write_text_file(
        contract_path, json.dumps(payload, ensure_ascii=True, indent=2)
    )
    _backdate_seed_file(image_path)
    _backdate_seed_file(contract_path)
    return contract_path


def _write_text_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(content)
        temp_path = Path(handle.name)
    _ = temp_path.replace(path)
    return path


def _backdate_seed_file(path: Path, age_sec: int = 5) -> None:
    target_ts = max(0.0, time() - float(age_sec))
    os.utime(path, (target_ts, target_ts))


def _write_stage2_adapter_debug_state(
    *, workspace: Path, service: str, port: int, expected_url_substring: str
) -> Path:
    debug_state_path = workspace / "adapter_debug_state.json"
    payload: dict[str, object]
    try:
        payload = collect_browser_debug_state(
            port=port,
            expected_url_substring=expected_url_substring,
            service=service,
        )
    except Exception as exc:
        payload = {
            "service": service,
            "port": port,
            "expected_url_substring": expected_url_substring,
            "snapshot_error": str(exc),
        }
    _ = _write_text_file(
        debug_state_path,
        json.dumps(_json_safe_mapping(payload), ensure_ascii=True, indent=2),
    )
    return debug_state_path


def _trim_retry_text(raw: str, *, limit: int = 800) -> str:
    text = raw.strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _append_retry_trace(
    trace: list[dict[str, object]],
    *,
    phase: str,
    attempt: int,
    result: subprocess.CompletedProcess[str],
) -> None:
    trace.append(
        {
            "phase": phase,
            "attempt": attempt,
            "returncode": int(getattr(result, "returncode", 0) or 0),
            "stdout": _trim_retry_text(str(getattr(result, "stdout", "") or "")),
            "stderr": _trim_retry_text(str(getattr(result, "stderr", "") or "")),
        }
    )


def _write_stage2_adapter_retry_trace(
    *, workspace: Path, trace: list[dict[str, object]]
) -> Path:
    retry_trace_path = workspace / "adapter_retry_trace.json"
    payload: dict[str, object] = {"entries": trace[-40:]}
    _ = _write_text_file(
        retry_trace_path,
        json.dumps(_json_safe_mapping(payload), ensure_ascii=True, indent=2),
    )
    return retry_trace_path


def _resolve_agent_browser_command(command: list[str]) -> list[str]:
    if not command or command[0] != "agent-browser":
        return command
    resolved = shutil.which("agent-browser")
    if resolved:
        return [resolved, *command[1:]]
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        npm_root = Path(appdata) / "npm"
        candidates = [
            npm_root / "agent-browser.cmd",
            npm_root
            / "node_modules"
            / "agent-browser"
            / "bin"
            / "agent-browser-win32-x64.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return [str(candidate), *command[1:]]
    return command


def _run_agent_browser_eval(
    port: int, script: str, *, timeout: int = 5
) -> subprocess.CompletedProcess[str]:
    command = ["agent-browser", "--cdp", str(port), "eval", script]
    resolved_command = _resolve_agent_browser_command(command)
    return subprocess.run(
        resolved_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())

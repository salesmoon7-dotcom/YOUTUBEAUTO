from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import time
from typing import cast
from uuid import uuid4

from runtime_v2 import exit_codes
from runtime_v2.bootstrap import ensure_runtime_bootstrap
from runtime_v2.browser.manager import BrowserManager, open_browser_for_login
from runtime_v2.browser.supervisor import BrowserSupervisor
from runtime_v2.config import (
    RuntimeConfig,
    WorkloadName,
    browser_session_root,
    probe_runtime_root,
    runtime_state_root,
)
from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.control_plane import run_control_loop_once
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
from runtime_v2.manager import seed_excel_row
from runtime_v2.n8n_adapter import (
    build_n8n_webhook_response,
    post_callback,
    write_mock_callback,
)
from runtime_v2.preflight import write_preflight_report
from runtime_v2.stage2.canva_worker import run_canva_job
from runtime_v2.stage2.geminigen_worker import run_geminigen_job
from runtime_v2.stage2.agent_browser_adapter import (
    stage2_attach_verify_succeeded,
    write_stage2_attach_evidence,
)
from runtime_v2.agent_browser.cdp_capture import write_functional_evidence_bundle
from runtime_v2.stage2.genspark_worker import run_genspark_job
from runtime_v2.stage2.json_builders import build_stage2_jobs
from runtime_v2.stage2.seaart_worker import run_seaart_job
from runtime_v2.supervisor import run_once, run_selftest
from runtime_v2.workers.agent_browser_worker import run_agent_browser_verify_job


class CliArgs(argparse.Namespace):
    owner: str
    once: bool
    control_once: bool
    control_once_detached: bool
    control_once_probe_child: bool
    excel_once: bool
    excel_path: str
    sheet_name: str
    row_index: int
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
    callback_url: str
    callback_mock_out: str
    gui_status_out: str
    probe_root: str
    seed_mock_chain: bool
    selftest_force_browser_fail: bool
    selftest_force_gpt_fail: bool
    open_browser_login: str
    readiness_check: bool
    runtime_root: str
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
        self.excel_path = ""
        self.sheet_name = "Sheet1"
        self.row_index = 0
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
        self.callback_url = ""
        self.callback_mock_out = ""
        self.gui_status_out = "system/runtime_v2/health/gui_status.json"
        self.probe_root = ""
        self.seed_mock_chain = False
        self.selftest_force_browser_fail = False
        self.selftest_force_gpt_fail = False
        self.open_browser_login = ""
        self.readiness_check = False
        self.runtime_root = ""
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
    _ = parser.add_argument("--excel-path", default="")
    _ = parser.add_argument("--sheet-name", default="Sheet1")
    _ = parser.add_argument("--row-index", type=int, default=0)
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
    _ = parser.add_argument("--callback-url", default="")
    _ = parser.add_argument("--callback-mock-out", default="")
    _ = parser.add_argument("--gui-status-out", default="")
    _ = parser.add_argument("--probe-root", default="")
    _ = parser.add_argument("--seed-mock-chain", action="store_true")
    _ = parser.add_argument("--selftest-force-browser-fail", action="store_true")
    _ = parser.add_argument("--selftest-force-gpt-fail", action="store_true")
    _ = parser.add_argument("--open-browser-login", default="")
    _ = parser.add_argument("--readiness-check", action="store_true")
    _ = parser.add_argument("--runtime-root", default="")
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
            bool(args.open_browser_login.strip()),
            args.readiness_check,
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
    elif args.control_once or args.control_once_probe_child or args.excel_once:
        mode = "control_once"
    else:
        mode = "once"
    run_id = str(uuid4())
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
    ensure_runtime_bootstrap(config, workload="qwen3_tts", run_id=run_id, mode=mode)
    seed_result: dict[str, object] | None = None
    if args.excel_once:
        seed_result = seed_excel_row(
            config=config,
            run_id=run_id,
            excel_path=args.excel_path,
            sheet_name=args.sheet_name,
            row_index=args.row_index,
        )
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

    if not args.control_once:
        gui_status_input = dict(result)
        gui_status_input.update(summary)
        gui_status_input["debug_log"] = str(debug_log)
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
        if str(last_result.get("status", "")) == "failed":
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
    if args.runtime_root.strip():
        command.extend(["--runtime-root", args.runtime_root.strip()])

    creationflags = 0
    creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    creationflags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
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


def _stage2_runner_for_service(service: str):
    mapping = {
        "genspark": run_genspark_job,
        "seaart": run_seaart_job,
        "geminigen": run_geminigen_job,
        "canva": run_canva_job,
    }
    return mapping[service]


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
    asset_root = probe_root / "stage2_row1_assets"
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
    workspace = (
        target_path.parent.parent if len(target_path.parents) >= 2 else Path.cwd()
    )
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_root = workspace / "agent_browser_adapter_artifacts"
    job = JobContract(
        job_id=f"agent-browser-stage2-{service}",
        workload="agent_browser_verify",
        checkpoint_key=f"agent-browser-stage2:{service}:{args.port}",
        payload={
            "service": service,
            "port": args.port,
            "expected_url_substring": args.expected_url_substring.strip(),
            "expected_title_substring": args.expected_title_substring.strip(),
        },
    )
    result = run_agent_browser_verify_job(job, artifact_root)
    attach_ok = stage2_attach_verify_succeeded(result)
    write_stage2_attach_evidence(
        workspace=workspace,
        service=service,
        port=args.port,
        result=result,
        probe_debug_only=True,
        recovery_attempted=False,
        placeholder_artifact=attach_ok and service != "geminigen",
    )
    if not attach_ok:
        return exit_codes.BROWSER_UNHEALTHY
    if service == "geminigen":
        return exit_codes.BROWSER_UNHEALTHY
    if service in {"seaart", "genspark", "canva"}:
        try:
            _ = write_functional_evidence_bundle(
                workspace=workspace,
                service=service,
                port=args.port,
                expected_url_substring=args.expected_url_substring.strip(),
                service_artifact_path=target_path,
            )
        except Exception:
            return exit_codes.BROWSER_UNHEALTHY
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _write_stage2_placeholder_artifact(target_path)
    return exit_codes.SUCCESS


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
        "--folder",
        str(project_root.resolve()),
        "--result-json",
        str(result_path.resolve()),
    ]
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
    target_path.write_bytes(candidates[0].read_bytes())
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


if __name__ == "__main__":
    raise SystemExit(main())

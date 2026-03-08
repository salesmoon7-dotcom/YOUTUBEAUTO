from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from time import time
from typing import cast
from uuid import uuid4

from runtime_v2 import exit_codes
from runtime_v2.bootstrap import ensure_runtime_bootstrap
from runtime_v2.browser.manager import open_browser_for_login
from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import build_explicit_job_contract
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
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status
from runtime_v2.latest_run import update_latest_run_pointers
from runtime_v2.manager import seed_excel_row
from runtime_v2.n8n_adapter import (
    build_n8n_webhook_response,
    post_callback,
    write_mock_callback,
)
from runtime_v2.result_router import write_result_router
from runtime_v2.supervisor import run_once, run_selftest


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
    callback_url: str
    callback_mock_out: str
    gui_status_out: str
    probe_root: str
    seed_mock_chain: bool
    selftest_force_browser_fail: bool
    selftest_force_gpt_fail: bool
    open_browser_login: str
    readiness_check: bool

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
        self.callback_url = ""
        self.callback_mock_out = ""
        self.gui_status_out = "system/runtime_v2/health/gui_status.json"
        self.probe_root = ""
        self.seed_mock_chain = False
        self.selftest_force_browser_fail = False
        self.selftest_force_gpt_fail = False
        self.open_browser_login = ""
        self.readiness_check = False


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
    _ = parser.add_argument("--callback-url", default="")
    _ = parser.add_argument("--callback-mock-out", default="")
    _ = parser.add_argument(
        "--gui-status-out", default="system/runtime_v2/health/gui_status.json"
    )
    _ = parser.add_argument("--probe-root", default="")
    _ = parser.add_argument("--seed-mock-chain", action="store_true")
    _ = parser.add_argument("--selftest-force-browser-fail", action="store_true")
    _ = parser.add_argument("--selftest-force-gpt-fail", action="store_true")
    _ = parser.add_argument("--open-browser-login", default="")
    _ = parser.add_argument("--readiness-check", action="store_true")
    args = parser.parse_args(namespace=CliArgs())

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
            bool(args.open_browser_login.strip()),
            args.readiness_check,
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
        args.control_once or args.control_once_detached or args.control_once_probe_child
    ):
        return exit_codes.CLI_USAGE
    if args.excel_once and args.row_index < 0:
        return exit_codes.CLI_USAGE
    if args.open_browser_login.strip():
        payload = open_browser_for_login(args.open_browser_login.strip())
        print(json.dumps(payload, ensure_ascii=True))
        return exit_codes.SUCCESS
    if args.readiness_check:
        config = _build_runtime_config(args)
        readiness = load_runtime_readiness(config, completed=True)
        print(json.dumps(readiness, ensure_ascii=True))
        return exit_code_from_readiness(readiness)

    if args.selftest_detached:
        return _spawn_detached_probe(args, mode="selftest")
    if args.control_once_detached:
        return _spawn_detached_probe(args, mode="control_once")

    if args.selftest or args.selftest_probe_child:
        mode = "selftest"
    elif args.control_once or args.control_once_probe_child or args.excel_once:
        mode = "control_once"
    else:
        mode = "once"
    run_id = str(uuid4())
    config = _build_runtime_config(args)
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
    if args.seed_mock_chain and (args.control_once or args.control_once_probe_child):
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
    except BaseException as exc:
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
        _ = write_gui_status(gui_payload, config.gui_status_file)
        _ = append_debug_event(
            debug_log,
            event="gui_status_snapshot",
            payload={
                "run_id": run_id,
                "mode": mode,
                "gui_payload": gui_payload,
            },
        )
        if args.once or args.selftest or args.selftest_probe_child:
            _ = write_result_router(
                [],
                config.artifact_root,
                config.result_router_file,
                metadata={
                    "run_id": run_id,
                    "mode": mode,
                    "status": str(
                        summary.get("status", result.get("status", "failed"))
                    ),
                    "code": code,
                    "exit_code": exit_code,
                    "stage": str(summary.get("stage", "")),
                    "error_code": str(summary.get("error_code", "")),
                    "manifest_path": str(summary.get("manifest_path", "")),
                    "result_path": str(summary.get("result_path", "")),
                    "debug_log": str(debug_log),
                    "ts": now_ts(),
                },
            )
        update_latest_run_pointers(
            config,
            run_id=run_id,
            mode=mode,
            status=str(summary.get("status", result.get("status", "failed"))),
            code=code,
            debug_log=str(debug_log),
            write_completed=True,
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
    if args.probe_root.strip() and (
        args.selftest_probe_child
        or args.control_once_probe_child
        or args.readiness_check
    ):
        root = _probe_root_path(args.probe_root)
        return RuntimeConfig.from_root(root)
    return RuntimeConfig(
        lease_file=Path("system/runtime_v2/health/gpu_scheduler_health.json"),
        gui_status_file=Path(args.gui_status_out),
    )


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

    stdout_path = probe_root / "logs" / "selftest_stdout.log"
    stderr_path = probe_root / "logs" / "selftest_stderr.log"
    child_flag = (
        "--selftest-probe-child" if mode == "selftest" else "--control-once-probe-child"
    )
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
    print(final_report(report))
    return exit_codes.SUCCESS


def _probe_root_path(raw_probe_root: str) -> Path:
    probe_root = raw_probe_root.strip()
    if probe_root:
        return Path(probe_root)
    return Path("system/runtime_v2_probe") / str(uuid4())


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

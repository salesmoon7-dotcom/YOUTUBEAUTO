from __future__ import annotations

import argparse
from uuid import uuid4

from runtime_v2 import exit_codes
from runtime_v2.contracts.json_contract import (
    emit_event,
    final_report,
    now_ts,
    validate_contract,
)
from runtime_v2.gui_adapter import build_gui_status_payload
from runtime_v2.n8n_adapter import build_n8n_webhook_response, write_mock_callback
from runtime_v2.supervisor import run_once, run_selftest


def _exit_code_from_status(code: str) -> int:
    mapping = {
        "OK": exit_codes.SUCCESS,
        "GPU_LEASE_BUSY": exit_codes.LEASE_BUSY,
        "BROWSER_UNHEALTHY": exit_codes.BROWSER_UNHEALTHY,
        "GPT_FLOOR_FAIL": exit_codes.GPT_FLOOR_FAIL,
        "SELFTEST_FAIL": exit_codes.SELFTEST_FAIL,
    }
    return mapping.get(code, exit_codes.CLI_USAGE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default="runtime_v2")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--callback-url", default="")
    parser.add_argument("--callback-mock-out", default="")
    args = parser.parse_args()

    if args.once and args.selftest:
        return exit_codes.CLI_USAGE

    mode = "selftest" if args.selftest else "once"
    run_id = str(uuid4())
    start_event = {
        "run_id": run_id,
        "event": "run_started",
        "ts": now_ts(),
        "mode": mode,
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

    result = (
        run_selftest(owner=args.owner) if args.selftest else run_once(owner=args.owner)
    )
    code = str(result.get("code", "CLI_USAGE"))
    exit_code = _exit_code_from_status(code)

    gui_payload = build_gui_status_payload(
        result, run_id=run_id, mode=mode, stage="finished", exit_code=exit_code
    )
    print(
        emit_event(
            {
                "run_id": run_id,
                "event": "gui_status",
                "ts": now_ts(),
                "payload": gui_payload,
            }
        )
    )

    if args.callback_url:
        callback_payload = build_n8n_webhook_response(
            result,
            callback_url=args.callback_url,
            run_id=run_id,
            mode=mode,
            exit_code=exit_code,
        )
        if args.callback_mock_out:
            try:
                write_mock_callback(callback_payload, args.callback_mock_out)
            except OSError:
                exit_code = exit_codes.CALLBACK_FAIL

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
    print(final_report(report))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

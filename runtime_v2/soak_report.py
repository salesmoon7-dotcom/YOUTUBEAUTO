from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.config import RuntimeConfig
from runtime_v2.evidence import load_runtime_readiness


def append_soak_event(
    config: RuntimeConfig,
    *,
    run_id: str,
    mode: str,
    status: str,
    code: str,
    exit_code: int,
    debug_log: str,
    summary: dict[str, object],
) -> Path:
    event = {
        "ts": round(time(), 3),
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "code": code,
        "exit_code": exit_code,
        "debug_log": debug_log,
        "result_path": str(config.result_router_file),
        "gui_status_path": str(config.gui_status_file),
        "browser_health_path": str(config.browser_health_file),
        "gpu_health_path": str(config.lease_file),
        "gpt_status_path": str(config.gpt_status_file),
        "control_plane_events_path": str(config.control_plane_events_file),
        "manifest_path": str(summary.get("manifest_path", "")),
        "final_artifact_path": str(summary.get("final_artifact_path", "")),
        "summary": summary,
    }
    config.soak_events_file.parent.mkdir(parents=True, exist_ok=True)
    with config.soak_events_file.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(event, ensure_ascii=True) + "\n")
    return config.soak_events_file


def load_soak_events(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            raw_payload = cast(object, json.loads(line))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw_payload, dict):
            continue
        typed = cast(dict[object, object], raw_payload)
        events.append({str(key): value for key, value in typed.items()})
    return events


def summarize_soak_events(events: list[dict[str, object]]) -> dict[str, object]:
    observations = len(events)
    if observations == 0:
        return {
            "observation_count": 0,
            "browser_availability_percent": 0.0,
            "gpu_duplicate_count": 0,
            "gpt_floor_breach_count": 0,
            "restart_count": 0,
            "failure_count": 0,
            "latest_failure": {},
            "verdict": "NO_DATA",
        }
    browser_healthy = 0
    gpu_duplicate_count = 0
    gpt_floor_breach_count = 0
    restart_count = 0
    failure_count = 0
    latest_failure: dict[str, object] = {}
    for event in events:
        code = str(event.get("code", ""))
        summary = (
            cast(dict[str, object], event.get("summary", {}))
            if isinstance(event.get("summary", {}), dict)
            else {}
        )
        if code in {"OK", "NO_WORK", "SEEDED_JOB", "CONTROL_BUSY"}:
            browser_healthy += 1
        if code == "GPU_LEASE_BUSY":
            gpu_duplicate_count += 1
        if code == "GPT_FLOOR_FAIL":
            gpt_floor_breach_count += 1
        if code in {
            "BROWSER_RESTART_EXHAUSTED",
            "BROWSER_UNHEALTHY",
            "BROWSER_BLOCKED",
        }:
            restart_count += 1
        if str(event.get("status", "")) == "failed":
            failure_count += 1
            latest_failure = {
                "run_id": str(event.get("run_id", "")),
                "code": code,
                "debug_log": str(event.get("debug_log", "")),
                "result_path": str(event.get("result_path", "")),
                "manifest_path": str(event.get("manifest_path", "")),
                "final_artifact_path": str(event.get("final_artifact_path", "")),
            }
        if bool(summary.get("warning_worker_error_code_mismatch", False)):
            latest_failure = latest_failure or {
                "run_id": str(event.get("run_id", "")),
                "code": code,
            }
    availability = round((browser_healthy / observations) * 100.0, 3)
    verdict = "PASS"
    if availability < 99.5 or gpu_duplicate_count > 0 or gpt_floor_breach_count > 0:
        verdict = "FAIL"
    return {
        "observation_count": observations,
        "browser_availability_percent": availability,
        "gpu_duplicate_count": gpu_duplicate_count,
        "gpt_floor_breach_count": gpt_floor_breach_count,
        "restart_count": restart_count,
        "failure_count": failure_count,
        "latest_failure": latest_failure,
        "verdict": verdict,
    }


def write_soak_report(config: RuntimeConfig) -> Path:
    events = load_soak_events(config.soak_events_file)
    summary = summarize_soak_events(events)
    latest_failure = cast(dict[str, object], summary.get("latest_failure", {}))
    lines = [
        "# Soak 24h Report",
        "",
        f"- Observation Count: {summary['observation_count']}",
        f"- Browser Availability: {summary['browser_availability_percent']}%",
        f"- GPU Duplicate Run: {summary['gpu_duplicate_count']}",
        f"- GPT Floor Breach Count: {summary['gpt_floor_breach_count']}",
        f"- Recovery Count: {summary['restart_count']}",
        f"- Failure Count: {summary['failure_count']}",
        f"- Verdict: {summary['verdict']}",
        "",
        "## Latest Failure",
        "",
        f"- run_id: {latest_failure.get('run_id', '')}",
        f"- code: {latest_failure.get('code', '')}",
        f"- debug_log: {latest_failure.get('debug_log', '')}",
        f"- result_path: {latest_failure.get('result_path', '')}",
        f"- manifest_path: {latest_failure.get('manifest_path', '')}",
        f"- final_artifact_path: {latest_failure.get('final_artifact_path', '')}",
    ]
    config.soak_report_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=config.soak_report_file.parent,
        prefix=f"{config.soak_report_file.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write("\n".join(lines) + "\n")
        temp_path = Path(handle.name)
    _ = temp_path.replace(config.soak_report_file)
    return config.soak_report_file


def build_soak_snapshot(config: RuntimeConfig) -> dict[str, object]:
    readiness = load_runtime_readiness(config, completed=True)
    return {
        "ready": bool(readiness.get("ready", False)),
        "code": str(readiness.get("code", "CLI_USAGE")),
        "trace_paths": cast(dict[str, object], readiness.get("trace_paths", {}))
        if isinstance(readiness.get("trace_paths", {}), dict)
        else {},
        "blockers": cast(list[object], readiness.get("blockers", []))
        if isinstance(readiness.get("blockers", []), list)
        else [],
    }

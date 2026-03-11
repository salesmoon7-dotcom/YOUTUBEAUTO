from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping

from runtime_v2.config import RuntimeConfig
from runtime_v2.browser.manager import default_browser_sessions_by_service


_DEFAULT_TARGETS: dict[str, dict[str, str]] = {
    "genspark": {
        "expected_url_substring": "genspark.ai",
        "expected_title_substring": "Genspark",
    },
    "seaart": {
        "expected_url_substring": "seaart.ai",
        "expected_title_substring": "SeaArt",
    },
    "geminigen": {
        "expected_url_substring": "geminigen.ai",
        "expected_title_substring": "Gemini",
    },
    "canva": {
        "expected_url_substring": "canva.com",
        "expected_title_substring": "Canva",
    },
}
REPO_ROOT = Path(__file__).resolve().parents[2]


def build_stage2_agent_browser_adapter_command(
    *,
    service: str,
    service_artifact_path: str,
    port: int | None = None,
    expected_url_substring: str = "",
    expected_title_substring: str = "",
) -> list[str]:
    target = _DEFAULT_TARGETS.get(service, {})
    resolved_port = port if port is not None else _default_port_for_service(service)
    resolved_url = expected_url_substring.strip() or str(
        target.get("expected_url_substring", "")
    )
    resolved_title = expected_title_substring.strip() or str(
        target.get("expected_title_substring", "")
    )
    command = [
        sys.executable,
        "-m",
        "runtime_v2.cli",
        "--agent-browser-stage2-adapter-child",
        "--service",
        service,
        "--port",
        str(resolved_port),
        "--service-artifact-path",
        str(Path(service_artifact_path)),
        "--runtime-root",
        str(_default_runtime_root()),
    ]
    if resolved_url:
        command.extend(["--expected-url-substring", resolved_url])
    if resolved_title:
        command.extend(["--expected-title-substring", resolved_title])
    return command


def canonical_stage2_adapter_env() -> dict[str, str]:
    repo_root = str(REPO_ROOT.resolve())
    current = os.environ.get("PYTHONPATH", "").strip()
    pythonpath = repo_root if not current else f"{repo_root}{os.pathsep}{current}"
    return {"PYTHONPATH": pythonpath}


def _default_port_for_service(service: str) -> int:
    sessions = default_browser_sessions_by_service()
    session = sessions.get(service)
    if session is None:
        raise ValueError(f"unknown_agent_browser_service:{service}")
    return session.port


def attach_evidence_path(workspace: Path) -> Path:
    return workspace / "attach_evidence.json"


def stage2_attach_verify_succeeded(result: Mapping[str, object]) -> bool:
    return str(result.get("status", "")) == "ok"


def write_stage2_attach_evidence(
    *,
    workspace: Path,
    service: str,
    port: int,
    result: Mapping[str, object],
    probe_debug_only: bool,
    recovery_attempted: bool,
    placeholder_artifact: bool,
) -> Path:
    details_raw = result.get("details", {})
    details = details_raw if isinstance(details_raw, dict) else {}
    payload = {
        "schema_version": "1.0",
        "service": service,
        "port": port,
        "status": str(result.get("status", "unknown")),
        "stage": str(result.get("stage", "agent_browser_verify")),
        "error_code": str(result.get("error_code", "")),
        "current_url": str(details.get("current_url", "")),
        "current_title": str(details.get("current_title", "")),
        "transcript_path": str(details.get("transcript_path", "")),
        "probe_debug_only": probe_debug_only,
        "recovery_attempted": recovery_attempted,
        "placeholder_artifact": placeholder_artifact,
    }
    evidence_path = attach_evidence_path(workspace)
    _ = evidence_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return evidence_path


def _default_runtime_root() -> Path:
    config = RuntimeConfig()
    return config.result_router_file.parent.parent.resolve()

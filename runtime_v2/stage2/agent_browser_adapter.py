from __future__ import annotations

import sys
from pathlib import Path

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


def _default_port_for_service(service: str) -> int:
    sessions = default_browser_sessions_by_service()
    session = sessions.get(service)
    if session is None:
        raise ValueError(f"unknown_agent_browser_service:{service}")
    return session.port


def attach_evidence_path(workspace: Path) -> Path:
    return workspace / "attach_evidence.json"


def _default_runtime_root() -> Path:
    config = RuntimeConfig()
    return config.result_router_file.parent.parent.resolve()

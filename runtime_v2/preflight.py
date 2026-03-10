from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from time import time

from runtime_v2.browser.manager import default_browser_sessions_by_service
from runtime_v2.config import RuntimeConfig


def build_preflight_report(config: RuntimeConfig) -> dict[str, object]:
    app_config_path = Path("system/runtime_v2/config/app_config.json")
    qwen_config_path = Path(r"D:/YOUTUBE_AUTO/system/config/qwen3_tts_config.json")
    rvc_config_path = Path(r"D:/YOUTUBE_AUTO/system/config/rvc_config.json")
    sessions = default_browser_sessions_by_service()
    report: dict[str, object] = {
        "schema_version": "1.0",
        "checked_at": round(time(), 3),
        "mode": "warn",
        "effective_config": {
            "runtime_root": str(config.result_router_file.parent.parent.resolve()),
            "artifact_root": str(config.artifact_root.resolve()),
            "input_root": str(config.input_root.resolve()),
            "gui_status_file": str(config.gui_status_file.resolve()),
        },
        "sources": {
            "runtime_app_config": str(app_config_path.resolve()),
            "qwen3_tts_config": str(qwen_config_path),
            "rvc_config": str(rvc_config_path),
        },
        "browser_services": {
            service: {
                "port": session.port,
                "profile_dir": session.profile_dir,
                "browser_family": session.browser_family,
            }
            for service, session in sessions.items()
        },
        "warnings": _collect_preflight_warnings(
            config=config,
            app_config_path=app_config_path,
            qwen_config_path=qwen_config_path,
            rvc_config_path=rvc_config_path,
            sessions=sessions,
        ),
    }
    return report


def write_preflight_report(config: RuntimeConfig) -> Path:
    report = build_preflight_report(config)
    output_file = config.gui_status_file.parent / "preflight_report.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_file.parent,
        prefix=f"{output_file.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(report, ensure_ascii=True, indent=2))
        temp_path = Path(handle.name)
    _ = temp_path.replace(output_file)
    return output_file


def _collect_preflight_warnings(
    *,
    config: RuntimeConfig,
    app_config_path: Path,
    qwen_config_path: Path,
    rvc_config_path: Path,
    sessions: dict[str, object],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for label, path in {
        "runtime_app_config": app_config_path,
        "qwen3_tts_config": qwen_config_path,
        "rvc_config": rvc_config_path,
    }.items():
        if not path.exists():
            warnings.append(
                {"kind": "missing_path", "source": label, "path": str(path)}
            )
    qwen_python = Path(r"D:/qwen3_tts_env/Scripts/python.exe")
    applio_python = Path(r"D:/Applio/env/python.exe")
    for label, path in {
        "qwen3_python": qwen_python,
        "rvc_python": applio_python,
    }.items():
        if not path.exists():
            warnings.append(
                {"kind": "missing_runtime", "source": label, "path": str(path)}
            )
    service_keys = {
        "genspark": "genspark_edge",
        "seaart": "seaart_chrome",
        "geminigen": "geminigen_uc",
        "canva": "canva_chrome",
    }
    for service, port_key in service_keys.items():
        session = sessions.get(service)
        if session is None:
            warnings.append({"kind": "missing_service_session", "service": service})
            continue
        profile_dir = Path(str(session.profile_dir))
        if not profile_dir.exists():
            warnings.append(
                {
                    "kind": "missing_profile_dir",
                    "service": service,
                    "path": str(profile_dir),
                }
            )
        if service == "geminigen" and port_key != "geminigen_uc":
            warnings.append(
                {
                    "kind": "service_key_mismatch",
                    "service": service,
                    "port_key": port_key,
                }
            )
    if os.environ.get("RUNTIME_V2_APP_CONFIG", "").strip():
        warnings.append({"kind": "env_override_active", "env": "RUNTIME_V2_APP_CONFIG"})
    if not config.artifact_root.exists():
        warnings.append(
            {
                "kind": "missing_path",
                "source": "artifact_root",
                "path": str(config.artifact_root),
            }
        )
    return warnings

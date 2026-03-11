from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import socket
import subprocess
from time import sleep, time
from typing import Mapping
import urllib.request

from runtime_v2.config import RuntimeConfig, browser_session_root


START_URLS: dict[str, str] = {
    "chatgpt": "https://chatgpt.com/",
    "genspark": "https://www.genspark.ai/",
    "seaart": "https://www.seaart.ai/ko/create/image?id=d4kssode878c7387fae0&model_ver_no=ef24b47a8d618127c9342fd0635aedb9",
    "geminigen": "https://geminigen.ai/app/video-gen",
    "canva": "https://www.canva.com/design/DAHAnm1uUBA/-FWB5gw_ir1U7Ls0ZHF9Ig/edit",
}

READY_URL_RULES: dict[str, tuple[str, ...]] = {
    "chatgpt": ("https://chatgpt.com/",),
    "seaart": ("https://www.seaart.ai/ko/create/image",),
    "canva": ("/design/", "/edit"),
}

LOGIN_URL_PATTERNS: dict[str, tuple[str, ...]] = {
    "chatgpt": ("auth/login", "/login", "accounts.google.com"),
    "genspark": ("login", "sign-in", "signin", "accounts.google.com"),
    "seaart": ("login", "signin", "sign-in", "accounts.google.com"),
    "geminigen": ("auth/login", "login", "signin", "sign-in", "accounts.google.com"),
    "canva": ("/login", "loginredirect", "accounts.google.com"),
}

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_APP_CONFIG = (
    WORKSPACE_ROOT / "system" / "runtime_v2" / "config" / "app_config.json"
)
LEGACY_SESSION_ROOT = (WORKSPACE_ROOT / "runtime_v2" / "sessions").resolve()


def _browser_plane_lock_file() -> Path:
    override = os.environ.get("RUNTIME_V2_BROWSER_PLANE_LOCK", "").strip()
    if override:
        return Path(override)
    return RuntimeConfig().lock_root / "browser_plane.lock"


def _browser_plane_lock_stale_sec() -> int:
    return max(1, int(RuntimeConfig().lock_mutex_stale_sec))


def _read_browser_plane_lock() -> dict[str, object]:
    lock_file = _browser_plane_lock_file()
    if not lock_file.exists():
        return {}
    try:
        raw_payload = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_payload, dict):
        return {}
    return {str(key): raw_payload[key] for key in raw_payload}


def _write_browser_plane_lock(
    payload: Mapping[str, object], *, replace: bool
) -> dict[str, object]:
    lock_file = _browser_plane_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if replace else "x"
    with lock_file.open(mode, encoding="utf-8") as handle:
        _ = handle.write(json.dumps(dict(payload), ensure_ascii=True))
    return dict(payload)


def _browser_plane_payload(run_id: str = "") -> dict[str, object]:
    now = round(time(), 3)
    return {
        "pid": os.getpid(),
        "acquired_at": now,
        "last_heartbeat_at": now,
        "run_id": run_id or "runtime_v2-browser-plane",
    }


def _browser_plane_metadata_valid(payload: dict[str, object]) -> bool:
    if _to_int(payload.get("pid", 0)) <= 0:
        return False
    if _to_float(payload.get("acquired_at", -1.0), -1.0) < 0.0:
        return False
    if _to_float(payload.get("last_heartbeat_at", -1.0), -1.0) < 0.0:
        return False
    return True


def inspect_browser_plane_owner() -> dict[str, object]:
    lock_file = _browser_plane_lock_file()
    payload = _read_browser_plane_lock()
    if not payload:
        return {
            "lock_state": "free",
            "owned": False,
            "metadata_valid": True,
            "pid_alive": False,
            "lock_age_sec": 0.0,
            "lock_file": str(lock_file),
        }
    metadata_valid = _browser_plane_metadata_valid(payload)
    owner_pid = _to_int(payload.get("pid", 0))
    pid_alive = _pid_is_running(owner_pid) if metadata_valid else False
    heartbeat_at = _to_float(payload.get("last_heartbeat_at", 0.0), 0.0)
    lock_age_sec = max(0.0, round(time() - heartbeat_at, 3))
    if metadata_valid and owner_pid == os.getpid():
        lock_state = "owned"
    elif not metadata_valid:
        lock_state = "unknown"
    elif not pid_alive:
        lock_state = "stale"
    else:
        lock_state = "busy"
    return {
        **payload,
        "lock_state": lock_state,
        "owned": lock_state == "owned",
        "metadata_valid": metadata_valid,
        "pid_alive": pid_alive,
        "lock_age_sec": lock_age_sec,
        "lock_file": str(lock_file),
    }


def ensure_browser_plane_ownership(run_id: str = "") -> dict[str, object]:
    lock_file = _browser_plane_lock_file()
    payload = _browser_plane_payload(run_id)
    snapshot = inspect_browser_plane_owner()
    lock_state = str(snapshot.get("lock_state", "free"))
    if lock_state == "free":
        try:
            _ = _write_browser_plane_lock(payload, replace=False)
        except FileExistsError:
            snapshot = inspect_browser_plane_owner()
            return {
                **snapshot,
                "owned": bool(snapshot.get("owned", False)),
                "action_result": "ownership_busy",
            }
        return {
            **payload,
            "lock_state": "owned",
            "owned": True,
            "metadata_valid": True,
            "pid_alive": True,
            "lock_age_sec": 0.0,
            "lock_file": str(lock_file),
            "action_result": "ownership_acquired",
        }
    if lock_state == "owned":
        updated = dict(snapshot)
        updated["last_heartbeat_at"] = payload["last_heartbeat_at"]
        _ = _write_browser_plane_lock(updated, replace=True)
        return {**updated, "owned": True, "action_result": "ownership_heartbeat"}
    if lock_state == "stale":
        takeover_payload = dict(payload)
        _ = _write_browser_plane_lock(takeover_payload, replace=True)
        return {
            **takeover_payload,
            "lock_state": "owned",
            "owned": True,
            "metadata_valid": True,
            "pid_alive": True,
            "lock_age_sec": 0.0,
            "lock_file": str(lock_file),
            "action_result": "ownership_stale_takeover",
        }
    action_result = "ownership_unknown" if lock_state == "unknown" else "ownership_busy"
    return {**snapshot, "owned": False, "action_result": action_result}


def release_browser_plane_ownership() -> None:
    snapshot = inspect_browser_plane_owner()
    if not bool(snapshot.get("owned", False)):
        return
    lock_file = _browser_plane_lock_file()
    try:
        if lock_file.exists():
            lock_file.unlink()
    except OSError:
        return


@dataclass(slots=True)
class BrowserSession:
    service: str
    group: str
    session_id: str
    port: int
    profile_dir: str
    status: str
    browser_family: str = "chrome"
    started_at: float = field(default_factory=time)
    last_seen_at: float = field(default_factory=time)
    restart_count: int = 0
    consecutive_failures: int = 0
    last_restart_at: float | None = None
    restart_history: list[float] = field(default_factory=list)
    lock_state: str = "free"
    lock_recovered: bool = False
    lock_pid_alive: bool = False
    lock_port_open: bool = False
    lock_metadata_valid: bool = True
    lock_age_sec: float = 0.0
    last_recovery_action: str = ""
    blocked_reason: str = ""

    def to_dict(self, healthy: bool) -> dict[str, object]:
        return {
            "service": self.service,
            "group": self.group,
            "session_id": self.session_id,
            "port": self.port,
            "profile_dir": self.profile_dir,
            "status": self.status,
            "browser_family": self.browser_family,
            "healthy": healthy,
            "started_at": self.started_at,
            "last_seen_at": self.last_seen_at,
            "restart_count": self.restart_count,
            "consecutive_failures": self.consecutive_failures,
            "last_restart_at": self.last_restart_at,
            "restart_history": list(self.restart_history),
            "lock_state": self.lock_state,
            "lock_recovered": self.lock_recovered,
            "lock_pid_alive": self.lock_pid_alive,
            "lock_port_open": self.lock_port_open,
            "lock_metadata_valid": self.lock_metadata_valid,
            "lock_age_sec": self.lock_age_sec,
            "last_recovery_action": self.last_recovery_action,
            "blocked_reason": self.blocked_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "BrowserSession":
        started_at = payload.get("started_at", time())
        last_seen_at = payload.get("last_seen_at", time())
        last_restart_at = payload.get("last_restart_at")
        restart_history_raw = payload.get("restart_history", [])
        restart_history = (
            [
                float(item)
                for item in restart_history_raw
                if isinstance(item, (int, float, str))
            ]
            if isinstance(restart_history_raw, list)
            else []
        )
        profile_dir = payload.get("profile_dir", "")
        resolved_profile_dir = (
            Path(str(profile_dir)).resolve() if str(profile_dir).strip() else Path()
        )
        return cls(
            service=str(payload.get("service", "unknown")),
            group=str(payload.get("group", "browser_pool")),
            session_id=str(payload.get("session_id", "primary")),
            port=_to_int(payload.get("port", 0)),
            profile_dir=""
            if not str(profile_dir).strip()
            else str(resolved_profile_dir),
            status=str(payload.get("status", "stopped")),
            browser_family=str(
                payload.get(
                    "browser_family",
                    _browser_family_for_service(str(payload.get("service", "unknown"))),
                )
            ),
            started_at=float(
                started_at if isinstance(started_at, (int, float, str)) else time()
            ),
            last_seen_at=float(
                last_seen_at if isinstance(last_seen_at, (int, float, str)) else time()
            ),
            restart_count=_to_int(payload.get("restart_count", 0)),
            consecutive_failures=_to_int(payload.get("consecutive_failures", 0)),
            last_restart_at=(
                float(last_restart_at)
                if isinstance(last_restart_at, (int, float, str))
                else None
            ),
            restart_history=restart_history,
            lock_state=str(payload.get("lock_state", "free")),
            lock_recovered=bool(payload.get("lock_recovered", False)),
            lock_pid_alive=bool(payload.get("lock_pid_alive", False)),
            lock_port_open=bool(payload.get("lock_port_open", False)),
            lock_metadata_valid=bool(payload.get("lock_metadata_valid", True)),
            lock_age_sec=_to_float(payload.get("lock_age_sec", 0.0), 0.0),
            last_recovery_action=str(payload.get("last_recovery_action", "")),
            blocked_reason=str(payload.get("blocked_reason", "")),
        )


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return default


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    return default


def _runtime_app_config_path() -> Path:
    override = os.environ.get("RUNTIME_V2_APP_CONFIG", "").strip()
    if override:
        return Path(override)
    return RUNTIME_APP_CONFIG


def _load_runtime_app_config() -> dict[str, object]:
    config_path = _runtime_app_config_path()
    if not config_path.exists() or not config_path.is_file():
        return {}
    try:
        raw_payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_payload, dict):
        return {}
    typed_payload = raw_payload
    return {str(key): typed_payload[key] for key in typed_payload}


def _allow_legacy_session_root() -> bool:
    override = (
        os.environ.get("RUNTIME_V2_ALLOW_LEGACY_SESSION_ROOT", "").strip().lower()
    )
    if override in {"1", "true", "yes", "on"}:
        return True
    runtime_config = _load_runtime_app_config()
    return bool(runtime_config.get("allow_legacy_session_root", False))


def _default_session_profile_dir(session_name: str) -> str:
    external_profile_dir = (browser_session_root() / session_name).resolve()
    legacy_profile_dir = (LEGACY_SESSION_ROOT / session_name).resolve()
    if external_profile_dir.exists():
        return str(external_profile_dir)
    if _allow_legacy_session_root() and legacy_profile_dir.exists():
        return str(legacy_profile_dir)
    return str(external_profile_dir)


def _browser_session_defaults() -> list[tuple[str, str, int, str]]:
    defaults = {
        "chatgpt": (
            "llm",
            9222,
            _default_session_profile_dir("chatgpt-primary"),
        ),
        "genspark": (
            "llm",
            9333,
            _default_session_profile_dir("genspark-primary"),
        ),
        "seaart": (
            "image",
            9444,
            _default_session_profile_dir("seaart-primary"),
        ),
        "geminigen": (
            "llm",
            9555,
            _default_session_profile_dir("geminigen-primary"),
        ),
        "canva": (
            "design",
            9666,
            _default_session_profile_dir("canva-primary"),
        ),
    }
    runtime_config = _load_runtime_app_config()
    ports_raw = runtime_config.get("ports", {})
    sessions_raw = runtime_config.get("sessions", {})
    ports = ports_raw if isinstance(ports_raw, dict) else {}
    session_dirs = sessions_raw if isinstance(sessions_raw, dict) else {}
    overrides = {
        "genspark": ("genspark_edge", "edge_debug"),
        "seaart": ("seaart_chrome", "seaart_chrome"),
        "geminigen": ("geminigen_uc", "geminigen_chrome_userdata"),
        "canva": ("canva_chrome", "canva_chrome"),
    }
    for service, (port_key, session_key) in overrides.items():
        group, default_port, default_profile = defaults[service]
        port = _to_int(ports.get(port_key, default_port), default_port)
        raw_profile = str(session_dirs.get(session_key, default_profile)).strip()
        profile_dir = (
            str(Path(raw_profile).resolve()) if raw_profile else default_profile
        )
        defaults[service] = (group, port, profile_dir)
    return [
        (service, group, port, profile_dir)
        for service, (group, port, profile_dir) in defaults.items()
    ]


def _browser_family_for_service(service: str) -> str:
    if service == "genspark":
        return "edge"
    if service == "geminigen":
        return "uc"
    return "chrome"


def default_browser_sessions() -> list[BrowserSession]:
    return [
        BrowserSession(
            service=service,
            group=group,
            session_id="primary",
            port=port,
            profile_dir=profile_dir,
            status="stopped",
            browser_family=_browser_family_for_service(service),
        )
        for service, group, port, profile_dir in _browser_session_defaults()
    ]


def default_browser_sessions_by_service() -> dict[str, BrowserSession]:
    return {session.service: session for session in default_browser_sessions()}


def reconcile_browser_sessions(
    loaded_sessions: list[BrowserSession],
) -> list[BrowserSession]:
    defaults = default_browser_sessions_by_service()
    loaded_by_service = {session.service: session for session in loaded_sessions}
    reconciled: list[BrowserSession] = []
    for service, default_session in defaults.items():
        loaded_session = loaded_by_service.get(service)
        if loaded_session is None:
            reconciled.append(default_session)
            continue
        reconciled.append(
            BrowserSession(
                service=default_session.service,
                group=default_session.group,
                session_id=loaded_session.session_id or default_session.session_id,
                port=default_session.port,
                profile_dir=default_session.profile_dir,
                status=loaded_session.status,
                browser_family=default_session.browser_family,
                started_at=loaded_session.started_at,
                last_seen_at=loaded_session.last_seen_at,
                restart_count=loaded_session.restart_count,
                consecutive_failures=loaded_session.consecutive_failures,
                last_restart_at=loaded_session.last_restart_at,
                restart_history=list(loaded_session.restart_history),
                lock_state=loaded_session.lock_state,
                lock_recovered=loaded_session.lock_recovered,
                lock_pid_alive=loaded_session.lock_pid_alive,
                lock_port_open=loaded_session.lock_port_open,
                lock_metadata_valid=loaded_session.lock_metadata_valid,
                lock_age_sec=loaded_session.lock_age_sec,
                last_recovery_action=loaded_session.last_recovery_action,
                blocked_reason=loaded_session.blocked_reason,
            )
        )
    return reconciled


def _profile_location_type(profile_dir: str) -> str:
    if not profile_dir.strip():
        return "unknown"
    path = Path(profile_dir).resolve()
    if path.is_relative_to(WORKSPACE_ROOT):
        return "project_subfolder"
    return "external"


def build_profile_storage_report() -> dict[str, dict[str, object]]:
    report: dict[str, dict[str, object]] = {}
    for session in default_browser_sessions():
        report[session.service] = {
            "profile_dir": session.profile_dir,
            "location_type": _profile_location_type(session.profile_dir),
            "browser": session.browser_family,
        }
    return report


def build_browser_inventory() -> dict[str, dict[str, object]]:
    storage_report = build_profile_storage_report()
    inventory: dict[str, dict[str, object]] = {}
    for session in default_browser_sessions():
        inventory[session.service] = {
            "browser": session.browser_family,
            "group": session.group,
            "session_id": session.session_id,
            "port": session.port,
            "profile": session.profile_dir,
            "location_type": storage_report[session.service]["location_type"],
        }
    return inventory


def _profile_lock_file(profile_dir: str) -> Path:
    return Path(profile_dir).resolve() / ".runtime_v2.profile.lock"


def _read_profile_lock(lock_file: Path) -> dict[str, object]:
    if not lock_file.exists():
        return {}
    try:
        raw_payload = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_payload, dict):
        return {}
    return {str(key): raw_payload[key] for key in raw_payload}


def _write_profile_lock(
    lock_file: Path, payload: Mapping[str, object]
) -> dict[str, object]:
    with lock_file.open("x", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
    return dict(payload)


def _rewrite_profile_lock(
    lock_file: Path, payload: Mapping[str, object]
) -> dict[str, object]:
    with lock_file.open("w", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
    return dict(payload)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_metadata_valid(payload: dict[str, object]) -> bool:
    required_keys = {
        "service",
        "session_id",
        "port",
        "pid",
        "profile_dir",
        "acquired_at",
    }
    if not required_keys.issubset(payload):
        return False
    if _to_int(payload.get("pid", 0)) <= 0:
        return False
    if _to_int(payload.get("port", 0)) <= 0:
        return False
    acquired_at = payload.get("acquired_at")
    return isinstance(acquired_at, (int, float, str))


def inspect_profile_lock(
    profile_dir: str,
    *,
    service: str = "",
    session_id: str = "primary",
    port: int = 0,
) -> dict[str, object]:
    lock_file = _profile_lock_file(profile_dir)
    existing_payload = _read_profile_lock(lock_file)
    if not existing_payload:
        return {
            "lock_state": "free",
            "metadata_valid": True,
            "pid_alive": False,
            "port_open": False,
            "lock_age_sec": 0.0,
            "lock_file": str(lock_file),
        }
    metadata_valid = _lock_metadata_valid(existing_payload)
    owner_pid = _to_int(existing_payload.get("pid", 0))
    owner_port = _to_int(existing_payload.get("port", port), port)
    pid_alive = _pid_is_running(owner_pid) if metadata_valid else False
    port_open = (
        _probe_local_port(owner_port) if metadata_valid and owner_port > 0 else False
    )
    acquired_at = existing_payload.get("acquired_at", 0.0)
    lock_age_sec = 0.0
    if isinstance(acquired_at, (int, float, str)):
        lock_age_sec = max(0.0, round(time() - _to_float(acquired_at, 0.0), 3))
    same_owner = (
        metadata_valid
        and str(existing_payload.get("service", "")) == service
        and str(existing_payload.get("session_id", "")) == session_id
        and owner_port == port
        and owner_pid == os.getpid()
    )
    if same_owner:
        lock_state = "owned"
    elif not metadata_valid:
        lock_state = "unknown"
    elif pid_alive or port_open:
        lock_state = "busy"
    else:
        lock_state = "stale"
    return {
        **existing_payload,
        "lock_state": lock_state,
        "metadata_valid": metadata_valid,
        "pid_alive": pid_alive,
        "port_open": port_open,
        "lock_age_sec": lock_age_sec,
        "lock_file": str(lock_file),
    }


def _apply_lock_result(session: BrowserSession, lock_result: dict[str, object]) -> None:
    session.lock_state = str(lock_result.get("lock_state", "free"))
    session.lock_recovered = bool(lock_result.get("recovered", False))
    session.lock_pid_alive = bool(lock_result.get("pid_alive", False))
    session.lock_port_open = bool(lock_result.get("port_open", False))
    session.lock_metadata_valid = bool(lock_result.get("metadata_valid", True))
    session.lock_age_sec = _to_float(lock_result.get("lock_age_sec", 0.0), 0.0)
    session.last_recovery_action = str(lock_result.get("action", ""))


def _clear_lock_result(session: BrowserSession) -> None:
    session.lock_state = "free"
    session.lock_recovered = False
    session.lock_pid_alive = False
    session.lock_port_open = False
    session.lock_metadata_valid = True
    session.lock_age_sec = 0.0
    session.last_recovery_action = ""


def acquire_profile_lock(
    profile_dir: str,
    *,
    service: str = "",
    session_id: str = "primary",
    port: int = 0,
) -> dict[str, object]:
    profile_path = Path(profile_dir).resolve()
    profile_path.mkdir(parents=True, exist_ok=True)
    lock_file = _profile_lock_file(str(profile_path))
    payload = {
        "service": service,
        "session_id": session_id,
        "port": port,
        "pid": os.getpid(),
        "profile_dir": str(profile_path),
        "acquired_at": round(time(), 3),
    }
    try:
        _ = _write_profile_lock(lock_file, payload)
        return {
            "locked": True,
            "lock_file": str(lock_file),
            "reused": False,
            "recovered": False,
            "lock_state": "owned",
            "metadata_valid": True,
            "pid_alive": True,
            "port_open": False,
            "lock_age_sec": 0.0,
            "action": "lock_acquired",
            **payload,
        }
    except FileExistsError:
        existing_payload = inspect_profile_lock(
            str(profile_path),
            service=service,
            session_id=session_id,
            port=port,
        )
        same_owner = str(existing_payload.get("lock_state", "")) == "owned"
        if same_owner:
            return {
                "locked": True,
                "lock_file": str(lock_file),
                "reused": True,
                "recovered": False,
                "action": "lock_reused",
                **existing_payload,
            }
        if str(existing_payload.get("lock_state", "")) == "stale":
            try:
                lock_file.unlink()
                _ = _write_profile_lock(lock_file, payload)
            except OSError:
                return {
                    "locked": False,
                    "lock_file": str(lock_file),
                    "reused": False,
                    "recovered": False,
                    "action": "lock_recovery_failed",
                    **existing_payload,
                }
            return {
                "locked": True,
                "lock_file": str(lock_file),
                "reused": False,
                "recovered": True,
                "lock_state": "stale",
                "metadata_valid": bool(existing_payload.get("metadata_valid", True)),
                "pid_alive": False,
                "port_open": False,
                "lock_age_sec": _to_float(
                    existing_payload.get("lock_age_sec", 0.0), 0.0
                ),
                "action": "stale_lock_recovered",
                **payload,
            }
        return {
            "locked": False,
            "lock_file": str(lock_file),
            "reused": False,
            "recovered": False,
            "action": "lock_denied",
            **existing_payload,
        }


def release_profile_lock(
    profile_dir: str, *, service: str = "", session_id: str = ""
) -> None:
    lock_file = _profile_lock_file(profile_dir)
    existing_payload = _read_profile_lock(lock_file)
    if service and str(existing_payload.get("service", "")) != service:
        return
    if session_id and str(existing_payload.get("session_id", "")) != session_id:
        return
    try:
        if lock_file.exists():
            lock_file.unlink()
    except OSError:
        return


def open_browser_for_login(
    service: str, *, manager: BrowserManager | None = None
) -> dict[str, object]:
    active_manager = manager or BrowserManager()
    session = active_manager._session_by_service(service)
    launched = _launch_debug_browser(session)
    return {
        "service": session.service,
        "browser": session.browser_family,
        "port": session.port,
        "profile_dir": session.profile_dir,
        "start_url": _start_url_for_service(service),
        "launched": launched,
    }


class BrowserManager:
    def __init__(self, sessions: list[BrowserSession] | None = None) -> None:
        self.running: bool = False
        self.sessions: list[BrowserSession] = sessions or default_browser_sessions()

    def start(self) -> None:
        self.running = True
        ownership = ensure_browser_plane_ownership()
        for session in self.sessions:
            if not bool(ownership.get("owned", False)):
                session.status = "external"
                session.consecutive_failures = 0
                continue
            session.status = "running"
            session.consecutive_failures = 0
            _ = _launch_debug_browser(session)

    def is_healthy(self) -> bool:
        return self.running and all(
            session.status == "running" for session in self.sessions
        )

    def restart(self, service: str) -> None:
        self.running = True
        session = self._session_by_service(service)
        ownership = ensure_browser_plane_ownership()
        if not bool(ownership.get("owned", False)):
            session.status = "external"
            return
        now = time()
        session.restart_count += 1
        session.started_at = now
        session.last_restart_at = now
        session.restart_history.append(now)
        session.consecutive_failures = 0
        session.status = "running"
        session.blocked_reason = ""
        _ = _launch_debug_browser(session)

    def shutdown(self) -> None:
        self.running = False
        now = time()
        for session in self.sessions:
            session.status = "stopped"
            session.last_seen_at = now
            release_profile_lock(
                session.profile_dir,
                service=session.service,
                session_id=session.session_id,
            )
        release_browser_plane_ownership()

    def mark_unhealthy(self, service: str) -> None:
        session = self._session_by_service(service)
        session.status = "unhealthy"
        session.consecutive_failures += 1

    def session_snapshots(
        self, forced_unhealthy_services: set[str] | None = None
    ) -> list[dict[str, object]]:
        now = time()
        snapshots: list[dict[str, object]] = []
        forced = forced_unhealthy_services or set()
        for session in self.sessions:
            healthy = False
            if self.running:
                healthy, next_status = _evaluate_session_health(session)
                if session.service in forced:
                    healthy = False
                    next_status = "unhealthy"
                if healthy:
                    session.status = next_status
                    session.consecutive_failures = 0
                    session.last_seen_at = now
                    session.blocked_reason = ""
                else:
                    session.status = next_status
                    if next_status != "restart_exhausted":
                        session.blocked_reason = ""
                    if next_status == "unhealthy":
                        session.consecutive_failures += 1
            snapshots.append(session.to_dict(healthy=healthy))
        return snapshots

    def _session_by_service(self, service: str) -> BrowserSession:
        for session in self.sessions:
            if session.service == service:
                return session
        raise ValueError(f"unknown browser service: {service}")


def _probe_local_port(port: int, timeout_sec: float = 0.2) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def _session_ready(session: BrowserSession) -> bool:
    profile_dir = (
        Path(session.profile_dir).resolve() if session.profile_dir.strip() else Path()
    )
    if not profile_dir.exists() or not profile_dir.is_dir():
        return False
    return (profile_dir / "session_ready.json").exists()


def _session_ready_file(session: BrowserSession) -> Path:
    profile_dir = (
        Path(session.profile_dir).resolve() if session.profile_dir.strip() else Path()
    )
    return profile_dir / "session_ready.json"


def _list_debug_tabs(session: BrowserSession) -> list[dict[str, object]]:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{session.port}/json", timeout=3
        ) as response:
            raw_payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(raw_payload, list):
        return []
    tabs: list[dict[str, object]] = []
    for raw_item in raw_payload:
        if isinstance(raw_item, dict):
            item = raw_item
            tabs.append({str(key): item[key] for key in item})
    return tabs


def _tab_matches_ready_rules(service: str, url: str) -> bool:
    normalized = url.strip().lower()
    if not normalized:
        return False
    if _tab_requires_login(service, normalized):
        return False
    if service == "canva":
        return "/design/" in normalized and "/edit" in normalized
    required_patterns = READY_URL_RULES.get(service, ())
    if not required_patterns:
        return normalized != "about:blank"
    return any(pattern in normalized for pattern in required_patterns)


def _tab_requires_login(service: str, url: str) -> bool:
    normalized = url.strip().lower()
    if not normalized:
        return False
    login_patterns = LOGIN_URL_PATTERNS.get(service, ())
    return any(pattern in normalized for pattern in login_patterns)


def _clear_session_ready_marker(session: BrowserSession) -> None:
    ready_file = _session_ready_file(session)
    try:
        if ready_file.exists():
            ready_file.unlink()
    except OSError:
        return


def _refresh_session_ready_marker(session: BrowserSession) -> bool:
    ready_file = _session_ready_file(session)
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    tabs = _list_debug_tabs(session)
    matched_url = ""
    for tab in tabs:
        raw_url = str(tab.get("url", "")).strip()
        if _tab_matches_ready_rules(session.service, raw_url):
            matched_url = raw_url
            break
    if not matched_url:
        _clear_session_ready_marker(session)
        return False
    payload = {
        "ready": True,
        "service": session.service,
        "port": session.port,
        "url": matched_url,
        "checked_at": round(time(), 3),
    }
    try:
        ready_file.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    except OSError:
        return False
    return True


def _evaluate_session_health(session: BrowserSession) -> tuple[bool, str]:
    port_healthy = _probe_local_port(session.port)
    if not port_healthy:
        _clear_session_ready_marker(session)
        if not _manager_owns_browser(session.service):
            _clear_lock_result(session)
            return False, "external"
        lock_result = inspect_profile_lock(
            session.profile_dir,
            service=session.service,
            session_id=session.session_id,
            port=session.port,
        )
        _apply_lock_result(session, lock_result)
        if session.lock_state == "stale":
            return (
                False,
                "stale_lock_recovered" if session.lock_recovered else "unhealthy",
            )
        if session.lock_state == "busy":
            return False, "busy_lock"
        if session.lock_state == "unknown":
            return False, "unknown_lock"
        return False, "unhealthy"
    _clear_lock_result(session)
    tabs = _list_debug_tabs(session)
    matched_url = ""
    saw_login_page = False
    for tab in tabs:
        raw_url = str(tab.get("url", "")).strip()
        if _tab_requires_login(session.service, raw_url):
            saw_login_page = True
            continue
        if _tab_matches_ready_rules(session.service, raw_url):
            matched_url = raw_url
            break
    if matched_url:
        _ = _refresh_session_ready_marker(session)
        return True, "running"
    _clear_session_ready_marker(session)
    if saw_login_page:
        return False, "login_required"
    if not _manager_owns_browser(session.service):
        return False, "external"
    return False, "unhealthy"


def _start_url_for_service(service: str) -> str:
    env_name = f"RUNTIME_V2_{service.upper()}_URL"
    override = os.environ.get(env_name, "").strip()
    if override:
        return override
    return START_URLS.get(service, "about:blank")


def _launch_debug_browser(session: BrowserSession) -> bool:
    if _probe_local_port(session.port):
        _clear_lock_result(session)
        return True
    executable = _resolve_browser_executable(session.service)
    if executable is None:
        session.status = "stopped"
        return False
    profile_dir = Path(session.profile_dir).resolve()
    session.profile_dir = str(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    lock_result = acquire_profile_lock(
        session.profile_dir,
        service=session.service,
        session_id=session.session_id,
        port=session.port,
    )
    _apply_lock_result(session, lock_result)
    if not bool(lock_result.get("locked", False)):
        if session.lock_state == "busy":
            session.status = "busy_lock"
        elif session.lock_state == "unknown":
            session.status = "unknown_lock"
        else:
            session.status = "unhealthy"
        return False
    command = [
        str(executable),
        f"--remote-debugging-port={session.port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        _start_url_for_service(session.service),
    ]
    creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
        getattr(subprocess, "DETACHED_PROCESS", 0)
    )
    try:
        child = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError:
        session.status = "stopped"
        release_profile_lock(
            session.profile_dir, service=session.service, session_id=session.session_id
        )
        return False
    for _ in range(20):
        sleep(0.5)
        if _probe_local_port(session.port):
            lock_file = _profile_lock_file(session.profile_dir)
            launched_pid = _to_int(getattr(child, "pid", 0))
            launch_lock_payload = {
                "service": session.service,
                "session_id": session.session_id,
                "port": session.port,
                "pid": launched_pid,
                "profile_dir": session.profile_dir,
                "acquired_at": round(time(), 3),
                "browser_pid": launched_pid,
            }
            try:
                _ = _rewrite_profile_lock(lock_file, launch_lock_payload)
            except OSError:
                session.status = "unknown_lock"
                return False
            session.status = "running"
            session.last_seen_at = time()
            session.lock_state = "owned"
            session.lock_pid_alive = True
            session.lock_port_open = True
            session.lock_metadata_valid = True
            session.lock_age_sec = 0.0
            session.last_recovery_action = "lock_transferred_to_browser_pid"
            return True
    session.status = "unhealthy"
    release_profile_lock(
        session.profile_dir, service=session.service, session_id=session.session_id
    )
    return False


def _resolve_browser_executable(service: str) -> Path | None:
    if service == "geminigen":
        env_names = [
            "RUNTIME_V2_UC_PATH",
            "UC_PATH",
            "RUNTIME_V2_CHROME_PATH",
            "CHROME_PATH",
        ]
    else:
        env_names = (
            ["RUNTIME_V2_EDGE_PATH", "EDGE_PATH"]
            if service == "genspark"
            else ["RUNTIME_V2_CHROME_PATH", "CHROME_PATH"]
        )
    for env_name in env_names:
        candidate = os.environ.get(env_name, "").strip()
        if candidate and Path(candidate).exists():
            return Path(candidate)
    if service == "genspark":
        candidates = [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ]
    else:
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _manager_owns_browser(service: str) -> bool:
    _ = service
    ownership = inspect_browser_plane_owner()
    return bool(ownership.get("owned", False))

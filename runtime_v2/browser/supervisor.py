from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from time import time
from typing import Callable
from typing import cast

from runtime_v2.browser.health import build_browser_health_payload, write_browser_health
from runtime_v2.browser.manager import (
    BrowserManager,
    ensure_browser_plane_ownership,
    inspect_browser_plane_owner,
    reconcile_browser_sessions,
)
from runtime_v2.browser.probe import summarize_browser_health
from runtime_v2.browser.registry import (
    build_browser_registry_payload,
    load_browser_registry,
    write_browser_registry,
)


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    return default


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return default


def _append_browser_event(
    record: dict[str, object], output_file: str | Path | None
) -> None:
    if output_file is None:
        return
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    _ = payload.setdefault("ts", round(time(), 3))
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _emit_browser_session_events(
    sessions: list[dict[str, object]],
    *,
    output_file: str | Path | None,
    run_id: str,
    busy_lock_escalation_sec: float | None = None,
    emit_escalations: bool = True,
) -> None:
    for session in sessions:
        recovered = bool(session.get("lock_recovered", False))
        status = "stale_lock_recovered" if recovered else str(session.get("status", ""))
        if status not in {
            "login_required",
            "busy_lock",
            "unknown_lock",
            "stale_lock_recovered",
            "restart_exhausted",
        }:
            continue
        action = "hold"
        if status == "stale_lock_recovered":
            action = "recover"
        _append_browser_event(
            {
                "event": "browser_supervisor_status",
                "run_id": run_id,
                "service": str(session.get("service", "")),
                "profile_dir": str(session.get("profile_dir", "")),
                "status": status,
                "lock_state": str(session.get("lock_state", "free")),
                "pid_alive": bool(session.get("lock_pid_alive", False)),
                "port_open": bool(session.get("lock_port_open", False)),
                "metadata_valid": bool(session.get("lock_metadata_valid", True)),
                "lock_age_sec": _to_float(session.get("lock_age_sec", 0.0), 0.0),
                "action": action,
                "action_result": "pending_restart"
                if status == "stale_lock_recovered"
                else "blocked",
                "error": "",
                "tick_id": run_id,
            },
            output_file,
        )
        lock_age_sec = _to_float(session.get("lock_age_sec", 0.0), 0.0)
        if (
            emit_escalations
            and status == "busy_lock"
            and busy_lock_escalation_sec is not None
            and lock_age_sec >= busy_lock_escalation_sec
        ):
            _append_browser_event(
                {
                    "event": "browser_supervisor_escalation",
                    "run_id": run_id,
                    "service": str(session.get("service", "")),
                    "profile_dir": str(session.get("profile_dir", "")),
                    "status": "busy_lock",
                    "lock_state": str(session.get("lock_state", "free")),
                    "pid_alive": bool(session.get("lock_pid_alive", False)),
                    "port_open": bool(session.get("lock_port_open", False)),
                    "metadata_valid": bool(session.get("lock_metadata_valid", True)),
                    "lock_age_sec": lock_age_sec,
                    "action": "escalate",
                    "action_result": "blocked",
                    "error": "",
                    "tick_id": run_id,
                },
                output_file,
            )


def _emit_browser_plane_ownership_event(
    ownership: dict[str, object], *, output_file: str | Path | None, run_id: str
) -> None:
    action_result = str(ownership.get("action_result", ""))
    if not action_result or action_result == "ownership_heartbeat":
        return
    _append_browser_event(
        {
            "event": "browser_plane_ownership",
            "run_id": run_id,
            "status": str(ownership.get("lock_state", "free")),
            "lock_state": str(ownership.get("lock_state", "free")),
            "pid_alive": bool(ownership.get("pid_alive", False)),
            "metadata_valid": bool(ownership.get("metadata_valid", True)),
            "lock_age_sec": _to_float(ownership.get("lock_age_sec", 0.0), 0.0),
            "action": "takeover"
            if action_result == "ownership_stale_takeover"
            else "hold",
            "action_result": action_result,
            "error": "",
            "tick_id": run_id,
        },
        output_file,
    )


def _prune_restart_history(
    history: list[float], *, now: float, window_sec: int
) -> list[float]:
    if window_sec <= 0:
        return list(history)
    window_start = now - float(window_sec)
    return [stamp for stamp in history if stamp >= window_start]


class BrowserSupervisor:
    def __init__(self, manager: BrowserManager) -> None:
        self.manager: BrowserManager = manager
        self._restart_inflight_lock: Lock = Lock()
        self._restart_inflight: set[str] = set()

    def _restart_guard_key(self, service: str, session_id: str) -> str:
        return f"{service}:{session_id}"

    def _begin_restart(self, service: str, session_id: str) -> bool:
        key = self._restart_guard_key(service, session_id)
        with self._restart_inflight_lock:
            if key in self._restart_inflight:
                return False
            self._restart_inflight.add(key)
        return True

    def _finish_restart(self, service: str, session_id: str) -> None:
        key = self._restart_guard_key(service, session_id)
        with self._restart_inflight_lock:
            self._restart_inflight.discard(key)

    def _restart_session(self, service: str, session_id: str) -> bool:
        if not self._begin_restart(service, session_id):
            return False
        try:
            self.manager.restart(service)
            return True
        finally:
            self._finish_restart(service, session_id)

    def ensure_healthy(
        self,
        *,
        force_unhealthy_service: str | None = None,
        recover_unhealthy: bool = True,
    ) -> dict[str, object]:
        if force_unhealthy_service:
            self.manager.mark_unhealthy(force_unhealthy_service)

        forced_services: set[str] = set()
        if force_unhealthy_service:
            forced_services.add(force_unhealthy_service)
        initial_sessions = self.manager.session_snapshots(
            forced_unhealthy_services=forced_services
        )
        initial_summary = summarize_browser_health(initial_sessions)
        unhealthy_services_value = initial_summary.get("unhealthy_services", [])
        unhealthy_services: list[str] = []
        if isinstance(unhealthy_services_value, list):
            raw_services = cast(list[object], unhealthy_services_value)
            for service_value in raw_services:
                if isinstance(service_value, str):
                    unhealthy_services.append(service_value)
                else:
                    unhealthy_services.append(repr(service_value))

        restarted_services: list[str] = []
        if recover_unhealthy:
            for service in unhealthy_services:
                session = self.manager._session_by_service(service)
                if session.status in {"unhealthy", "stopped", "stale_lock_recovered"}:
                    if self._restart_session(session.service, session.session_id):
                        restarted_services.append(service)

        final_sessions = self.manager.session_snapshots(
            forced_unhealthy_services=forced_services if not recover_unhealthy else None
        )
        final_summary = summarize_browser_health(final_sessions)
        return {
            "restarted_services": restarted_services,
            "initial_summary": initial_summary,
            "final_summary": final_summary,
            "sessions": final_sessions,
        }

    def tick(
        self,
        *,
        registry_file: str | Path,
        health_file: str | Path,
        events_file: str | Path | None = None,
        run_id: str = "",
        force_unhealthy_service: str | None = None,
        recover_unhealthy: bool = True,
        restart_threshold: int = 2,
        cooldown_sec: int = 60,
        restart_budget: int = 3,
        restart_window_sec: int = 300,
        now_fn: Callable[[], float] = time,
    ) -> dict[str, object]:
        previous_ownership = inspect_browser_plane_owner()
        loaded_sessions = load_browser_registry(registry_file)
        if loaded_sessions:
            self.manager.sessions = reconcile_browser_sessions(loaded_sessions)
            self.manager.running = True
            if all(session.status == "stopped" for session in self.manager.sessions):
                self.manager.start()
        elif not self.manager.running:
            self.manager.start()

        ownership = ensure_browser_plane_ownership(run_id=run_id)
        previous_state = str(previous_ownership.get("lock_state", "free"))
        if bool(previous_ownership.get("owned", False)) and not bool(
            ownership.get("owned", False)
        ):
            ownership = {**ownership, "action_result": "ownership_lost"}
        elif not bool(previous_ownership.get("owned", False)) and bool(
            ownership.get("owned", False)
        ):
            if previous_state == "stale":
                ownership = {**ownership, "action_result": "ownership_stale_takeover"}
            elif previous_state == "free":
                ownership = {**ownership, "action_result": "ownership_acquired"}
        _emit_browser_plane_ownership_event(
            ownership,
            output_file=events_file,
            run_id=run_id,
        )

        if force_unhealthy_service:
            self.manager.mark_unhealthy(force_unhealthy_service)

        forced_services: set[str] = set()
        if force_unhealthy_service:
            forced_services.add(force_unhealthy_service)
        initial_sessions = self.manager.session_snapshots(
            forced_unhealthy_services=forced_services
        )
        _emit_browser_session_events(
            initial_sessions,
            output_file=events_file,
            run_id=run_id,
            busy_lock_escalation_sec=float(max(cooldown_sec, 1)),
            emit_escalations=False,
        )
        initial_summary = summarize_browser_health(initial_sessions)
        restarted_services: list[str] = []
        exhausted_services: dict[str, dict[str, object]] = {}
        if recover_unhealthy:
            now = now_fn()
            for session in self.manager.sessions:
                session.restart_history = _prune_restart_history(
                    list(session.restart_history),
                    now=now,
                    window_sec=restart_window_sec,
                )
                is_unhealthy = session.status in {
                    "unhealthy",
                    "stopped",
                    "stale_lock_recovered",
                }
                cooldown_elapsed = session.last_restart_at is None or (
                    now - session.last_restart_at >= cooldown_sec
                )
                should_restart = (
                    is_unhealthy
                    and session.consecutive_failures >= restart_threshold
                    and cooldown_elapsed
                )
                if should_restart and len(session.restart_history) >= restart_budget:
                    session.status = "restart_exhausted"
                    session.blocked_reason = "restart_budget_exhausted"
                    session.last_recovery_action = "restart_budget_exhausted"
                    exhausted_services[session.service] = {
                        "restart_count_in_window": len(session.restart_history),
                        "restart_window_sec": restart_window_sec,
                        "restart_budget": restart_budget,
                        "last_status": "unhealthy",
                    }
                    _append_browser_event(
                        {
                            "event": "browser_restart_budget_exhausted",
                            "run_id": run_id,
                            "service": session.service,
                            "profile_dir": session.profile_dir,
                            "status": "restart_exhausted",
                            "lock_state": session.lock_state,
                            "pid_alive": session.lock_pid_alive,
                            "port_open": session.lock_port_open,
                            "metadata_valid": session.lock_metadata_valid,
                            "lock_age_sec": session.lock_age_sec,
                            "action": "hold",
                            "action_result": "blocked",
                            "error": "restart_budget_exhausted",
                            "tick_id": run_id,
                            "restart_count_in_window": len(session.restart_history),
                            "restart_window_sec": restart_window_sec,
                            "restart_budget": restart_budget,
                            "last_status": "unhealthy",
                        },
                        events_file,
                    )
                    continue
                if should_restart:
                    if not self._restart_session(session.service, session.session_id):
                        continue
                    restarted_services.append(session.service)
                    if session.lock_recovered:
                        _append_browser_event(
                            {
                                "event": "browser_supervisor_recovery",
                                "run_id": run_id,
                                "service": session.service,
                                "profile_dir": session.profile_dir,
                                "status": "stale_lock_recovered",
                                "lock_state": session.lock_state,
                                "pid_alive": session.lock_pid_alive,
                                "port_open": session.lock_port_open,
                                "metadata_valid": session.lock_metadata_valid,
                                "lock_age_sec": session.lock_age_sec,
                                "action": "clear_lock",
                                "action_result": "ok",
                                "error": "",
                                "tick_id": run_id,
                            },
                            events_file,
                        )
                    _append_browser_event(
                        {
                            "event": "browser_supervisor_restart",
                            "run_id": run_id,
                            "service": session.service,
                            "profile_dir": session.profile_dir,
                            "status": session.status,
                            "lock_state": session.lock_state,
                            "pid_alive": session.lock_pid_alive,
                            "port_open": session.lock_port_open,
                            "metadata_valid": session.lock_metadata_valid,
                            "lock_age_sec": session.lock_age_sec,
                            "action": "restart",
                            "action_result": "attempted",
                            "error": "",
                            "tick_id": run_id,
                        },
                        events_file,
                    )

        final_sessions = self.manager.session_snapshots(
            forced_unhealthy_services=forced_services if not recover_unhealthy else None
        )
        for session_payload in final_sessions:
            service = str(session_payload.get("service", ""))
            exhausted = exhausted_services.get(service)
            if exhausted is None:
                continue
            session_payload["healthy"] = False
            session_payload["status"] = "restart_exhausted"
            session_payload["blocked_reason"] = "restart_budget_exhausted"
            session_payload["last_recovery_action"] = "restart_budget_exhausted"
            session_payload["restart_count_in_window"] = _to_int(
                exhausted.get("restart_count_in_window", 0), 0
            )
            session_payload["restart_window_sec"] = _to_int(
                exhausted.get("restart_window_sec", 0), 0
            )
            session_payload["restart_budget"] = _to_int(
                exhausted.get("restart_budget", 0), 0
            )
        _emit_browser_session_events(
            final_sessions,
            output_file=events_file,
            run_id=run_id,
            busy_lock_escalation_sec=float(max(cooldown_sec, 1)),
        )
        final_summary = summarize_browser_health(final_sessions)
        registry_payload = build_browser_registry_payload(final_sessions, run_id=run_id)
        health_payload = build_browser_health_payload(final_sessions, run_id=run_id)
        _ = write_browser_registry(registry_payload, registry_file)
        _ = write_browser_health(health_payload, health_file)
        return {
            "restarted_services": restarted_services,
            "initial_summary": initial_summary,
            "final_summary": final_summary,
            "sessions": final_sessions,
        }

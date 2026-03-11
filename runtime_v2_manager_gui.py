from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from time import sleep, time
from tkinter import messagebox, ttk
from typing import Callable, cast
from uuid import uuid4

from runtime_v2.browser.manager import open_browser_for_login
from runtime_v2.bootstrap import ensure_runtime_bootstrap
from runtime_v2.config import GpuWorkload, RuntimeConfig
from runtime_v2.control_plane import (
    run_control_loop_once,
    seed_control_job,
)
from runtime_v2.control_plane_feeder import seed_local_jobs
from runtime_v2.contracts.job_contract import JobContract
from runtime_v2.debug_log import (
    append_debug_event,
    debug_log_path,
    exception_payload,
    summarize_runtime_result,
)
from runtime_v2.evidence import load_runtime_readiness
from runtime_v2.gpt.floor import load_gpt_status, write_gpt_status
from runtime_v2.gpu.lease import (
    Lease,
    build_gpu_health_payload,
    write_gpu_health_payload,
)
from runtime_v2.gui_adapter import build_gui_status_payload, write_gui_status
from runtime_v2.manager import seed_excel_row


BASE_DIR = Path(__file__).resolve().parent


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        raw_payload = cast(dict[object, object], payload)
        typed: dict[str, object] = {}
        for raw_key in raw_payload:
            typed[str(raw_key)] = raw_payload[raw_key]
        return typed
    return None


def _coerce_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw_payload = cast(dict[object, object], value)
    typed: dict[str, object] = {}
    for raw_key, raw_value in raw_payload.items():
        typed[str(raw_key)] = raw_value
    return typed


def _worker_error_code_mismatch_warning(
    result_payload: dict[str, object] | None,
) -> str:
    if result_payload is None:
        return ""
    metadata = _coerce_mapping(result_payload.get("metadata"))
    if metadata is None:
        return ""
    canonical_handoff = _coerce_mapping(metadata.get("canonical_handoff"))
    if canonical_handoff is None:
        return ""
    return str(canonical_handoff.get("warning_worker_error_code_mismatch", "")).strip()


def _read_json_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    raw_payload = cast(list[object], payload)
    items: list[dict[str, object]] = []
    for entry in raw_payload:
        if isinstance(entry, dict):
            raw_entry = cast(dict[object, object], entry)
            typed: dict[str, object] = {}
            for raw_key in raw_entry:
                typed[str(raw_key)] = raw_entry[raw_key]
            items.append(typed)
    return items


def _read_jsonl_tail(path: Path, limit: int = 40) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, object]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            payload = cast(object, json.loads(line))
        except json.JSONDecodeError:
            continue
        typed_payload = _coerce_mapping(payload)
        if typed_payload is not None:
            records.append(typed_payload)
    return records


def _latest_final_output_record(path: Path) -> dict[str, object] | None:
    records = _read_jsonl_tail(path, limit=200)
    for record in reversed(records):
        if str(record.get("event", "")).strip() != "job_summary":
            continue
        if bool(record.get("final_output", False)):
            return record
    return None


def _archived_contract_count(root: Path) -> int:
    if not root.exists():
        return 0
    job_like = list(root.glob("*.job.json"))
    legacy_job_like = [
        path
        for path in root.glob("*.job.*.json")
        if not path.name.endswith(".reason.json")
    ]
    return len(job_like) + len(legacy_job_like)


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _display_worker_error_code(code: str) -> str:
    normalized = code.strip()
    if normalized == "BROWSER_RESTART_EXHAUSTED":
        return "BROWSER_RESTART_EXHAUSTED(restart budget exhausted)"
    return normalized


def _runtime_config_from_text(runtime_root: str) -> RuntimeConfig:
    normalized = runtime_root.strip()
    if not normalized:
        return RuntimeConfig()
    return RuntimeConfig.from_root(Path(normalized).resolve())


def _readiness_blocker_messages(readiness: dict[str, object]) -> list[str]:
    blockers_obj = readiness.get("blockers", [])
    if not isinstance(blockers_obj, list):
        return []
    typed_blockers = cast(list[object], blockers_obj)
    messages: list[str] = []
    for raw_blocker in typed_blockers:
        if not isinstance(raw_blocker, dict):
            continue
        blocker = _coerce_mapping(cast(object, raw_blocker))
        if blocker is None:
            continue
        axis = str(blocker.get("axis", "unknown")).strip()
        code = str(blocker.get("code", "UNKNOWN")).strip()
        reason = str(blocker.get("reason", "")).strip()
        message = f"{axis}:{code}"
        if reason:
            message = f"{message}({reason})"
        messages.append(message)
    return messages


def _format_seed_summary(
    seed_result: dict[str, object] | None,
    *,
    excel_path: str,
    sheet_name: str,
    row_index: int,
) -> str:
    if seed_result is None:
        return "seed: not started"
    status = str(seed_result.get("status", "unknown")).strip()
    if status == "seeded":
        topic_spec = _coerce_mapping(seed_result.get("topic_spec"))
        row_ref = (
            "-"
            if topic_spec is None
            else str(topic_spec.get("row_ref", "-")).strip() or "-"
        )
        job_id = str(seed_result.get("job_id", "-")).strip() or "-"
        return f"seed: seeded row={row_ref} job={job_id}"
    if status == "no_work":
        return f"seed: no work excel={excel_path} sheet={sheet_name} row={row_index}"
    code = str(seed_result.get("code", "UNKNOWN")).strip()
    return f"seed: status={status} code={code}"


def _format_terminal_evidence_summary(
    result_payload: dict[str, object] | None,
    gui_payload: dict[str, object] | None,
) -> str:
    metadata = (
        None
        if result_payload is None
        else _coerce_mapping(result_payload.get("metadata"))
    )
    run_id = ""
    if metadata is not None:
        run_id = str(metadata.get("run_id", "")).strip()
    if not run_id and gui_payload is not None:
        run_id = str(gui_payload.get("run_id", "")).strip()
    final_output = False
    if metadata is not None:
        final_output = bool(metadata.get("final_output", False))
    if not final_output and gui_payload is not None:
        final_output = bool(gui_payload.get("final_output", False))
    final_artifact_path = ""
    if metadata is not None:
        final_artifact_path = str(metadata.get("final_artifact_path", "")).strip()
    if not final_artifact_path and gui_payload is not None:
        final_artifact_path = str(gui_payload.get("final_artifact_path", "")).strip()
    if final_output and final_artifact_path:
        return f"run_id={run_id or '-'} final_output=true path={final_artifact_path}"
    attached_failure_path = ""
    if metadata is not None:
        attached_failure_path = str(metadata.get("failure_summary_path", "")).strip()
    if not attached_failure_path and gui_payload is not None:
        attached_failure_path = str(gui_payload.get("failure_summary_path", "")).strip()
    if attached_failure_path:
        return f"run_id={run_id or '-'} failure_summary={attached_failure_path}"
    if run_id:
        return f"run_id={run_id} pending terminal evidence"
    return "evidence: latest result unavailable"


def _blocking_browser_service_messages(
    browser_registry: dict[str, object] | None,
) -> list[str]:
    if browser_registry is None:
        return []
    sessions_obj = browser_registry.get("sessions", [])
    if not isinstance(sessions_obj, list):
        return []
    blocked: list[str] = []
    for raw_session in cast(list[object], sessions_obj):
        session = _coerce_mapping(raw_session)
        if session is None:
            continue
        status = str(session.get("status", "")).strip().lower()
        if status not in {"login_required", "busy_lock", "unknown_lock"}:
            continue
        service = str(session.get("service", "unknown")).strip().lower() or "unknown"
        blocked.append(f"{service}={status}")
    return blocked


class RuntimeV2ManagerGUI:
    SETTINGS_FILE: Path = (
        BASE_DIR / "system" / "runtime_v2" / "config" / "manager_gui_settings.json"
    )

    def __init__(self) -> None:
        self.root: tk.Tk = tk.Tk()
        self.root.title("runtime_v2 Manager")
        self.root.geometry("720x980")
        _ = self.root.configure(bg="#f4f4f4")
        _ = self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.config: RuntimeConfig = RuntimeConfig()
        self.owner: str = "runtime_v2_gui"
        self.poll_ms: int = 1000
        self.loop_sleep_sec: float = 2.0

        self.running: bool = False
        self.paused: bool = False
        self.stop_requested: bool = False
        self.stop_event: threading.Event = threading.Event()
        self.pause_event: threading.Event = threading.Event()
        self.control_lock: threading.Lock = threading.Lock()
        self.worker_thread: threading.Thread | None = None
        self.action_thread: threading.Thread | None = None
        self.refresh_after_id: str | None = None

        default_excel_path = BASE_DIR / "4 머니.xlsx"
        self.runtime_root_text: tk.StringVar = tk.StringVar(value="")
        self.excel_path_text: tk.StringVar = tk.StringVar(
            value=str(default_excel_path.resolve())
            if default_excel_path.exists()
            else ""
        )
        self.sheet_name_text: tk.StringVar = tk.StringVar(value="Sheet1")
        self.row_index_text: tk.StringVar = tk.StringVar(value="0")
        self.login_service_text: tk.StringVar = tk.StringVar(value="chatgpt")
        self.selected_workload: tk.StringVar = tk.StringVar(value="qwen3_tts")
        self.source_path_text: tk.StringVar = tk.StringVar(value="")
        self.audio_path_text: tk.StringVar = tk.StringVar(value="")
        self.script_text: tk.StringVar = tk.StringVar(value="")
        self.duration_text: tk.StringVar = tk.StringVar(value="8")
        self.model_name_text: tk.StringVar = tk.StringVar(value="")
        self.status_text: tk.StringVar = tk.StringVar(value="대기")
        self.warning_text: tk.StringVar = tk.StringVar(value="경고 없음")
        self.last_result_text: tk.StringVar = tk.StringVar(value="최근 실행 없음")
        self.queue_text: tk.StringVar = tk.StringVar(value="queue: 0")
        self.gpt_text: tk.StringVar = tk.StringVar(value="gpt: unknown")
        self.gpu_text: tk.StringVar = tk.StringVar(value="gpu: unknown")
        self.browser_text: tk.StringVar = tk.StringVar(value="browser: unknown")
        self.artifact_text: tk.StringVar = tk.StringVar(value="artifacts: 0")
        self.readiness_text: tk.StringVar = tk.StringVar(value="readiness: unknown")
        self.browser_services_text: tk.StringVar = tk.StringVar(
            value="services: unknown"
        )
        self.latest_run_text: tk.StringVar = tk.StringVar(value="run_id: -")
        self.seed_result_summary_text: tk.StringVar = tk.StringVar(
            value="seed: not started"
        )
        self.evidence_summary_text: tk.StringVar = tk.StringVar(
            value="evidence: latest result unavailable"
        )
        self.log_buffer: list[str] = []
        self.last_event_ts: float = 0.0
        self.ui_queue: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()

        self.program_rows: dict[str, dict[str, ttk.Label]] = {}
        self.queue_list: tk.Listbox = tk.Listbox(self.root)
        self.log_text: tk.Text = tk.Text(self.root)

        self._load_settings()
        self._refresh_runtime_config()
        self._build_ui()
        self._ensure_snapshot_contracts()
        self.refresh_after_id = self.root.after(200, self.refresh_dashboard)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_control_frame(main)
        self._build_overview_frame(main)
        self._build_programs_frame(main)
        self._build_queue_frame(main)
        self._build_logs_frame(main)

    def _build_control_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Stage 5 Console", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        runtime_row = ttk.Frame(frame)
        runtime_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(runtime_row, text="Runtime root:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(runtime_row, textvariable=self.runtime_root_text).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        tk.Button(
            runtime_row,
            text="Health Refresh",
            width=14,
            command=self.refresh_dashboard_now,
        ).pack(side=tk.LEFT, padx=(8, 0))

        excel_row = ttk.Frame(frame)
        excel_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(excel_row, text="Excel:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(excel_row, textvariable=self.excel_path_text).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        row_select = ttk.Frame(frame)
        row_select.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(row_select, text="Sheet:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(row_select, textvariable=self.sheet_name_text, width=16).pack(
            side=tk.LEFT
        )
        ttk.Label(row_select, text="Row index:").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Entry(row_select, textvariable=self.row_index_text, width=8).pack(
            side=tk.LEFT
        )
        ttk.Label(row_select, text="Login browser:").pack(side=tk.LEFT, padx=(8, 4))
        browser_combo = ttk.Combobox(
            row_select, textvariable=self.login_service_text, state="readonly", width=12
        )
        browser_combo["values"] = (
            "chatgpt",
            "genspark",
            "seaart",
            "geminigen",
            "canva",
        )
        browser_combo.pack(side=tk.LEFT)

        note_row = ttk.Frame(frame)
        note_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(
            note_row,
            text="주의: 1행 테스트는 row index 1이 아니라 준비된 테스트 행 1개를 의미합니다.",
            foreground="#6b4f00",
        ).pack(anchor="w")

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X)
        tk.Button(
            action_row,
            text="Excel Seed 1-Row",
            width=16,
            command=self.trigger_excel_seed,
        ).pack(side=tk.LEFT)
        tk.Button(
            action_row, text="Control Once", width=12, command=self.trigger_control_once
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            action_row,
            text="Open Login Browser",
            width=16,
            command=self.trigger_open_login_browser,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            action_row, text="Scan Inbox", width=12, command=self.trigger_scan_inbox
        ).pack(side=tk.LEFT, padx=(12, 4))
        tk.Button(
            action_row, text="GPT Spawn", width=12, command=self.trigger_gpt_spawn
        ).pack(side=tk.LEFT)

        advanced = ttk.LabelFrame(frame, text="Advanced", padding=6)
        advanced.pack(fill=tk.X, pady=(8, 0))

        top = ttk.Frame(advanced)
        top.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(top, text="기본 작업군:").pack(side=tk.LEFT)
        combo = ttk.Combobox(
            top, textvariable=self.selected_workload, state="readonly", width=16
        )
        combo["values"] = ("qwen3_tts", "rvc", "kenburns")
        combo.pack(side=tk.LEFT, padx=(6, 0))

        row = ttk.Frame(advanced)
        row.pack(fill=tk.X, pady=(0, 6))
        tk.Button(
            row, text="▶ Start", width=10, command=self.start_loop, fg="#1f7a1f"
        ).pack(side=tk.LEFT)
        tk.Button(
            row, text="⏸ Pause", width=10, command=self.toggle_pause, fg="#b36b00"
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            row, text="■ Stop", width=10, command=self.stop_loop, fg="#b32020"
        ).pack(side=tk.LEFT)
        tk.Button(row, text="↻ Recovery", width=12, command=self.trigger_recovery).pack(
            side=tk.LEFT, padx=(16, 4)
        )

        seed = ttk.Frame(advanced)
        seed.pack(fill=tk.X)
        ttk.Label(seed, text="path:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(seed, textvariable=self.source_path_text, width=26).pack(side=tk.LEFT)
        ttk.Label(seed, text="audio:").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Entry(seed, textvariable=self.audio_path_text, width=24).pack(side=tk.LEFT)

        tune = ttk.Frame(advanced)
        tune.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(tune, text="duration:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(tune, textvariable=self.duration_text, width=6).pack(side=tk.LEFT)
        ttk.Label(tune, text="model:").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Entry(tune, textvariable=self.model_name_text, width=14).pack(side=tk.LEFT)

        prompt = ttk.Frame(advanced)
        prompt.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(prompt, text="script:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(prompt, textvariable=self.script_text, width=64).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        seed_buttons = ttk.Frame(advanced)
        seed_buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(seed_buttons, text="큐 삽입:").pack(side=tk.LEFT)
        tk.Button(
            seed_buttons,
            text="QWEN3",
            width=10,
            command=lambda: self.seed_job("qwen3_tts"),
        ).pack(side=tk.LEFT, padx=(6, 4))
        tk.Button(
            seed_buttons, text="RVC", width=10, command=lambda: self.seed_job("rvc")
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            seed_buttons,
            text="KenBurns",
            width=10,
            command=lambda: self.seed_job("kenburns"),
        ).pack(side=tk.LEFT, padx=4)

    def _build_overview_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Overview", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            frame, textvariable=self.status_text, font=("Malgun Gothic", 10, "bold")
        ).pack(anchor="w")
        ttk.Label(frame, textvariable=self.warning_text, foreground="#b32020").pack(
            anchor="w", pady=(4, 0)
        )
        ttk.Label(frame, textvariable=self.last_result_text).pack(
            anchor="w", pady=(4, 0)
        )

        operator = ttk.Frame(frame)
        operator.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(operator, textvariable=self.readiness_text).pack(anchor="w")
        ttk.Label(operator, textvariable=self.browser_services_text).pack(
            anchor="w", pady=(2, 0)
        )
        ttk.Label(operator, textvariable=self.latest_run_text).pack(
            anchor="w", pady=(2, 0)
        )
        ttk.Label(operator, textvariable=self.seed_result_summary_text).pack(
            anchor="w", pady=(2, 0)
        )
        ttk.Label(operator, textvariable=self.evidence_summary_text).pack(
            anchor="w", pady=(2, 0)
        )

        grid = ttk.Frame(frame)
        grid.pack(fill=tk.X, pady=(6, 0))
        for index, var in enumerate(
            (
                self.browser_text,
                self.gpu_text,
                self.gpt_text,
                self.queue_text,
                self.artifact_text,
            )
        ):
            label = ttk.Label(grid, textvariable=var, relief=tk.GROOVE, padding=6)
            _ = label.grid(
                row=index // 2, column=index % 2, sticky="ew", padx=2, pady=2
            )
        _ = grid.grid_columnconfigure(0, weight=1)
        _ = grid.grid_columnconfigure(1, weight=1)

    def _build_programs_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Programs", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        for program in (
            "GPT",
            "Genspark",
            "SeaArt",
            "Browser",
            "GeminiGen",
            "KenBurns",
            "QWEN3_TTS",
            "RVC",
            "Result",
            "GUI",
        ):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=program, width=12).pack(side=tk.LEFT)
            status = ttk.Label(row, text="대기", width=20)
            status.pack(side=tk.LEFT)
            detail = ttk.Label(row, text="", width=40)
            detail.pack(side=tk.LEFT, padx=(6, 0))
            self.program_rows[program] = {"status": status, "detail": detail}

    def _build_queue_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Queue / Recovery", padding=8)
        frame.pack(fill=tk.BOTH, expand=False, pady=(0, 8))
        self.queue_list = tk.Listbox(frame, height=10, font=("Consolas", 9))
        self.queue_list.pack(fill=tk.BOTH, expand=True)

    def _build_logs_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Logs", padding=8)
        frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            frame, height=18, font=("Consolas", 9), bg="#263238", fg="#eceff1"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _append_log(self, message: str) -> None:
        timestamp = time()
        line = f"[{timestamp:.3f}] {message}"
        self.log_buffer.append(line)
        if len(self.log_buffer) > 300:
            self.log_buffer = self.log_buffer[-300:]
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "\n".join(self.log_buffer))
        self.log_text.see(tk.END)

    def _summarize_control_result(self, result: dict[str, object]) -> str:
        summary = summarize_runtime_result(result)
        log_ref = debug_log_path(
            self.config.debug_log_root, str(summary.get("job_id", "gui-session"))
        )
        parts = [
            f"status={summary.get('status', '?')}",
            f"code={summary.get('code', '')}",
        ]
        if str(summary.get("job_id", "")):
            parts.append(f"job={summary.get('job_id', '')}")
        if str(summary.get("workload", "")):
            parts.append(f"workload={summary.get('workload', '')}")
        if str(summary.get("stage", "")):
            parts.append(f"stage={summary.get('stage', '')}")
        if str(summary.get("error_code", "")):
            parts.append(f"error={summary.get('error_code', '')}")
        parts.append(f"debug={log_ref}")
        return " ".join(parts)

    def _enqueue_ui(self, action: str, value: str) -> None:
        self.ui_queue.put((action, value))

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                action, value = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if action == "log":
                self._append_log(value)
            elif action == "last_result":
                self.last_result_text.set(value)
            elif action == "status":
                self.status_text.set(value)
            elif action == "seed_summary":
                self.seed_result_summary_text.set(value)
            elif action == "refresh":
                self._refresh_dashboard_once()

    def _set_program_row(
        self, program: str, *, status: str | None = None, detail: str | None = None
    ) -> None:
        row = self.program_rows.get(program)
        if row is None:
            return
        if status is not None:
            _ = row["status"].config(text=status)
        if detail is not None:
            _ = row["detail"].config(text=detail)

    def _snapshot_warning(
        self, name: str, payload: dict[str, object] | None, fresh_sec: int
    ) -> str | None:
        if payload is None:
            return f"{name} snapshot missing"
        checked_at = _to_float(payload.get("checked_at", 0.0), 0.0)
        if checked_at <= 0:
            return f"{name} snapshot timestamp missing"
        age = max(0.0, time() - checked_at)
        if age > fresh_sec:
            return f"{name} snapshot stale ({int(age)}s)"
        return None

    def _load_settings(self) -> None:
        payload = _read_json(self.SETTINGS_FILE)
        if payload is None:
            return
        self.runtime_root_text.set(str(payload.get("runtime_root", "")))
        self.excel_path_text.set(
            str(payload.get("excel_path", self.excel_path_text.get()))
        )
        self.sheet_name_text.set(str(payload.get("sheet_name", "Sheet1")))
        self.row_index_text.set(str(payload.get("row_index", "0")))
        login_service = str(payload.get("login_service", "chatgpt")).strip().lower()
        if login_service in {"chatgpt", "genspark", "seaart", "geminigen", "canva"}:
            self.login_service_text.set(login_service)
        workload = str(payload.get("selected_workload", "qwen3_tts"))
        if workload in {"qwen3_tts", "rvc", "kenburns"}:
            self.selected_workload.set(workload)
        self.source_path_text.set(str(payload.get("source_path", "")))
        self.audio_path_text.set(str(payload.get("audio_path", "")))
        self.script_text.set(str(payload.get("script_text", "")))
        self.duration_text.set(str(payload.get("duration_sec", "8")))
        self.model_name_text.set(str(payload.get("model_name", "")))

    def _save_settings(self) -> None:
        self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "runtime_root": self.runtime_root_text.get().strip(),
            "excel_path": self.excel_path_text.get().strip(),
            "sheet_name": self.sheet_name_text.get().strip(),
            "row_index": self.row_index_text.get().strip(),
            "login_service": self.login_service_text.get().strip(),
            "selected_workload": self.selected_workload.get(),
            "source_path": self.source_path_text.get().strip(),
            "audio_path": self.audio_path_text.get().strip(),
            "script_text": self.script_text.get().strip(),
            "duration_sec": self.duration_text.get().strip(),
            "model_name": self.model_name_text.get().strip(),
        }
        _ = self.SETTINGS_FILE.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
        )

    def _refresh_runtime_config(self, *, force: bool = False) -> None:
        action_running = (
            self.action_thread is not None and self.action_thread.is_alive()
        )
        if not force and (self.running or action_running):
            return
        self.config = _runtime_config_from_text(self.runtime_root_text.get())

    def _parsed_row_index(self) -> int | None:
        raw = self.row_index_text.get().strip()
        if not raw:
            return 0
        try:
            row_index = int(raw)
        except ValueError:
            _ = messagebox.showwarning("runtime_v2", "row index는 정수여야 합니다.")
            return None
        if row_index < 0:
            _ = messagebox.showwarning("runtime_v2", "row index는 0 이상이어야 합니다.")
            return None
        return row_index

    def _start_background_action(
        self, action_name: str, action: Callable[[], None]
    ) -> None:
        if self.action_thread is not None and self.action_thread.is_alive():
            _ = messagebox.showwarning("runtime_v2", "다른 작업이 아직 실행 중입니다.")
            return

        def runner() -> None:
            self._enqueue_ui("status", f"{action_name} 실행중")
            try:
                action()
            except Exception as exc:
                _ = append_debug_event(
                    debug_log_path(self.config.debug_log_root, "gui-session"),
                    event="gui_manual_action_exception",
                    level="ERROR",
                    payload={
                        "owner": self.owner,
                        "action_name": action_name,
                        **exception_payload(exc),
                    },
                )
                self._enqueue_ui("log", f"{action_name} failed: {exc}")
                self._enqueue_ui("last_result", f"{action_name}: failed {exc}")
            finally:
                self._enqueue_ui("status", "실행중" if self.running else "대기")
                self._enqueue_ui("refresh", "")

        self.action_thread = threading.Thread(target=runner, daemon=True)
        self.action_thread.start()

    def refresh_dashboard_now(self) -> None:
        self._refresh_runtime_config(force=True)
        self._save_settings()
        self._refresh_dashboard_once()
        self._append_log("manual health refresh")

    def trigger_excel_seed(self) -> None:
        if self.running:
            _ = messagebox.showwarning(
                "runtime_v2",
                "manual Stage 5 seed 전에는 long-running loop를 먼저 중지하세요.",
            )
            return
        self._refresh_runtime_config(force=True)
        row_index = self._parsed_row_index()
        if row_index is None:
            return
        excel_path = self.excel_path_text.get().strip()
        if not excel_path:
            _ = messagebox.showwarning("runtime_v2", "excel path를 입력하세요.")
            return
        run_id = str(uuid4())
        seed_result = seed_excel_row(
            config=self.config,
            run_id=run_id,
            excel_path=excel_path,
            sheet_name=self.sheet_name_text.get().strip() or "Sheet1",
            row_index=row_index,
        )
        self._save_settings()
        summary = _format_seed_summary(
            seed_result,
            excel_path=excel_path,
            sheet_name=self.sheet_name_text.get().strip() or "Sheet1",
            row_index=row_index,
        )
        self.seed_result_summary_text.set(summary)
        self.latest_run_text.set(f"run_id: {run_id}")
        self.last_result_text.set(summary)
        self._append_log(summary)
        self._refresh_dashboard_once()

    def _manual_control_stop_reasons(self) -> list[str]:
        self._refresh_runtime_config(force=True)
        readiness = load_runtime_readiness(self.config, completed=True)
        stop_reasons = _readiness_blocker_messages(readiness)
        browser_registry = _read_json(self.config.browser_registry_file)
        stop_reasons.extend(_blocking_browser_service_messages(browser_registry))
        return stop_reasons

    def trigger_control_once(self) -> None:
        if self.running:
            _ = messagebox.showwarning(
                "runtime_v2",
                "manual Stage 5 control 전에는 long-running loop를 먼저 중지하세요.",
            )
            return
        stop_reasons = self._manual_control_stop_reasons()
        if stop_reasons:
            message = " | ".join(stop_reasons[:4])
            self._append_log(f"control once blocked: {message}")
            self.last_result_text.set(f"control once blocked: {message}")
            _ = messagebox.showwarning("runtime_v2", f"No-Go 상태입니다: {message}")
            self._refresh_dashboard_once()
            return

        def action() -> None:
            self._refresh_runtime_config(force=True)
            result = self._run_control_once()
            summary_line = self._summarize_control_result(result)
            self._enqueue_ui("last_result", f"control once: {summary_line}")
            self._enqueue_ui("log", f"control once: {summary_line}")

        self._start_background_action("control once", action)

    def trigger_open_login_browser(self) -> None:
        service = self.login_service_text.get().strip().lower()
        if service not in {"chatgpt", "genspark", "seaart", "geminigen", "canva"}:
            _ = messagebox.showwarning(
                "runtime_v2", "지원하지 않는 브라우저 서비스입니다."
            )
            return

        def action() -> None:
            payload = open_browser_for_login(service)
            summary = (
                f"login browser: service={payload.get('service', service)} "
                f"port={payload.get('port', 0)} launched={payload.get('launched', False)}"
            )
            self._enqueue_ui("last_result", summary)
            self._enqueue_ui("log", summary)

        self._start_background_action("open login browser", action)

    def start_loop(self) -> None:
        if self.running:
            return
        self.running = True
        self.paused = False
        self.stop_requested = False
        self.stop_event.clear()
        self.pause_event.clear()
        self._save_settings()
        self.status_text.set("실행중")
        self._append_log("control loop started")
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.worker_thread.start()

    def toggle_pause(self) -> None:
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_event.set()
        else:
            self.pause_event.clear()
        self.status_text.set("일시정지" if self.paused else "실행중")
        self._append_log(
            "control loop paused" if self.paused else "control loop resumed"
        )

    def stop_loop(self) -> None:
        self.stop_requested = True
        self.running = False
        self.paused = False
        self.stop_event.set()
        self.pause_event.clear()
        self.status_text.set("중지")
        self._append_log("control loop stopped")

    def trigger_recovery(self) -> None:
        workload = self.selected_workload.get()
        self._append_log(f"manual recovery triggered for {workload}")
        result = self._run_control_once()
        self.last_result_text.set(
            f"recovery: {str(result.get('result', result))[:120]}"
        )
        self._refresh_dashboard_once()

    def trigger_gpt_spawn(self) -> None:
        status = load_gpt_status(self.config.gpt_status_file)
        if status is None:
            _ = messagebox.showwarning("runtime_v2", "gpt_status.json 이 없습니다.")
            return
        pending_boot_value = status.get("pending_boot", 0)
        pending_boot = (
            int(pending_boot_value)
            if isinstance(pending_boot_value, (int, float, str))
            else 0
        )
        status["pending_boot"] = pending_boot + 1
        status["last_spawn_at"] = round(time(), 3)
        _ = write_gpt_status(status, self.config.gpt_status_file)
        self._append_log("manual GPT spawn check triggered")
        self._refresh_dashboard_once()

    def trigger_scan_inbox(self) -> None:
        seeded_jobs = seed_local_jobs(self.config)
        self._append_log(f"scan inbox seeded={len(seeded_jobs)}")
        self._refresh_dashboard_once()

    def seed_job(self, workload: GpuWorkload) -> None:
        payload = self._build_job_payload(workload)
        if payload is None:
            return
        job = JobContract(
            job_id=f"{workload}-{uuid4()}",
            workload=workload,
            status="queued",
            payload=payload,
        )
        seed_control_job(job=job, config=self.config)
        self._save_settings()
        self._append_log(f"queued job: {job.job_id} payload={payload}")
        self._refresh_dashboard_once()

    def _build_job_payload(self, workload: GpuWorkload) -> dict[str, object] | None:
        payload: dict[str, object] = {}
        source_path = self.source_path_text.get().strip()
        audio_path = self.audio_path_text.get().strip()
        script_text = self.script_text.get().strip()
        duration_sec = _to_int(self.duration_text.get().strip())
        if workload == "qwen3_tts":
            if not script_text:
                _ = messagebox.showwarning("runtime_v2", "script 값을 입력하세요.")
                return None
            payload["script_text"] = script_text
            if source_path:
                payload["image_path"] = source_path
            return payload
        if not source_path:
            _ = messagebox.showwarning("runtime_v2", "path 값을 입력하세요.")
            return None
        payload["source_path"] = source_path
        if workload == "kenburns":
            payload["duration_sec"] = max(1, duration_sec)
        if workload == "rvc" and audio_path:
            payload["audio_path"] = audio_path
        model_name = self.model_name_text.get().strip()
        if workload == "rvc" and model_name:
            payload["model_name"] = model_name
        return payload

    def _run_loop(self) -> None:
        while self.running and not self.stop_event.is_set():
            try:
                if self.pause_event.is_set():
                    sleep(self.loop_sleep_sec)
                    continue
                result = self._run_control_once()
                result_summary = summarize_runtime_result(result)
                summary_line = self._summarize_control_result(result)
                self._enqueue_ui("last_result", f"last: {summary_line}")
                self._enqueue_ui("log", f"control result: {summary_line}")
                _ = append_debug_event(
                    debug_log_path(
                        self.config.debug_log_root,
                        str(result_summary.get("job_id", "gui-session")),
                    ),
                    event="gui_control_result",
                    level="ERROR"
                    if str(result.get("status", "")) == "failed"
                    else "INFO",
                    payload={
                        "owner": self.owner,
                        "result": result,
                    },
                )
                recovery = _coerce_mapping(result.get("recovery", {}))
                backoff_value = self.loop_sleep_sec
                if recovery is not None:
                    backoff_value = _to_float(
                        recovery.get("backoff_sec", self.loop_sleep_sec),
                        self.loop_sleep_sec,
                    )
                if result.get("code") == "NO_JOB":
                    sleep(max(self.loop_sleep_sec, 5.0))
                    continue
                sleep(max(self.loop_sleep_sec, backoff_value))
            except BaseException as exc:
                _ = append_debug_event(
                    debug_log_path(self.config.debug_log_root, "gui-session"),
                    event="gui_loop_exception",
                    level="ERROR",
                    payload={
                        "owner": self.owner,
                        **exception_payload(exc),
                    },
                )
                raise

    def refresh_dashboard(self) -> None:
        try:
            self._drain_ui_queue()
            self._refresh_dashboard_once()
        except Exception as exc:
            self._append_log(f"dashboard refresh failed: {exc}")
            self.warning_text.set(f"dashboard refresh failed: {exc}")
            _ = append_debug_event(
                debug_log_path(self.config.debug_log_root, "gui-session"),
                event="gui_refresh_exception",
                level="ERROR",
                payload={
                    "owner": self.owner,
                    **exception_payload(exc),
                },
            )
        finally:
            self.refresh_after_id = self.root.after(
                self.poll_ms, self.refresh_dashboard
            )

    def _run_control_once(self) -> dict[str, object]:
        if not self.control_lock.acquire(blocking=False):
            return {
                "status": "busy",
                "code": "CONTROL_BUSY",
                "result": "control loop busy",
            }
        try:
            return run_control_loop_once(owner=self.owner, config=self.config)
        finally:
            self.control_lock.release()

    def _refresh_dashboard_once(self) -> None:
        self._refresh_runtime_config()
        self._ensure_snapshot_contracts()
        self._update_operator_panel()
        self._update_browser_panel()
        self._update_gpu_panel()
        self._update_gpt_panel()
        self._update_queue_panel()
        self._update_artifact_panel()
        self._update_program_panel()
        self._update_warning_panel()
        self._update_log_panel()

    def _ensure_snapshot_contracts(self) -> None:
        ensure_runtime_bootstrap(
            self.config,
            workload=self._selected_gpu_workload(),
            run_id="gui-bootstrap",
            mode="local_gui",
        )

    def _update_operator_panel(self) -> None:
        readiness = load_runtime_readiness(self.config, completed=True)
        blocker_messages = _readiness_blocker_messages(readiness)
        if bool(readiness.get("ready", False)) and not blocker_messages:
            self.readiness_text.set("readiness: ready")
        elif blocker_messages:
            self.readiness_text.set(f"readiness: {' | '.join(blocker_messages[:3])}")
        else:
            self.readiness_text.set(
                f"readiness: code={str(readiness.get('code', 'UNKNOWN')).strip() or 'UNKNOWN'}"
            )

        result_payload = _read_json(self.config.result_router_file)
        gui_payload = _read_json(self.config.gui_status_file)
        self.evidence_summary_text.set(
            _format_terminal_evidence_summary(result_payload, gui_payload)
        )

        result_metadata = (
            None
            if result_payload is None
            else _coerce_mapping(result_payload.get("metadata"))
        )
        latest_run_id = ""
        if result_metadata is not None:
            latest_run_id = str(result_metadata.get("run_id", "")).strip()
        if not latest_run_id and gui_payload is not None:
            latest_run_id = str(gui_payload.get("run_id", "")).strip()
        if not latest_run_id:
            latest_run_id = str(readiness.get("snapshot_run_id", "")).strip()
        self.latest_run_text.set(f"run_id: {latest_run_id or '-'}")

    def _normalize_gpu_health_snapshot(self) -> None:
        payload = _read_json(self.config.lease_file)
        if payload is None:
            _ = write_gpu_health_payload(
                build_gpu_health_payload(
                    self._selected_gpu_workload(),
                    lock_key=f"lock:{self._selected_gpu_workload()}",
                    lease=None,
                    event="idle",
                ),
                self.config.lease_file,
            )
            return
        has_schema = isinstance(payload.get("schema_version"), str) and isinstance(
            payload.get("checked_at"), (int, float)
        )
        if has_schema:
            return
        lease_payload = None
        lock_key = ""
        if all(key in payload for key in ("key", "owner", "expires_at")):
            lease_payload = payload
            lock_key = str(payload.get("key", "")).strip()
        workload = _workload_from_lock_key(lock_key) or self._selected_gpu_workload()
        normalized = build_gpu_health_payload(
            workload,
            lock_key=lock_key or f"lock:{workload}",
            lease=None
            if lease_payload is None
            else Lease.from_dict(_lease_like_payload(lease_payload)),
            event="normalized_legacy_snapshot" if lease_payload is not None else "idle",
        )
        _ = write_gpu_health_payload(normalized, self.config.lease_file)

    def _normalize_gui_status_snapshot(self) -> None:
        payload = _read_json(self.config.gui_status_file)
        if payload is None:
            return
        has_schema = isinstance(payload.get("schema_version"), str) and isinstance(
            payload.get("checked_at"), (int, float)
        )
        if has_schema:
            return
        status_payload = _coerce_mapping(payload.get("status", {}))
        normalized = build_gui_status_payload(
            {} if status_payload is None else status_payload,
            run_id=str(payload.get("run_id", "gui-bootstrap")),
            mode=str(payload.get("mode", "local_gui")),
            stage=str(payload.get("stage", "idle")),
            exit_code=_to_int(payload.get("exit_code", 0)),
        )
        _ = write_gui_status(normalized, self.config.gui_status_file)

    def _selected_gpu_workload(self) -> GpuWorkload:
        workload = self.selected_workload.get().strip()
        if workload == "rvc":
            return "rvc"
        if workload == "kenburns":
            return "kenburns"
        return "qwen3_tts"

    def _update_browser_panel(self) -> None:
        payload = _read_json(self.config.browser_health_file)
        registry = _read_json(self.config.browser_registry_file)
        if payload is None:
            self.browser_text.set("browser: missing")
            self.browser_services_text.set("services: browser registry missing")
            return
        healthy = _to_int(payload.get("healthy_count", 0))
        total = _to_int(payload.get("session_count", 0))
        self.browser_text.set(f"browser: {healthy}/{total} healthy")
        service_summaries: list[str] = []
        if registry is not None:
            sessions = registry.get("sessions", [])
            if isinstance(sessions, list):
                typed_sessions = cast(list[object], sessions)
                row_map = {
                    "chatgpt": "GPT",
                    "genspark": "Genspark",
                    "seaart": "SeaArt",
                    "geminigen": "GeminiGen",
                    "canva": "Browser",
                }
                for item in typed_sessions:
                    item_dict = _coerce_mapping(item)
                    if item_dict is None:
                        continue
                    row_name = row_map.get(
                        str(item_dict.get("service", "")).strip().lower()
                    )
                    if row_name is None:
                        continue
                    row_status = str(item_dict.get("status", "대기"))
                    port = _to_int(item_dict.get("port", 0))
                    failures = _to_int(item_dict.get("consecutive_failures", 0))
                    self._set_program_row(
                        row_name,
                        status=row_status,
                        detail=f"port={port} fail={failures}",
                    )
                    service_summaries.append(f"{row_name}={row_status}")
        self.browser_services_text.set(
            "services: "
            + (
                ", ".join(service_summaries)
                if service_summaries
                else "no live sessions"
            )
        )

    def _update_gpu_panel(self) -> None:
        payload = _read_json(self.config.lease_file)
        if payload is None:
            self.gpu_text.set("gpu: missing")
            return
        self.gpu_text.set(
            f"gpu: {payload.get('workload', '?')} / {payload.get('event', 'unknown')}"
        )
        lease_payload = _coerce_mapping(payload.get("lease"))
        owner = "-" if lease_payload is None else str(lease_payload.get("owner", "-"))
        workload = str(payload.get("workload", "qwen3_tts")).strip().lower()
        row_name = _program_row_for_workload(workload)
        self._set_program_row(
            row_name, status=str(payload.get("event", "대기")), detail=f"owner={owner}"
        )

    def _update_gpt_panel(self) -> None:
        payload = load_gpt_status(self.config.gpt_status_file)
        if payload is None:
            self.gpt_text.set("gpt: missing")
            return
        ok_count = _to_int(payload.get("ok_count", 0))
        pending_boot = _to_int(payload.get("pending_boot", 0))
        self.gpt_text.set(f"gpt: ok={ok_count}, pending_boot={pending_boot}")

    def _update_queue_panel(self) -> None:
        items = _read_json_list(self.config.queue_store_file)
        self.queue_text.set(f"queue: {len(items)}")
        self.queue_list.delete(0, tk.END)
        for item in items[:100]:
            job_id = str(item.get("job_id", "unknown"))
            workload = str(item.get("workload", "?"))
            status = str(item.get("status", "queued"))
            attempts = item.get("attempts", 0)
            payload = _coerce_mapping(item.get("payload", {}))
            chain_depth = (
                0 if payload is None else _to_int(payload.get("chain_depth", 0))
            )
            routed_from = (
                "-" if payload is None else str(payload.get("routed_from", "-"))
            )
            self.queue_list.insert(
                tk.END,
                f"{status:10} {workload:10} d={chain_depth} tries={attempts} from={routed_from} {job_id}",
            )

    def _update_artifact_panel(self) -> None:
        payload = _read_json(self.config.result_router_file)
        if payload is None:
            inbox_root = self.config.input_root
            accepted = _archived_contract_count(inbox_root / "accepted")
            invalid = _archived_contract_count(inbox_root / "invalid")
            self.artifact_text.set(
                f"artifacts: 0 / accepted={accepted} invalid={invalid}"
            )
            return
        artifacts_obj = payload.get("artifacts", [])
        artifacts = (
            cast(list[object], artifacts_obj) if isinstance(artifacts_obj, list) else []
        )
        count = len(artifacts)
        metadata = _coerce_mapping(payload.get("metadata", {}))
        result_job = "-" if metadata is None else str(metadata.get("job_id", "-"))
        result_run_id = "-" if metadata is None else str(metadata.get("run_id", "-"))
        completion_state = (
            "-" if metadata is None else str(metadata.get("completion_state", "-"))
        )
        final_output = (
            False if metadata is None else bool(metadata.get("final_output", False))
        )
        final_artifact = (
            "" if metadata is None else str(metadata.get("final_artifact", ""))
        )
        result_status = "-" if metadata is None else str(metadata.get("status", "-"))
        result_code = "-" if metadata is None else str(metadata.get("code", "-"))
        final_record = _latest_final_output_record(
            self.config.control_plane_events_file
        )
        last_final_artifact = (
            "" if final_record is None else str(final_record.get("final_artifact", ""))
        )
        inbox_root = self.config.input_root
        accepted = _archived_contract_count(inbox_root / "accepted")
        invalid = _archived_contract_count(inbox_root / "invalid")
        latest_text = f"artifacts: {count} / accepted={accepted} invalid={invalid} / job={result_job}"
        if last_final_artifact:
            latest_text = f"{latest_text} / last={last_final_artifact}"
        self.artifact_text.set(latest_text)
        render_detail = f"art={count} acc={accepted} inv={invalid} run={result_run_id} code={result_code}"
        if final_output and final_artifact:
            render_detail = f"final={final_artifact}"
        elif last_final_artifact:
            render_detail = f"latest={result_code} last={last_final_artifact}"
        render_status = completion_state
        if final_output:
            render_status = "최종완료"
        elif result_status == "idle" or result_code == "NO_JOB":
            render_status = "유휴"
        elif not render_status or render_status == "-":
            render_status = "완료" if count > 0 else "대기"
        self._set_program_row("Result", status=render_status, detail=render_detail[:40])

    def _update_program_panel(self) -> None:
        gui_payload = _read_json(self.config.gui_status_file)
        if gui_payload is not None:
            status_payload = _coerce_mapping(gui_payload.get("status", {}))
            worker_stage = str(gui_payload.get("worker_stage", "")).strip()
            if not worker_stage and status_payload is not None:
                worker_stage = str(
                    status_payload.get("worker_stage", gui_payload.get("stage", "-"))
                ).strip()
            worker_error_code = str(gui_payload.get("worker_error_code", "")).strip()
            if not worker_error_code and status_payload is not None:
                worker_error_code = str(
                    status_payload.get("worker_error_code", "")
                ).strip()
            worker_error_display = _display_worker_error_code(worker_error_code)
            result_path = str(gui_payload.get("result_path", "")).strip()
            if not result_path and status_payload is not None:
                result_path = str(status_payload.get("result_path", "")).strip()
            manifest_path = str(gui_payload.get("manifest_path", "")).strip()
            if not manifest_path and status_payload is not None:
                manifest_path = str(status_payload.get("manifest_path", "")).strip()
            backoff_sec = (
                0
                if status_payload is None
                else _to_int(status_payload.get("backoff_sec", 0))
            )
            self._set_program_row(
                "GUI",
                status=str(gui_payload.get("stage", "대기")),
                detail=(
                    f"exit={gui_payload.get('exit_code', '?')} stage={worker_stage} err={worker_error_display or '-'} "
                    f"retry={backoff_sec}s"
                )[:40],
            )
            if worker_error_code or str(gui_payload.get("exit_code", 0)) != "0":
                path_ref = result_path or manifest_path or "-"
                self.last_result_text.set(
                    f"실패정보: stage={worker_stage} error={worker_error_display or '-'} path={path_ref}"
                )

        browser_health = _read_json(self.config.browser_health_file)
        if browser_health is not None:
            unhealthy = browser_health.get("unhealthy_count", 0)
            self._set_program_row(
                "Browser",
                status="경고" if str(unhealthy) != "0" else "정상",
                detail=f"availability={browser_health.get('availability_percent', 0)}% unhealthy={unhealthy}"[
                    :40
                ],
            )

    def _update_log_panel(self) -> None:
        event_records = _read_jsonl_tail(
            self.config.control_plane_events_file, limit=20
        )
        new_lines: list[str] = []
        for record in event_records:
            ts = _to_float(record.get("ts", 0.0), 0.0)
            if ts <= self.last_event_ts:
                continue
            event_name = str(record.get("event", "")).strip()
            if event_name == "next_job_rejected":
                new_lines.append(
                    f"event next_job_rejected parent={record.get('parent_job_id', '?')} job={record.get('job_id', '-')} reason={record.get('reason', '?')}"
                )
            elif event_name == "stale_running_recovered":
                new_lines.append(
                    f"event stale_running job={record.get('job_id', '?')} action={record.get('action', '?')} age={record.get('age_sec', 0)}"
                )
            elif event_name == "job_summary":
                done_state = str(record.get("completion_state", "-") or "-")
                final_output = bool(record.get("final_output", False))
                final_artifact = str(record.get("final_artifact", "") or "-")
                worker_error_display = _display_worker_error_code(
                    str(record.get("worker_error_code", "-") or "-")
                )
                new_lines.append(
                    f"summary job={record.get('job_id', '?')} ok={record.get('success', False)} stage={record.get('worker_stage', '-')} err={worker_error_display} tries={record.get('attempts', 0)} backoff={record.get('backoff_sec', 0)} art={record.get('artifact_count', 0)} next={record.get('next_jobs_count', 0)} routed={record.get('routed_count', 0)} depth={record.get('chain_depth', 0)} from={record.get('routed_from', '-') or '-'} done={done_state} final={final_output} file={final_artifact}"
                )
            else:
                new_lines.append(
                    f"event job={record.get('job_id', '?')} {record.get('previous_status', '?')} -> {record.get('status', '?')} from={record.get('routed_from', '-')} depth={record.get('chain_depth', 0)}"
                )
            self.last_event_ts = ts
        for line in new_lines:
            self._append_log(line)

    def _update_warning_panel(self) -> None:
        warnings: list[str] = []
        gui_status = _read_json(self.config.gui_status_file)
        gui_warning = self._snapshot_warning("gui", gui_status, fresh_sec=120)
        if gui_warning is not None:
            warnings.append(gui_warning)
        browser_health = _read_json(self.config.browser_health_file)
        browser_warning = self._snapshot_warning(
            "browser", browser_health, fresh_sec=120
        )
        if browser_warning is not None:
            warnings.append(browser_warning)
        browser_registry = _read_json(self.config.browser_registry_file)
        browser_registry_warning = self._snapshot_warning(
            "browser_registry", browser_registry, fresh_sec=120
        )
        if browser_registry_warning is not None:
            warnings.append(browser_registry_warning)
        if browser_health is not None and bool(
            browser_health.get("unhealthy_count", 0)
        ):
            warnings.append("browser unhealthy detected")
        gpt_status = load_gpt_status(self.config.gpt_status_file)
        gpt_warning = self._snapshot_warning("gpt", gpt_status, fresh_sec=120)
        if gpt_warning is not None:
            warnings.append(gpt_warning)
        gpt_endpoints = (
            []
            if gpt_status is None
            or not isinstance(gpt_status.get("endpoints", []), list)
            else cast(list[object], gpt_status.get("endpoints", []))
        )
        gpt_pending_boot = (
            0 if gpt_status is None else _to_int(gpt_status.get("pending_boot", 0))
        )
        gpt_idle_bootstrap = len(gpt_endpoints) == 0 and gpt_pending_boot == 0
        if (
            gpt_status is not None
            and bool(gpt_status.get("floor_breached", False))
            and not gpt_idle_bootstrap
        ):
            warnings.append("gpt floor breached")
        gpu_health = _read_json(self.config.lease_file)
        gpu_warning = self._snapshot_warning("gpu", gpu_health, fresh_sec=120)
        if gpu_warning is not None:
            warnings.append(gpu_warning)
        if gpu_health is not None and str(gpu_health.get("event", "")) in {
            "lock_busy",
            "renew_failed",
        }:
            warnings.append(str(gpu_health.get("event", "gpu warning")))
        result_payload = _read_json(self.config.result_router_file)
        result_warning = self._snapshot_warning("result", result_payload, fresh_sec=300)
        if result_warning is not None and result_payload is not None:
            warnings.append(result_warning)
        mismatch_warning = _worker_error_code_mismatch_warning(result_payload)
        if mismatch_warning:
            warnings.append(f"worker error mismatch: {mismatch_warning}")
        gui_payload = _read_json(self.config.gui_status_file)
        status_payload = (
            None
            if gui_payload is None
            else _coerce_mapping(gui_payload.get("status", {}))
        )
        if gui_payload is not None:
            invalid_reason = (
                ""
                if status_payload is None
                else str(status_payload.get("invalid_reason", "")).strip()
            )
            if invalid_reason:
                warnings.append(f"invalid contract: {invalid_reason}")
            worker_stage = str(gui_payload.get("worker_stage", "")).strip()
            if not worker_stage and status_payload is not None:
                worker_stage = str(status_payload.get("worker_stage", "")).strip()
            worker_error_code = str(gui_payload.get("worker_error_code", "")).strip()
            if not worker_error_code and status_payload is not None:
                worker_error_code = str(
                    status_payload.get("worker_error_code", "")
                ).strip()
            worker_error_display = _display_worker_error_code(worker_error_code)
            result_path = str(gui_payload.get("result_path", "")).strip()
            if not result_path and status_payload is not None:
                result_path = str(status_payload.get("result_path", "")).strip()
            if worker_error_code or worker_stage:
                warnings.append(
                    f"job failure: stage={worker_stage or '-'} error={worker_error_display or '-'} path={result_path or '-'}"
                )
        self.warning_text.set(" | ".join(warnings) if warnings else "경고 없음")

    def on_close(self) -> None:
        self.stop_loop()
        self._save_settings()
        if self.refresh_after_id is not None:
            self.root.after_cancel(self.refresh_after_id)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    app = RuntimeV2ManagerGUI()
    app.run()
    return 0


def _lease_like_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "key": str(payload.get("key", "")),
        "owner": str(payload.get("owner", "")),
        "token": _to_int(payload.get("token", 0)),
        "expires_at": _to_float(payload.get("expires_at", 0.0), 0.0),
        "run_id": str(payload.get("run_id", "unknown")),
        "pid": _to_int(payload.get("pid", 0)),
        "started_at": _to_float(payload.get("started_at", 0.0), 0.0),
        "host": str(payload.get("host", "unknown")),
    }


def _workload_from_lock_key(lock_key: str) -> GpuWorkload | None:
    normalized = lock_key.strip().lower()
    if normalized.endswith("qwen3_tts"):
        return "qwen3_tts"
    if normalized.endswith("rvc"):
        return "rvc"
    if normalized.endswith("kenburns"):
        return "kenburns"
    return None


def _program_row_for_workload(workload: str) -> str:
    normalized = workload.strip().lower()
    if normalized == "rvc":
        return "RVC"
    if normalized == "kenburns":
        return "KenBurns"
    return "QWEN3_TTS"


if __name__ == "__main__":
    raise SystemExit(main())

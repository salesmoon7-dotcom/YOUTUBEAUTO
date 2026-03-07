from __future__ import annotations

import json
import os
import socket
import tempfile
from typing import cast
from dataclasses import dataclass
from pathlib import Path
from time import time

from runtime_v2.config import GpuWorkload, RuntimeConfig


WORKLOAD_LOCK_KEYS: dict[GpuWorkload, str] = {
    "qwen3_tts": "lock:qwen3_tts",
    "rvc": "lock:rvc",
    "kenburns": "lock:kenburns",
}


def lease_key_for_workload(workload: GpuWorkload) -> str:
    return WORKLOAD_LOCK_KEYS[workload]


def lease_file_for_workload(config: RuntimeConfig, workload: GpuWorkload) -> Path:
    return config.lock_root / f"{workload}.lease.json"


def lock_file_for_workload(config: RuntimeConfig, workload: GpuWorkload) -> Path:
    return config.lock_root / f"{workload}.lock"


def lease_store_for_workload(config: RuntimeConfig, workload: GpuWorkload) -> "LeaseStore":
    lock_stale_sec = getattr(config, "lock_mutex_stale_sec", 30)
    return LeaseStore(
        lease_file=lease_file_for_workload(config, workload),
        lock_file=lock_file_for_workload(config, workload),
        lock_stale_sec=int(lock_stale_sec) if isinstance(lock_stale_sec, (int, float, str)) else 30,
    )


@dataclass(slots=True)
class Lease:
    key: str
    owner: str
    token: int
    expires_at: float
    run_id: str
    pid: int
    started_at: float
    host: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "owner": self.owner,
            "token": self.token,
            "expires_at": self.expires_at,
            "run_id": self.run_id,
            "pid": self.pid,
            "started_at": self.started_at,
            "host": self.host,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "Lease":
        token_value = payload.get("token", 0)
        expires_at_value = payload.get("expires_at", 0.0)
        pid_value = payload.get("pid", 0)
        started_at_value = payload.get("started_at", 0.0)
        return cls(
            key=str(payload["key"]),
            owner=str(payload["owner"]),
            token=int(token_value if isinstance(token_value, (int, float, str)) else 0),
            expires_at=float(
                expires_at_value
                if isinstance(expires_at_value, (int, float, str))
                else 0.0
            ),
            run_id=str(payload.get("run_id", "unknown")),
            pid=int(pid_value if isinstance(pid_value, (int, float, str)) else 0),
            started_at=float(
                started_at_value if isinstance(started_at_value, (int, float, str)) else 0.0
            ),
            host=str(payload.get("host", "unknown")),
        )


class LeaseStore:
    def __init__(
        self,
        lease_file: Path | None = None,
        lock_file: Path | None = None,
        lock_stale_sec: int = 30,
    ) -> None:
        self._leases: dict[str, Lease] = {}
        self._token: int = 0
        self._lease_file: Path | None = lease_file
        self._lock_file: Path | None = lock_file
        self._lock_stale_sec: int = lock_stale_sec

    def acquire(
        self,
        key: str,
        owner: str,
        ttl_sec: int = 180,
        run_id: str = "unknown",
        pid: int | None = None,
        started_at: float | None = None,
        host: str | None = None,
    ) -> Lease | None:
        now = time()
        if not self._acquire_lock_file():
            return None
        try:
            self._recover_stale(key, now)
            current = self._leases.get(key)
            if current and current.expires_at > now:
                return None
            self._token += 1
            lease = Lease(
                key=key,
                owner=owner,
                token=self._token,
                expires_at=now + ttl_sec,
                run_id=run_id,
                pid=os.getpid() if pid is None else pid,
                started_at=now if started_at is None else started_at,
                host=socket.gethostname() if host is None else host,
            )
            self._leases[key] = lease
            self._persist(lease)
            return lease
        finally:
            self._release_lock_file()

    def renew(self, key: str, owner: str, token: int, ttl_sec: int = 180) -> Lease | None:
        now = time()
        if not self._acquire_lock_file():
            return None
        try:
            self._recover_stale(key, now)
            current = self._leases.get(key)
            if current is None:
                return None
            if current.owner != owner or current.token != token:
                return None
            current.expires_at = now + ttl_sec
            self._persist(current)
            return current
        finally:
            self._release_lock_file()

    def release(self, key: str, owner: str, token: int | None = None) -> bool:
        if not self._acquire_lock_file():
            return False
        try:
            current = self._leases.get(key)
            if not current or current.owner != owner:
                return False
            if token is not None and current.token != token:
                return False
            del self._leases[key]
            self._remove_persisted(key)
            return True
        finally:
            self._release_lock_file()

    def snapshot(self, key: str) -> Lease | None:
        now = time()
        self._recover_stale(key, now)
        return self._leases.get(key)

    def _recover_stale(self, key: str, now: float) -> None:
        current = self._leases.get(key)
        if current is not None and self._is_stale(current, now):
            del self._leases[key]

        persisted = self._load_persisted(key)
        if persisted is not None:
            self._token = max(self._token, persisted.token)
            if self._is_stale(persisted, now):
                self._remove_persisted(key)
            else:
                self._leases[key] = persisted

    def _acquire_lock_file(self) -> bool:
        if self._lock_file is None:
            return True
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        if self._lock_file.exists():
            try:
                age = time() - self._lock_file.stat().st_mtime
            except OSError:
                age = 0.0
            if age > float(self._lock_stale_sec):
                try:
                    self._lock_file.unlink()
                except OSError:
                    return False
        try:
            handle = os.open(str(self._lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        os.close(handle)
        return True

    def _release_lock_file(self) -> None:
        if self._lock_file is None or not self._lock_file.exists():
            return
        self._lock_file.unlink()

    def _is_stale(self, lease: Lease, now: float) -> bool:
        if lease.expires_at <= now:
            return True
        if lease.host == socket.gethostname() and lease.pid > 0:
            if lease.pid == os.getpid():
                return False
            if not _pid_is_alive(lease.pid):
                return True
        return False

    def _load_persisted(self, key: str) -> Lease | None:
        if self._lease_file is None or not self._lease_file.exists():
            return None
        try:
            raw_payload = cast(object, json.loads(self._lease_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw_payload, dict):
            return None
        raw_payload_dict = cast(dict[object, object], raw_payload)
        payload: dict[str, object] = {}
        for raw_name, raw_value in raw_payload_dict.items():
            payload[str(raw_name)] = raw_value
        if payload.get("key") != key:
            return None
        return Lease.from_dict(payload)

    def _persist(self, lease: Lease) -> None:
        if self._lease_file is None:
            return
        self._lease_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._lease_file.parent,
            prefix=f"{self._lease_file.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            _ = handle.write(json.dumps(lease.to_dict(), ensure_ascii=True))
            temp_path = Path(handle.name)
        _ = temp_path.replace(self._lease_file)

    def _remove_persisted(self, key: str) -> None:
        if self._lease_file is None or not self._lease_file.exists():
            return
        persisted = self._load_persisted(key)
        if persisted is not None:
            self._lease_file.unlink()


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def build_gpu_health_payload(
    workload: GpuWorkload,
    lock_key: str,
    lease: Lease | None,
    event: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "runtime": "runtime_v2",
        "workload": workload,
        "lock_key": lock_key,
        "event": event,
        "checked_at": round(time(), 3),
        "lease": None if lease is None else lease.to_dict(),
    }


def write_gpu_health_payload(payload: dict[str, object], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_file.parent,
        prefix=f"{output_file.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(output_file)
    return output_file

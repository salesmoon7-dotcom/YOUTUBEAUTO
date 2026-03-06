from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(slots=True)
class Lease:
    key: str
    owner: str
    token: int
    expires_at: float


class LeaseStore:
    def __init__(self) -> None:
        self._leases: dict[str, Lease] = {}
        self._token = 0

    def acquire(self, key: str, owner: str, ttl_sec: int = 180) -> Lease | None:
        now = time()
        current = self._leases.get(key)
        if current and current.expires_at > now:
            return None
        self._token += 1
        lease = Lease(key=key, owner=owner, token=self._token, expires_at=now + ttl_sec)
        self._leases[key] = lease
        return lease

    def release(self, key: str, owner: str) -> bool:
        current = self._leases.get(key)
        if not current or current.owner != owner:
            return False
        del self._leases[key]
        return True

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import monotonic, sleep
from types import TracebackType
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class UrlOpenResponse(Protocol):
    status: int

    def getcode(self) -> int: ...


class UrlOpenContext(Protocol):
    def __enter__(self) -> UrlOpenResponse: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


def build_n8n_webhook_response(
    status: dict[str, object],
    callback_url: str,
    run_id: str,
    mode: str,
    exit_code: int,
) -> dict[str, object]:
    """Remote n8n webhook payload contract for orchestration server."""
    return {
        "schema_version": "1.0",
        "execution_env": "remote_n8n",
        "callback_url": callback_url,
        "run_id": run_id,
        "mode": mode,
        "exit_code": exit_code,
        "ok": status.get("status") == "ok",
        "runtime": "runtime_v2",
        "status": status,
    }


def write_mock_callback(payload: dict[str, object], output_file: str) -> None:
    _ = _write_json_atomic(payload, Path(output_file))


def post_callback(
    payload: dict[str, object],
    timeout_sec: float = 5.0,
    max_attempts: int = 3,
    backoff_sec: float = 0.5,
) -> dict[str, object]:
    callback_url = str(payload.get("callback_url", ""))
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    attempts = max(1, max_attempts)
    last_error = "unknown"
    last_status_code: int | None = None
    started_at = monotonic()
    attempt = 0
    retryable = False
    for attempt in range(1, attempts + 1):
        request = Request(
            callback_url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with cast(UrlOpenContext, urlopen(request, timeout=timeout_sec)) as response:
                status_code = int(response.status or response.getcode())
                return {
                    "ok": 200 <= status_code < 300,
                    "callback_url": callback_url,
                    "attempts": attempt,
                    "status_code": status_code,
                    "retryable": False,
                    "timeout_sec": timeout_sec,
                    "max_attempts": attempts,
                    "backoff_sec": backoff_sec,
                    "duration_sec": round(monotonic() - started_at, 3),
                }
        except HTTPError as exc:
            last_status_code = int(exc.code)
            last_error = f"HTTP {exc.code}"
            retryable = 500 <= exc.code < 600
            if not retryable:
                break
        except URLError as exc:
            last_error = str(exc.reason)
            retryable = True
        except OSError as exc:
            last_error = str(exc)
            retryable = True
        if attempt < attempts and retryable:
            sleep(backoff_sec * attempt)
    result: dict[str, object] = {
        "ok": False,
        "callback_url": callback_url,
        "attempts": attempt,
        "error": last_error,
        "retryable": retryable,
        "timeout_sec": timeout_sec,
        "max_attempts": attempts,
        "backoff_sec": backoff_sec,
        "duration_sec": round(monotonic() - started_at, 3),
    }
    if last_status_code is not None:
        result["status_code"] = last_status_code
    return result


def _write_json_atomic(payload: dict[str, object], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        _ = handle.write(json.dumps(payload, ensure_ascii=True))
        temp_path = Path(handle.name)
    _ = temp_path.replace(path)
    return path

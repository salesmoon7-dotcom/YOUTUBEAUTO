from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import time
from typing import cast

from runtime_v2.contracts.job_contract import JobContract


class QueueStoreError(RuntimeError):
    pass


class QueueStore:
    def __init__(self, queue_file: Path) -> None:
        self.queue_file: Path = queue_file

    def load(self) -> list[JobContract]:
        if not self.queue_file.exists():
            return []
        try:
            raw_payload_obj = cast(
                object, json.loads(self.queue_file.read_text(encoding="utf-8"))
            )
        except json.JSONDecodeError:
            raise QueueStoreError("queue_store_invalid")
        if not isinstance(raw_payload_obj, list):
            raise QueueStoreError("queue_store_invalid")
        raw_payload = cast(list[object], raw_payload_obj)
        jobs: list[JobContract] = []
        for raw_item in raw_payload:
            if isinstance(raw_item, dict):
                item = cast(dict[object, object], raw_item)
                typed_item: dict[str, object] = {}
                for raw_key in item:
                    typed_item[str(raw_key)] = item[raw_key]
                jobs.append(JobContract.from_dict(typed_item))
        return jobs

    def save(self, jobs: list[JobContract]) -> Path:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        payload = [job.to_dict() for job in jobs]
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.queue_file.parent,
            prefix=f"{self.queue_file.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            _ = handle.write(json.dumps(payload, ensure_ascii=True))
            temp_path = Path(handle.name)
        _ = temp_path.replace(self.queue_file)
        return self.queue_file

    def next_queued(self) -> JobContract | None:
        for job in self.load():
            if job.status == "queued":
                return job
        return None

    def upsert(self, job: JobContract) -> Path:
        jobs = self.load()
        replaced = False
        for index, current in enumerate(jobs):
            if current.job_id == job.job_id:
                job.updated_at = time()
                jobs[index] = job
                replaced = True
                break
        if not replaced:
            jobs.append(job)
        return self.save(jobs)

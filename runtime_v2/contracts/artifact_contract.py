from __future__ import annotations

import hashlib
from pathlib import Path
from time import time


def artifact_record(artifact_path: Path, root: Path) -> dict[str, object]:
    resolved_artifact = artifact_path.resolve()
    resolved_root = root.resolve()
    if resolved_root not in resolved_artifact.parents and resolved_artifact != resolved_root:
        raise ValueError("artifact path must remain under configured root")
    if not resolved_artifact.exists() or not resolved_artifact.is_file():
        raise ValueError("artifact path must exist as a file")
    digest = hashlib.sha256(resolved_artifact.read_bytes()).hexdigest()
    return {
        "path": str(resolved_artifact),
        "sha256": digest,
        "created_at": round(time(), 3),
    }

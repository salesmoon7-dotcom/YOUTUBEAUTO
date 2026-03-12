from __future__ import annotations

from hashlib import sha256


TOPIC_SPEC_CONTRACT = "topic_spec"
TOPIC_SPEC_VERSION = "1.0"


def snapshot_hash_for_excel_snapshot(excel_snapshot: str) -> str:
    return sha256(excel_snapshot.encode("utf-8")).hexdigest()


def build_topic_spec(
    *,
    run_id: str,
    row_ref: str,
    topic: str,
    status_snapshot: str,
    excel_snapshot: str,
    bgm: str = "",
    url: str = "",
    ref_img_1: str = "",
    ref_img_2: str = "",
    videos: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract": TOPIC_SPEC_CONTRACT,
        "contract_version": TOPIC_SPEC_VERSION,
        "run_id": run_id,
        "row_ref": row_ref,
        "topic": topic.strip(),
        "status_snapshot": status_snapshot.strip(),
        "excel_snapshot_hash": snapshot_hash_for_excel_snapshot(excel_snapshot),
    }
    if bgm.strip():
        payload["bgm"] = bgm.strip()
    if url.strip():
        payload["url"] = url.strip()
    if ref_img_1.strip():
        payload["ref_img_1"] = ref_img_1.strip()
    if ref_img_2.strip():
        payload["ref_img_2"] = ref_img_2.strip()
    normalized_videos = [item.strip() for item in (videos or []) if item.strip()]
    if normalized_videos:
        payload["videos"] = normalized_videos
    return payload


def validate_topic_spec(payload: dict[str, object]) -> tuple[bool, list[str]]:
    required = ["run_id", "row_ref", "topic", "status_snapshot", "excel_snapshot_hash"]
    missing = [key for key in required if key not in payload]
    if "topic" in payload and not str(payload.get("topic", "")).strip():
        missing.append("topic")
    if "run_id" in payload and not str(payload.get("run_id", "")).strip():
        missing.append("run_id")
    if "row_ref" in payload and not str(payload.get("row_ref", "")).strip():
        missing.append("row_ref")
    if (
        "excel_snapshot_hash" in payload
        and not str(payload.get("excel_snapshot_hash", "")).strip()
    ):
        missing.append("excel_snapshot_hash")
    if str(payload.get("contract", "")).strip() != TOPIC_SPEC_CONTRACT:
        missing.append("contract")
    if str(payload.get("contract_version", "")).strip() != TOPIC_SPEC_VERSION:
        missing.append("contract_version")
    return (len(missing) == 0, missing)

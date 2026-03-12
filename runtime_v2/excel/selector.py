from __future__ import annotations

from pathlib import Path

from runtime_v2.contracts.topic_spec import build_topic_spec
from runtime_v2.excel.source import read_excel_row, read_excel_rows


PENDING_STATUSES = {"", "partial", "failed", "nan"}


def row_ref(sheet_name: str, row_index: int) -> str:
    return f"{sheet_name}!row{row_index + 1}"


def _lookup_value(row_map: dict[str, object], field_name: str) -> object:
    normalized_target = field_name.strip().lower()
    for key, value in row_map.items():
        if key.strip().lower() == normalized_target:
            return value
    return ""


def _optional_text(row_map: dict[str, object], field_name: str) -> str:
    raw_value = _lookup_value(row_map, field_name)
    return "" if raw_value is None else str(raw_value).strip()


def _video_values(row_map: dict[str, object]) -> list[str]:
    videos: list[str] = []
    for index in range(1, 51):
        value = _optional_text(row_map, f"Video{index}")
        if value:
            videos.append(value)
    return videos


def select_topic_spec(
    excel_path: str | Path,
    *,
    sheet_name: str,
    row_index: int,
    run_id: str,
) -> dict[str, object] | None:
    row_map = read_excel_row(excel_path, sheet_name=sheet_name, row_index=row_index)
    raw_topic = _lookup_value(row_map, "Topic")
    raw_status = _lookup_value(row_map, "Status")
    topic = "" if raw_topic is None else str(raw_topic).strip()
    status = "" if raw_status is None else str(raw_status).strip()
    if not topic:
        return None
    if status.lower() not in PENDING_STATUSES:
        return None
    snapshot = f"{topic}|{status}|{sheet_name}|{row_index}"
    return build_topic_spec(
        run_id=run_id,
        row_ref=row_ref(sheet_name, row_index),
        topic=topic,
        status_snapshot=status,
        excel_snapshot=snapshot,
        bgm=_optional_text(row_map, "BGM"),
        url=_optional_text(row_map, "URL"),
        ref_img_1=_optional_text(row_map, "Ref Img 1"),
        ref_img_2=_optional_text(row_map, "Ref Img 2"),
        videos=_video_values(row_map),
    )


def select_pending_row_indexes(
    excel_path: str | Path,
    *,
    sheet_name: str,
    limit: int,
) -> list[int]:
    if limit <= 0:
        return []
    row_maps = read_excel_rows(excel_path, sheet_name=sheet_name)
    selected: list[int] = []
    for index, row_map in enumerate(row_maps):
        raw_topic = _lookup_value(row_map, "Topic")
        raw_status = _lookup_value(row_map, "Status")
        topic = "" if raw_topic is None else str(raw_topic).strip()
        status = "" if raw_status is None else str(raw_status).strip()
        if not topic:
            continue
        if status.lower() not in PENDING_STATUSES:
            continue
        selected.append(index)
        if len(selected) >= limit:
            break
    return selected

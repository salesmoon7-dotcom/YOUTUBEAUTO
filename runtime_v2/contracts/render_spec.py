from __future__ import annotations


def build_render_spec(
    *,
    run_id: str,
    row_ref: str,
    asset_refs: list[str],
    timeline: list[dict[str, object]],
    audio_refs: list[str],
    thumbnail_refs: list[str],
    reason_code: str,
) -> dict[str, object]:
    return {
        "contract": "render_spec",
        "contract_version": "1.1",
        "run_id": run_id,
        "row_ref": row_ref,
        "asset_refs": asset_refs,
        "timeline": timeline,
        "audio_refs": audio_refs,
        "thumbnail_refs": thumbnail_refs,
        "reason_code": reason_code,
    }

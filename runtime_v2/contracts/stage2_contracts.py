from __future__ import annotations


def build_stage2_payload(
    *,
    run_id: str,
    row_ref: str,
    scene_index: int,
    prompt: str,
    asset_root: str,
    reason_code: str,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "row_ref": row_ref,
        "scene_index": scene_index,
        "prompt": prompt,
        "asset_root": asset_root,
        "reason_code": reason_code,
    }

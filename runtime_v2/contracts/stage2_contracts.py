from __future__ import annotations


def build_stage2_payload(
    *,
    run_id: str,
    row_ref: str,
    scene_index: int,
    prompt: str,
    asset_root: str,
    reason_code: str,
    ref_img_1: str = "",
    ref_img_2: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": run_id,
        "row_ref": row_ref,
        "scene_index": scene_index,
        "prompt": prompt,
        "asset_root": asset_root,
        "reason_code": reason_code,
    }
    if ref_img_1.strip():
        payload["ref_img_1"] = ref_img_1.strip()
    if ref_img_2.strip():
        payload["ref_img_2"] = ref_img_2.strip()
    return payload

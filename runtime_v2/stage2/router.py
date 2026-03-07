from __future__ import annotations

from runtime_v2.stage2.json_builders import build_stage2_jobs


def route_video_plan(video_plan: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object]]:
    return build_stage2_jobs(video_plan)

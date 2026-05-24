# Legacy vs Runtime_v2 Coverage Map

Goal: Compare the actual legacy program inventory against the current `runtime_v2` implementation/documentation surface, so completion claims can be made against the full legacy map instead of only the currently active closeout chain.

## Coverage Status Key

- `Covered` - runtime_v2 has an explicit program/worker/backend path plus evidence-backed docs/tests.
- `Partially Covered` - runtime_v2 has some explicit code/docs, but the legacy surface is broader than the current runtime coverage or evidence is still partial.
- `Not Covered` - no meaningful runtime_v2 counterpart is currently documented or evidenced.
- `Hold` - code exists, but current truthful blocker is intentionally deferred and should not be used for completion claims.

## Program Coverage Matrix

| Legacy Program | Legacy Entrypoint | Runtime_v2 Counterpart | Current Coverage | Evidence |
|---|---|---|---|---|
| ChatGPT | `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py` | `runtime_v2/stage1/chatgpt_backend.py`, `runtime_v2/stage1/chatgpt_interaction.py`, `runtime_v2/stage1/chatgpt_runner.py` | Covered | `docs/COMPLETED.md` records real-first success, handoff bridge, backend interface, parser and gating work; active closeout reruns now pass stage1 |
| Qwen3 TTS | `D:\YOUTUBE_AUTO\scripts\qwen3_tts_automation.py` | `runtime_v2/workers/qwen3_worker.py` | Covered | `docs/COMPLETED.md` documents canonical worker evidence and current reruns complete qwen successfully |
| Genspark | `D:\YOUTUBE_AUTO\scripts\genspark_automation.py` | `runtime_v2/stage2/genspark_worker.py`, `runtime_v2/cli.py`, `runtime_v2/stage2/agent_browser_adapter.py` | Covered | `docs/COMPLETED.md`, recent commits `06dce73` and `c4d4d4b`, and fresh rerun evidence show `genspark ref-1` and main image jobs now close truthfully |
| SeaArt | `D:\YOUTUBE_AUTO\scripts\seaart_automation.py` | `runtime_v2/stage2/seaart_worker.py` | Covered | `docs/COMPLETED.md` documents functional verification and fresh rerun evidence shows ref/main SeaArt jobs complete |
| GeminiGen | `D:\YOUTUBE_AUTO\scripts\geminigen_automation.py` | `runtime_v2/stage2/geminigen_worker.py` | Covered | hidden legacy `--repair-session`, reboot-safe browser recover, bounded page-context fetch fallback, truthful probe-result/render-spec contracts, and fresh logged-in proof `D:\YOUTUBEAUTO_RUNTIME\probe\geminigen-login-proof-20260519-a\probe_result.json` now show live GeminiGen generation closing as `OK` |
| Canva | `D:\YOUTUBE_AUTO\scripts\canva_automation.py` | `runtime_v2/stage2/canva_worker.py`, `runtime_v2/workers/agent_browser_worker.py`, `runtime_v2/cli.py` | Hold | fresh isolated boundary `D:\YOUTUBEAUTO_RUNTIME\probe\canva-boundary-20260524-e\runtime\artifacts\canva\canva-canva-boundary-20260524-e-3\canva-boundary-20260524-e\result.json` and earlier row15 evidence `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\probe_result.json` both pin the truthful blocker as `CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED`; latest explicit-job rerun also leaves canonical runtime snapshots (`latest_completed_run.json`, `evidence/result.json`, `health/gui_status.json`) aligned to the same credit gate, so the remaining blocker is a live Product Background OOPIF credit purchase gate and must not be counted as done |
| Ken Burns | `D:\YOUTUBE_AUTO\scripts\ken_burns_effect.py` | `runtime_v2/workers/kenburns_worker.py` | Covered | `docs/COMPLETED.md` records actual kenburn artifact evidence |
| Render | `D:/YOUTUBE_AUTO/scripts/render.py` | `runtime_v2/stage3/render_worker.py` | Covered | `run_render_job()` now has focused parity proof for blocked audio-not-ready, timeline ffmpeg + mux, optional BGM overlay, audio concat, and canonical audio fallback, with manual QA confirming deterministic final artifact behavior |
| RVC / Applio | `D:\YOUTUBE_AUTO\scripts\rvc_voice_convert.py`, `D:\YOUTUBE_AUTO\scripts\applio_server_manager.py` | `runtime_v2/workers/rvc_worker.py` | Covered | `docs/COMPLETED.md` records canonical worker evidence and exploratory functional verification |
| VoiceVox | `D:/YOUTUBE_AUTO/scripts/voicevox_automation.py` | `runtime_v2/workers/voicevox_worker.py`, `runtime_v2/control_plane.py`, `runtime_v2/control_plane_feeder.py` | Covered | explicit `voicevox` workload/worker exists, dispatch is registered, inbox contracts are allowed, and GPU lease identity is intentionally shared with `qwen3_tts` |
| Vrew | `D:\YOUTUBE_AUTO\scripts\vrew_web_automation.py` | no direct runtime_v2 program surface | Not Covered | No explicit `runtime_v2` Vrew worker/backend was found in code/docs |
| ACE BGM | `D:\YOUTUBE_AUTO\scripts\ace_bgm_automation.py` | no direct runtime_v2 worker | Not Covered | No explicit ACE/BGM worker surfaced in runtime_v2 code; docs only mention BGM as part of payload/content contracts |
| Google Sheets sync | `D:/YOUTUBE_AUTO/scripts/google_sheets_sync.py` | `runtime_v2/workers/google_sheets_sync_worker.py`, `runtime_v2/excel/source.py`, `runtime_v2/control_plane.py`, `runtime_v2/control_plane_feeder.py` | Deprecated | User explicitly said Google Sheets sync is not used; exclude it from active migration targets and completion range |
| n8n / Mybox upload | `D:/YOUTUBE_AUTO/scripts/n8n_mybox_upload.py` | `runtime_v2/workers/n8n_upload_worker.py`, `runtime_v2/n8n_adapter.py`, `runtime_v2/control_plane.py`, `runtime_v2/control_plane_feeder.py` | Covered | explicit `n8n_upload` local workload exists, dispatches through control plane, validates local artifact inputs, and bridges deterministically to the callback transport |
| Supervisor / scheduler / session orchestration | `D:\YOUTUBE_AUTO\scripts\supervisor.py`, `scheduler.py`, `session_manager.py`, `retry_queue.py` | `runtime_v2/supervisor.py`, `runtime_v2/browser/supervisor.py`, `runtime_v2/browser/manager.py`, `runtime_v2/queue_store.py` | Covered | multiple completed batches document browser plane, queue persistence, retry, and orchestration responsibilities in runtime_v2 |
| Timeline / SRT / shorts ops | `D:/YOUTUBE_AUTO/scripts/timeline_generator.py`, `D:/YOUTUBE_AUTO/scripts/srt_generator.py`, `D:/YOUTUBE_AUTO/scripts/shorts_render.py` | `runtime_v2/workers/timeline_worker.py`, `runtime_v2/workers/srt_worker.py`, `runtime_v2/workers/shorts_render_worker.py` (explicit timeline + SRT + shorts workloads) | Covered | explicit `timeline`, `srt`, and `shorts_render` local workloads now exist with dispatch paths, inbox allow-lists, deterministic artifact generation, and focused/manual verification for each legacy surface |

## What This Means For Completion Claims

### Safe claim
You may say: the active migration range is now passing through the non-Canva chain, including GeminiGen, and the remaining top-level hold is Canva.

### Unsafe claim
Do **not** say: all non-Canva legacy programs are fully complete.

That stronger claim would still overstate the current runtime_v2 coverage if it included deprecated or intentionally deferred surfaces (for example `Canva` hold, or deprecated `Vrew` / `ACE BGM` / `Google Sheets sync`). Fresh `D:\YOUTUBEAUTO_RUNTIME\probe\geminigen-login-proof-20260519-a\probe_result.json` removes `GeminiGen` from that partially-covered set for the active migration range.

## Practical Rule Going Forward

Before saying a legacy area is done, compare against both:
1. `docs/plans/2026-04-23-legacy-program-inventory-map.md`
2. this coverage map

That keeps two questions separate:
- what exists in legacy?
- what runtime_v2 actually covers right now?

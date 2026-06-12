# Legacy vs Runtime_v2 Coverage Map

Goal: Compare the actual legacy program inventory against the current `runtime_v2` implementation/documentation surface, so completion claims can be made against the full legacy map instead of only the currently active closeout chain.

## Coverage Status Key

- `Covered` - runtime_v2 has an explicit program/worker/backend path plus evidence-backed docs/tests.
- `Partially Covered` - runtime_v2 has some explicit code/docs, but the legacy surface is broader than the current runtime coverage or evidence is still partial.
- `E2E Unverified` - component source/probe/doc evidence may exist, but accepted user-visible Excel-driven end-to-end execution is not proven.
- `Not Covered` - no meaningful runtime_v2 counterpart is currently documented or evidenced.
- `Hold` - code exists, but current truthful blocker is intentionally deferred and should not be used for completion claims.

## Program Coverage Matrix

| Legacy Program | Legacy Entrypoint | Runtime_v2 Counterpart | Current Coverage | Evidence |
|---|---|---|---|---|
| ChatGPT | `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py` | `runtime_v2/stage1/chatgpt_backend.py`, `runtime_v2/stage1/chatgpt_interaction.py`, `runtime_v2/stage1/chatgpt_runner.py` | E2E Unverified | component source/probe/doc evidence exists, but accepted Excel-driven E2E completion through final render is not proven |
| Qwen3 TTS | `D:\YOUTUBE_AUTO\scripts\qwen3_tts_automation.py` | `runtime_v2/workers/qwen3_worker.py` | E2E Unverified | worker/source evidence exists, but actual local voice stage completion inside the accepted Excel-driven E2E chain is not proven |
| Genspark | `D:\YOUTUBE_AUTO\scripts\genspark_automation.py` | `runtime_v2/stage2/genspark_worker.py`, `runtime_v2/cli.py`, `runtime_v2/stage2/agent_browser_adapter.py` | E2E Unverified | source/probe/doc evidence exists, but accepted image-service execution inside the full Excel-driven E2E chain is not proven |
| SeaArt | `D:\YOUTUBE_AUTO\scripts\seaart_automation.py` | `runtime_v2/stage2/seaart_worker.py` | E2E Unverified | source/probe/doc evidence exists, but accepted image-service execution inside the full Excel-driven E2E chain is not proven |
| GeminiGen | `D:\YOUTUBE_AUTO\scripts\geminigen_automation.py` | `runtime_v2/stage2/geminigen_worker.py` | E2E Unverified | component/probe evidence exists, but accepted GeminiGen execution inside the Excel-driven E2E target is not proven |
| Canva | `D:\YOUTUBE_AUTO\scripts\canva_automation.py` | `runtime_v2/stage2/canva_worker.py`, `runtime_v2/workers/agent_browser_worker.py`, `runtime_v2/cli.py` | Hold | fresh isolated boundary `D:\YOUTUBEAUTO_RUNTIME\probe\canva-boundary-20260524-e\runtime\artifacts\canva\canva-canva-boundary-20260524-e-3\canva-boundary-20260524-e\result.json` and earlier row15 evidence `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\probe_result.json` both pin the truthful blocker as `CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED`; latest explicit-job rerun also leaves canonical runtime snapshots (`latest_completed_run.json`, `evidence/result.json`, `health/gui_status.json`) aligned to the same credit gate, so the remaining blocker is a live Product Background OOPIF credit purchase gate and must not be counted as done |
| Ken Burns | `D:\YOUTUBE_AUTO\scripts\ken_burns_effect.py` | `runtime_v2/workers/kenburns_worker.py` | E2E Unverified | component artifact/source evidence exists, but accepted execution inside the Excel-driven E2E chain is not proven |
| Render | `D:/YOUTUBE_AUTO/scripts/render.py` | `runtime_v2/stage3/render_worker.py` | E2E Unverified | render component evidence exists, but accepted final artifact generation from the full Excel-driven E2E chain is not proven |
| RVC / Applio | `D:\YOUTUBE_AUTO\scripts\rvc_voice_convert.py`, `D:\YOUTUBE_AUTO\scripts\applio_server_manager.py` | `runtime_v2/workers/rvc_worker.py` | E2E Unverified | worker/source evidence exists, but accepted RVC execution inside the Excel-driven E2E chain is not proven |
| VoiceVox | `D:/YOUTUBE_AUTO/scripts/voicevox_automation.py` | `runtime_v2/workers/voicevox_worker.py`, `runtime_v2/control_plane.py`, `runtime_v2/control_plane_feeder.py` | E2E Unverified | workload/dispatch source evidence exists, but accepted local TTS execution inside the Excel-driven E2E chain is not proven |
| Vrew | `D:\YOUTUBE_AUTO\scripts\vrew_web_automation.py` | no direct runtime_v2 program surface | Not Covered | No explicit `runtime_v2` Vrew worker/backend was found in code/docs |
| ACE BGM | `D:\YOUTUBE_AUTO\scripts\ace_bgm_automation.py` | no direct runtime_v2 worker | Not Covered | No explicit ACE/BGM worker surfaced in runtime_v2 code; docs only mention BGM as part of payload/content contracts |
| Google Sheets sync | `D:/YOUTUBE_AUTO/scripts/google_sheets_sync.py` | `runtime_v2/workers/google_sheets_sync_worker.py`, `runtime_v2/excel/source.py`, `runtime_v2/control_plane.py`, `runtime_v2/control_plane_feeder.py` | Deprecated | User explicitly said Google Sheets sync is not used; exclude it from active migration targets and completion range |
| n8n / Mybox upload | `D:/YOUTUBE_AUTO/scripts/n8n_mybox_upload.py` | `runtime_v2/workers/n8n_upload_worker.py`, `runtime_v2/n8n_adapter.py`, `runtime_v2/control_plane.py`, `runtime_v2/control_plane_feeder.py` | Covered | explicit `n8n_upload` local workload exists, dispatches through control plane, validates local artifact inputs, and bridges deterministically to the callback transport |
| Supervisor / scheduler / session orchestration | `D:\YOUTUBE_AUTO\scripts\supervisor.py`, `scheduler.py`, `session_manager.py`, `retry_queue.py` | `runtime_v2/supervisor.py`, `runtime_v2/browser/supervisor.py`, `runtime_v2/browser/manager.py`, `runtime_v2/queue_store.py` | Covered | multiple completed batches document browser plane, queue persistence, retry, and orchestration responsibilities in runtime_v2 |
| Timeline / SRT / shorts ops | `D:/YOUTUBE_AUTO/scripts/timeline_generator.py`, `D:/YOUTUBE_AUTO/scripts/srt_generator.py`, `D:/YOUTUBE_AUTO/scripts/shorts_render.py` | `runtime_v2/workers/timeline_worker.py`, `runtime_v2/workers/srt_worker.py`, `runtime_v2/workers/shorts_render_worker.py` (explicit timeline + SRT + shorts workloads) | Covered | explicit `timeline`, `srt`, and `shorts_render` local workloads now exist with dispatch paths, inbox allow-lists, deterministic artifact generation, and focused/manual verification for each legacy surface |

## What This Means For Completion Claims

### Safe claim
You may say: source/probe/doc coverage claims exist for several components, but accepted user-visible Excel-driven E2E execution remains unverified.

### Unsafe claim
Do **not** say: the non-Canva chain, row15 closeout, GeminiGen, local voice, or final render path is complete as a user-visible Excel-driven E2E program.

That stronger claim would overstate the current runtime_v2 coverage because the accepted Excel row -> GPT -> image services -> GeminiGen -> local voice/TTS/RVC -> render path has not been proven by user-visible E2E execution.

## Practical Rule Going Forward

Before saying a legacy area is done, compare against both:
1. `docs/plans/2026-04-23-legacy-program-inventory-map.md`
2. this coverage map

That keeps two questions separate:
- what exists in legacy?
- what runtime_v2 actually covers right now?

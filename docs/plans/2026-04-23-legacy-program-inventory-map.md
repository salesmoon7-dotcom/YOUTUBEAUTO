# Legacy Program Inventory Map

Goal: Rebuild the actual legacy program map from `D:\YOUTUBE_AUTO` and compare it against the program set implied by current `runtime_v2` docs.

## What The Current Docs Explicitly Track

Current docs repeatedly talk about the following runtime/service programs:
- ChatGPT
- Qwen3 TTS
- Genspark
- SeaArt
- GeminiGen
- Canva
- Kenburns
- RVC
- TTS / audio-related stages
- Render

Primary doc evidence:
- `docs/TODO.md` lines 226-233 list non-GPT program status buckets for `SeaArt`, `Genspark`, `Canva`, `TTS`, `GeminiGen`, `Kenburn`, `RVC`.
- `docs/plans/2026-04-13-runtime-v2-handoff.md` centers active execution context around `chatgpt`, `qwen`, `genspark`, and `canva`, but does not present a full inventory table.

## Actual Legacy Program Inventory From `D:\YOUTUBE_AUTO\scripts`

The following programs are directly evidenced by entrypoint scripts and top-of-file headers/docstrings.

### Core browser / service automation programs

| Program | Legacy entrypoint | Evidence |
|---|---|---|
| ChatGPT | `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py` | Header: `ChatGPT AI Automation Tool`; input/output contract documented in file header |
| Qwen3 TTS | `D:\YOUTUBE_AUTO\scripts\qwen3_tts_automation.py` | Header: `Qwen3 TTS automation (VOICEVOX-compatible flow).` |
| Genspark | `D:\YOUTUBE_AUTO\scripts\genspark_automation.py` | Header: `Genspark 이미지 생성 자동화 프로그램` |
| SeaArt | `D:\YOUTUBE_AUTO\scripts\seaart_automation.py` | Header: `SeaArt 이미지 생성 자동화 프로그램` |
| GeminiGen | `D:\YOUTUBE_AUTO\scripts\geminigen_automation.py` | Header: `GeminiGen.ai 동영상 생성 자동화 프로그램` |
| Canva | `D:\YOUTUBE_AUTO\scripts\canva_automation.py` | Header: `Canva 썸네일 자동 생성 프로그램` |
| VoiceVox | `D:\YOUTUBE_AUTO\scripts\voicevox_automation.py` | Header indicates VOICEVOX voice generation automation |
| Vrew | `D:\YOUTUBE_AUTO\scripts\vrew_web_automation.py` | Header: `Vrew 웹 자동화 (Selenium + pyautogui)` |

### Core post-processing / media pipeline programs

| Program | Legacy entrypoint | Evidence |
|---|---|---|
| Ken Burns | `D:\YOUTUBE_AUTO\scripts\ken_burns_effect.py` | Header: `Ken Burns 효과 (팬 & 줌) FFmpeg 래퍼 모듈` |
| Render | `D:\YOUTUBE_AUTO\scripts\render.py` | Header: `FFmpeg + Whisper 렌더링 파이프라인` |
| RVC / Applio | `D:\YOUTUBE_AUTO\scripts\rvc_voice_convert.py` | Header: `RVC 음성 변환 자동화 (Applio CLI 래퍼).` |
| ACE BGM | `D:\YOUTUBE_AUTO\scripts\ace_bgm_automation.py` | Header indicates ACE-Step 1.5 BGM automation |

### Supporting orchestration / ops programs that also matter

These are not just random helpers; they are part of the operational legacy surface and should not be ignored when comparing legacy to runtime_v2:
- `D:\YOUTUBE_AUTO\scripts\supervisor.py`
- `D:\YOUTUBE_AUTO\scripts\session_manager.py`
- `D:\YOUTUBE_AUTO\scripts\scheduler.py`
- `D:\YOUTUBE_AUTO\scripts\retry_queue.py`
- `D:\YOUTUBE_AUTO\scripts\timeline_generator.py`
- `D:\YOUTUBE_AUTO\scripts\srt_generator.py`
- `D:\YOUTUBE_AUTO\scripts\google_sheets_sync.py`
- `D:\YOUTUBE_AUTO\scripts\n8n_mybox_upload.py`
- `D:\YOUTUBE_AUTO\scripts\applio_server_manager.py`
- `D:\YOUTUBE_AUTO\scripts\shorts_render.py`
- `D:\YOUTUBE_AUTO\scripts\run_stage2_cli.py`

## Where Current Docs Are Too Narrow

### 1. Docs center active blockers, not the whole program map
`docs/plans/2026-04-13-runtime-v2-handoff.md` is useful for current execution state, but it is not a reliable inventory of all legacy programs.

### 2. Non-Canva gap was partly a map problem
A lot of recent reasoning focused on `chatgpt / qwen / genspark / canva`, but the actual legacy estate is wider and includes at least:
- `GeminiGen`
- `VoiceVox`
- `Vrew` (deprecated / no longer an active migration target)
- `ACE BGM` (deprecated / no longer an active migration target)
- `google_sheets_sync`
- `n8n_mybox_upload`
- `shorts_render`
- orchestration/ops modules like `supervisor`, `scheduler`, `retry_queue`, `session_manager`

### 3. TODO has status buckets but not a canonical inventory table
`docs/TODO.md` contains status-oriented mentions, but not a one-glance legacy program inventory table that says what each program is and what its representative legacy entrypoint is.

## Correction To Use Going Forward

### Actual Program Target

The program being developed is an Excel-driven end-to-end automation pipeline:

`Excel row -> GPT text/plan -> image generation services -> GeminiGen video -> local voice/TTS/RVC -> render/final artifact`

Completion claims must be made against this whole target. Component source, probe, or documentation evidence is not enough to claim the user-visible program is complete.

When we say legacy program analysis, the minimum inventory should include:
- ChatGPT
- Qwen3 TTS
- Genspark
- SeaArt
- GeminiGen
- Canva
- Ken Burns
- Render
- RVC / Applio
- VoiceVox
- Vrew
- ACE BGM
- Sheets / n8n upload surfaces
- scheduler / supervisor / session / retry orchestration surfaces

## Practical Rule

Before saying all non-Canva work is done, compare against this inventory rather than only the currently active closeout chain.

Deprecated by current user direction and therefore excluded from active migration targeting:
- `Vrew`
- `ACE BGM`
- `Google Sheets sync`

That does not mean every listed program has an open blocker right now.
It means the legacy map must be understood at this broader program level before making completion claims.

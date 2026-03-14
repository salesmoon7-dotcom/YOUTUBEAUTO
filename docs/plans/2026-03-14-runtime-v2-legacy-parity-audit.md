# Runtime V2 Legacy Parity Audit

## Scope

This document records the actual parity audit results for browser services and local subprograms.

Status legend:
- `MATCHED` = runtime_v2 is confirmed equivalent to legacy for this item
- `DIFFERS-A` = observable behavior/output/settings differ from legacy and must be fixed or explicitly accepted
- `DIFFERS-B` = internal implementation differs, but observable behavior may still be equivalent
- `UNKNOWN-PATH` = legacy source/config path is not yet pinned precisely enough
- `UNKNOWN-EVIDENCE` = source path is known, but direct comparison evidence is still missing

Audit completion rule:
- `UNKNOWN-PATH = 0`
- `UNKNOWN-EVIDENCE = 0`
- every `DIFFERS-A` item is either fixed or explicitly accepted with reason/impact/test note
- every `DIFFERS-B` item is explicitly confirmed as behavior-equivalent or reclassified

---

## 1. Browser Services

### 1.1 ChatGPT

Legacy source:
- `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py`

Runtime_v2 source:
- `runtime_v2/browser/manager.py`
- `runtime_v2/stage1/chatgpt_backend.py`
- `runtime_v2/stage1/chatgpt_interaction.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Browser family | `undetected_chromedriver` in `chatgpt_automation.py` | browser plane config in `runtime_v2/browser/manager.py` | DIFFERS-B | runtime_v2 uses managed browser-plane abstraction rather than legacy direct Selenium/UC launch |
| Initial URL | custom GPT URL in `chatgpt_automation.py:82-109` | `SERVICE_TARGETS['chatgpt']` in `runtime_v2/browser/manager.py:17-21` | MATCHED | same GPT endpoint |
| Logged-in session/profile persistence | legacy session backup/reuse logic in `chatgpt_automation.py` | runtime_v2 browser plane profile/session management | UNKNOWN-EVIDENCE | same intent, but exact profile semantics need direct path/launch comparison |
| Prompt submit semantics | Selenium input/send flow in `chatgpt_automation.py` | `AgentBrowserCdpBackend.submit_prompt()` in `runtime_v2/stage1/chatgpt_backend.py` | DIFFERS-B | runtime_v2 uses CDP/eval + state polling instead of Selenium actions |
| Output capture contract | raw DOM/html parsing in legacy | `raw_output.json`, `parsed_payload.json`, `stage1_handoff.json` in runtime_v2 | DIFFERS-B | runtime_v2 uses stricter contract/evidence layer |

### 1.2 Genspark

Legacy source:
- `D:\YOUTUBE_AUTO\scripts\genspark_automation.py`

Runtime_v2 source:
- `runtime_v2/browser/manager.py`
- `runtime_v2/workers/agent_browser_worker.py`
- `runtime_v2/agent_browser/cdp_capture.py`
- `runtime_v2/cli.py`
- `runtime_v2/stage2/genspark_worker.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Initial URL | `GENSPARK_URL = https://www.genspark.ai/agents?type=image_generation_agent` | `SERVICE_TARGETS['genspark'].start_url = https://www.genspark.ai/` | DIFFERS-A | runtime_v2 starts broader and then narrows by expected URL contract |
| Browser family / port | Selenium Edge, `EDGE_DEBUG_PORT = get_port('genspark_edge')` | runtime_v2 browser plane + `genspark` session in manager/preflight | UNKNOWN-EVIDENCE | port intent is similar, but browser family/profile mapping still needs direct confirmation |
| Prompt input field | `textarea.j-search-input` in legacy | same selector via `cli.py` / agent-browser actions | MATCHED | selector aligned |
| Generate/submit semantics | legacy Selenium click flow on `.enter-icon-wrapper` | runtime_v2 eval/native setter + Enter + CTA retry | DIFFERS-A | runtime_v2 is currently more defensive/contract-heavy than legacy |
| Result tab/card handling | legacy dedicated automation assumptions around generated image area | runtime_v2 currently required multiple fixes for compose/result/one-tab selection | DIFFERS-A | this was the main live blocker area |
| Artifact capture target | legacy uses chat image / asset selectors and download flow | runtime_v2 uses CDP capture + fallback + fresh result selection | DIFFERS-A | same goal, different implementation and stricter fail-close behavior |

### 1.3 SeaArt

Legacy source:
- `D:\YOUTUBE_AUTO\scripts\seaart_automation.py`

Runtime_v2 source:
- `runtime_v2/stage2/seaart_worker.py`
- `runtime_v2/cli.py`
- `runtime_v2/workers/agent_browser_worker.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Browser family / port | Selenium Chrome + `seaart_chrome` debug port | browser plane + `seaart` worker adapter path | UNKNOWN-EVIDENCE | exact family/profile launch needs direct parity confirmation |
| Prompt input target | `textarea.el-textarea__inner` | runtime_v2 SeaArt worker + browser adapter path | MATCHED | selector intent aligned |
| Generate button | `#generate-btn` in legacy | runtime_v2 SeaArt adapter path | MATCHED | selector intent aligned |
| Ref-image upload order | legacy upload ordering is explicit | runtime_v2 ref-image-first parity already implemented | MATCHED | contract intentionally aligned |
| Final image capture | legacy DOM/download flow | runtime_v2 adapter + truthful artifact path | DIFFERS-B | same output intent, different capture mechanism |

### 1.4 Canva

Legacy source:
- legacy thumbnail automation path under `D:\YOUTUBE_AUTO`

Runtime_v2 source:
- `runtime_v2/stage2/canva_worker.py`
- browser plane config in `runtime_v2/browser/manager.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Browser family/profile/port | `canva_automation.py:96-116` uses Chrome + `canva_chrome` session (`CANVA_CHROME_PORT`, `CANVA_SESSION_DIR`) | `runtime_v2/browser/manager.py:482-507` maps `canva -> canva_chrome`, browser family `chrome` | DIFFERS-B | browser family/session key match, but exact configured port/profile path still needs one-to-one path equality confirmation |
| Template/input/button sequence | `canva_automation.py` clones template, edits AI background/text, downloads current page PNG | runtime_v2 adapter-backed child in `runtime_v2/stage2/canva_worker.py` | UNKNOWN-EVIDENCE | legacy source path is pinned, but direct selector/button-by-button comparison still needs to be filled |
| Thumbnail artifact semantics | legacy THUMB export path | runtime_v2 `canva_worker` `service_artifact_path` contract | MATCHED | output contract aligns at high level |

### 1.5 GeminiGen

Legacy source:
- legacy video generation path under `D:\YOUTUBE_AUTO`

Runtime_v2 source:
- `runtime_v2/stage2/geminigen_worker.py`
- `runtime_v2/agent_browser/cdp_capture.py`
- `runtime_v2/cli.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Initial URL | `geminigen_automation.py:253-257` defines `generate_page_url=https://geminigen.ai/app/video-gen`, plus `/generate` and `/` alternatives | `SERVICE_TARGETS['geminigen'].start_url=https://geminigen.ai/app/video-gen` | MATCHED | main runtime_v2 start URL matches the primary legacy generate page |
| Browser family / port/profile | `geminigen_automation.py:149-152` uses UC Chrome userdata `geminigen_chrome_userdata` | `runtime_v2/browser/manager.py:483-507` maps `geminigen -> geminigen_uc/geminigen_chrome_userdata`, browser family `uc` | DIFFERS-B | browser family/session-root intent aligned, but exact configured port/profile path still needs one-to-one path equality confirmation |
| First-frame handling | legacy image-to-video flow | `geminigen_worker.py` uses `first_frame_path` | MATCHED | contract exists in both |
| Video capture/export | legacy download/export semantics plus explicit retry/cooldown/session rules in `geminigen_automation.py:153-208` | runtime_v2 truthful video capture in CDP path | DIFFERS-B | runtime_v2 is stricter about truthful artifact gate and simpler than legacy retry/session policy |

---

## 2. Local Subprograms

### 2.1 Qwen3 TTS

Legacy source:
- `D:\YOUTUBE_AUTO\scripts\qwen3_tts_automation.py`
- `D:\YOUTUBE_AUTO\system\config\qwen3_tts_config.json`

Runtime_v2 source:
- `runtime_v2/workers/qwen3_worker.py`
- `runtime_v2/preflight.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Python path | default `D:/qwen3_tts_env/Scripts/python.exe` | `preflight.py` checks same runtime path | MATCHED | path expectation aligned |
| Model id / generation defaults | `qwen3_tts_config.json` sets `model_id=Qwen/Qwen3-TTS-12Hz-1.7B-Base`, `device=cuda:0`, `dtype=float32`, `attn_implementation=eager`, `x_vector_only_mode=true` | runtime_v2 now loads and exposes the same legacy config/runtime values in worker prompt/details while invoking the same legacy script path | MATCHED | unit test + manual QA confirmed legacy runtime values are loaded and surfaced |
| Reference audio loading | legacy config uses `reference_audio_default=D:/qwen3_tts_data/raw_audio/male_extra/ref.MP3` and per-channel overrides (`4 -> same MP3`) | runtime_v2 now resolves `reference_audio_default/by_channel` and records `ref_audio_used` in worker details / adapter input | MATCHED | channel-based ref audio selection restored and manually verified on channel 4 |
| Output format | legacy config default `output_format=mp3`, but legacy script normalizes unsupported formats to `flac` (`qwen3_tts_automation.py:317-320`) | runtime_v2 now normalizes output format with the same rule and passes it through worker prompt/details | MATCHED | manual QA confirmed `mp3` config normalizes to `flac` |

### 2.2 RVC

Legacy source:
- `D:\YOUTUBE_AUTO\scripts\rvc_voice_convert.py`
- `D:\YOUTUBE_AUTO\system\config\rvc_config.json`

Runtime_v2 source:
- `runtime_v2/workers/rvc_worker.py`
- `runtime_v2/preflight.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Active model selection | `rvc_config.json` sets `active_model=jp_narrator_v1` with explicit `models` table | runtime_v2 now falls back to legacy `active_model` when `model_name` is omitted | MATCHED | unit test + manual QA confirmed `rvc_request.json.model_name = jp_narrator_v1` |
| Applio python/core path | legacy config pins `applio_python=D:/Applio/env/python.exe`, `applio_core=D:/Applio/core.py` | runtime_v2 now exposes `applio_python/applio_core` in worker request/details and preflight warnings | MATCHED | unit test + manual preflight report confirmed both paths are checked and surfaced |
| Input mode | legacy script is centered on source audio / extracted video audio flow, not explicit `tts-source` / `gemi-video-source` naming | runtime_v2 explicitly splits `tts-source` and `gemi-video-source` | DIFFERS-A | architectural and behavior difference |
| Output naming | legacy config `export_format=FLAC`, script-managed naming/trim | runtime_v2 now emits canonical `speech_rvc.flac` when legacy export format is FLAC, with `.wav` left only as compatibility fallback in downstream lookup | MATCHED | unit test + manual QA confirmed canonical RVC next-job path now uses `.flac` |

### 2.3 KenBurns

Legacy source:
- `D:\YOUTUBE_AUTO\scripts\ken_burns_effect.py`

Runtime_v2 source:
- `runtime_v2/workers/kenburns_worker.py`

Checklist:

| Item | Legacy evidence | Runtime_v2 evidence | Status | Notes |
|---|---|---|---|---|
| Output resolution | legacy default `1920x1080` | runtime_v2 `OUTPUT_WIDTH/HEIGHT = 1920x1080` | MATCHED | aligned |
| FPS | `ken_burns_effect.py` default `fps=60` | runtime_v2 `OUTPUT_FPS = 60` | MATCHED | verified with current runtime output via `ffprobe` (`60/1`) |
| Default duration | legacy default/docstring `12s` | runtime_v2 defaults to `12s` via payload fallback | MATCHED | verified with current runtime output via `ffprobe` (`12.000000`) |
| Zoom/pan defaults | legacy `zoom_ratio=1.13`, `PAN_TRAVEL_RATIO=0.40`, richer preset/effect sequence model | runtime_v2 `DEFAULT_PAN_PCT=0.40`, `DEFAULT_ZOOM_PCT=0.13`, still simplified direction/zoom model | DIFFERS-A | core numeric defaults restored and verified in ffmpeg filter, but richer preset/effect sequence model still differs |
| Upscale width | legacy default `8000` | runtime_v2 `UPSCALE_WIDTH = 8000` | MATCHED | verified in current ffmpeg filter chain |

---

## 3. Cross-cutting Findings

1. Browser services are output-contract aligned enough to pass Stage 5/5B, but several still differ from legacy in browser family, initial URL strictness, tab semantics, and capture policy.
2. Local subprogram parity is weaker than browser parity. `qwen3_tts`, `rvc`, and `kenburns` still show clear configuration/behavior deltas from legacy defaults.
3. `DIFFERS-A` items are not acceptable by default; they require either restoration to legacy behavior or explicit acceptance with reason/impact/test note.
4. `UNKNOWN-PATH` and `UNKNOWN-EVIDENCE` must both reach zero before parity audit can be declared complete.

## 4. Immediate Next Audit Actions

1. Extract the exact legacy Canva and GeminiGen browser scripts/configs and clear the `UNKNOWN-PATH` / `UNKNOWN-EVIDENCE` rows.
2. Split all remaining browser/service diffs into `DIFFERS-A` vs `DIFFERS-B` and resolve classification ambiguity.
3. Restore or explicitly accept the remaining `rvc` config-driven behavior (`input mode semantics`).
4. Decide whether `kenburns` should be aligned back toward the remaining legacy richer preset/effect-sequence model, or explicitly accept the current simplified motion model after numeric defaults (`60fps`, `12s`, `8000px`, `zoom_ratio=1.13`, `PAN_TRAVEL_RATIO=0.40`) were restored.

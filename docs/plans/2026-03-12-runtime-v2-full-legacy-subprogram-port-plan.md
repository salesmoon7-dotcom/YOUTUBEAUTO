# Runtime V2 Full Legacy Subprogram Port Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `D:\YOUTUBE_AUTO`의 하부프로그램 동작을 `runtime_v2`에 먼저 **전체 이식**한 뒤, 마지막에 세부 디버그/파이프라인 연결을 맞추어 GPT 이후 이미지/썸네일/동영상/오디오/후처리 체인이 레거시 순서, 레거시 설정값, 레거시 브라우저 상호작용 기준을 만족하도록 복원합니다.

**Architecture:** 이 계획은 개별 서비스 디버깅이 아니라 **전체 이식 우선 전략**입니다. 1단계에서 레거시 하부프로그램 로직을 서비스별로 최대한 그대로 가져오고, 2단계에서 `runtime_v2` 계약/오케스트레이션에 연결하며, 3단계에서 current-session real gate와 1행 테스트를 수행합니다. 단, 브라우저 하부프로그램의 클릭/버튼/탭 전환/입력 방식과 로컬 프로그램의 모델/효과/기본 설정값은 **레거시 기준이 `runtime_v2` 내부 단순화보다 우선**합니다. `runtime_v2`의 단일 writer / 단일 failure contract / fail-closed 원칙은 최종 연결 단계에서 맞추되, 그 과정에서 서비스 동작과 설정값을 레거시와 다르게 바꾸는 단순화는 허용하지 않습니다.

**Tech Stack:** Python 3.13, `runtime_v2`, stage2 browser workers, GPU/local workers, legacy scripts under `D:\YOUTUBE_AUTO\scripts`, JSON contracts, evidence bundles under `D:\YOUTUBEAUTO_RUNTIME\probe`, targeted `unittest`, `py_compile`

**Status:** IN_PROGRESS (updated 2026-03-13, Stage 5/5B complete)

## Closed-Loop Progress Update

Completed broad parity batches already pushed to `main`:
- `SeaArt/Genspark` ref-image-first parity and real artifact gate alignment
- `Canva` parity and `Agent Browser Verify` stage2/browser action contract alignment
- `GeminiGen` truthful-artifact/default-path parity
- `KenBurns` resident/bundle-map parity including manifest SSOT and local-only output contract
- `Qwen3` current-session Gate C parity (`voice_json` only green blocked; canonical qwen3/rvc audio now required)
- `RVC` source-mode sequencing parity (`tts-source` vs `gemi-video-source`) and downstream lane selection
- `Render` row-level current-session closeout, Stage5/5B probes, Stage6 readiness, Stage7 soak report, promotion gate evaluation, GUI/runtime orchestration parity

Remaining active work is now:
1. Stage 6/7 operational `24h soak` verification gap (final stage, deferred by user instruction)

Current verification snapshot (canonical runtime root, 2026-03-14):
- manual Stage 5 (`1-row`) smoke passed with current-session render final output and readiness green
- manual Stage 5B (`5-row`) batch smoke passed with `probe_success=true`, five successful row reports, and final artifacts for all rows
- latest canonical runtime evidence is aligned on current-session render success (`run_id=898057c2-e52b-4bd4-ab5f-e9432813b60c-row05` at the time of Stage 5B completion)
- `--readiness-check` returns `ready=true`, blockers empty, promotion gates `A/B/C/D` all passed
- multiple parity restores are already landed on `main`: KenBurns numeric defaults + effect sequence 1차, qwen3_tts reference audio/output/runtime defaults, RVC active model/applio/runtime format + mode semantics, Genspark initial URL, Canva clone semantics, GeminiGen control semantics surfacing
- `Canva` now surfaces the full legacy sequence intent in the stage2 child/worker contract: clone counts, background generation, upload/remove-background, position, text edit, export/download, cleanup evidence fields are recorded in `attach_evidence.json` and worker details
- same-session live Canva validation completed on the real `canva` browser session (`port 9666`), and the surfaced sequence closed with all success fields true plus a real `THUMB.png` output in `tmp_canva_live_validate/exports/`
- Stage 5/5B completion does not waive the parity requirement: browser click/submit behavior and local subprogram settings must still be compared against legacy before architecture is considered settled
- user explicitly asked not to run 24h tests in the current cycle, so Stage 6/7 remains deferred even after Stage 5/5B completion

Deferred/non-active follow-up notes:
- native-only `qwen3_tts` / `rvc` lanes still fail closed by design; adapter-backed production path is the current whole-port target
- `GeminiGen` truthful capture now supports direct video URL capture, but `blob:`/strict CORS video delivery may still fail closed until a service-specific fallback is added
- explicit user instruction: do not execute `24h soak` in the current run; keep Stage 6/7 as documented but unexecuted
- local program settings parity (`qwen3_tts`, `rvc`, `kenburns`) and browser click/submit semantics parity must be audited against legacy scripts/configs before the architecture is called final

---

## In-Scope Workload Inventory

| Workload | Included | Notes |
|---|---|---|
| `chatgpt` | Yes | Fresh row-level source of truth for all downstream work |
| `seaart` | Yes | Immediate post-GPT image worker |
| `genspark` | Yes | Immediate post-GPT image worker |
| `canva` | Yes | Thumbnail worker |
| `geminigen` | Yes | Image-to-video worker |
| `qwen3_tts` | Yes | Audio worker |
| `rvc` | Yes | Audio conversion worker |
| `kenburns` | Yes | Resident/inbox GPU worker |
| `render` | Yes | Final composition worker |
| `agent_browser_verify` | Yes | Shared browser adapter/action runtime used by stage2 browser services |

Excluded from this plan:
- one-off probe/debug helpers that are not part of the production runtime contract

---

## Decision Log

- Port target is **contract-equivalent behavior**, not wholesale code copy.
- Browser services must prefer **legacy-equivalent interaction semantics** over cleaner CDP/eval abstractions when the two diverge.
- Local subprograms (`qwen3_tts`, `rvc`, `kenburns`) must prefer **legacy-equivalent config values and effect defaults** over runtime_v2-specific simplifications when the two diverge.
- Legacy implementation is already functionally complete enough that **whole-service port first, fine-grained debugging later** is the preferred delivery strategy.
- `KenBurns` is split into:
  - `v1`: single-scene resident/inbox GPU workload
  - `v2`: `scene_bundle_map` orchestration parity
- `RVC` is split into:
  - `tts-source` mode
  - `gemi-video-source` mode
- `ChatGPT` browser environment is a separate parent risk and should be stabilized before claiming full end-to-end parity.

---

## Cross-Service Dependency Summary

| Upstream | Downstream | Canonical handoff | Current state |
|---|---|---|---|
| GPT/stage1 | SeaArt/Genspark | `stage1_handoff.contract.scene_prompts`, `ref_img_1`, `ref_img_2` | present |
| GPT/stage1 | Canva | `title_for_thumb`, `ref_img_1`, `ref_img_2` | present |
| GPT/stage1 | GeminiGen | `videos`, `first_frame_path`, selected image refs | present, truthful artifact gate added |
| GPT/stage1 | Qwen3 TTS | `voice_groups/voice_texts` | present, current-session gate added |
| Qwen3 TTS | RVC | `next_jobs` or explicit audio handoff | present, canonical lane sequencing added |
| image/audio outputs | KenBurns | inbox or bundle map | present (`v1` + `v2` parity landed) |
| routed assets/audio | Render | `render_spec`, `asset_manifest`, row-run latest snapshot | present, row-level closeout added |

## Why the original plan drifted

The repository already had earlier plans for service order and verification, but execution drifted for three concrete reasons:

1. **Prompt-only shortcuts replaced the legacy order**
   - We attempted browser-child generation with prompt text before restoring the legacy `Ref Img 1 -> Ref Img 2 -> image generation` order.
   - This especially broke `Genspark/SeaArt`, where the prompt text explicitly referenced ref images that had not been generated or uploaded yet.

2. **We diagnosed the wrong boundary first**
   - We spent too long on image-service polling/click timing before fixing the actual upstream contracts (`request.json` vs `request_payload.json`, ref propagation, browser input actions).
   - This created many retries that did not test the real production sequence.

3. **Success criteria were too loose**
   - attach success, placeholder artifact creation, and direct-child return codes were sometimes treated as if they proved meaningful row-level success.
   - That violated the project rule that only current-session evidence with real artifacts counts as success.

## Enforcement rules for this port

To prevent repeating the same drift, all future work under this plan must obey the following rules:

1. **Do not skip the legacy order**
   - `Ref Img 1` and `Ref Img 2` jobs must be generated first.
   - `Genspark/SeaArt` scene jobs must not run until those ref jobs have either succeeded or failed closed.

2. **Use the worker’s real request contract**
   - Browser children must prefer `request.json` (`payload` wrapper) over ad-hoc `request_payload.json` and only use the latter as compatibility fallback.

3. **No placeholder counts as success**
   - A service is not considered passed if `placeholder_artifact=true`, if the target artifact path is missing, or if only attach/transcript evidence exists.

4. **One gate at a time**
   - Do not move from `SeaArt/Genspark` to `Canva/GeminiGen` until at least one real artifact gate is green in the current session.

5. **Current-session evidence only**
   - Historical probe artifacts are reference/debug aids only; pass/fail is judged only from the current runtime session.

6. **Legacy interaction/config parity beats internal simplification**
   - If a browser service works only by changing click/submit/tab behavior away from legacy, treat that as a parity regression until explicitly justified.
   - If a local program works only by changing core defaults (model path, voice/reference loading, effect defaults, fps/duration/output defaults) away from legacy, treat that as a parity regression until explicitly justified.

---

## Service Port Cards

### 0. ChatGPT

**Required inputs**
- row/topic selection
- logged-in longform GPT browser environment
- parser-expected output contract

**Output artifacts**
- `raw_output.json`
- `parsed_payload.json`
- `stage1_handoff.json`
- `video_plan.json`

**Success markers**
- non-fallback current-session capture
- parser-valid payload
- downstream queueable handoff

**Failure markers**
- `topic_spec_fallback`
- malformed payload (`invalid_voice_groups`, etc.)
- browser/input/read instability

### 1. SeaArt

**Required inputs**
- prompt
- `ref_img_1`, `ref_img_2` (legacy order)
- browser session on 9444

**Output artifacts**
- `*_SEA_*.png` equivalent image artifact

**Success markers**
- prompt input transcript
- generate click transcript
- non-placeholder artifact
- `result.json.status=ok`

**Failure markers**
- no prompt input
- no file upload
- placeholder-only artifact
- browser adapter fail-close

### 2. Genspark

**Required inputs**
- prompt
- `ref_img_1`, `ref_img_2`
- browser session on 9333

**Output artifacts**
- `_GENS_*` / equivalent generated image

**Success markers**
- correct tab (`agents?type=image_generation_agent` or valid result tab)
- prompt input transcript
- generate click transcript
- real image src capture/download

**Failure markers**
- home-tab drift
- no input
- no send/generate
- placeholder-only capture
- `BROWSER_UNHEALTHY=20`

### 3. Canva

**Required inputs**
- `thumb_data`
- `ref_img_1`, `ref_img_2`

**Output artifacts**
- `THUMB.png` equivalent

### 4. GeminiGen

**Required inputs**
- `videos`
- `first_frame_path`
- selected image refs

**Output artifacts**
- `_GEMI.mp4`

### 5. Agent Browser Verify

**Required inputs**
- service
- port
- canonical request payload
- service-specific actions

**Output artifacts**
- `attach_evidence.json`
- transcript
- optional `functional_evidence`

**Success markers**
- prompt input transcript
- upload transcript when needed
- generate/click transcript
- non-placeholder artifact when applicable

**Failure markers**
- no action transcript
- navigation/context destroy
- placeholder-only artifact

### 6. Render

**Required inputs**
- `render_spec`
- `asset_refs`, `audio_refs`, `thumbnail_refs`

**Output artifacts**
- final mp4 output

**Success markers**
- final output path exists
- current-session assets referenced consistently

**Failure markers**
- `render_inputs_not_ready`
- missing upstream artifacts

### 7. Qwen3 TTS

**Required inputs**
- `voice_groups` / `voice_texts`

**Output artifacts**
- `voice/#NN.flac`
- `#00.txt`

### 8. RVC

**Required inputs**
- `tts-source` or `gemi-video-source`
- `model_name`

**Output artifacts**
- converted audio artifact

### 9. KenBurns

**Required inputs**
- image
- audio(optional for v1, required for target flow if specified)

**Output artifacts**
- final mp4

---

## Field Matrix (must be locked before implementation)

| Service | Direct fields consumed | Missing today |
|---|---|---|
| ChatGPT | `topic`, browser environment, parser-required shape | manual live-service stability only |
| SeaArt | `prompt`, `ref_img_1`, `ref_img_2` | no active broad parity gap |
| Genspark | `prompt`, `ref_img_1`, `ref_img_2` | no active broad parity gap |
| Canva | `thumb_data`, `ref_img_1`, `ref_img_2` | no active broad parity gap |
| GeminiGen | `videos`, `first_frame_path` | prompt/generate action hardening is follow-up, not current broad parity blocker |
| Agent Browser Verify | `request.json(payload)`, actions, upload paths | no active broad parity gap |
| Render | `render_spec`, `asset_refs`, `audio_refs`, `thumbnail_refs` | no active broad parity gap; manual row verification remains |
| Qwen3 | `voice_groups/voice_texts` | no active broad parity gap in gate layer |
| RVC | `source_path`, `model_name`, mode split | no active broad parity gap |
| KenBurns | `image/audio` or bundle map | no active broad parity gap |

---

## Failure Matrix (canonical)

Every service must distinguish at least:

1. input missing
2. browser/adapter/session failure
3. output not created
4. output reused
5. artifact path invalid
6. downstream handoff missing

---

## Golden Evidence Requirements

Each service must have 3 evidence gates:

1. **mock** - contract path only
2. **smoke** - real adapter/worker 1회
3. **real** - legacy-equivalent input with meaningful artifact

Evidence bundle per service:
- request artifact (`request.json`, `request_payload.json`, equivalent)
- transcript/stdout/stderr
- result.json
- final artifact path

## Promotion Gates (single source of truth)

### Gate A - Immediate post-GPT
- `ChatGPT` fresh current-session success
- `SeaArt` real current-session artifact
- `Genspark` real current-session artifact

### Gate B - Browser/video expansion
- `Canva` real current-session artifact
- `GeminiGen` real current-session artifact OR explicitly locked fail-close policy with truthful evidence

### Gate C - Audio/GPU expansion
- `Qwen3 TTS` real current-session artifact
- `RVC` chosen mode real current-session artifact
- `KenBurns v1` real current-session artifact

### Gate D - Orchestration
- `Render` final current-session output
- row-level orchestration closes without historical stand-ins

---

## Execution Order

## Delivery Phases

### Phase 1 - Full legacy logic port first

- 목표: 각 하부프로그램이 레거시와 같은 방식으로 단독 동작하도록 먼저 옮깁니다.
- 이 단계에서는 `runtime_v2` current-session orchestration보다 **서비스 기능 parity**를 우선합니다.

### Phase 2 - Runtime_v2 pipeline wiring second

- 목표: Phase 1에서 포팅한 서비스들을 `runtime_v2` 계약/queue/next-jobs에 연결합니다.
- 이 단계에서만 `single writer`, `failure contract`, `gate`를 최종 정렬합니다.

### Phase 3 - Real gate and 1-row verification

- 목표: current-session evidence로 각 서비스 real gate를 닫고 마지막에 1행 테스트를 수행합니다.

## Phase-by-phase execution rule

1. **Phase 1에서는 서비스 단독 기능 parity를 먼저 닫습니다**
2. **Phase 2에서만 runtime_v2 pipeline에 연결합니다**
3. **Phase 3에서만 1행 테스트로 진입합니다**

### Batch A - Immediate post-GPT
1. SeaArt
2. Genspark
3. Qwen3 TTS

### Batch B - Upstream dependent
4. Canva
5. GeminiGen
6. KenBurns v1
7. RVC mode split

### Batch C - Orchestration parity
8. KenBurns v2 bundle map
9. RVC full upstream/downstream orchestration
10. integrated row-level gate

---

## Remaining verification tasks

### Task 1: Stage 5 manual 1-row smoke (Completed for generic gate, pending for user-designated semantic row)

**Files:**
- `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`
- canonical runtime evidence under runtime root (manual execution evidence)

**Steps**
1. real-service browser/audio/ffmpeg 자원에서 준비된 테스트 행 1개를 current-session 기준으로 완료
2. `run_id`, `error_code`, `attempt/backoff` 3축과 final output/failure summary를 같은 latest-run 의미로 확인

Completion status:
- completed on canonical runtime root with current-session `render final.mp4`
- readiness green and promotion gates `A/B/C/D` all passed after the final row closeout/Gate B fixes
- fresh detached rerun reaffirmed completion at `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-rerun-03\probe_result.json` with `status=ok`, `code=OK`, `probe_success=true`
- follow-up required: rerun the same Stage 5 minimum flow on the user-designated semantic target row `요양 시설 비용 현실과 준비해야 할 금액` (`Sheet1` row 16 / CLI `--row-index 14`) before treating the row-specific ask as closed
- addressed in this session:
  - fail-closed gate for missing real GPT output (no more `topic_spec_fallback` success leakage)
  - stage1 Excel writeback stale-snapshot bug
  - stage1 declared next-job fan-out limit (`12 -> 128`)
  - ChatGPT same-tab lifecycle reset via `Page.navigate(CHATGPT_LONGFORM_URL)` + `Page.reload(ignoreCache=true)`
  - detached probe/process launch updated to include `CREATE_NO_WINDOW`
  - legacy voice grouping contract restored so `Voice 13-16(4)` is preserved as one grouped mapping with `original_voices=[13,14,15,16]`
  - live ChatGPT prompt no longer includes the extra line `"[Ref Img 1], [Ref Img 2], [Video1], [Video2] ... 블록도 함께 채우세요."`
  - qwen terminal artifact contract updated from `speech.wav` assumption toward legacy-aligned `speech.flac` / `voice/#NN.flac`
- current blocker update: semantic row verification is still open because the current session was interrupted before any final rerun completed with closing evidence.
- current evidence: grouped `voice_texts.json` correctness and FLAC-aligned qwen contract were both reflected in runtime_v2 code/tests, but no final `probe_result.json`, `failure_summary.json`, or `render/` artifact was produced before user-requested stop.
- current session stop condition: runtime-related Python processes were force-stopped on user request, so this session ends with `verification interrupted`, not `verification complete`.
- next remediation target: resume from a clean semantic-row rerun only when explicit re-run is desired, using the now-updated prompt/tabs/voice-grouping/qwen-FLAC contracts.
- oracle-reviewed shortest-time closeout strategy:
  - run only one clean semantic-row detached verification cycle (`Sheet1` row 16 / CLI `--row-index 14`) with a fresh `probe_root`
  - before that run, execute only `python -m runtime_v2.cli --readiness-check`; if readiness fails, stop and fix only that blocker
  - do **not** rerun generic Stage 5, Stage 5B, 24h soak, or broad pytest suites during closeout
  - accept closeout only when the single semantic-row run leaves closed evidence: `probe_result.json` + (`render_final.mp4` or `failure_summary.json`)
  - if that one semantic-row run fails for a deterministic contract/logic reason, stop rerunning and switch to single-blocker debugging only

### Task 2: Stage 5B manual 5-row smoke (Completed)

**Files:**
- `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`
- canonical runtime evidence under runtime root (manual execution evidence)

**Steps**
1. Stage 5 성공 후 준비된 5개 행을 동일 계약으로 순차 검증
2. 각 행의 final output/failure summary와 latest-run alignment를 기록

Completion status:
- completed on canonical runtime root with detached 5-row probe
- `probe_success=true`, `selected_rows=[38,39,40,41,42]`, `row_reports_count=5`
- all five row reports completed with `status=ok`, `code=OK`, and non-empty `final_artifact_path`

### Task 3: Legacy parity audit for settings and browser behavior (Completed)

**Why this remains required:**
- user explicitly identified this as the highest-priority completion criterion
- passing Stage 5/5B smoke is not enough if browser services or local subprograms achieve that result with settings/behaviors that diverge from legacy

**Audit scope:**
- browser services: `chatgpt`, `genspark`, `seaart`, `geminigen`, `canva`
- local subprograms: `qwen3_tts`, `rvc`, `kenburns`

**Required comparisons against legacy:**
1. browser type, profile root, port/debug attach mode, viewport/window-size related settings
2. exact interaction semantics: which field is filled, which button is clicked, whether tabs are reused/opened/switched, and in what order
3. local program settings: model/config/python path, voice/reference-audio loading, RVC active model/input mode, KenBurns effect defaults (`pan_direction`, `zoom_mode`, percentages, output size/fps)
4. any fallback or compatibility path that changes observable behavior compared to legacy

**Completion condition:**
- a file-by-file parity audit exists for browser + local subprogram settings/behavior
- confirmed deltas are either removed or explicitly justified as unavoidable runtime_v2 contract changes

**Execution checklist (service-by-service):**

1. **ChatGPT parity checklist**
   - Compare legacy source of truth with `runtime_v2` source:
     - legacy: `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py`
     - runtime_v2: `runtime_v2/browser/manager.py`, `runtime_v2/stage1/chatgpt_backend.py`, `runtime_v2/stage1/chatgpt_interaction.py`
   - Confirm parity for:
     - browser family/profile root/debug port
     - initial URL and logged-in session assumptions
     - prompt submit target and button semantics
     - output capture contract (`raw_output.json`, `parsed_payload.json`, `stage1_handoff.json`)
   - Record: matched items, divergent items, required fixes/justifications

2. **Genspark parity checklist**
   - Compare:
     - legacy: `D:\YOUTUBE_AUTO\scripts\genspark_automation.py`
     - runtime_v2: `runtime_v2/cli.py`, `runtime_v2/workers/agent_browser_worker.py`, `runtime_v2/agent_browser/cdp_capture.py`
   - Confirm parity for:
     - starting URL / one-tab vs. multi-tab assumptions
     - exact prompt input field
     - exact submit button / CTA sequence
     - result-tab/result-card interpretation
     - artifact capture target and download path
   - Record: whether runtime_v2 click/submit/capture semantics are legacy-equivalent or intentionally different

3. **SeaArt parity checklist**
   - Compare:
     - legacy: `D:\YOUTUBE_AUTO\scripts\seaart_automation.py`
     - runtime_v2: `runtime_v2/stage2/seaart_worker.py`, `runtime_v2/cli.py`, `runtime_v2/workers/agent_browser_worker.py`
   - Confirm parity for:
     - browser profile/port
     - ref-image upload order
     - prompt input target
     - generate button semantics
     - final image capture semantics

4. **Canva parity checklist**
   - Compare:
     - legacy: relevant thumbnail automation path under `D:\YOUTUBE_AUTO`
     - runtime_v2: `runtime_v2/stage2/canva_worker.py`, browser-plane config
   - Confirm parity for:
     - profile/port/browser family
     - template/input field/button sequence
     - thumbnail export path / artifact naming

5. **GeminiGen parity checklist**
   - Compare:
     - legacy: `D:\YOUTUBE_AUTO` Gemini/video generation automation path
     - runtime_v2: `runtime_v2/stage2/geminigen_worker.py`, `runtime_v2/agent_browser/cdp_capture.py`, `runtime_v2/cli.py`
   - Confirm parity for:
     - first-frame input handling
     - browser/video prompt sequence
     - video export/capture semantics
     - whether runtime_v2 truthful-artifact gate is stricter than legacy and why

6. **Qwen3 TTS parity checklist**
   - Compare:
     - legacy: `D:\YOUTUBE_AUTO\scripts\qwen3_tts_automation.py`, `D:\YOUTUBE_AUTO\system\config\qwen3_tts_config.json`
     - runtime_v2: `runtime_v2/workers\qwen3_worker.py`, `runtime_v2\preflight.py`
   - Confirm parity for:
     - python executable path
     - model id / device / dtype / generation defaults
     - reference audio loading rule
     - voice JSON input contract
     - output format and artifact naming

7. **RVC parity checklist**
   - Compare:
     - legacy: `D:\YOUTUBE_AUTO\scripts\rvc_voice_convert.py`, `D:\YOUTUBE_AUTO\system\config\rvc_config.json`
     - runtime_v2: `runtime_v2\workers\rvc_worker.py`, `runtime_v2\preflight.py`
   - Confirm parity for:
     - applio/python path and model selection
     - input mode (`tts-source` vs `gemi-video-source`) mapping
     - extracted audio vs source audio rule
     - output file naming and downstream handoff semantics

8. **KenBurns parity checklist**
   - Compare:
     - legacy: `D:\YOUTUBE_AUTO` KenBurns effect/render path
     - runtime_v2: `runtime_v2\workers\kenburns_worker.py`
   - Confirm parity for:
     - output width/height/fps defaults
     - pan/zoom direction and percentage defaults
     - single-scene vs bundle-map orchestration behavior
     - audio mux semantics and manifest output path rules

9. **Cross-cutting browser settings checklist**
   - Compare runtime_v2 browser plane (`runtime_v2/browser/manager.py`, `runtime_v2/preflight.py`) against legacy browser scripts for:
     - profile root
     - debug port allocation
     - browser family choice
     - viewport/window-size assumptions where explicit
     - login/session persistence assumptions

10. **Cross-cutting fallback checklist**
    - For each service, explicitly list any remaining fallback/compatibility path and classify it as:
      - required for legacy parity
      - temporary diagnostic fallback
      - removable after parity audit

**Required output artifact for this task:**
- one parity audit document or checklist result per service/local subprogram
- one cross-cutting summary of accepted vs rejected deltas

Current audit artifact:
- `docs/plans/2026-03-14-runtime-v2-legacy-parity-audit.md`

Parity closeout note from the audit artifact:
- `KenBurns` richer preset system was reviewed against legacy `scripts/ken_burns_effect.py` and explicitly accepted as non-blocking for the current runtime contract. Legacy observable default motion is driven by `EFFECT_SEQUENCE` + `get_effect_for_index()`, and runtime_v2 now matches the 8-step sequence, `static`, and center/corner anchor semantics used by that default path.

### Task 4: Stage 6/7 operational soak verification gap (Pending by user instruction, final stage)

**Files:**
- `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`
- `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- canonical soak evidence/report files

**Execution order requirement:**
- this stage is allowed only after:
  - targeted/unit verification passes
  - manual Stage 5 (`1-row`) smoke passes
  - manual Stage 5B (`5-row`) smoke passes
  - required legacy parity audit items are resolved or explicitly accepted

**Steps**
1. 24h soak readiness를 실제 latest-run evidence와 manual smoke 결과로 재판정
2. `soak_24h_report.md` 기준의 operational verification gap을 닫기

Current status:
- not executed in this cycle because user explicitly asked not to run 24h tests

---

## Done Gate

This port is complete only when:
- `ChatGPT`, `Agent Browser Verify`, `Render`까지 포함한 전체 workload inventory가 카드/게이트를 가짐
- each service has mock + smoke + real evidence
- service-specific failure matrix is explicit
- row-level orchestration uses current-session artifacts, not historical stand-ins
- no service is marked complete on placeholder artifacts alone

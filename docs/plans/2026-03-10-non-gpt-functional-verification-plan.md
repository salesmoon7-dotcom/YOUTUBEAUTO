# Non-GPT Functional Verification Plan

## Goal

- 비-`GPT` 하부프로그램 전체를 `Implemented`나 `Contract-verified` 수준이 아니라, 실제로 **Functionally-verified** 상태까지 올립니다.
- 각 프로그램마다 최소 1개의 실제 동작 evidence를 확보하고, 그 evidence가 없으면 완료로 올리지 않습니다.

## Scope

- 대상 프로그램:
  - `SeaArt`
  - `Genspark`
  - `TTS`
  - `GeminiGen`
  - `Canva`
  - `Kenburn`
  - `RVC`

## Principles

- 레거시 구현체 직접 호출 금지
- `runtime_v2` 내부 계약/adapter/worker만 사용
- fail-closed 유지
- single writer / single failure contract 유지
- evidence 없으면 완료 주장 금지

## Verification Levels

### 1. Implemented

- worker/bridge/adapter 경로가 존재함
- 단위 테스트가 일부 존재할 수 있음

### 2. Contract-verified

- 입력/출력/실패 계약 테스트가 있음
- adapter/bridge schema가 고정됨

### 3. Functionally-verified

- 실제 row/asset 기준 최소 1회 실행 evidence가 있음
- final artifact 또는 equivalent runtime evidence가 있음
- expected downstream handoff까지 이어짐

## Service-by-Service Definition of Done

### SeaArt

- Required evidence:
  - 실제 row 기준 image generation artifact 1개
  - adapter transcript / stdout / stderr
  - final `service_artifact_path`
- Done when:
  - `status=ok`
  - output image exists
  - downstream handoff path preserved

#### Current evidence

- `system/runtime_v2_probe/seaart-functional-03/exports/seaart.png`
- `system/runtime_v2_probe/seaart-functional-03/functional_evidence/final_screen.png`
- `system/runtime_v2_probe/seaart-functional-03/functional_evidence/evidence.json`

#### Current status

- `Functionally-verified`

### Genspark

- Required evidence:
  - 실제 row 기준 image generation artifact 1개
  - category/model branch evidence
  - final `service_artifact_path`
- Done when:
  - `status=ok`
  - output image exists

#### Current evidence

- `system/runtime_v2_probe/genspark-functional-02/exports/genspark.png`
- `system/runtime_v2_probe/genspark-functional-02/functional_evidence/final_screen.png`
- `system/runtime_v2_probe/genspark-functional-02/functional_evidence/evidence.json`

#### Current status

- `Functionally-verified`
- canonical adapter child adoption: complete

### TTS (`qwen3_tts`)

- Required evidence:
  - `voice_texts` 기반 실제 오디오 산출물
  - `voice/#NN.*` equivalent output evidence
  - `#00.txt` 또는 equivalent script bundle evidence
- Done when:
  - multiple voice lines are consumed
  - audio artifact exists
  - downstream consumer can resolve the produced path(s)

#### Exploratory note

- `system/runtime_v2_probe/qwen3-functional-01/`에서 legacy folder mode를 이용한 exploratory evidence는 생성되었습니다.
- 이 exploratory lane은 legacy-style folder output을 확인한 참고 근거입니다.
- 별도로 `runtime_v2` canonical worker path evidence는 `system/runtime_v2_probe/qwen3-canonical-03/`에 존재합니다.
- 여기서 canonical worker evidence는 `runtime_v2` worker/adapter 경로로 재현 가능한 입력과 산출물(`voice/#NN.flac`)이 확인됐다는 뜻이며, full pipeline closeout을 뜻하지는 않습니다.

#### Current evidence

- `system/runtime_v2_probe/qwen3-functional-01/episode/voice/#01.flac`
- `system/runtime_v2_probe/qwen3-functional-01/episode/voice/#02.flac`
- `system/runtime_v2_probe/qwen3-functional-01/episode/voice/#00.txt`
- `system/runtime_v2_probe/qwen3-functional-01/result.json`

#### Current status

- `Functionally-verified`
- canonical worker adoption: complete (`system/runtime_v2_probe/qwen3-canonical-03/`)
- note: canonical worker functional evidence는 확보됐지만, full downstream orchestration closeout(실제 GPT handoff 연결, 관측, end-to-end gate)은 아직 active integration plan의 범위로 남아 있습니다.

### GeminiGen

- Required evidence:
  - 실제 이미지 입력 기반 video artifact 1개 (`_GEMI.mp4` equivalent)
  - input image selection evidence
  - final video artifact path
- Done when:
  - `status=ok`
  - video artifact exists

#### Current blocker note

- direct helper inspection 기준 현재 페이지에서 식별되는 첫 번째 이미지가 실제 생성 산출물이 아니라 사이트 로고(`logo-with-text.png`)입니다.
- 따라서 현재 helper만으로는 진실한 functional evidence를 만들 수 없습니다.
- attach-only `agent-browser` child는 이제 placeholder success를 만들지 않고 fail-closed로 종료합니다.
- 실제 생성 산출물 선택 규칙을 추가로 정의하기 전까지는 `Contract-verified` 상태를 유지합니다.

### Canva

- Required evidence:
  - `title_for_thumb` + `ref_img_1/ref_img_2` 기반 thumbnail artifact 1개
  - `THUMB.png` equivalent path
  - thumb data split evidence (`line1`, `line2`)
- Done when:
  - `status=ok`
  - thumbnail exists

#### Current evidence

- `system/runtime_v2_probe/canva-functional-03/exports/THUMB.png`
- `system/runtime_v2_probe/canva-functional-03/functional_evidence/final_screen.png`
- `system/runtime_v2_probe/canva-functional-03/functional_evidence/evidence.json`

#### Current status

- `Functionally-verified`
- canonical adapter child adoption: complete

### Kenburn

- Required evidence:
  - `scene_bundle_map` 또는 equivalent multi-scene input evidence
  - image + voice pair consumption evidence
  - final mp4 output
- Done when:
  - bundle input is consumed
  - final video artifact exists

#### Current evidence

- `system/runtime_v2_probe/kenburn-functional-03/artifacts/kenburns/kenburn-func-03/kenburns.mp4`
- `system/runtime_v2_probe/kenburn-functional-03/result.json`

#### Current status

- `Functionally-verified`

### RVC

- Required evidence:
  - `tts-source` mode evidence
  - `gemi-video-source` mode evidence
  - final converted audio artifact
- Done when:
  - at least one source mode is proven end-to-end
  - preferred target is both modes covered

#### Exploratory note

- `system/runtime_v2_probe/rvc-functional-01/`에서 Applio infer 기반 exploratory evidence는 생성되었습니다.
- 이 exploratory lane은 adapter/operator 중심 참고 근거입니다.
- 별도로 `runtime_v2` canonical worker path evidence는 `system/runtime_v2_probe/rvc-canonical-04/`에 존재합니다.
- 여기서 canonical worker evidence는 `runtime_v2` worker/adapter 경로로 재현 가능한 변환 산출물이 확인됐다는 뜻이며, source-mode/후처리 orchestration 완료를 뜻하지는 않습니다.

#### Current evidence

- `system/runtime_v2_probe/rvc-functional-01/output.flac`
- `system/runtime_v2_probe/rvc-functional-01/stdout.txt`
- `system/runtime_v2_probe/rvc-functional-01/stderr.txt`

#### Current status

- `Functionally-verified`
- canonical worker adoption: complete (`system/runtime_v2_probe/rvc-canonical-04/`)
- note: canonical worker functional evidence는 확보됐지만, source-mode split과 후처리 orchestration closeout은 아직 남아 있습니다.

## Execution Order

### Batch A. Immediate post-GPT services

1. `SeaArt`
2. `Genspark`
3. `TTS`

Reason:
- GPT handoff 직후 가장 먼저 실행 가능한 서비스들이고, 이후 단계의 upstream artifact를 만듭니다.

### Batch B. Upstream-artifact dependent services

4. `GeminiGen`
5. `Canva`
6. `Kenburn`
7. `RVC`

Reason:
- 이미지/오디오/비디오 선행 산출물이 있어야 하므로 뒤에서 검증하는 것이 맞습니다.

## Required Evidence Bundle Per Service

각 서비스는 아래 4종을 기본 evidence bundle로 남깁니다.

1. `input.json` or request artifact
2. `stdout/stderr` or transcript
3. `result.json`
4. final artifact path or equivalent runtime proof

## Failure Matrix Requirement

각 서비스 검증 시 반드시 아래를 구분합니다.

- input missing
- adapter/browser/session failure
- output not created
- output reused
- artifact path invalid
- downstream handoff missing

## Ready-to-Mark-Complete Rule

- 서비스 하나라도 `Functionally-verified` evidence가 없으면 비-`GPT` 전체 완료로 올리지 않습니다.
- 최소 상태 표기는 아래처럼 합니다.
  - `SeaArt`: Contract-verified / Functionally-verified
  - `Genspark`: ...
  - `TTS`: ...
  - `GeminiGen`: ...
  - `Canva`: ...
  - `Kenburn`: ...
  - `RVC`: ...

## Immediate Next Step

- 바로 다음 실행은 `SeaArt`, `Genspark`, `TTS`의 functional evidence를 1개씩 확보하는 것입니다.
- 그 뒤 `GeminiGen`, `Canva`, `Kenburn`, `RVC` 순으로 확장합니다.

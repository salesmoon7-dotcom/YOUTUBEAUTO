# Runtime_v2 Subprogram Gap Analysis Plan

## Why This Plan Is Needed

- 기존 통합 계획은 실행 순서와 대전제는 잡았지만, 디버깅 시간을 줄이기 위한 **정밀 차이 분석**이 부족했습니다.
- 특히 아래 4개가 빠져 있었습니다.
  1. 레거시 vs `runtime_v2` **필드 단위 매핑표**
  2. 서비스별 **failure matrix**
  3. 서비스별 **golden input / golden output / golden evidence**
  4. 실제 테스트 전 **readiness checklist**

## Goal

- `ChatGPT`, `SeaArt`, `Genspark`, `TTS`, `GeminiGen`, `Canva`, `Kenburn`, `RVC` 각각에 대해
  - 레거시 계약
  - 현재 `runtime_v2` 계약
  - 차이(gap)
  - 실제 실패로 이어지는 조건
  - 준비 완료 판정 기준
  를 문서와 테스트 기준으로 고정합니다.

## Non-Negotiable Principles

- 레거시 프로그램은 **실패한 복잡계**로 간주합니다.
- 구현 재사용이 아니라 `계약/파싱 규칙/입출력 기대값`만 참고합니다.
- `runtime_v2` 대전제를 깨지 않습니다.
  - single writer
  - single failure contract
  - worker policy-free
  - adapter boundary
  - fail-closed

## Deliverables

### 1. Field Matrix

- 서비스별로 아래를 표로 정리합니다.
  - legacy field name
  - legacy source (Excel column / JSON / folder)
  - runtime_v2 source field
  - required / optional
  - current status (`implemented`, `partial`, `missing`)

### 2. Failure Matrix

- 서비스별로 아래를 표로 정리합니다.
  - missing input
  - browser/session failure
  - parse drift
  - artifact missing
  - adapter timeout
  - expected canonical error code

### 3. Golden Cases

- 서비스별 최소 1개씩 정의합니다.
  - golden input
  - golden output path
  - golden evidence file
  - completion state

### 4. Readiness Checklist

- 실제 테스트 전 반드시 참이어야 하는 조건을 체크리스트로 고정합니다.
  - browser live attach ready
- stage1 handoff fields ready
- downstream required artifacts ready
- worker adapter path ready
- queue/control/snapshot consistency ready

## Analysis Artifacts (Keep As Reference)

- 이 문서는 이후 모든 준비도 점검의 기준 문서로 유지합니다.
- 아래 문서들과 함께 묶어서 참고합니다.
  - `docs/plans/2026-03-09-legacy-post-gpt-service-contract-survey.md`
  - `docs/plans/2026-03-09-runtime-v2-legacy-pipeline-feasibility-plan.md`
  - `docs/plans/2026-03-10-runtime-v2-subprogram-integration-execution-plan.md`
  - `docs/TODO.md`

### How to use this analysis later

- 새 구현을 시작하기 전에 먼저 이 문서의 `Field Matrix`, `Failure Matrix`, `Golden Cases`, `Readiness Checklist`를 갱신합니다.
- 디버깅이 시작되면, 바로 코드로 들어가지 말고 먼저 어떤 matrix 행이 깨졌는지부터 표시합니다.
- 실제 테스트를 다시 시작할 때도, 이 문서에서 `ready`로 바뀐 항목만 실행합니다.

## Required Analysis Passes

### Pass A. ChatGPT

- 입력 selector
- 전송 selector
- 응답 완료 판단
- 응답 추출 형식
- downstream handoff 필드 completeness

### Pass B. Immediate post-GPT services

- `SeaArt`
- `Genspark`
- `TTS`

Focus:
- GPT 직후 어떤 필드만 있으면 시작 가능한가
- 실제 blocker가 브라우저인지 입력인지 산출물인지 구분

### Pass C. Upstream-artifact dependent services

- `GeminiGen`
- `Canva`
- `Kenburn`
- `RVC`

Focus:
- 이미지/Voice/Video 선행 산출물이 정확히 무엇인가
- 어떤 필드가 없으면 즉시 실패해야 하는가

## Execution Order

### Phase 1. Field Matrix completion

- `stage1_handoff` 기준으로 downstream field matrix를 완결합니다.
- 반드시 포함:
  - `title`
  - `title_for_thumb`
  - `description`
  - `keywords`
  - `bgm`
  - `voice_groups`
  - `voice_texts`
  - `scene_prompts` / `#01...`
  - `ref_img_1`
  - `ref_img_2`

### Phase 2. Failure Matrix completion

- 각 서비스별 canonical error code를 정리합니다.
- 목표는 “디버깅할 때 어디가 먼저 깨졌는지”를 바로 알 수 있게 하는 것입니다.

### Phase 3. Golden evidence definition

- 각 하부프로그램마다 최소 1개 evidence bundle을 정의합니다.
- 이후 테스트는 이 golden bundle과 비교하는 식으로 진행합니다.

### Phase 4. Readiness gate definition

- `mock`
- `smoke`
- `real`

각 단계에서 무엇이 준비 완료인지 문서로 고정합니다.

## Done Definition

- 서비스별 field matrix 완성
- 서비스별 failure matrix 완성
- golden evidence 목록 완성
- readiness checklist 완성
- 이후 실제 테스트는 이 문서를 기준으로만 시작

## Immediate Next Step

- 가장 먼저 할 일은 `ChatGPT`를 포함한 **필드 단위 matrix**를 완성하는 것입니다.
- 그 다음으로 각 하부프로그램별 **failure matrix**를 작성합니다.

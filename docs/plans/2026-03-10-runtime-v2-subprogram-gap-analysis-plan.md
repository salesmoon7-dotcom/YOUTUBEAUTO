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

---

## GPT Field Matrix

| Legacy field | Legacy source | runtime_v2 source | Required | Current status | Notes |
|---|---|---|---|---|---|
| `title` | GPT text / Excel title | `stage1_handoff.contract.title` | Yes | implemented | `runtime_v2/stage1/parsed_payload.py` |
| `title_for_thumb` | GPT thumb title | `stage1_handoff.contract.title_for_thumb` | Yes | implemented | inline label parsing까지 반영 |
| `description` | GPT summary block | `stage1_handoff.contract.description` | Yes | implemented | browser snapshot / gpt_response_text 경로 공통 |
| `keywords` | GPT keyword list | `stage1_handoff.contract.keywords` | Yes | implemented | list normalized |
| `bgm` | GPT BGM field | `stage1_handoff.contract.bgm` | Yes | implemented | empty string 허용, key는 canonical |
| `voice_groups` | GPT/Excel voice mapping | `stage1_handoff.contract.voice_groups` | Yes | implemented | `stage1_handoff` SSOT schema에서 검증 |
| `voice_texts` | downstream-friendly row voice map | `stage1_handoff.contract.voice_texts` | Optional | implemented | `handoff_schema`가 `scene_prompts`에서 생성 |
| `scene_prompts` / `#01...` | GPT scene lines | `stage1_handoff.contract.scene_prompts` | Yes | implemented | inline label/value 파싱 반영 |
| `ref_img_1` | operator/legacy image ref | `stage1_handoff.contract.ref_img_1` | Optional | partial | schema/default는 있음, 실제 ChatGPT 생산 경로는 아직 비어 있음 |
| `ref_img_2` | operator/legacy image ref | `stage1_handoff.contract.ref_img_2` | Optional | partial | schema/default는 있음, 실제 ChatGPT 생산 경로는 아직 비어 있음 |
| `gpt_response_text` | real assistant output | `topic_spec.gpt_response_text` | Internal bridge | partial | snapshot/gpt text 주입은 구현됨, real-first evidence는 미완료 |

### GPT Field Matrix interpretation

- `stage1_handoff.contract`는 이미 downstream이 읽기 좋은 canonical field 집합을 갖고 있습니다.
- 현재 진짜 gap은 **field 존재 자체**보다 `gpt_response_text`를 실제 browser interaction layer가 얼마나 안정적으로 만들어 주는가입니다.
- `ref_img_1/ref_img_2`는 schema/default는 있지만 ChatGPT canonical producer로서 아직 실질 생산 경로가 없습니다.

## GPT Failure Matrix

| Failure class | Trigger | Canonical error code | Layer | Current status | Debug meaning |
|---|---|---|---|---|---|
| backend unavailable on submit | `agent-browser --cdp 9222 eval` submit 실패 / `os error 10060` | `CHATGPT_BACKEND_UNAVAILABLE` + `failure_stage=submit` | `chatgpt_interaction` | implemented | 포트/attach/backend 계층 문제 |
| backend unavailable on read | response poll 중 `read timeout` / attach 실패 | `CHATGPT_BACKEND_UNAVAILABLE` + `failure_stage=read` | `chatgpt_interaction` | implemented | 응답 대기/attach/backend 계층 문제 |
| response timeout | stable assistant text가 timeout까지 확보되지 않음 | `CHATGPT_RESPONSE_TIMEOUT` | `chatgpt_interaction` | implemented | interaction completed 판단 실패 |
| invalid topic spec | upstream topic spec missing/invalid | `invalid_topic_spec` | `chatgpt_runner` | implemented | 입력 계약 문제 |
| artifact invalid | voice groups / parsed payload shape mismatch | `artifact_invalid` | `chatgpt_runner` / parsed payload | implemented | parser/bridge contract 문제 |
| route failure | video plan -> downstream jobs 구성 실패 | `route_failed` | `chatgpt_runner` | implemented | stage1->stage2 bridge 문제 |

### GPT Failure Matrix interpretation

- 파서는 이미 별도 failure class를 갖고 있고, 현재 blocker는 parser가 아니라 `CHATGPT_BACKEND_UNAVAILABLE` 계열입니다.
- 즉, 실제 테스트가 막힐 때 먼저 봐야 할 행은 backend submit/read 계층입니다.

## GPT Golden Cases

| Golden case | Input | Output | Evidence | Completion |
|---|---|---|---|---|
| browser snapshot bridge | `browser_evidence.snapshot_path` -> snapshot text | `stage1_handoff.json` | `system/runtime_v2_probe/stage1-row13-evidence-05/` | handoff ready |
| gpt text bridge | `gpt_response_text` direct injection | `stage1_handoff.json` | `system/runtime_v2_probe/stage1-row13-evidence-04/` | handoff ready |
| topic-spec fallback | topic only -> synthetic parsed payload | `stage1_handoff.json` | `system/runtime_v2_probe/stage1-row13-evidence-01/` | handoff ready |

### GPT Golden evidence notes

- 이후 `real-first test`는 위 3개와 같은 파일 레이아웃을 유지해야 합니다.
- 특히 `raw_output.json`, `parsed_payload.json`, `stage1_handoff.json` 3종은 항상 남겨야 합니다.
- live `browser_evidence(service=chatgpt, port)` 경로는 `raw_output.json.gpt_capture`와 `raw_output.json.browser_evidence`를 함께 남겨야 합니다.

## GPT Readiness Checklist

### Mock Ready

- [x] `CHATGPT_BACKEND_UNAVAILABLE` canonical failure contract 존재
- [x] `failure_stage=submit/read` 존재
- [x] `chatgpt_runner` retry semantics 존재
- [x] parser -> handoff contract tests 존재

### Smoke Ready

- [x] browser snapshot -> `gpt_response_text` bridge evidence 존재
- [x] `gpt_response_text` -> `stage1_handoff` evidence 존재
- [x] downstream `next_jobs` stage1 bridge evidence 존재

### Real Ready

- [ ] 실제 ChatGPT assistant response artifact 생성
- [ ] real assistant response가 snapshot placeholder가 아닌지 증명
- [ ] same run_id 기준 `raw_output -> parsed_payload -> handoff` evidence 확보
- [ ] downstream 1개 서비스가 handoff-derived payload로 real run 성공

### Latest GPT-only progress

- [x] live capture success/failure metadata가 `raw_output.json.gpt_capture`에 기록됨
- [x] live 의도에서 capture failure는 fail-close 됨
- [x] no-port live request도 silent fallback 없이 fail-close 됨
- [x] live fail-closed에서도 `raw_output.json`과 `result.json.details.stage1_result.raw_output_path`가 남음
- [ ] `system/runtime_v2_probe/first-test-real-live-06/` 기준 real assistant artifact는 아직 실패(`CHATGPT_BACKEND_UNAVAILABLE`)

## Current GPT Verdict

- `Mock`: Yes
- `Smoke`: Yes
- `Real first`: Not yet

즉, 현재 GPT는 **구축은 상당 부분 완료됐지만 real-first gate는 아직 닫히지 않은 상태**입니다.

### Latest GPT-only follow-up

- `runtime_v2/stage1/handoff_schema.py`가 `version`을 항상 `stage1_handoff.v1.0`으로 정규화하도록 보강했습니다.
- `run_stage1_chatgpt_job()` 결과의 `stage1_handoff.contract`는 이제 `voice_texts`, `ref_img_1`, `ref_img_2`를 항상 포함합니다.
- 따라서 GPT Field Matrix의 “필수 필드 존재”는 현재 코드 산출물 기준으로 증명 가능합니다.

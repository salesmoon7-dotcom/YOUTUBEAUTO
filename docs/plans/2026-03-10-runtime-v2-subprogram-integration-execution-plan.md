# Runtime_v2 Subprogram Integration Execution Plan

## Goal

- `runtime_v2`가 `1차 테스트`와 `2차 1행 테스트`를 수행할 수 있도록, 하부 프로그램 전체를 현재 프로젝트의 대전제에 맞게 통합합니다.
- 레거시 프로젝트는 **복잡도가 폭증해 디버깅을 포기한 실패한 프로젝트**로 간주하고, 구현체 재사용이 아니라 **계약 추출용 참고 자료**로만 사용합니다.

## Non-Negotiable Principles

- 레거시 프로그램을 직접 실행 엔진으로 재사용하지 않습니다.
- 레거시에서 가져올 수 있는 것은 아래 두 가지만 허용합니다.
  - 입력/출력 계약
  - 순수 파싱 규칙
- `runtime_v2`는 아래 대전제를 계속 지킵니다.
  - single writer
  - single failure contract
  - worker policy-free
  - adapter boundary 유지
  - fail-closed

## Why This Plan Exists

- 현재까지는 stage1/agent-browser/downstream worker의 여러 축이 부분적으로 준비됐지만, “실제 테스트를 시작할 수 있는 환경”과 “실제 테스트 자체”가 섞여 있었습니다.
- 먼저 필요한 것은 테스트 실행이 아니라, **테스트 가능한 통합 환경**을 닫는 것입니다.

## Canonical Subprogram Graph

### A. GPT stage

- 역할: 입력 Topic을 downstream이 소비 가능한 canonical handoff로 변환
- canonical output:
  - `raw_output.json`
  - `parsed_payload.json`
  - `stage1_handoff.json`
- 최소 필드:
  - `title`
  - `title_for_thumb`
  - `description`
  - `keywords`
  - `bgm`
  - `voice_groups` / `voice_texts`
  - `scene_prompts` (`#01`, `#02`, ...)

### B. Immediate post-GPT stage

- GPT handoff만 있으면 바로 시작 가능한 하부 프로그램
  - `SeaArt`
  - `Genspark`
  - `TTS`

### C. Upstream-artifact dependent stage

- 선행 산출물이 있어야 시작 가능한 하부 프로그램
  - `GeminiGen` -> 선행 이미지 필요
  - `Canva` -> `Title for Thumb` + 가능하면 참조 이미지 필요
  - `Kenburn` -> 이미지 + Voice 필요
  - `RVC` -> 원본 TTS 또는 `_GEMI.mp4` 필요

## Current Reality Check

### Ready enough

- `agent-browser` live attach: `ChatGPT/Genspark/SeaArt/GeminiGen/Canva` 확인 완료
- stage2 worker adapter path 및 detached probe 완료
- `stage1.v1` handoff 계약 존재
- legacy post-GPT 서비스 계약 조사 문서 존재

### Not ready enough

- ChatGPT 실제 응답 생성/대기/완료 판정 계층이 아직 `runtime_v2`에 canonicalized 되어 있지 않음
- `1차 테스트`의 실제 blocker는 파서가 아니라 **ChatGPT 상호작용 안정성**임
- 따라서 지금 해야 할 것은 downstream 확장이 아니라 **ChatGPT interaction layer 구현**임
- 추가 확인:
  - `agent-browser --cdp 9222 eval ...` 는 현재 ChatGPT 세션에서 `os error 10060`으로 불안정합니다.
  - Selenium attach도 foreground Chrome과 별개로 내부 session bootstrap에서 read timeout이 발생했습니다.
  - 따라서 남은 실제 blocker는 `ChatGPT` 브라우저 입력/응답 자동화 백엔드 안정화입니다.
  - immediate safe action applied: `runtime_v2/stage1/chatgpt_interaction.py` now surfaces backend instability as canonical failure contract (`CHATGPT_BACKEND_UNAVAILABLE` + `failure_stage=submit/read`) instead of raw `RuntimeError` propagation.
  - `runtime_v2/stage1/chatgpt_runner.py`도 이 canonical failure contract를 해석해 browser relaunch/retry 여부를 결정하도록 맞췄습니다.
  - 따라서 현재 1차 조치의 목적은 “포트 불안정을 숨기지 않고, 상위 계층이 같은 의미로 재시도하게 만드는 것”입니다.
  - follow-up applied: `chatgpt_interaction`는 이제 `session_probe` backend를 통해 raw CDP HTTP(`/json/list`) 상태를 `final_state`로 기록할 수 있습니다. 즉, `agent-browser` eval 실패와 raw CDP 관측 상태를 같은 failure contract에서 함께 보게 됩니다.
  - follow-up complete: `submit/read` 실행은 `runtime_v2/stage1/chatgpt_backend.py`의 `ChatGPTBackend` 인터페이스 뒤로 숨겨졌고, 현행 `AgentBrowserCdpBackend`가 기본 구현입니다.
  - 남은 핵심은 backend 종류를 더 늘리는 것보다, 실제 real-first test evidence를 다시 확보하는 것입니다.

## Program-by-Program Integration Matrix

| Program | Legacy contract role | runtime_v2 current status | Remaining gap | Ready for real test? |
|---|---|---|---|---|
| ChatGPT | canonical producer of downstream fields (`Title`, `Thumb`, `Voice`, `Description`, `Keywords`, scene prompts) | `stage1.v1` handoff exists, parser exists, browser snapshot hookup exists | real prompt submission / send / response-complete wait is not canonicalized | No |
| SeaArt | immediate post-GPT image generator | stage2 worker + agent-browser/live attach evidence complete | consumes minimal handoff, richer GPT field linkage still pending | Yes (after ChatGPT handoff) |
| Genspark | immediate post-GPT image generator | stage2 worker + agent-browser/live attach evidence complete | same as above | Yes (after ChatGPT handoff) |
| TTS | immediate post-GPT voice generator | feeder/workload/worker contracts exist | real upstream `voice_texts` handoff from ChatGPT still not canonicalized | Partial |
| GeminiGen | image->video downstream | stage2 worker + live attach evidence complete | depends on upstream image artifact readiness | Partial |
| Canva | title/thumb + ref image downstream | stage2 worker + live attach evidence complete | depends on upstream `title_for_thumb` + reference image parity | Partial |
| Kenburn | image + voice -> video compositor | GPU worker/feeder exist | depends on image/voice bundle map parity | Partial |
| RVC | TTS/video-derived voice conversion | GPU worker/feeder exist | depends on stable TTS/Gemini video upstream contracts | Partial |

### Matrix interpretation

- 현재 downstream 프로그램 대부분은 “실행 가능한 worker/adapter contract”까지는 준비되어 있습니다.
- 그러나 **실제 테스트 준비도**를 막는 핵심 병목은 여전히 `ChatGPT`입니다.
- 이유는 downstream contract의 대부분이 GPT가 채우는 canonical handoff field에 의존하기 때문입니다.
- 따라서 다음 구현 우선순위는 계속해서 `ChatGPT interaction layer canonicalization`입니다.

## Execution Order

### Phase 1. ChatGPT interaction layer canonicalization

- 레거시 `chatgpt_automation.py`에서 이미 확인한 전략을 `runtime_v2` helper로 이식
- 범위:
  - 입력 selector fallback
    - `#prompt-textarea`
    - `div.ProseMirror[contenteditable='true']`
    - `textarea[name='prompt-textarea']`
    - `textarea`
  - 입력 방식
    - ProseMirror `execCommand('delete')` + `execCommand('insertText')`
    - `input/change/keyup` 이벤트 발생
    - 최후 `send_keys`/keyboard fallback
  - 전송 selector fallback
    - `button[data-testid='send-button']`
    - `#composer-submit-button`
    - `button[aria-label='메시지 보내기']`
    - `button[aria-label='Send Message']`
  - 응답 완료 판단
    - stop button 존재/소멸
    - assistant block/markdown/code block 추출

### Phase 2. Real GPT response -> stage1 handoff bridge

- 위 상호작용 계층이 생성한 실제 GPT 응답을 `gpt_response_text`로 저장
- `stage1.v1` 파서에 연결
- 결과를 Excel/JSON handoff로 병합
- follow-up complete:
  - `stage1_handoff` SSOT schema 추가
  - Excel export/import bridge 추가
  - `handoff -> excel row -> handoff` 라운드트립 계약 테스트 추가
  - downstream-friendly 필드 (`voice_texts`, `Ref Img 1`, `Ref Img 2`, `BGM`, `#01...`)를 정본 규칙으로 고정
  - `qwen3_tts`는 이제 `voice_texts`를 직접 소비할 수 있음
  - `canva`는 이제 `stage1_handoff.ref_img_1/ref_img_2`와 multiline `title_for_thumb`를 직접 소비함
  - `stage1_handoff.contract.version`은 이제 항상 `stage1_handoff.v1.0`으로 정규화됩니다.
  - live `browser_evidence(service=chatgpt, port)` 경로는 이제 `raw_output.json.gpt_capture`에 `status/submit_info/final_state`와 실패 시 `error_code/failure_stage/details`를 기록합니다.
  - live 의도에서 최종 캡처 실패 시 `topic_spec_fallback`로 진행하지 않고 canonical error code로 fail-close 됩니다.

### Phase 3. Ready-to-test gate

- 아래 3개가 모두 참이면 `1차 테스트 준비 완료`
  1. ChatGPT real response artifact 생성
  2. parsed handoff 필드 채움
  3. downstream 1개 서비스가 handoff-derived payload로 실제 실행 가능

- current progress:
  - 1번의 파일 스키마와 failure semantics는 준비 완료입니다. 남은 것은 실제 live artifact를 다시 생성하는 운영 단계입니다.
  - real-first execution attempted: `system/runtime_v2_probe/first-test-real-live-06/`
    - `raw_output.json.gpt_capture`와 `result.json.details.stage1_result.raw_output_path`는 확보되었습니다.
    - verdict: `CHATGPT_BACKEND_UNAVAILABLE` fail-close
    - browser/gpt floor 자체는 healthy였지만, 실제 ChatGPT submit 경로에서 `os error 10060`이 재현되었습니다.
    - 따라서 real-first gate는 아직 `No`, but evidence chain is now preserved even on failure.
  - prompt alignment applied: live ChatGPT 경로는 이제 legacy-style longform production prompt(`영상 제작 모드`, `가이드 최종 출력 포맷`, `[Voice]` 시작, `Research Locale: JP`, `Topic: ...`)를 canonical builder로 생성해 전송합니다.
- backend hardening applied: `AgentBrowserCdpBackend`는 `tab list -> best tab select -> tab <idx> -> eval` 흐름과 retryable `os error 10060/timeout` 재시도를 사용합니다.
  - completion rule hardened: ChatGPT 완료 판정은 `stop-button`이 실제로 나타났다가 사라진 뒤 텍스트가 안정화될 때만 성공으로 봅니다.
  - post-hardening execution attempted: `system/runtime_v2_probe/first-test-real-live-08/`
    - queue는 `running`까지 진입해 이전보다 깊게 들어갔습니다.
    - 하지만 성공 artifact는 아직 생성하지 못해, depth 증가와 잔여 blocker를 동시에 확인했습니다.
  - raw CDP websocket fallback applied: `Runtime.evaluate`는 이제 `suppress_origin=True`로 origin 403을 우회할 수 있습니다.
  - post-fallback execution attempted: `system/runtime_v2_probe/first-test-real-live-09/`
    - raw websocket handshake 자체는 성공 가능함을 확인했습니다.
    - 다만 real-live 전체 흐름은 아직 성공 artifact 대신 `running` 정체와 `NO_JOB` 혼재를 보여, 남은 blocker가 `agent-browser eval` 단일 문제가 아니라 control pass sequencing / long-running interaction 상태 관리까지 포함함을 드러냈습니다.

### Phase 4. Test order

- `mock`
  - payload/next_jobs/adapter semantics만 검증
- `smoke`
  - ChatGPT response -> parsed handoff까지만 실제 확인
- `real first test`
  - `4 머니.xlsx` `Sheet1!row13`
  - real GPT response
  - real parse/handoff
  - downstream 1개 item 처리

## Explicit Do / Do Not

### Do

- 레거시의 계약과 파싱 규칙을 참고합니다.
- `runtime_v2` 내부 helper/contract/test를 늘립니다.
- evidence-first로 진행합니다.

### Do Not

- 레거시 하부 프로그램 자체를 `runtime_v2`에서 직접 호출하지 않습니다.
- 레거시 구조를 그대로 재현하지 않습니다.
- 테스트 준비가 안 된 상태에서 실제 테스트를 반복하지 않습니다.

## Done Definition

- `runtime_v2` 안에서 ChatGPT 실제 응답 생성/완료 판정/파싱/handoff가 닫힘
- `Sheet1!row13` 기준 real first test evidence 확보
- downstream 1개 item real run evidence 확보
- 문서/TODO/COMPLETED가 같은 의미를 사용함

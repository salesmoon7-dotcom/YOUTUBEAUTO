# Runtime_v2 Legacy Pipeline Feasibility Plan

## Goal

- 레거시 프로그램의 실제 row 처리 파이프라인을 단계/산출물/판정 기준으로 고정합니다.
- 현재 `runtime_v2`가 어느 단계까지 동일하게 구현되었고, 무엇이 축약/누락/대체되었는지 확정합니다.
- 이 매핑을 기준으로 `1차 테스트`와 이후 `2차 테스트`를 시작해도 되는지 판정 가능한 Ready-to-Test 게이트를 정의합니다.

## Why This Plan Exists

- 현재 사용자는 `GPT 출력 -> 파싱 -> Excel/JSON 전달 -> 이미지/영상 단계` 전체 흐름이 실제로 준비되었는지 먼저 확인하길 원합니다.
- `runtime_v2`의 stage1은 현재 `topic_spec -> video_plan` 최소 planner에 가깝고, 레거시 `chatgpt_automation.py`가 수행하던 실제 GPT 응답 파싱/필드 분해/엑셀 handoff와는 계약 수준이 다릅니다.
- 따라서 테스트를 더 진행하기 전에 레거시와 `runtime_v2`의 계약 차이를 먼저 고정해야 합니다.

## Observed Legacy Flow

### 1. ChatGPT step

- Source: `D:/YOUTUBE_AUTO/scripts/chatgpt_automation.py`
- Input: `4 머니.xlsx`의 `Topic` 열
- Output target: same Excel row columns
  - `Title`
  - `Title for Thumb`
  - `Voice`
  - scene/video prompt columns
  - `Description`
  - `Keywords`
- Behavior:
  - GPT 응답을 받아 DOM/HTML/parser 계층으로 복구 파싱
  - 필드 단위로 정규화
  - 엑셀 컬럼에 직접 병합
  - 임시 JSON/상태 파일과 함께 후속 단계가 읽을 수 있게 handoff

### 2. Image / Thumbnail / Video steps

- `D:/YOUTUBE_AUTO/scripts/genspark_automation.py`
  - 엑셀의 이미지 프롬프트를 읽고 Genspark image output 생성
- `D:/YOUTUBE_AUTO/scripts/seaart_automation.py`
  - 엑셀 이미지 프롬프트를 읽고 SeaArt image output 생성
- `D:/YOUTUBE_AUTO/scripts/canva_automation.py`
  - `Title for Thumb` + ref image를 읽어 썸네일 PNG 생성
- `D:/YOUTUBE_AUTO/scripts/geminigen_automation.py`
  - 이미지 입력을 읽어 video output 생성

### 3. Legacy Contract Summary

- 레거시는 Excel이 canonical state store입니다.
- GPT 단계에서 이미 downstream 필드를 대부분 완성합니다.
- 후속 브라우저 프로그램은 Excel/JSON 산출물을 읽어 독립 실행합니다.
- 즉, 테스트 시작점은 `GPT 응답 파싱이 완료되어 downstream 필드가 실제로 채워졌는가` 입니다.

## Observed Runtime_v2 Flow

### 1. Stage1 current behavior

- Sources:
  - `runtime_v2/stage1/chatgpt_runner.py`
  - `runtime_v2/contracts/video_plan.py`
  - `runtime_v2/excel/state_store.py`
- Current contract:
  - `topic_spec -> video_plan`
  - `scene_plan`, `voice_plan`, `asset_plan`, `reason_code`, `evidence`
  - route -> stage2 jobs
- Current Excel merge:
  - `Status`
  - `Video Plan` or `Script`
  - `Reason Code`
- Missing relative to legacy:
  - GPT raw output capture contract
  - GPT structured parse contract for `Title`, `Title for Thumb`, `Description`, `Keywords`, per-scene prompt columns
  - parsed JSON handoff contract that mirrors legacy downstream needs

### 2. Stage2 current behavior

- Sources:
  - `runtime_v2/stage2/json_builders.py`
  - `runtime_v2/stage2/genspark_worker.py`
  - `runtime_v2/stage2/seaart_worker.py`
  - `runtime_v2/stage2/canva_worker.py`
  - `runtime_v2/stage2/geminigen_worker.py`
- Current contract:
  - `video_plan`을 기반으로 service payload 생성
  - `service_artifact_path` 기준 산출물 계약 유지
  - `use_agent_browser_services` opt-in 가능
  - detached row1 probe 존재
- Current limitation:
  - downstream worker는 동작하지만 upstream GPT parse completeness를 전제로 하지 않습니다.
  - 즉, stage2는 최소 artifact contract는 있으나, 레거시 downstream 필드 completeness와는 아직 1:1이 아닙니다.

## Legacy -> Runtime_v2 Mapping

| Legacy step | Legacy artifact/contract | Runtime_v2 current equivalent | Status |
|---|---|---|---|
| Topic row read | Excel `Topic`, `Status` snapshot | `topic_spec` | Same intent |
| GPT execution | real GPT browser output | 없음 (`topic_spec` 기반 planner only) | Missing |
| GPT parse | structured field extraction | 없음 | Missing |
| Excel handoff | Title/Thumb/Voice/Scene/Description/Keywords columns | `merge_video_plan_to_excel()` minimal summary only | Reduced |
| JSON handoff | downstream scripts read JSON/temp outputs | `video_plan.json`, `stage1_result`, stage2 payloads | Partial |
| Genspark image | direct browser automation | stage2 worker + adapter/agent-browser | Partial/Replaceable |
| SeaArt image | direct browser automation | stage2 worker + adapter/placeholder | Partial/Replaceable |
| Canva thumb | Title for Thumb + ref img | stage2 worker + adapter/placeholder | Partial/Replaceable |
| GeminiGen video | image->video | stage2 worker + adapter/placeholder | Partial/Replaceable |

## Blocking Gaps Before True Test Readiness

### Blocker A. GPT real-output contract missing

- 현재 `runtime_v2` stage1은 실제 GPT 출력/응답 parser를 돌리지 않습니다.
- 따라서 사용자가 요구한 `GPT 출력 -> 파싱 -> Excel/JSON 전달`의 본질은 아직 구현되지 않았습니다.

### Blocker B. Parsed field handoff missing

- 레거시 기준 downstream이 기대하는 `Title`, `Title for Thumb`, `Description`, `Keywords`, per-scene prompt field가 `runtime_v2` canonical contract에 없습니다.
- 따라서 현재 stage2 artifact success는 “최소 worker contract success”일 뿐, 레거시 동등 handoff success가 아닙니다.

### Blocker C. Test meaning drift

- 지금 `1차 테스트`를 진행하면 “한 개 item 처리 가능성”은 확인할 수 있지만, 사용자가 기대한 “레거시와 같은 GPT→파싱→전달 파이프라인 검증”은 아닙니다.

## Ready-to-Test Gates

아래 3개가 모두 만족될 때만 “레거시 의미의 1차 테스트 준비 완료”로 판정합니다.

1. **GPT Output Gate**
- 실제 GPT 출력이 artifact로 저장됨
- raw output path + parsed output path가 남음

2. **Parse/Handoff Gate**
- 최소 필드가 canonical JSON에 존재함
  - `title`
  - `title_for_thumb`
  - `description`
  - `keywords`
  - `voice_plan`
  - scene prompt set
- Excel merge 경로가 최소 field subset을 기록함

3. **Downstream Consumption Gate**
- stage2 worker가 위 parsed handoff를 읽어 실제 payload를 구성함
- placeholder가 아니라 handoff-derived payload 사용 여부를 판정 가능해야 함

## Execution Plan

### Task 1. Define canonical GPT parse contract

- Add a `stage1_parsed_payload` contract in `runtime_v2`
- Include legacy-equivalent fields:
  - title
  - thumb title
  - description
  - keywords
  - voice/script mapping
  - scene prompts

### Task 2. Separate stage1 planner from stage1 parser

- 현재 `build_video_plan_from_topic_spec()`는 planner 역할만 합니다.
- 이를 유지하되, 실제 테스트 readiness는 별도 parser contract가 있을 때만 `ready`로 간주합니다.

### Task 3. Add Excel/JSON handoff bridge

- `runtime_v2/excel/state_store.py`에 최소 parsed fields merge 함수 추가
- 동시에 canonical JSON handoff file 저장

### Task 4. Rewire stage2 payload builders

- `runtime_v2/stage2/json_builders.py`가 planner fallback만 보지 않고 parsed handoff도 읽게 만듭니다.

### Task 5. Only then resume 1st test

- `4 머니.xlsx` row13 기준으로
  - GPT output artifact 생성
  - parse JSON 생성
  - Excel/JSON handoff 기록
  - stage2 one-item run
- 이 순서를 실제 evidence로 확인합니다.

## Current Decision

- `stage1 GPT output/parse/handoff canonical contract` 1차 배치는 구현되었습니다.
- 실제 evidence:
  - `system/runtime_v2_probe/stage1-row13-evidence-01/raw_output.json`
  - `system/runtime_v2_probe/stage1-row13-evidence-01/parsed_payload.json`
  - `system/runtime_v2_probe/stage1-row13-evidence-01/stage1_handoff.json`
- `Sheet1!row13` 기준으로 위 3개 artifact가 생성되고, downstream `next_jobs`도 3개(`genspark`, `seaart`, `render`)까지 이어지는 것을 확인했습니다.
- 남은 일은 이 canonical parsed handoff를 실제 GPT/browser 실행 결과와 연결하고, Excel handoff 필드를 레거시 수준까지 넓히는 것입니다.

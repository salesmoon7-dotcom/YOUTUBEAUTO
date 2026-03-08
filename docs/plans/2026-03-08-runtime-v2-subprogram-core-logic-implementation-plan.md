# Runtime V2 Subprogram Core Logic Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`의 하부프로그램 핵심 로직을 `gpt -> seaart -> genspark -> canva -> geminigen -> tts -> kenburns -> rvc` 순서로 하나씩 구현해, 먼저 1개 처리와 1행 처리를 검증하고, 파이프라인 완료 뒤에는 24시간 가동 완성 단계로 확장합니다.

**Architecture:** 각 프로그램의 core logic는 `입력 계약 검증 -> 단일 실행 adapter 호출 -> 산출물 존재 검증 -> 표준 worker_result 반환`까지만 포함합니다. 재시도, backoff, 로그인 복구, queue 정책, latest-run writer는 상위 owner가 계속 소유하며, 워커는 fail-closed와 관측 가능한 evidence만 보장합니다.

**Document Status:** 이 문서는 구현 완료 보고가 아니라 실행 계획입니다. 아래 task/command/expected 항목은 앞으로 검증할 절차이며, 실제 완료 판정은 각 단계의 코드 변경과 명령 증거가 확인된 뒤에만 내립니다.

**Reference Boundary:** `D:\YOUTUBE_AUTO`의 기존 구현은 핵심 기능을 이해하기 위한 참고 입력만 제공합니다. `runtime_v2`는 자체 계약과 자체 adapter를 기준으로 재구성하며, 참고 저장소의 모듈/클래스/함수/상태모델을 직접 재사용, 포팅, 호출하지 않습니다.

**Tech Stack:** Python 3.13, `runtime_v2`, browser manager/supervisor, JSON contracts, file-based evidence, existing `tests/test_runtime_v2_stage1_chatgpt.py`, `tests/test_runtime_v2_stage2_workers.py`, `tests/test_runtime_v2_stage2_contracts.py`, `tests/test_runtime_v2_gpu_workers.py`, `tests/test_runtime_v2_phase2.py`, `tests/test_runtime_v2_control_plane_chain.py`

---

## Current Audit

- `runtime_v2/manager.py`, `runtime_v2/excel/source.py`, `runtime_v2/excel/selector.py`에는 Excel의 `Topic`/`Status`를 읽어 `topic_spec`으로 변환하는 최소 ingest 경로가 존재합니다.
- `runtime_v2/stage1/chatgpt_runner.py`는 이미 들어온 `topic_spec`을 `video_plan.json -> next_jobs[]`로 바꾸는 stage1 planner입니다.
- 다만 이 둘을 합쳐도, 참고 문서가 보여주는 GPT의 실제 핵심 책임(행 선택 기준, topic parsing, JSON mapping, 결과 merge까지 포함한 row 실행 계약)을 아직 모두 대체했다고 볼 수는 없습니다.
- 따라서 GPT는 `완료`가 아니라 `minimal ingest exists, full parsing/mapping core missing` 상태로 분류합니다.
- 현재 구현(As-is)은 `Excel Topic/Status ingest -> topic_spec -> stage1 planner consumes topic_spec`까지입니다.
- 아직 미구현(Not yet)은 `행 단위 GPT parsing`, `컬럼/필드 매핑`, `row 실행 오케스트레이션`, `결과/상태의 Excel 반영 parity`입니다.
- `runtime_v2/stage2/genspark_worker.py`, `runtime_v2/stage2/seaart_worker.py`, `runtime_v2/stage2/canva_worker.py`, `runtime_v2/stage2/geminigen_worker.py`는 현재 모두 `native_not_implemented_result(...)`로 종료합니다.
- `runtime_v2/stage2/json_builders.py`는 stage2 payload와 산출물 경로만 만들고, 실제 서비스 핵심 로직은 아직 비어 있습니다.
- `runtime_v2/workers/qwen3_worker.py`, `runtime_v2/workers/kenburns_worker.py`, `runtime_v2/workers/rvc_worker.py`와 `tests/test_runtime_v2_gpu_workers.py` 기준으로 TTS/GPU 계열은 별도 축으로 이미 존재하므로, stage2 4서비스 다음 순서로 같은 하부프로그램 계획에 포함해야 합니다.
- GPT 참고 기준은 `D:\YOUTUBE_AUTO\docs\plans\2026-02-26-gpt-parser-stabilization-report.md`, `D:\YOUTUBE_AUTO\docs\plans\2026-03-02-row12-gpt-json-mapping-report.md`, `D:\YOUTUBE_AUTO\docs\plans\2026-03-01-chatgpt-root-cause-and-simplification-plan.md`에서 확인하고, 서비스별 핵심 산출 책임은 `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py`, `D:\YOUTUBE_AUTO\scripts\seaart_automation.py`, `D:\YOUTUBE_AUTO\scripts\genspark_automation.py`, `D:\YOUTUBE_AUTO\scripts\canva_automation.py`, `D:\YOUTUBE_AUTO\scripts\geminigen_automation.py`, `D:\YOUTUBE_AUTO\tests\test_geminigen_json_contract.py`를 참조 전용으로 읽어 추출합니다.

## Investigation Findings

- Observation: GPT는 `topic_spec` 이후 planner는 있으나 row 실행 계약 전체는 아직 아닙니다.
  - Evidence: `runtime_v2/manager.py`, `runtime_v2/excel/source.py`, `runtime_v2/excel/selector.py`, `runtime_v2/stage1/chatgpt_runner.py`, `tests/test_runtime_v2_excel_bridge.py`, `tests/test_runtime_v2_stage1_excel_merge.py`
  - Conclusion: GPT는 별도 감사/분해 task가 먼저 필요합니다.
  - Unknown: row parsing/mapping parity를 어디까지 runtime_v2에서 재구성할지
- Observation: SeaArt/Genspark/Canva/GeminiGen stage2 worker는 현재 placeholder입니다.
  - Evidence: `runtime_v2/stage2/seaart_worker.py`, `runtime_v2/stage2/genspark_worker.py`, `runtime_v2/stage2/canva_worker.py`, `runtime_v2/stage2/geminigen_worker.py`
  - Conclusion: 비-GPT 서비스는 공통적으로 `1개 처리 -> 1행 처리` 구조가 적합합니다.
  - Unknown: Genspark/GeminiGen의 세부 출력 제약과 row 집계 성격
- Observation: TTS/KenBurns/RVC는 runtime_v2 안에 이미 worker/test 축이 존재합니다.
  - Evidence: `runtime_v2/workers/qwen3_worker.py`, `runtime_v2/workers/kenburns_worker.py`, `runtime_v2/workers/rvc_worker.py`, `tests/test_runtime_v2_gpu_workers.py`, `tests/test_runtime_v2_phase2.py`
  - Conclusion: stage2 4서비스와 별개가 아니라 같은 하부프로그램 완성 순서에 포함해야 합니다.
  - Unknown: 1행 기준 체인 검증에서 어떤 row policy를 최소 기준으로 잠글지

## Scope Coverage Matrix

| Service | Minimum support in this plan | Phase 1 evidence | Phase 2 evidence | Phase 3 relation |
|---|---|---|---|---|
| GPT | Excel topic ingest + planner audit | topic_spec seed + planner output | row parsing/mapping/merge evidence | GPT floor/health 24h에 연결 |
| SeaArt | one image-item path | single artifact exists | one row assigned items handled | 24h에서는 browser health 영향 |
| Genspark | one service-item path | single artifact exists | one row assigned items handled | 24h에서는 browser health 영향 |
| Canva | one thumbnail-item path | single static artifact exists | one row thumbnail item handled | 24h에서는 browser/download health 영향 |
| GeminiGen | one video-item attempt path | contract + artifact attempt | one row selected items handled | 24h에서는 browser/state stability 영향 |
| TTS | one audio-item path | single audio artifact exists | one row voice chain handled | 24h에서는 GPU lock/state 영향 |
| KenBurns | one video compose path | single video artifact exists | one row compose chain handled | 24h에서는 GPU lock/state 영향 |
| RVC | one voice-convert path | single converted audio artifact exists | one row voice chain handled | 24h에서는 GPU lock/state 영향 |
| 24h | pipeline already complete | not applicable | not applicable | health/evidence stability gate |

## Phase Advancement Targets

각 단계는 참고 기준과의 `전체 parity`가 아니라, runtime_v2에서 안전하게 증명된 완성도 수준을 뜻합니다. 참고 기준은 회귀/일관성 확인용 비교 대상일 뿐이며, 완료 범위는 아래 `지원 사용자 여정 + 품질 게이트 + 비목표`로 한정합니다.

| Service | 1차 목표 완료 시점 | 2차 목표 완료 시점 | 명시적 비목표 |
|---|---|---|---|
| GPT | `Excel topic ingest -> topic_spec -> stage1 planner` 대표 여정 1개가 검증되고 planner 산출이 남음 | `row selection -> parsing/mapping -> stage1 merge evidence`까지 닫히고 최소 1종 실패 분류가 보임 | 레퍼런스의 모든 prompt 옵션/튜닝/UI 패리티 |
| SeaArt | `단일 prompt -> 단일 image artifact` 여정 1개와 파일 무결성이 검증됨 | row 안에서 item 집합이 순서/중단 기준 1종 아래 처리되고 대기/실패 관측 포인트가 남음 | 전체 파라미터/배치/업스케일 패리티 |
| Genspark | `단일 prompt -> 단일 service artifact` 여정 1개가 검증됨 | row 안에서 item 집합이 처리되고 queue/장시간 작업 관측 포인트 또는 실패 분류 1종이 추가됨 | 모든 모드/슬라이드/플러그인 패리티 |
| Canva | `thumb_data -> 단일 static artifact` 여정 1개와 export 성공이 검증됨 | row 안에서 thumbnail item 처리와 입력 조합/산출 evidence가 남고 주요 실패 요인 1종이 분류됨 | 전체 에디터 기능/모든 export 포맷 패리티 |
| GeminiGen | `reference input -> 단일 video artifact attempt` 여정 1개와 계약 필드가 검증됨 | row 안에서 selected scene 집합이 처리되고 selection policy 또는 실패 복구 기준 1종이 검증됨 | 전체 모델/모드/파라미터 패리티 |
| TTS | `script text -> 단일 audio artifact` 여정 1개와 기본 길이 제약이 검증됨 | row voice chain 안에서 TTS 산출 전달과 chunk/실패 처리 1종이 검증됨 | 전체 SSML/발음 사전/세부 보이스 패리티 |
| KenBurns | `image/audio inputs -> 단일 video artifact` 여정 1개와 결정적 산출이 검증됨 | row compose chain 안에서 KenBurns 산출과 전환/타이밍 기준 1종이 검증됨 | 전체 편집 파라미터/GUI 수준 패리티 |
| RVC | `voice input -> 단일 converted artifact` 여정 1개와 GPU gate 준수가 검증됨 | row voice chain 안에서 upstream/downstream evidence 연결과 장시간 처리 기준 1종이 검증됨 | 전체 모델 관리/고급 파라미터 패리티 |
| 24h | 해당 없음 | 해당 없음 | 개별 서비스의 최초 happy-path 구현 대체 |

이 표의 의미는 `1차 = 프로그램 자체의 최소 독립 처리 검증`, `2차 = row 문맥 안에서의 최소 연결/집계/중단 기준 + 안정성/관측성 1종 검증`입니다. 이 수준을 넘는 품질/속도/대량 처리/전체 parity는 3차 목표 이전에 완료로 주장하지 않습니다.

## Core Logic Definition (Locked)

각 하부프로그램의 core logic는 아래 4개만 포함합니다.

1. 입력 계약 검증 (`prompt`, `scene_index`, `service_artifact_path`, 추가 필수 필드)
2. 단일 실행 경로 호출 (서비스별 core function 1개)
3. 기대 산출물 파일 존재/확장자 검증
4. `worker_result` 표준 필드와 workspace evidence 기록

아래는 core logic에 포함하지 않습니다.

- 로그인 복구, 세션 교체, browser health 판정
- retry/backoff/circuit 정책
- Excel 직접 갱신
- placeholder 성공, fallback OK, 침묵 보정

## Non-Goals

- 참고 저장소의 모듈/클래스/함수 시그니처를 `runtime_v2`에 복제하지 않습니다.
- 참고 저장소 경로를 runtime 경로, adapter 경로, worker 경로에 의존성으로 연결하지 않습니다.
- 참고 저장소의 상태/에러/재시도 모델을 그대로 가져오지 않고 `runtime_v2` 계약으로 다시 정의합니다.

## Reference-Only Core Responsibilities (Observed vs Assumed)

- GPT
  - Observed: Excel row/topic 입력을 바탕으로 row 실행 계약, parsing/mapping, 결과 merge까지 연결되는 더 넓은 책임이 문서에 나타납니다.
  - Assumed for runtime_v2: 현재는 `topic_spec` 이후 planner/runner 범위부터 다시 잠그고 확장합니다.
- SeaArt
  - Observed: `D:\YOUTUBE_AUTO\scripts\seaart_automation.py`는 이미지 프롬프트를 받아 SeaArt에서 이미지 산출/다운로드를 수행하는 자동화 프로그램입니다.
  - Assumed for runtime_v2: 최소 코어는 `prompt -> image artifact` 수준으로 두고, 장수/모델/큐 모드는 증거 확보 전까지 코어로 고정하지 않습니다.
- Genspark
  - Observed: `D:\YOUTUBE_AUTO\scripts\genspark_automation.py`는 이미지 생성 자동화로 설명되지만, 문서상 카테고리/모드/슬라이드 경로가 섞여 있어 단일 출력 규칙을 아직 고정하면 안 됩니다.
  - Assumed for runtime_v2: 최소 코어는 `prompt -> service artifact` 수준의 가설만 유지하고, 출력 모달리티/수량/세부 모델은 추후 관측으로 확정합니다.
- Canva
  - Observed: `D:\YOUTUBE_AUTO\scripts\canva_automation.py`는 `Title for Thumb`/참조 이미지/템플릿 조합을 바탕으로 정적 디자인 산출물을 내보냅니다.
  - Assumed for runtime_v2: 최소 코어는 `thumb_data -> static thumbnail artifact`이며, PNG는 현재 사용 케이스의 목표 포맷일 뿐 Canva의 전체 코어로 단정하지 않습니다.
- GeminiGen
  - Observed: `D:\YOUTUBE_AUTO\scripts\geminigen_automation.py`와 `D:\YOUTUBE_AUTO\tests\test_geminigen_json_contract.py`는 사람 카테고리 기준 task를 만들고, first frame 입력을 바탕으로 `_GEMI` 영상 산출을 시도합니다.
  - Assumed for runtime_v2: 최소 코어는 `selected scene/reference input -> video artifact attempt`이며, mp4 단일 포맷/단일 파일을 코어로 확정하지 않습니다.
- TTS (`qwen3_tts`)
  - Observed: `runtime_v2/workers/qwen3_worker.py`와 `tests/test_runtime_v2_gpu_workers.py` 기준으로 텍스트 입력을 받아 음성 산출물을 남기는 worker 축이 이미 존재합니다.
  - Assumed for runtime_v2: 최소 코어는 `script text -> audio artifact`입니다.
- KenBurns
  - Observed: `runtime_v2/workers/kenburns_worker.py`와 `tests/test_runtime_v2_gpu_workers.py` 기준으로 이미지/오디오를 받아 영상 산출물을 조합하는 worker 축이 이미 존재합니다.
  - Assumed for runtime_v2: 최소 코어는 `image/audio inputs -> video artifact`입니다.
- RVC
  - Observed: `runtime_v2/workers/rvc_worker.py`와 `tests/test_runtime_v2_gpu_workers.py` 기준으로 음성 입력을 변환 산출물로 바꾸는 worker 축이 이미 존재합니다.
  - Assumed for runtime_v2: 최소 코어는 `voice input -> converted voice artifact`입니다.

## Order Policy

구현 순서는 반드시 아래 순서를 지킵니다.

1. GPT
2. SeaArt
3. Genspark
4. Canva
5. GeminiGen
6. TTS
7. KenBurns
8. RVC
9. 24h Operation Completion

한 프로그램이 `contract + artifact + evidence + error_code`를 닫기 전에는 다음 프로그램으로 넘어가지 않습니다.

### Task 1: GPT Input Contract And Parsing Scope Audit

**Files:**
- Modify: `runtime_v2/manager.py`
- Modify: `runtime_v2/excel/source.py`
- Modify: `runtime_v2/excel/selector.py`
- Modify: `runtime_v2/stage1/chatgpt_runner.py`
- Test: `tests/test_runtime_v2_excel_bridge.py`
- Test: `tests/test_runtime_v2_excel_topic_end_to_end.py`
- Test: `tests/test_runtime_v2_stage1_chatgpt.py`
- Test: `tests/test_runtime_v2_stage1_excel_merge.py`

**Step 1: GPT의 현재 구현 범위를 실패 테스트로 고정합니다**

```python
def test_excel_topic_row_seeds_topic_spec_before_stage1_runner():
    seeded = seed_excel_row(...)
    assert seeded["status"] == "seeded"
    assert seeded["topic_spec"]["topic"] == "Bridge topic"

def test_stage1_runner_only_plans_from_existing_topic_spec():
    result = run_stage1_chatgpt_job(topic_spec, workspace, debug_log="logs/run.jsonl")
    assert result["status"] == "ok"
    assert Path(result["result_path"]).exists()
    assert result["next_jobs"]
```

**Step 2: 테스트를 실행해 현재 범위를 사실로 확정합니다**

Run: `python -m pytest tests/test_runtime_v2_excel_bridge.py tests/test_runtime_v2_excel_topic_end_to_end.py tests/test_runtime_v2_stage1_chatgpt.py tests/test_runtime_v2_stage1_excel_merge.py -q`
Expected: 최소 ingest와 stage1 planner 범위는 PASS하지만, GPT parser/mapping parity는 아직 증명되지 않음

**Step 3: GPT의 부족한 범위를 분리합니다**

```python
seeded = seed_excel_row(...)
topic_spec = seeded["topic_spec"]
video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)
next_jobs, _ = route_video_plan(video_plan)
```

**Step 4: GPT 완료 기준을 다시 잠급니다**

- GPT 완료 기준은 `topic_spec planner exists`가 아니라 `row selection -> Excel topic ingest -> topic parsing/mapping -> stage1 plan -> stage1 merge evidence`까지 닫히는 것입니다.
- 현재 구현은 `Excel Topic/Status ingest`와 `topic_spec -> video_plan -> next_jobs`까지만 존재하므로, GPT는 이후 별도 구현 task로 더 쪼개야 합니다.
- Stage1 runner 하나만 hardening해서 GPT가 끝난 것으로 판정하지 않습니다.
- 현 단계 문서에서는 GPT를 레거시 의미의 `parser/mapping core`와 동등하다고 표현하지 않고, `post-ingest stage1 planner/runner`로 한정해 부릅니다.

## Non-GPT Two-Phase Plan

비-GPT 서비스는 모두 같은 두 단계로 진행합니다.

- 1차 목표: `1개 처리 검증`
  - 의미: 단일 item 하나를 끝까지 통과시키는 입출력 계약과 happy-path 산출물을 증명합니다.
  - 포함: 입력 계약, 단일 adapter 호출, 산출물 존재 확인, 최소 오류 1종 표면화
  - 제외: 대량 처리, 일반화, retry/recovery, 성능, 복수 정책
- 2차 목표: `1행 처리 검증`
  - 의미: row 내부 item 묶음을 한 번 처리하면서 순서/중단/집계 중 최소 1개 정책을 증명합니다.
  - 포함: item 반복, row 단위 evidence, 부분 실패 관측 포인트
  - 제외: 모든 row 정책 완성, 모든 예외 케이스, 대량 row 처리
- 3차 목표: `24시간 가동 완성`
  - 의미: 전체 파이프라인이 닫힌 뒤에만 적용하는 운영 단계로, 24시간 상시 가동 중 헬스/재기동/락/증거가 안정적으로 유지되는지 검증합니다.
  - 포함: browser health, GPT floor, GPU lock, latest-run/result evidence의 운영 안정성
  - 제외: 개별 하부프로그램의 최초 happy-path 구현

이 구조는 `row = item 반복 + 최소 묶음 제어`라는 현재 가정 위에 서 있습니다. 만약 특정 서비스의 row가 집계/공유 상태/교차 검증을 더 강하게 요구하면, 2차 목표는 `1행 최소 집계 1종 검증`까지만 잠그고, 그 즉시 동일 세션의 새 기능 추가를 중단한 뒤 canonical plan 기준의 아키텍처 재검토로 승격합니다.

## Commit Rule Per Task

- 각 Task의 1차 목표 또는 2차 목표를 통과한 뒤에는 바로 그 범위만 커밋합니다.
- 기본 커밋 템플릿은 저장소 스타일을 따라 `semantic + english`로 유지합니다.
- 예시:
  - `git add tests/test_runtime_v2_stage2_workers.py runtime_v2/stage2/seaart_worker.py`
  - `git commit -m "feat: prove seaart single-item path"`
  - `git add tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_stage2_workers.py runtime_v2/stage2/json_builders.py`
  - `git commit -m "feat: prove seaart single-row path"`
- 한 커밋이 여러 목표를 동시에 닫지 않도록 `1차 목표`와 `2차 목표`는 별도 커밋으로 유지합니다.

### Task 2: SeaArt Two-Phase Validation

**Files:**
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Modify: `runtime_v2/stage2/json_builders.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`

**1차 목표: 1개 처리 검증**

```python
def test_seaart_worker_processes_one_item_and_writes_artifact(tmp_path):
    result = run_seaart_job(job, tmp_path / "artifacts")
    assert result["status"] == "ok"
    assert Path(job.payload["service_artifact_path"]).exists()
```

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k seaart`
Expected: 처음에는 `native_seaart_not_implemented`로 FAIL, 구현 후 PASS

**2차 목표: 1행 처리 검증**

```python
def test_seaart_row_processing_handles_all_items_for_one_row(tmp_path):
    jobs, _ = build_stage2_jobs(video_plan)
    seaart_jobs = [job for job in jobs if job["job"]["worker"] == "seaart"]
    assert seaart_jobs
```

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_stage2_workers.py -q -k seaart`
Expected: 1행에서 배정된 SeaArt item들이 모두 표준 evidence를 남김

### Task 3: Genspark Two-Phase Validation

**Files:**
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Modify: `runtime_v2/stage2/json_builders.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`

**1차 목표: 1개 처리 검증**

```python
def test_genspark_worker_processes_one_item_and_writes_artifact(tmp_path):
    result = run_genspark_job(job, tmp_path / "artifacts")
    assert result["status"] == "ok"
    assert Path(job.payload["service_artifact_path"]).exists()
```

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k genspark`
Expected: 처음에는 `native_genspark_not_implemented`로 FAIL, 구현 후 PASS

**2차 목표: 1행 처리 검증**

```python
def test_genspark_row_processing_handles_all_items_for_one_row(tmp_path):
    jobs, _ = build_stage2_jobs(video_plan)
    genspark_jobs = [job for job in jobs if job["job"]["worker"] == "genspark"]
    assert genspark_jobs
```

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_stage2_workers.py -q -k genspark`
Expected: 1행에서 배정된 Genspark item들이 모두 표준 evidence를 남김

### Task 4: Canva Two-Phase Validation

**Files:**
- Modify: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Modify: `runtime_v2/stage2/request_builders.py`
- Modify: `runtime_v2/stage2/json_builders.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`

**1차 목표: 1개 처리 검증**

```python
def test_canva_worker_processes_one_item_and_writes_thumbnail(tmp_path):
    result = run_canva_job(job, tmp_path / "artifacts")
    assert result["status"] == "ok"
    assert Path(job.payload["service_artifact_path"]).exists()
```

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k canva`
Expected: 처음에는 `native_canva_not_implemented`로 FAIL, 구현 후 PASS

**2차 목표: 1행 처리 검증**

```python
def test_canva_row_processing_handles_thumbnail_item_for_one_row(tmp_path):
    jobs, _ = build_stage2_jobs(video_plan)
    canva_jobs = [job for job in jobs if job["job"]["worker"] == "canva"]
    assert canva_jobs
```

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_stage2_workers.py -q -k canva`
Expected: 1행에서 배정된 Canva item이 표준 evidence를 남김

### Task 5: GeminiGen Two-Phase Validation

**Files:**
- Modify: `runtime_v2/stage2/json_builders.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`

**1차 목표: 1개 처리 검증**

```python
def test_geminigen_contract_and_worker_process_one_item(tmp_path):
    assert "source_frame_path" in job.payload
    result = run_geminigen_job(job, tmp_path / "artifacts")
    assert Path(job.payload["service_artifact_path"]).exists()
```

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_stage2_workers.py -q -k geminigen`
Expected: 처음에는 계약/worker 공백으로 FAIL, 구현 후 PASS

**2차 목표: 1행 처리 검증**

```python
def test_geminigen_row_processing_handles_all_selected_items_for_one_row(tmp_path):
    jobs, _ = build_stage2_jobs(video_plan)
    geminigen_jobs = [job for job in jobs if job["job"]["worker"] == "geminigen"]
    assert geminigen_jobs
```

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_stage2_workers.py -q -k geminigen`
Expected: 1행에서 선택된 GeminiGen item들이 모두 표준 evidence를 남김

### Task 6: TTS Two-Phase Validation

**Files:**
- Verify: `runtime_v2/workers/qwen3_worker.py`
- Test: `tests/test_runtime_v2_gpu_workers.py`
- Test: `tests/test_runtime_v2_phase2.py`

**1차 목표: 1개 처리 검증**

- TTS: `script text -> audio artifact`

Run: `python -m pytest tests/test_runtime_v2_gpu_workers.py -q -k qwen3`
Expected: 단일 TTS item이 audio artifact를 남기고 기본 계약과 충돌하지 않음을 확인

**2차 목표: 1행 처리 검증**

- row 하나에서 TTS 산출이 다음 단계로 전달되는지 확인합니다.

Run: `python -m pytest tests/test_runtime_v2_phase2.py -q`
Expected: 1행 기준 phase2 체인에서 TTS evidence가 남김

### Task 7: KenBurns Two-Phase Validation

**Files:**
- Verify: `runtime_v2/workers/kenburns_worker.py`
- Test: `tests/test_runtime_v2_gpu_workers.py`
- Test: `tests/test_runtime_v2_phase2.py`

**1차 목표: 1개 처리 검증**

- KenBurns: `image/audio inputs -> video artifact`

Run: `python -m pytest tests/test_runtime_v2_gpu_workers.py -q -k kenburns`
Expected: 단일 KenBurns item이 video artifact를 남기고 기본 계약과 충돌하지 않음을 확인

**2차 목표: 1행 처리 검증**

- row 하나에서 KenBurns 산출이 row evidence와 함께 남는지 확인합니다.

Run: `python -m pytest tests/test_runtime_v2_phase2.py -q`
Expected: 1행 기준 phase2 체인에서 KenBurns evidence가 남김

### Task 8: RVC Two-Phase Validation

**Files:**
- Verify: `runtime_v2/workers/rvc_worker.py`
- Test: `tests/test_runtime_v2_gpu_workers.py`
- Test: `tests/test_runtime_v2_phase2.py`

**1차 목표: 1개 처리 검증**

- RVC: `voice input -> converted voice artifact`

Run: `python -m pytest tests/test_runtime_v2_gpu_workers.py -q -k rvc`
Expected: 단일 RVC item이 converted artifact를 남기고 GPU gate와 충돌하지 않음을 확인

**2차 목표: 1행 처리 검증**

- row 하나에서 RVC 산출이 upstream/downstream evidence와 함께 연결되는지 확인합니다.

Run: `python -m pytest tests/test_runtime_v2_phase2.py -q`
Expected: 1행 기준 phase2 체인에서 RVC evidence가 남김

### Task 9: Cross-Service Verification Gate

**Files:**
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`
- Test: `tests/test_runtime_v2_stage1_chatgpt.py`

**Step 1: 프로그램별 테스트를 모두 순차 실행합니다**

Run: `python -m pytest tests/test_runtime_v2_stage1_chatgpt.py -q`
Expected: PASS

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py -q`
Expected: PASS

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q`
Expected: PASS

**Step 2: guardrail 증거를 확인합니다**

Run: `python -m py_compile runtime_v2/stage1/chatgpt_runner.py runtime_v2/stage2/genspark_worker.py runtime_v2/stage2/seaart_worker.py runtime_v2/stage2/canva_worker.py runtime_v2/stage2/geminigen_worker.py runtime_v2/stage2/json_builders.py runtime_v2/contracts/stage2_contracts.py`
Expected: PASS

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q`
Expected: `run_id`, `error_code`, `attempt/backoff` 의미 drift 관련 계약 테스트가 PASS

Run: `python -c "from pathlib import Path; p=Path(r'D:\YOUTUBEAUTO\docs\plans\2026-03-08-runtime-v2-subprogram-core-logic-implementation-plan.md'); text=p.read_text(encoding='utf-8'); print('run_id' in text, 'error_code' in text, 'attempt/backoff' in text)"`
Expected: `True True True`

**Step 3: 단계 완료 판정을 고정합니다**

- 1차 목표 완료는 `1개 item happy-path가 검증됨`을 의미할 뿐, 범용 처리 완료를 뜻하지 않습니다.
- 2차 목표 완료는 `1행 묶음 제어가 검증됨`을 의미할 뿐, 모든 row 정책 완료를 뜻하지 않습니다.
- 3차 목표 완료는 `파이프라인 완료 뒤 24시간 운영 안정성이 검증됨`을 의미하며, 이 단계 전에는 24h 완료를 주장하지 않습니다.
- 각 프로그램은 해당 단계에서 잠근 `service_artifact_path` 또는 동등한 표준 artifact evidence를 남겨야 합니다.
- `run_id`, `error_code`, `attempt/backoff` 의미 drift가 없을 때만 다음 프로그램으로 진행합니다.

### Task 10: 24h Operation Completion Gate

이 단계는 개별 하부프로그램과 1행 파이프라인이 모두 닫힌 뒤에만 진행합니다.

**Files:**
- Verify: `runtime_v2/browser/supervisor.py`
- Verify: `runtime_v2/gpt_pool_monitor.py`
- Verify: `runtime_v2/gpt_autospawn.py`
- Verify: `runtime_v2/gpu/lease.py`
- Verify: `system/runtime_v2/health/*.json`

**3차 목표: 24시간 가동 완성**

- browser health가 24시간 동안 fail-closed로 유지됩니다.
- GPT floor 자동복구가 drift 없이 동작합니다.
- GPU lock 중복 실행이 0건입니다.
- latest-run / result evidence가 계속 맞습니다.

Run: `python -m pytest tests/test_runtime_v2_phase2.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_gpu_workers.py -q`
Expected: 파이프라인 완료 후 운영 안정성 검증이 PASS

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q`
Expected: latest/evidence drift와 contract semantics가 24h 단계에서도 PASS

## Anti-Patterns (Do Not Reintroduce)

- 참고 저장소 스크립트 직접 호출 금지
- 워커 내부 retry/backoff/login recovery 금지
- 성공 산출물 없이 `ok` 반환 금지
- Excel 직접 쓰기 금지
- 서비스별 예외 분기 누적 금지

## Recommended Execution Mode

- 실제 구현은 한 세션에 한 프로그램만 진행합니다.
- 순서는 반드시 `gpt -> seaart -> genspark -> canva -> geminigen -> tts -> kenburns -> rvc -> 24h`입니다.
- 프로그램 하나 완료 후에만 다음 프로그램 계획을 활성화합니다.

# Runtime V2 Blocker Fix Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers/executing-plans` to implement this plan task-by-task.

**Goal:** `runtime_v2`의 실동작을 막는 blocker 5개를 순서대로 제거해, `Excel Topic -> Stage1 -> Stage2 -> Final`이 실제 서비스 호출과 실제 산출물 기준으로 끝까지 이어지게 만듭니다.

**Architecture:** 수정 순서는 `Stage1 실제화 -> next_jobs 연결 -> Stage2/Final placeholder 제거 -> qwen3/rvc 실기능 정합화 -> 게이트/증거 신뢰성 보강`으로 고정합니다. 앞 단계가 막히면 다음 단계를 건드리지 않고, 모든 작업은 TDD와 증거 기반 검증으로 진행합니다.

**Tech Stack:** Python `unittest`, `runtime_v2` control plane, browser automation sessions, ffmpeg, evidence/result router, Excel manager sync.

---

## Canonical Plan Link

- 이 문서는 구현 blocker를 task 단위로 분해한 보조 문서입니다.
- `docs/plans/2026-03-08-browser-session-stability-plan.md`를 `1행 smoke 전까지의 단일 canonical remediation plan`으로 사용합니다.
- blocker 추가/삭제/우선순위 변경은 먼저 canonical plan에 반영한 뒤, 여기에는 구현 task만 동기화합니다.
- 이 문서와 canonical plan이 충돌하면 canonical plan을 우선합니다.

## Blocker Scope Lock

- 이 문서는 blocker 구현 순서만 다룹니다.
- 아래 항목은 blocker task를 진행하기 전에 canonical plan에서 먼저 닫혀 있어야 합니다.
  1. `GPT floor` 정상화 기준
  2. latest-run evidence join 규칙
  3. browser canonical profile ownership 계약
  4. blocked/backoff semantics 공통 정의
  5. legacy carryover 적용/미적용 판정 기준

## Blocker Map

| Blocker ID | 증상 | 주요 파일 | 계획 Task |
|---|---|---|---|
| B1 | Stage1이 실제 ChatGPT 작업이 아니라 placeholder plan 생성 | `runtime_v2/stage1/chatgpt_runner.py` | Task 1 |
| B2 | Stage1 성공 후에도 downstream 체인이 안 이어짐 | `runtime_v2/stage1/chatgpt_runner.py`, `runtime_v2/control_plane.py` | Task 2 |
| B3 | Stage2/Final worker가 실제 서비스 대신 placeholder 파일만 생성 | `runtime_v2/stage2/*.py`, `runtime_v2/stage3/render_worker.py` | Task 3 |
| B4 | `qwen3_tts`/`rvc` 이름과 실제 기능이 불일치 | `runtime_v2/workers/qwen3_worker.py`, `runtime_v2/workers/rvc_worker.py` | Task 4 |
| B5 | 실패/health/evidence 신뢰성이 약해 거짓 PASS/FAIL 가능 | `runtime_v2/control_plane.py`, `runtime_v2/supervisor.py`, `runtime_v2/browser/manager.py` | Task 5 |

## External Dependency Test Strategy

- 기본 단위테스트: mock runner / adapter double / fake artifact로 오프라인 실행
- detached smoke: `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md` Stage 4 명령과 증거 기준을 그대로 사용
- 실서비스 통합테스트: `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md` Stage 5를 canonical smoke로 사용하고, 작업자는 명시적 환경 게이트 `RUNTIME_V2_REAL_SMOKE=1`이 있을 때만 실행
- 실서비스 smoke 명령 집합:
  - `python -m runtime_v2.cli --excel-once --excel-path "D:\YOUTUBEAUTO\4 머니.xlsx" --sheet-name "Sheet1" --row-index 0`
  - `python -m runtime_v2.cli --control-once` (필요 횟수만큼 반복)
- 실서비스 smoke 수집 증거:
  - `system/runtime_v2/health/gui_status.json`
  - `system/runtime_v2/health/gpt_status.json`
  - `system/runtime_v2/health/gpu_scheduler_health.json`
  - `system/runtime_v2/evidence/result.json`
  - `system/runtime_v2/evidence/control_plane_events.jsonl`
  - `system/runtime_v2/evidence/failure_summary.json` (실패 시)
  - `system/runtime_v2/logs/<run_id>.jsonl`
- 실서비스 smoke 통과 기준:
  - 동일 `run_id`가 seed -> stage1 -> stage2 -> final evidence까지 이어짐
  - final output 또는 failure summary가 한 번에 판정 가능함
  - `result.json` / `gui_status.json` / `control_plane_events.jsonl`이 같은 latest-run 의미로 조인 가능함
- 해석 고정:
  - `엑셀 1행 테스트`는 `row-index=1`이 아니라 `실제 테스트 행 1개를 성공시키는 smoke`를 의미함
  - 24시간 검증은 위 smoke 이후 개발 최종 단계에서만 수행함
- 실서비스 전제:
  - 브라우저 로그인 세션 준비
  - ffmpeg 실행 가능
  - qwen3/rvc 실행 환경 준비
  - 네트워크/API/계정 의존성 충족
- 규칙: 로컬 `unittest`는 외부 계정/네트워크가 없어도 재현 가능해야 함
- 규칙: Task 1~5 완료 판정은 `로컬 unittest PASS + detached smoke PASS + 실서비스 smoke 1회 PASS 또는 구조화된 실패 증거 확보`까지 포함해야 함

## Shared Contract Lock

`next_jobs` / downstream seed 최소 스키마:

```json
{
  "stage1_result": {
    "status": "ok|error",
    "run_id": "string",
    "row_ref": "string",
    "next_jobs": [
      {
        "contract": "runtime_v2_inbox_job",
        "job": {
          "job_id": "string",
          "worker": "string",
          "checkpoint_key": "string",
          "payload": {
            "run_id": "string",
            "row_ref": "string"
          }
        }
      }
    ],
    "debug_log": "string",
    "reason_code": "string",
    "error_code": "string",
    "result_path": "string"
  }
}
```

실패 시 최소 추적 스키마:

```json
{
  "stage1_result": {
    "status": "error",
    "run_id": "string",
    "row_ref": "string",
    "next_jobs": [],
    "error_code": "string",
    "reason_code": "string",
    "debug_log": "string",
    "result_path": "string"
  }
}
```

필수 규칙:
- `next_jobs`는 항상 배열이며, 성공이면 1개 이상 또는 명시적 `reason_code=no_downstream_jobs`로 남아야 함
- `next_jobs[*].job.payload.run_id`와 상위 `stage1_result.run_id`는 동일
- 실패 추적 필드는 Stage1 result top-level에 유지하고, downstream seed 내부로 숨기지 않음
- `run_id`는 Stage1 -> Stage2 -> Final까지 동일
- `checkpoint_key`는 idempotency 기준으로 유지
- 실패 시에도 `error_code`, `debug_log`, `result_path` 중 하나 이상 추적 가능해야 함

## Verification Artifact Lock

- latest-run canonical evidence:
  - `system/runtime_v2/evidence/result.json`
  - `system/runtime_v2/evidence/control_plane_events.jsonl`
  - `system/runtime_v2/health/gui_status.json`
  - `system/runtime_v2/health/browser_health.json`
  - `system/runtime_v2/health/gpt_status.json`
  - `system/runtime_v2/health/gpu_scheduler_health.json`
- per-run debug evidence:
  - `system/runtime_v2/logs/<run_id>.jsonl`
  - `system/runtime_v2/evidence/failure_summary.json` (실패 시)
- task verification bundle:
  - `system/runtime_v2/evidence/verification/task-<n>-commands.txt`
  - `system/runtime_v2/evidence/verification/task-<n>-oracle.txt`
  - `system/runtime_v2/evidence/verification/task-<n>-kimoring.txt`
- 판정 규칙:
  - task 완료 보고 전 `task-<n>-commands.txt`에 실제 실행 명령과 종료 결과를 남김
  - Oracle 검토 결과와 kimoring 검증 결과는 각각 전용 파일에 저장해 재검토 가능해야 함
  - latest-run evidence의 `run_id`와 per-run log의 `run_id`가 일치하지 않으면 그 task는 미완료로 간주

## Task 1: Stage1을 실제 작업 준비 단계로 전환

**Blocker ID:** B1
**재현:** `python -m unittest tests.test_runtime_v2_stage1_chatgpt -v`
**수락 기준:** Stage1 결과가 placeholder plan이 아니라 downstream-ready result/evidence를 반환

**Files:**
- Modify: `runtime_v2/stage1/chatgpt_runner.py`
- Modify: `runtime_v2/stage1/result_contract.py`
- Test: `tests/test_runtime_v2_stage1_chatgpt.py`

**Step 1: Write the failing tests**

추가 테스트 항목:
- `run_stage1_chatgpt_job()`가 placeholder `scene_plan` 고정값이 아니라 입력/외부 실행 결과를 반영해야 함
- Stage1 결과에 `next_jobs` 배열과 shared contract lock 기준의 downstream 준비 정보가 있어야 함
- 실패 시 `debug_log`, `reason_code`, `run_id`가 Stage1 result top-level에 유지되어야 함

예시:
```python
def test_stage1_result_contains_downstream_seed_data():
    result = run_stage1_chatgpt_job(topic_spec, workspace, debug_log="x")
    assert result["status"] == "ok"
    assert result["next_jobs"]
```

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_runtime_v2_stage1_chatgpt -v
```

Expected: `next_jobs` 부재 또는 placeholder scene assertions로 FAIL

**Step 3: Write minimal implementation**

- `build_video_plan_from_topic_spec()`가 고정 scene 2개 생성만 하지 않도록 입력 기반 builder로 분리
- `run_stage1_chatgpt_job()`가 최소 1개 이상의 downstream seed 정보를 `next_jobs`로 반환
- `stage1_result_payload()`는 downstream seed/evidence를 담을 수 있게 유지

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest tests.test_runtime_v2_stage1_chatgpt -v
```

Expected: PASS

**Step 5: Verify**

Run:
```bash
python -m compileall -q runtime_v2 tests
```

Check:
- `lsp_diagnostics` on `runtime_v2/stage1/chatgpt_runner.py`
- `lsp_diagnostics` on `runtime_v2/stage1/result_contract.py`

---

## Task 2: Stage1 -> Stage2 체인 연결 복구

**Blocker ID:** B2
**재현:** `python -m unittest tests.test_runtime_v2_control_plane_chain tests.test_runtime_v2_excel_topic_end_to_end -v`
**수락 기준:** Stage1 성공 후 `next_jobs`가 queue/control plane에서 실제 downstream seed로 연결되고, malformed result/JSON parse 실패는 구조화된 실패로 승격되어 downstream queue를 만들지 않음

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/manager.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_excel_topic_end_to_end.py`

**Step 1: Write the failing tests**

추가 테스트 항목:
- Stage1 성공 후 `control_plane`이 `next_jobs`를 큐에 넣음
- `run_id`가 Stage1 -> Stage2 seed까지 동일하게 유지됨
- manager가 Stage1 종료를 실제 Stage2 진입 가능 상태로만 표시함
- worker result JSON parse 실패 시 `_worker_result_contract()`가 silent pass 하지 않고 `error_code`와 `debug_log`를 남기며 실패 처리함

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_runtime_v2_control_plane_chain tests.test_runtime_v2_excel_topic_end_to_end -v
```

Expected: downstream queue 부재로 FAIL

**Step 3: Write minimal implementation**

- `control_plane.py`의 silent result parsing 실패를 먼저 노출시켜 체인 실패가 숨지 않게 함
- `control_plane`이 Stage1 worker result의 `next_jobs`를 표준 경로로 큐잉
- debug log/evidence path는 `RuntimeConfig` 기준으로 유지
- manager sync는 downstream seed 이전에 premature success를 쓰지 않음

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest tests.test_runtime_v2_control_plane_chain tests.test_runtime_v2_excel_topic_end_to_end -v
```

Expected: PASS

**Step 5: Verify**

Check:
- `lsp_diagnostics` on `runtime_v2/control_plane.py`
- `lsp_diagnostics` on `runtime_v2/manager.py`

---

## Task 3: Stage2/Final placeholder 제거

**Blocker ID:** B3
**재현:** `python -m unittest tests.test_runtime_v2_stage2_workers tests.test_runtime_v2_stage2_contracts tests.test_runtime_v2_final_video_flow -v`
**수락 기준:** placeholder 텍스트 파일이 아니라 실제 adapter/runner 결과 또는 fail-closed 결과만 허용

**Files:**
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Modify: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/stage2/json_builders.py`
- Modify: `runtime_v2/stage3/render_worker.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`
- Test: `tests/test_runtime_v2_final_video_flow.py`

**Step 1: Write the failing tests**

추가 테스트 항목:
- Stage2 worker가 placeholder 텍스트 파일이 아닌 실제 외부 실행 결과를 기준으로 성공/실패 판정
- `build_stage2_jobs()`가 scene 개수와 worker 매핑 규칙을 명확히 유지
- `render_worker`가 실제 입력 asset/render_spec을 소비하지 않으면 실패

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_runtime_v2_stage2_workers tests.test_runtime_v2_stage2_contracts tests.test_runtime_v2_final_video_flow -v
```

Expected: placeholder 제거 관련 assertion으로 FAIL

**Step 3: Write minimal implementation**

- Stage2 worker는 request만 저장하고 성공 처리하는 패턴을 제거
- 실제 service adapter 또는 external-process runner 호출 결과가 없으면 fail-closed
- `json_builders.py`는 scene/workload mapping 손실이 없도록 수정
- `render_worker`는 실재 asset/timeline 입력 없으면 완료 처리하지 않음

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest tests.test_runtime_v2_stage2_workers tests.test_runtime_v2_stage2_contracts tests.test_runtime_v2_final_video_flow -v
```

Expected: PASS

**Step 5: Verify**

Check:
- `lsp_diagnostics` on all modified stage2/stage3 files

---

## Task 4: qwen3/rvc 워커를 이름에 맞는 실제 기능으로 정합화

**Blocker ID:** B4
**재현:** `python -m unittest tests.test_runtime_v2_gpu_workers -v`
**수락 기준:** worker 이름과 실제 처리 방식이 contract 수준에서 일치하고, fallback이면 명시적으로 드러남

**Files:**
- Modify: `runtime_v2/workers/qwen3_worker.py`
- Modify: `runtime_v2/workers/rvc_worker.py`
- Modify: `runtime_v2/workers/external_process.py` (필요 시)
- Test: `tests/test_runtime_v2_gpu_workers.py`

**Step 1: Write the failing tests**

추가 테스트 항목:
- `qwen3_tts`가 Windows TTS fallback만으로 성공 처리되지 않음
- `rvc`가 단순 ffmpeg normalize/mux와 구분되는 실제 변환 contract를 요구
- 입력 누락/실행 파일 누락 시 error_code가 분명해야 함

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_runtime_v2_gpu_workers -v
```

Expected: placeholder/generic success 관련 assertion으로 FAIL

**Step 3: Write minimal implementation**

- `qwen3_worker.py`는 최소한 명시적 adapter/runner contract를 사용하고, fallback이면 fallback임을 드러내며 성공 기준을 엄격화
- `rvc_worker.py`는 `model_name`만 기록하고 무시하는 구조를 제거
- external process failure는 구조화된 error_code로 유지

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest tests.test_runtime_v2_gpu_workers -v
```

Expected: PASS

**Step 5: Verify**

Check:
- `lsp_diagnostics` on `runtime_v2/workers/qwen3_worker.py`
- `lsp_diagnostics` on `runtime_v2/workers/rvc_worker.py`

---

## Task 5: 게이트/증거 신뢰성 보강

**Blocker ID:** B5
**재현:** `python -m unittest tests.test_runtime_v2_browser_plane tests.test_runtime_v2_phase2 tests.test_runtime_v2_final_video_flow -v`
**수락 기준:** silent pass/fake OK 없이 실패는 실패로 기록되고, health/evidence가 latest-run 기준으로 해석 가능

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/result_router.py` (필요 시)
- Test: `tests/test_runtime_v2_browser_plane.py`
- Test: `tests/test_runtime_v2_phase2.py`
- Test: `tests/test_runtime_v2_final_video_flow.py`

**Step 1: Write the failing tests**

추가 테스트 항목:
- `_worker_result_contract()`가 JSON 파싱 실패를 숨기지 않음
- browser health가 포트 오픈만으로 healthy 처리되지 않음
- GPT floor/gate가 fake OK를 쓰지 않고 실제 상태 기반으로 실패함
- latest-run evidence가 실패 경로에서도 일관되게 남음

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_runtime_v2_browser_plane tests.test_runtime_v2_phase2 tests.test_runtime_v2_final_video_flow -v
```

Expected: hidden failure / fake health 관련 assertion으로 FAIL

**Step 3: Write minimal implementation**

- `control_plane.py`의 silent `pass` 제거, 구조화된 fallback 기록 추가
- `supervisor.py`는 fake GPT endpoint 대신 실제 상태 소스를 사용
- `browser/manager.py`는 최소한 로그인/작업 가능 상태를 반영할 수 있는 health contract로 승격

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest tests.test_runtime_v2_browser_plane tests.test_runtime_v2_phase2 tests.test_runtime_v2_final_video_flow -v
```

Expected: PASS

**Step 5: Final verification**

Run:
```bash
python -m unittest tests.test_runtime_v2_excel_bridge tests.test_runtime_v2_stage1_chatgpt tests.test_runtime_v2_stage1_excel_merge tests.test_runtime_v2_stage2_contracts tests.test_runtime_v2_stage2_workers tests.test_runtime_v2_final_video_flow tests.test_runtime_v2_excel_topic_end_to_end tests.test_runtime_v2_control_plane_chain tests.test_runtime_v2_browser_plane tests.test_runtime_v2_gpu_workers tests.test_runtime_v2_phase2 -v
python -m compileall -q runtime_v2 tests
```

Expected:
- 전체 테스트 PASS
- compileall 성공
- 수정 파일 `lsp_diagnostics` error 0건

Verification evidence:
- `system/runtime_v2/evidence/verification/task-5-oracle.txt`
- `system/runtime_v2/evidence/verification/task-5-kimoring.txt`
- `system/runtime_v2/evidence/verification/task-5-commands.txt`
- latest-run canonical evidence (`system/runtime_v2/evidence/result.json`, `system/runtime_v2/evidence/control_plane_events.jsonl`, `system/runtime_v2/health/gui_status.json`)

---

## Plan Notes

- 이 계획은 blocker만 다룹니다. 성능 최적화, soak 자동화, 문서 polish는 범위 밖입니다.
- 모든 Task는 Oracle 검토 후 다음 Task로 넘어갑니다.
- 모든 Task는 kimoring 검증(`verify-code-quality`, `verify-single-change`, `verify-debug-convention`)을 통과해야 완료로 간주합니다.

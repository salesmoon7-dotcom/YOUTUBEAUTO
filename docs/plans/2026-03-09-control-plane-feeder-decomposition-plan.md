# Control Plane Feeder Decomposition Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** `runtime_v2/control_plane.py`에서 입력 수집/검증/아카이브/feeder state 책임만 분리해 디버깅 효율을 높이고, 정책/의미 결정권은 기존 control plane에 그대로 유지합니다.

**Architecture:** `run_control_loop_once()`와 failure/recovery/chaining/snapshot writer는 `control_plane.py`에 남기고, `seed_local_jobs()`와 `_discover_*`, explicit contract parsing, feeder state I/O를 `runtime_v2/control_plane_feeder.py`로 옮깁니다. 이 계획은 “단일 의미 권한”을 깨지 않고 control plane의 다책임 구조 중 가장 낮은 위험의 I/O 수집층만 분리하는 1차 배치입니다.

**Tech Stack:** Python 3.13, `RuntimeConfig`, `JobContract`, `QueueStore`, pytest, py_compile, LSP diagnostics

**Document Status:** COMPLETED - first safe feeder decomposition batch implemented on 2026-03-09.

**Current Decision:** NO-GO for second decomposition batch right now. Oracle review concluded that after feeder extraction, the remaining complexity in `runtime_v2/control_plane.py` is naturally cohesive orchestration rather than harmful semantic drift. In particular, splitting worker dispatch now would likely increase file-to-file jumps during debugging without materially reducing policy complexity.

---

## Why This Plan Exists

- `runtime_v2/control_plane.py`는 현재 약 1965줄이며, queue control / worker execution / recovery / snapshot / events / feeder discovery가 한 파일에 섞여 있습니다.
- Oracle review 결과, 가장 안전한 첫 분해 경계는 `seed_local_jobs()`와 explicit contract feeder 묶음입니다.
- 반대로 failure contract, blocked 의미, downstream chaining, snapshot writer를 분리하면 대전제(디버깅 효율, 파이프라인 단순성, 단일 의미 권한)를 해칠 위험이 큽니다.

## Fixed Boundaries

- `control_plane.py`에 남길 것
  - `run_control_loop_once()`
  - runtime preflight -> worker result 해석
  - blocked/failed/retryable/completion 의미 결정
  - downstream next job seeding 규칙
  - latest/result/gui/events/debug writer
- `control_plane_feeder.py`로 옮길 것
  - `seed_local_jobs()`
  - `_discover_explicit_contract_jobs()`
  - `_job_from_explicit_contract()`
  - `_job_from_explicit_payload()`
  - `_archive_explicit_contract()`
  - `_discover_qwen_jobs()` / `_discover_kenburns_jobs()` / `_discover_rvc_jobs()`
  - `_load_feeder_state()` / `_save_feeder_state()`
  - feeder용 path safety helper

---

## Execution Plan

### Task 1. Feeder extraction baseline 고정

**Files:**
- Read/Test: `tests/test_runtime_v2_control_plane_chain.py`
- Read/Test: `tests/test_runtime_v2_excel_bridge.py`
- Read: `runtime_v2/control_plane.py`

**Do:**
- 현재 `seed_local_jobs()` 외부 계약과 explicit contract discovery 관련 회귀 테스트를 기준선으로 고정합니다.

**Verification:**
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_control_plane_runs_chatgpt_job_and_seeds_stage2_jobs_with_same_run_id -q`
- `python -m pytest tests/test_runtime_v2_excel_bridge.py -q`

### Task 2. Feeder 모듈 추출

**Files:**
- Create: `runtime_v2/control_plane_feeder.py`
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_excel_bridge.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Do:**
- feeder discovery / explicit contract parsing / feeder state I/O를 새 모듈로 이동합니다.
- `control_plane.py`는 `seed_local_jobs()` 공개 계약만 그대로 re-export 하거나 thin wrapper로 유지합니다.
- downstream policy helper와 recovery/snapshot writer는 옮기지 않습니다.

**Exit:**
- `control_plane.py`에서 feeder 관련 덩어리가 사라집니다.
- 테스트 관점에서 `seed_local_jobs()` 사용 경로는 동일하게 유지됩니다.

### Task 3. 분해 후 구조 검증과 문서 업데이트

**Files:**
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`
- Modify: `docs/plans/2026-03-09-control-plane-feeder-decomposition-plan.md`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_excel_bridge.py`

**Do:**
- 1차 분해 완료 사실과 남은 hotspot(`_run_worker` dispatch, event/snapshot bundle)은 아직 control plane에 남긴다고 문서화합니다.

**Verification:**
- `python -m py_compile runtime_v2/control_plane.py runtime_v2/control_plane_feeder.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_excel_bridge.py`
- LSP diagnostics on modified files

---

## Done Definition

- `control_plane.py`는 feeder 수집/아카이브보다 control-plane 의미 결정에 더 집중된 파일이 됩니다.
- feeder extraction 후에도 `run_id`, `error_code`, `attempt/backoff` 의미는 기존과 동일합니다.
- downstream next job seeding 규칙은 여전히 `control_plane.py`에 남아 있습니다.
- 테스트와 py_compile, LSP diagnostics evidence가 fresh 상태로 확보됩니다.

## Completion Note

- `runtime_v2/control_plane_feeder.py`를 추가해 `seed_local_jobs()`와 explicit contract discovery / feeder state I/O / local path validation을 분리했습니다.
- `runtime_v2/control_plane.py`는 control loop, failure/recovery/chaining, snapshot/event writer, worker dispatch에 더 집중된 파일이 되었습니다.
- 2차 분해(특히 worker dispatch 분리)는 현재 시점에서는 보류합니다. 재개 조건은 다음 중 하나입니다.
  - `_run_worker()` 주변 디버깅 왕복이 최근 3회 중 절반 이상 반복될 때
  - 새 workload가 3개 이상 추가되어 dispatch 변경 충돌이 실제로 생길 때
  - 동기 함수 호출 스위치가 아니라 worker 선택 정책 자체를 바꿔야 할 때
- 분해 후 fresh verification:
  - `python -m pytest tests/test_runtime_v2_excel_bridge.py::RuntimeV2ExcelBridgeTests::test_subprograms_never_receive_excel_path_directly -q`
  - `python -m pytest tests/test_runtime_v2_excel_bridge.py::RuntimeV2ExcelBridgeTests::test_resident_worker_poll_enforces_configured_stable_file_age -q`
  - `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_control_plane_runs_chatgpt_job_and_seeds_stage2_jobs_with_same_run_id -q`
  - `python -m py_compile runtime_v2/control_plane.py runtime_v2/control_plane_feeder.py tests/test_runtime_v2_excel_bridge.py tests/test_runtime_v2_control_plane_chain.py`

# Runtime V2 Architecture Robustness Review Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`의 구조를 `single owner`, `single writer`, `single failure contract`, `single adapter` 원칙 아래에서 다시 잠그고, 앞으로 기능을 더 붙여도 대전제가 흔들리지 않도록 견고성/효율성 보강 작업을 단계적으로 수행합니다.

**Architecture:** 이번 계획은 대규모 재작성보다 `증거 고정 -> writer 단일화 -> failure contract 단일화 -> adapter 경계 고정 -> mock/legacy 보정 축소 -> 장기 게이트 고정` 순서를 따릅니다. 핵심은 “빠르게 개발하기 위해 먼저 구조를 단순하고 재현 가능하게 만든다”는 점이며, 모든 단계는 fail-closed를 유지하고 `run_id`, `error_code`, `attempt/backoff` 의미 drift를 금지합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, JSON state/evidence files, `RuntimeConfig`, `control_plane`, `latest_run`, `result_router`, `worker_registry`, `pytest`, project verify skills

---

## Why This Plan Exists

- `docs/sop/SOP_runtime_v2_development_guardrails.md`는 `관측 기반`, `단일 writer`, `단일 failure contract`, `단일 reference adapter`, `fail-closed`를 대전제로 고정합니다.
- 현재 코드베이스에는 그 방향성이 이미 구현되어 있지만, 아래 구조 리스크가 남아 있습니다.
  - latest/result pointer 의미가 `runtime_v2/control_plane.py`, `runtime_v2/bootstrap.py`, `runtime_v2/cli.py`, `runtime_v2/manager.py`에서 분산 작성될 여지
  - worker의 `completion.state`/`error_code`가 상위 recovery 의미와 섞이는 failure-contract 누수
  - `adapter_command` 기반 외부 호출 seam이 서비스별로 늘어나며 reference adapter 경계가 약해질 위험
  - `mock_chain` 경로가 실제 control plane 안에 깊이 들어가 운영 경로와 테스트 경로가 멀어질 위험
  - 레거시보다 구조는 좋아졌지만 실제 서비스 성숙도와 coverage는 아직 좁은 상태

## Non-Goals

- 레거시 코드를 직접 포팅하거나 호출하지 않습니다.
- 한 번에 여러 구조를 동시에 갈아엎는 대규모 재작성은 하지 않습니다.
- fail-open, fallback OK, 암묵 보정 로직을 추가하지 않습니다.
- 24h soak 자체를 이 계획의 초기 단계 완료 기준으로 사용하지 않습니다.

## Fixed Invariants

아래는 모든 task에서 유지해야 하는 고정 불변식입니다.

1. latest-run 최종 의미는 단일 owner가 소유합니다.
2. `status`, `error_code`, `completion.state`, `retryable`는 하나의 계약 의미만 가집니다.
3. worker는 정책을 결정하지 않고 contract/evidence만 반환합니다.
4. 외부 실행은 단일 adapter 경로 또는 단일 helper 경로로 수렴시킵니다.
5. 모든 수정 후 최소 검증은 `run_id`, `error_code`, `attempt/backoff` 의미 일치입니다.

## Evidence Baseline

현재 계획 수립의 직접 근거는 아래 파일들입니다.

- Guardrails: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Canonical plan: `docs/plans/2026-03-08-runtime-v2-subprogram-core-logic-implementation-plan.md`
- Writer/ownership hotspots:
  - `runtime_v2/control_plane.py`
  - `runtime_v2/latest_run.py`
  - `runtime_v2/result_router.py`
  - `runtime_v2/bootstrap.py`
  - `runtime_v2/cli.py`
  - `runtime_v2/manager.py`
- Worker contract/runtime helpers:
  - `runtime_v2/workers/job_runtime.py`
  - `runtime_v2/workers/native_only.py`
  - `runtime_v2/workers/qwen3_worker.py`
  - `runtime_v2/workers/rvc_worker.py`
  - `runtime_v2/stage2/seaart_worker.py`
  - `runtime_v2/stage2/genspark_worker.py`
  - `runtime_v2/stage2/canva_worker.py`
  - `runtime_v2/stage2/geminigen_worker.py`
- Current tests:
  - `tests/test_runtime_v2_latest_run.py`
  - `tests/test_runtime_v2_control_plane_chain.py`
  - `tests/test_runtime_v2_gpu_workers.py`
  - `tests/test_runtime_v2_stage2_workers.py`
  - `tests/test_runtime_v2_stage2_contracts.py`
  - `tests/test_runtime_v2_phase2.py`
- Legacy comparison references:
  - `D:\YOUTUBE_AUTO\docs\plans\2026-03-01-chatgpt-root-cause-and-simplification-plan.md`
  - `D:\YOUTUBE_AUTO\docs\plans\2026-02-26-gpt-parser-stabilization-report.md`

## Milestone Map

- M0: Evidence baseline and risk map locked
- M1: latest/result writer single-owner consolidation
- M2: failure contract freeze
- M3: adapter boundary consolidation
- M4: mock/legacy compensation isolation
- M5: verification gates and growth rules hardened

---

### Task 1: Lock The Evidence Baseline And Risk Map

**Files:**
- Modify: `docs/plans/2026-03-09-runtime-v2-architecture-robustness-review-plan.md`
- Read: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Read: `docs/plans/2026-03-08-runtime-v2-subprogram-core-logic-implementation-plan.md`
- Read: `runtime_v2/control_plane.py`
- Read: `runtime_v2/latest_run.py`
- Read: `runtime_v2/result_router.py`

**Step 1: Baseline assertions를 문서에 고정합니다**

```text
- latest-run writer candidate modules
- result writer candidate modules
- failure-contract leak candidates
- adapter-command entrypoints
- mock-only path entrypoints
```

**Step 2: 직접 근거를 재확인합니다**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py -q`
Expected: 현재 latest-run join 및 control-plane contract baseline이 PASS

**Step 3: Risk map을 확정합니다**

- P0: multi-writer drift
- P0: failure contract leakage
- P1: adapter sprawl / false success
- P1: mock-path divergence
- P2: legacy parity gap and coverage gap

**Step 4: Commit**

```bash
git add docs/plans/2026-03-09-runtime-v2-architecture-robustness-review-plan.md
git commit -m "docs: lock runtime_v2 robustness risk map"
```

### Task 2: Consolidate Latest/Result Single Writer

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/bootstrap.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/manager.py`
- Modify: `runtime_v2/latest_run.py`
- Modify: `runtime_v2/result_router.py`
- Test: `tests/test_runtime_v2_latest_run.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Failing test를 먼저 추가합니다**

```python
def test_only_single_runtime_api_updates_latest_and_result_snapshots():
    ...
```

**Step 2: 테스트를 실행해 RED를 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py -q -k single_runtime_api`
Expected: FAIL because writer path is still distributed

**Step 3: 단일 writer helper를 도입합니다**

- `control_plane`가 직접 쓰는 latest/result 갱신을 helper로 감쌉니다
- `bootstrap`, `cli`, `manager`는 raw write 대신 동일 helper 또는 명시적 bootstrap-only API만 사용하게 정리합니다

**Step 4: 기존 경로를 helper로 교체합니다**

```text
bootstrap -> bootstrap-only snapshot init
cli -> runtime summary snapshot helper
manager -> failure/final sync helper
control_plane -> canonical final writer helper
```

**Step 5: GREEN을 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py -q`
Expected: PASS, pointer/result/gui/events join이 같은 run_id로 유지

**Step 6: Commit**

```bash
git add runtime_v2/control_plane.py runtime_v2/bootstrap.py runtime_v2/cli.py runtime_v2/manager.py runtime_v2/latest_run.py runtime_v2/result_router.py tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py
git commit -m "fix: consolidate runtime snapshot writers"
```

### Task 3: Freeze Failure Contract Semantics

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/workers/job_runtime.py`
- Modify: `runtime_v2/workers/native_only.py`
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Modify: `runtime_v2/workers/qwen3_worker.py`
- Modify: `runtime_v2/workers/rvc_worker.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_gpu_workers.py`

**Step 1: 계약 의미를 failing test로 고정합니다**

```python
def test_control_plane_uses_retryable_not_completion_state_for_retry_decision():
    ...

def test_input_contract_failure_is_failed_not_blocked():
    ...
```

**Step 2: RED를 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k retryable`
Expected: FAIL before semantics are fully frozen

**Step 3: 의미를 분리합니다**

- `completion.state`는 output/result meaning만 담당
- `retryable`은 recovery hint만 담당
- `error_code`는 failure axis naming만 담당
- blocked 정책은 runtime/control-plane에서만 결정

**Step 4: worker 반환값을 정리합니다**

- 입력 계약 실패는 `failed + retryable=False`
- browser/gpt/gpu preflight blocked는 runtime 레이어에서만 `blocked/hold/fixed backoff`
- worker 내부는 policy-oriented blocked semantics를 새로 만들지 않음

**Step 5: 관련 회귀를 실행합니다**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_gpu_workers.py -q`
Expected: PASS, blocked/backoff/attempt semantics가 drift 없이 유지

**Step 6: Commit**

```bash
git add runtime_v2/control_plane.py runtime_v2/workers/job_runtime.py runtime_v2/workers/native_only.py runtime_v2/stage2/*.py runtime_v2/workers/qwen3_worker.py runtime_v2/workers/rvc_worker.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_gpu_workers.py
git commit -m "fix: freeze runtime_v2 failure contract semantics"
```

### Task 4: Consolidate External Adapter Boundary

**Files:**
- Create: `runtime_v2/workers/external_process.py`
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Modify: `runtime_v2/workers/qwen3_worker.py`
- Modify: `runtime_v2/workers/rvc_worker.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_gpu_workers.py`

**Step 1: Failing test를 추가합니다**

```python
def test_worker_success_path_requires_adapter_helper_and_verified_new_output():
    ...
```

**Step 2: RED 확인**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_gpu_workers.py -q -k adapter_helper`
Expected: FAIL because workers still run service-specific subprocess logic inline

**Step 3: 공통 helper를 도입합니다**

- adapter command/stdio/evidence/output verification 공통 처리
- 허용된 실행 shape만 통과
- 기존 임의 payload command 의존을 축소

**Step 4: worker별 inline subprocess를 helper 호출로 교체합니다**

```text
stage2 4종 + qwen3 + rvc -> same helper
```

**Step 5: false-success를 차단합니다**

- 기존 파일 재사용만으로 성공하는지 확인하는 테스트 추가
- output path scope와 evidence 생성 순서를 고정

**Step 6: 회귀 확인**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_gpu_workers.py tests/test_runtime_v2_phase2.py -q`
Expected: PASS

**Step 7: Commit**

```bash
git add runtime_v2/workers/external_process.py runtime_v2/stage2/*.py runtime_v2/workers/qwen3_worker.py runtime_v2/workers/rvc_worker.py tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_gpu_workers.py tests/test_runtime_v2_phase2.py
git commit -m "refactor: unify external adapter execution paths"
```

### Task 5: Isolate Mock Paths From Runtime Semantics

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/config.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_phase2.py`

**Step 1: failing test를 추가합니다**

```python
def test_mock_chain_requires_explicit_probe_or_debug_mode():
    ...
```

**Step 2: RED 확인**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k mock_chain_requires_explicit`
Expected: FAIL before isolation is tightened

**Step 3: mock path 진입을 더 명시적으로 제한합니다**

- probe-root/debug-only contract
- 운영 기본 경로에서는 mock_chain 사용 불가
- mock artifacts는 `_mock` 전용 evidence root만 사용

**Step 4: GREEN 확인**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_phase2.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/control_plane.py runtime_v2/cli.py runtime_v2/config.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_phase2.py
git commit -m "fix: isolate mock chain from runtime path"
```

### Task 6: Document Legacy Compensation Strategy Without Reimporting Legacy Drift

**Files:**
- Modify: `docs/plans/2026-03-09-runtime-v2-architecture-robustness-review-plan.md`
- Modify: `docs/plans/2026-03-08-runtime-v2-subprogram-core-logic-implementation-plan.md`
- Read: `D:\YOUTUBE_AUTO\docs\plans\2026-03-01-chatgpt-root-cause-and-simplification-plan.md`
- Read: `D:\YOUTUBE_AUTO\docs\plans\2026-02-26-gpt-parser-stabilization-report.md`

**Step 1: Legacy strengths와 current gaps를 표로 고정합니다**

```text
legacy strength -> current gap -> compensation in runtime_v2
```

**Step 2: 임시 보정 허용 범위를 문서화합니다**

- parity comparison은 허용
- direct import/porting은 금지
- temporary compensation removal gate를 명시

**Step 3: 관련 canonical wording을 정리합니다**

Run: `python -c "from pathlib import Path; p=Path(r'D:\YOUTUBEAUTO\docs\plans\2026-03-09-runtime-v2-architecture-robustness-review-plan.md'); print(p.exists())"`
Expected: `True`

**Step 4: Commit**

```bash
git add docs/plans/2026-03-09-runtime-v2-architecture-robustness-review-plan.md docs/plans/2026-03-08-runtime-v2-subprogram-core-logic-implementation-plan.md
git commit -m "docs: define runtime_v2 legacy compensation strategy"
```

### Task 7: Lock Final Verification Gates For Growth

**Files:**
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/plans/2026-03-09-runtime-v2-architecture-robustness-review-plan.md`
- Test: `tests/test_runtime_v2_latest_run.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_phase2.py`
- Test: `tests/test_runtime_v2_gpu_workers.py`

**Step 1: 성장 게이트를 문서로 잠급니다**

- static diagnostics
- targeted pytest
- `verify-implementation`
- readiness regression
- 24h는 later soak stage로 유지

**Step 2: 최종 검증 명령을 문서에 고정합니다**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_phase2.py tests/test_runtime_v2_gpu_workers.py -q`
Expected: PASS

Run: `python -m py_compile runtime_v2/control_plane.py runtime_v2/latest_run.py runtime_v2/result_router.py runtime_v2/cli.py runtime_v2/bootstrap.py runtime_v2/manager.py`
Expected: PASS

Run: `python -c "from pathlib import Path; text=Path(r'D:\YOUTUBEAUTO\docs\sop\SOP_runtime_v2_development_guardrails.md').read_text(encoding='utf-8'); print('single writer' in text.lower() or '단일 writer' in text)"`
Expected: `True`

**Step 3: Commit**

```bash
git add docs/sop/SOP_runtime_v2_development_guardrails.md docs/plans/2026-03-09-runtime-v2-architecture-robustness-review-plan.md tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_phase2.py tests/test_runtime_v2_gpu_workers.py
git commit -m "docs: lock runtime_v2 robustness verification gates"
```

## Milestone Exit Criteria

- M1 exit: latest/result/gui/events join이 단일 API 아래 유지되고 `tests/test_runtime_v2_latest_run.py`가 이를 잠금
- M2 exit: blocked/backoff/retryable semantics가 worker와 control plane에서 분리되어 `tests/test_runtime_v2_control_plane_chain.py`로 재현 가능
- M3 exit: 외부 실행이 단일 helper 경로를 통과하고 false-success 회귀가 테스트로 차단됨
- M4 exit: mock 경로가 운영 경로와 명시적으로 분리되고 legacy 보정이 문서화됨
- M5 exit: 성장 시 기본 회귀 명령과 verify gate가 문서/테스트로 고정됨

## Final Verification Bundle

모든 milestone 이후 최종 확인은 아래 순서로 고정합니다.

1. `python -m pytest tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_gpu_workers.py tests/test_runtime_v2_phase2.py -q`
2. `python -m py_compile runtime_v2/control_plane.py runtime_v2/latest_run.py runtime_v2/result_router.py runtime_v2/bootstrap.py runtime_v2/cli.py runtime_v2/manager.py runtime_v2/stage2/seaart_worker.py runtime_v2/stage2/genspark_worker.py runtime_v2/stage2/canva_worker.py runtime_v2/stage2/geminigen_worker.py runtime_v2/workers/qwen3_worker.py runtime_v2/workers/rvc_worker.py`
3. `verify-implementation`
4. `python -m pytest tests/test_runtime_v2_phase2.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_gpu_workers.py -q`

## Success Definition

이 계획의 성공은 “기능이 더 많아졌다”가 아니라 아래가 참이 되는 것입니다.

- 새 worker/service를 붙여도 writer 수와 failure axis 의미가 늘어나지 않습니다.
- 디버깅 시 `run_id -> latest -> gui/result/events -> worker result` 추적이 한 번에 됩니다.
- fail-closed를 완화하지 않고도 retry/backoff/blocked 의미를 빠르게 이해할 수 있습니다.
- 레거시보다 실제 coverage는 좁더라도, 구조적으로는 더 안전하고 더 빠르게 확장할 수 있습니다.

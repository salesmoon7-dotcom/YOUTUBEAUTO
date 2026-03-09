# Runtime V2 Guardrail Drift Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** `runtime_v2`의 후속 구조 audit에서 확인된 residual drift를 정리해, `single writer`, `single failure contract`, `worker policy-free`, `single reference adapter` 대전제를 다시 canonical state로 잠급니다.

**Document Status:** COMPLETED - follow-up remediation unit closed on 2026-03-09 after Task 1~6 implementation and interrupt-safe verification.

**Completion Note:** 채팅 interruption guardrail 때문에 검증은 `interrupt-safe` 방식으로 수행했습니다. 즉, broad parallel/file-level bundle 대신 케이스 단위 pytest와 파일 단위 `py_compile`, LSP diagnostics를 fresh evidence로 사용했습니다.

**Post-Close Follow-Up Audit:** 같은 세션의 추가 조사에서 residual drift 3건을 더 확인했고 즉시 닫았습니다. (1) `runtime_v2/stage1/chatgpt_runner.py`가 `route_video_plan()`으로 downstream `next_jobs`를 직접 생성하던 policy leakage, (2) `runtime_v2/latest_run.py` / `runtime_v2/cli.py`가 CLI 경로에서 latest pointer를 직접 갱신하던 ownership drift, (3) `runtime_v2/cli.py`의 stage2 adapter child가 검증 실패 후 내부 recovery tick + 재검증을 수행하던 policy drift입니다. 이 세 항목은 worker/CLI가 policy를 결정하지 않고 control-plane/helper만 의미를 소유하도록 다시 정리했습니다.

**Why This Plan Exists:** `docs/plans/2026-03-09-runtime-v2-architecture-robustness-review-plan.md`는 완료 처리되었지만, 이번 후속 audit에서 latest writer 분산, failure 의미 재합성, CLI/worker 정책 누수가 여전히 남아 있음을 확인했습니다. 따라서 기존 완료 기록은 유지하되, 새 drift remediation unit을 별도 active plan으로 열어 구조 대전제를 다시 닫습니다.

**Canonical Guardrails:**
- `docs/sop/SOP_runtime_v2_development_guardrails.md`
- `CLAUDE.md`

---

## Non-Goals

- 레거시 parity 전체를 이번 remediation unit의 완료 기준으로 사용하지 않습니다.
- 새 기능 추가나 서비스 확장을 이번 작업의 주목표로 삼지 않습니다.
- fail-open, fallback OK, 임시 분기 추가로 구조 drift를 덮지 않습니다.
- 24h soak 자체를 초기 완료 기준으로 사용하지 않습니다.

## Fixed Invariants

- latest/result/latest-run 의미는 단일 owner layer에서만 최종 확정합니다.
- `run_id`, `error_code`, `attempt/backoff`는 cross-file로 같은 의미를 유지해야 합니다.
- worker는 evidence/result contract만 반환하고, 정책은 orchestration layer가 결정합니다.
- external adapter 호출은 helper와 adapter builder의 단일 경로로 수렴해야 합니다.
- blocked 판단은 fail-closed를 유지하며, `unknown`이나 누락을 `OK`로 합성하지 않습니다.

---

## Audit Summary

### Finding 1. Latest snapshot writer가 단일하지 않습니다

- Guardrail: `latest-run snapshot`의 writer는 하나만 둡니다.
- Evidence:
  - `runtime_v2/latest_run.py:81`
  - `runtime_v2/control_plane.py:426`
  - `runtime_v2/cli.py:488`
  - `runtime_v2/manager.py:217`
  - `runtime_v2/manager.py:316`
  - `runtime_v2/bootstrap.py:79`
- Risk:
  - same run에 대한 latest/result/gui pointer overwrite 가능성
  - run_id drift 원인 추적 난이도 증가
  - control plane 외부에서 latest 의미를 바꾸는 구조 고착

### Finding 2. Failure contract 의미가 한 점에서 결정되지 않습니다

- Guardrail: 같은 failure axis는 한 이름, 한 의미만 가집니다.
- Evidence:
  - `runtime_v2/supervisor.py:285`
  - `runtime_v2/supervisor.py:303`
  - `runtime_v2/supervisor.py:335`
  - `runtime_v2/control_plane.py:1783`
  - `runtime_v2/control_plane.py:1800`
  - `runtime_v2/evidence.py:255`
- Risk:
  - top-level runtime code와 worker contract가 서로 다른 blocked/failed 의미를 재합성함
  - `completion.state`, `retryable`, `error_code`, `status`가 회복 정책과 결과 의미를 동시에 품음
  - `attempt/backoff` 검증이 상태 의미 drift에 취약해짐

### Finding 3. Worker와 CLI에 orchestration 정책이 남아 있습니다

- Guardrail: worker는 자기 결과만 반환하고 재시도/blocked/backoff 정책은 상위 orchestration에서만 결정합니다.
- Evidence:
  - `runtime_v2/workers/agent_browser_worker.py:163`
  - `runtime_v2/stage2/genspark_worker.py:38`
  - `runtime_v2/stage2/canva_worker.py:43`
  - `runtime_v2/cli.py:818`
  - `runtime_v2/cli.py:972`
- Risk:
  - worker가 `next_jobs`와 replan 흐름까지 일부 결정함
  - CLI가 attach recovery/fallback placeholder 정책을 별도로 품어 adapter 경계가 흐려짐
  - 동일 실패를 control plane, CLI, worker가 각자 다르게 보정할 여지

### Finding 4. Adapter boundary가 하나의 경로로 수렴하지 않습니다

- Guardrail: 외부 참고 호출은 adapter 경로 하나로만 통과시킵니다.
- Evidence:
  - `runtime_v2/stage2/agent_browser_adapter.py:30`
  - `runtime_v2/cli.py:766`
  - `runtime_v2/cli.py:822`
  - `runtime_v2/workers/external_process.py:93`
- Risk:
  - canonical adapter builder 외에 CLI placeholder/fallback path가 별도 존재
  - service별 성공 기준이 helper 외부에서 달라질 수 있음
  - false success와 임시 우회가 장기 구조로 굳을 수 있음

### Finding 5. Recovery/retry 의미 구현이 여러 파일에 중복됩니다

- Evidence:
  - `runtime_v2/retry_budget.py:4`
  - `runtime_v2/recovery_policy.py:39`
  - `runtime_v2/circuit_breaker.py:13`
  - `runtime_v2/control_plane.py:1201`
- Risk:
  - retry/backoff/circuit semantics 수정 시 단일 변경 원칙이 깨짐
  - 같은 정책 이름이 여러 구현으로 분리되어 drift 가능성 상승

---

## Remediation Thesis

- writer는 `control_plane` 최종 writer API 하나로 수렴합니다.
- runtime preflight와 worker result를 명확히 분리해 failure contract를 동결합니다.
- worker는 evidence/result만 반환하고 `next_jobs` 생성, blocked 정책, fallback 결정은 orchestration layer로 올립니다.
- external adapter 호출은 helper 하나와 adapter builder 하나로 수렴시키고 CLI 우회 경로는 probe/debug 전용으로 격리합니다.
- retry/backoff/circuit 의미는 한 구현 경로로 정리합니다.

---

## Milestone Map

- M0: audit findings and invariants lock
- M1: single latest/result writer consolidation
- M2: failure contract freeze
- M3: worker policy leakage removal
- M4: adapter boundary consolidation
- M5: retry/backoff semantics unification and verification gate close

---

## Execution Plan

### Task 1. Audit baseline을 테스트와 문서로 고정

**Files:**
- Modify: `docs/plans/2026-03-09-runtime-v2-guardrail-drift-remediation-plan.md`
- Modify: `docs/TODO.md`
- Read/Test: `tests/test_runtime_v2_latest_run.py`
- Read/Test: `tests/test_runtime_v2_control_plane_chain.py`

**Owner Layer:** docs / verification baseline

**Do:**
- 이번 audit의 P0/P1/P2 리스크를 문서 기준선으로 고정합니다.
- writer/failure/policy/adaptor hotspot을 테스트 추가 대상과 1:1로 연결합니다.

**Verification:**
- `python -m pytest tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py -q`

### Task 2. Latest/result writer를 단일 API로 수렴

**Files:**
- Modify: `runtime_v2/latest_run.py`
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/bootstrap.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/manager.py`
- Test: `tests/test_runtime_v2_latest_run.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Owner Layer:** control plane / latest-run writer API

**Do:**
- latest/result/gui/events 갱신을 canonical runtime snapshot API 하나로 감쌉니다.
- `bootstrap`, `cli`, `manager`는 raw write 대신 명시적 helper만 사용하게 제한합니다.
- `control_plane`만 최종 latest 의미를 소유하도록 경계를 다시 고정합니다.

**Exit:**
- 같은 run에서 pointer/result/gui join이 항상 동일 `run_id`로 정렬됩니다.
- writer entrypoint 수가 문서상/코드상으로 명시적으로 감소합니다.

### Task 3. Failure contract 의미를 동결

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/workers/job_runtime.py`
- Modify: `runtime_v2/evidence.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_gpu_workers.py`

**Owner Layer:** runtime preflight + control-plane contract interpretation

**Do:**
- `completion.state`는 output/result meaning만 담당하게 합니다.
- `retryable`은 recovery hint만 담당하게 합니다.
- `error_code`는 failure axis naming만 담당하게 합니다.
- runtime preflight blocked는 runtime/control-plane에서만 결정하게 하고 worker 내부 blocked policy를 축소합니다.

**Exit:**
- `run_id`, `error_code`, `attempt/backoff` 의미를 cross-file로 추적했을 때 재합성 지점이 줄어듭니다.

### Task 4. Worker policy leakage 제거

**Files:**
- Modify: `runtime_v2/workers/agent_browser_worker.py`
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Modify: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_agent_browser.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`

**Owner Layer:** control-plane downstream routing

**Do:**
- worker가 직접 `next_jobs`나 replan policy를 생성하는 경로를 축소하거나 orchestration helper로 이동합니다.
- worker는 evidence, artifact, validated output, input failure만 반환합니다.
- 상위 control plane이 downstream chaining을 단일 규칙으로 결정합니다.

**Exit:**
- worker별로 다른 실패 후속정책이 아니라 control-plane의 공통 chaining 규칙으로 수렴합니다.

### Task 5. Adapter boundary와 CLI fallback을 probe/debug 전용으로 격리

**Files:**
- Modify: `runtime_v2/stage2/agent_browser_adapter.py`
- Modify: `runtime_v2/workers/external_process.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Modify: `runtime_v2/stage2/canva_worker.py`
- Test: `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`

**Owner Layer:** external adapter boundary

**Do:**
- adapter helper 밖에서 placeholder/fallback 성공을 판정하지 못하게 정리합니다.
- CLI recovery path는 probe/debug contract로만 명시하고 운영 기본 경로와 분리합니다.
- 서비스별 adapter success 판정을 helper contract 하나로 통일합니다.

**Exit:**
- adapter success/failure/evidence contract가 worker/CLI/helper 사이에서 하나로 맞춰집니다.

### Task 6. Retry/backoff/circuit semantics를 단일 구현으로 정리

**Files:**
- Modify: `runtime_v2/retry_budget.py`
- Modify: `runtime_v2/recovery_policy.py`
- Modify: `runtime_v2/circuit_breaker.py`
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Owner Layer:** recovery policy

**Do:**
- 중복 helper를 줄이고 canonical policy module 하나를 기준으로 사용합니다.
- control plane의 wrapper는 의미 변환이 아니라 연결 역할만 남깁니다.

**Exit:**
- retry/backoff/circuit 규칙 변경 지점이 실질적으로 한 곳으로 줄어듭니다.

---

## Priority

- P0: Task 2 single writer
- P0: Task 3 failure contract freeze
- P1: Task 4 worker policy leakage
- P1: Task 5 adapter boundary consolidation
- P2: Task 6 retry/backoff dedupe

## Verification Bundle

- `lsp_diagnostics` on modified files
- `python -m pytest tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_control_plane_chain.py -q`
- `python -m pytest tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_gpu_workers.py tests/test_runtime_v2_agent_browser.py tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py -q`
- `python -m py_compile runtime_v2/control_plane.py runtime_v2/latest_run.py runtime_v2/cli.py runtime_v2/manager.py runtime_v2/supervisor.py`
- `verify-implementation`

## Done Definition

- latest writer가 문서와 코드 모두에서 단일 API/단일 owner로 설명 가능합니다.
- blocked/failed/retryable/completion 의미가 파일마다 다르게 재합성되지 않습니다.
- worker는 정책을 결정하지 않고 evidence/result만 반환합니다.
- adapter success path가 helper 하나로 수렴합니다.
- verification bundle evidence가 fresh 상태로 확보됩니다.

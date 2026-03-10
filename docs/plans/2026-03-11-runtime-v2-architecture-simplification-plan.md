# Runtime_v2 Architecture Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`를 디버깅 효율성, 파이프라인 단순성, 견고성 대전제에 맞게 더 단순하고 설명 가능한 구조로 수렴시킵니다.

**Architecture:** 이번 계획은 새 기능 추가가 아니라 owner 정리와 drift 제거가 목적입니다. 핵심은 (1) run 의미의 단일화, (2) guardrail 누적 방지, (3) 복구 책임의 단일화입니다. 모든 변경은 fail-closed를 유지하되, 예외 분기 수와 의미 해석 지점을 줄이는 방향으로만 진행합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, `control_plane`, `latest_run`, browser plane, JSON evidence snapshots, `pytest`, `py_compile`, project verify skills

---

### Task 1: Run Identity Audit Lock

Status: COMPLETE (confirmed by Oracle review in this session)

**Files:**
- Modify: `docs/reference/error-code-semantics.md`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Test: `tests/test_runtime_v2_error_code_docs_drift.py`

**Step 1: Add run identity rules to docs**

Document that:
- `control_plane` is the final owner of run meaning
- `latest_run` is an alias/index, not a semantic authority
- browser/gpt/worker layers may emit evidence, but must not redefine run meaning

**Step 2: Add doc assertions to drift test**

Extend `tests/test_runtime_v2_error_code_docs_drift.py` so it also checks these tokens exist in the two canonical docs:
- `control_plane`
- `latest_run`
- `run_id`
- `single writer`

**Step 3: Run doc drift test**

Run: `python -m pytest tests/test_runtime_v2_error_code_docs_drift.py -q`
Expected: PASS

**Step 4: Commit**

```bash
git add docs/reference/error-code-semantics.md docs/sop/SOP_runtime_v2_development_guardrails.md tests/test_runtime_v2_error_code_docs_drift.py
git commit -m "docs: lock runtime_v2 run identity rules"
```

### Task 2: Recovery Owner Freeze

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Modify: `runtime_v2/cli.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write failing tests for recovery owner assumptions**

Add tests proving:
- control-plane makes retry/backoff/failure final decisions
- browser supervisor reports health/recovery outcomes but does not create new work
- CLI best-effort paths do not become policy owners

**Step 2: Run tests to confirm current gaps (if any)**

Run targeted tests one by one.

**Step 3: Remove any residual policy leakage**

Only if tests show leakage:
- move retry/recovery branching to `control_plane`
- downgrade CLI/browser paths to evidence/reporting only

**Step 4: Re-run targeted regressions**

Run:
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "retry or blocked or exhausted"`
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "restart or busy or lock"`

Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/control_plane.py runtime_v2/browser/supervisor.py runtime_v2/cli.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_browser_plane.py
git commit -m "fix: freeze runtime_v2 recovery ownership"
```

### Task 3: Guardrail Accumulation Controls

Status: COMPLETE (confirmed by Oracle review in this session)

**Files:**
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/reference/error-code-semantics.md`
- Create: `tests/test_runtime_v2_guardrail_contract.py`

**Step 1: Define guardrail addition rule**

Add explicit guardrail acceptance criteria to docs:
- owner layer
- solved failure mode
- removal condition

**Step 2: Add a lightweight guardrail contract test**

Create `tests/test_runtime_v2_guardrail_contract.py` that checks canonical docs contain these required phrases:
- `owner`
- `failure mode`
- `removal`

**Step 3: Run the test**

Run: `python -m pytest tests/test_runtime_v2_guardrail_contract.py -q`
Expected: PASS

**Step 4: Commit**

```bash
git add docs/sop/SOP_runtime_v2_development_guardrails.md docs/reference/error-code-semantics.md tests/test_runtime_v2_guardrail_contract.py
git commit -m "test: add runtime_v2 guardrail contract checks"
```

### Task 4: Single Meaning Snapshot Review

Status: COMPLETE

**Files:**
- Modify: `runtime_v2/latest_run.py`
- Modify: `runtime_v2/evidence.py`
- Modify: `runtime_v2/debug_log.py`
- Test: `tests/test_runtime_v2_latest_run.py`
- Test: `tests/test_runtime_v2_evidence.py`
- Test: `tests/test_runtime_v2_debug_log.py`

**Step 1: Write failing tests for mixed meanings**

Add/extend tests that prove:
- canonical handoff carries canonical meaning only
- evidence preserves mismatch as warning, not a new blocker class
- debug log clearly marks raw values as raw

**Step 2: Run tests to identify meaning drift**

Run one-by-one targeted tests.

**Step 3: Tighten boundaries only where tests fail**

Do not add fields unless required. Prefer renaming or narrowing existing fields over new structure.

**Step 4: Re-run targeted bundle**

Run:
- `python -m pytest tests/test_runtime_v2_latest_run.py -q`
- `python -m pytest tests/test_runtime_v2_evidence.py -q`
- `python -m pytest tests/test_runtime_v2_debug_log.py -q`

Expected: PASS

### Progress note

- `runtime_v2/evidence.py` now resolves a single `snapshot_run_id` from the review/readiness payload instead of letting `latest_run`/`gui_status`/`result_metadata` be interpreted separately.
- `tests/test_runtime_v2_evidence.py` now locks this with two regressions:
  - resolver prefers `result_metadata.run_id`
  - drifted inputs still expose one normalized `snapshot_run_id`
- `runtime_v2/debug_log.py` now marks `error_code_source` together with `raw_error_code`, so raw vs canonical meaning is explicit in debug summaries.
- verification bundle passed:
  - `python -m pytest tests/test_runtime_v2_latest_run.py -q`
  - `python -m pytest tests/test_runtime_v2_evidence.py -q`
  - `python -m pytest tests/test_runtime_v2_debug_log.py -q`
  - `python -m py_compile runtime_v2/latest_run.py runtime_v2/evidence.py runtime_v2/debug_log.py`

**Step 5: Commit**

```bash
git add runtime_v2/latest_run.py runtime_v2/evidence.py runtime_v2/debug_log.py tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_evidence.py tests/test_runtime_v2_debug_log.py
git commit -m "fix: tighten runtime_v2 snapshot meaning boundaries"
```

### Task 5: Hotspot Review of control_plane.py

**Files:**
- Read: `runtime_v2/control_plane.py`
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`
- Create or Modify: `docs/plans/2026-03-11-control-plane-hotspot-review.md`

**Step 1: Record current hotspot facts**

Write a short review doc that captures:
- current responsibilities in `control_plane.py`
- which ones are canonical and should stay
- which ones are future decomposition candidates
- exact reopen conditions for decomposition

**Step 2: Update TODO/COMPLETED**

Do not open a new implementation unit unless a real trigger exists. Record this as a review artifact, not a feature plan.

**Step 3: Run doc checks**

Run:
- `python -m pytest tests/test_runtime_v2_error_code_docs_drift.py -q`

Expected: PASS

**Step 4: Commit**

```bash
git add docs/TODO.md docs/COMPLETED.md docs/plans/2026-03-11-control-plane-hotspot-review.md
git commit -m "docs: record control plane hotspot review"
```

### Task 6: Final Verification Gate

Status: COMPLETE (fresh pytest bundle, py_compile, and guardrails re-check closed in this session)

**Files:**
- Read: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Run tests only

**Step 1: Run focused verification set**

Run:
- `python -m pytest tests/test_runtime_v2_error_code_docs_drift.py -q`
- `python -m pytest tests/test_runtime_v2_latest_run.py -q`
- `python -m pytest tests/test_runtime_v2_evidence.py -q`
- `python -m pytest tests/test_runtime_v2_debug_log.py -q`
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q`

**Step 2: Run compile checks**

Run:
- `python -m py_compile runtime_v2/error_codes.py runtime_v2/latest_run.py runtime_v2/evidence.py runtime_v2/debug_log.py runtime_v2/control_plane.py`

**Step 3: Re-read guardrails before claiming completion**

Confirm these still hold:
- single writer
- single failure contract
- worker policy-free
- single reference adapter

**Step 4: Commit final cleanup if needed**

Only if verification reveals small doc/test drift.

---

Plan complete and saved to `docs/plans/2026-03-11-runtime-v2-architecture-simplification-plan.md`.

실행 선택지는 두 가지입니다.

1. **Subagent-Driven (이 세션)** - 태스크별로 바로 구현하고 중간 검토를 반복합니다.
2. **Parallel Session (별도 세션)** - `executing-plans` 기준으로 분리된 구현 세션에서 배치 실행합니다.

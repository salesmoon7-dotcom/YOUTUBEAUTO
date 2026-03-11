# Runtime_v2 Residual Drift Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers/executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`의 남은 구조 drift를 정리해 `event single writer`, `single failure contract`, `dispatch 단순성`을 실제 코드에서도 다시 잠급니다.

**Architecture:** 이번 계획은 새 기능 추가가 아니라 잔여 owner drift 제거가 목적입니다. `control_plane`이 event/snapshot 의미를 단일 소유하고, `supervisor/browser/worker`는 raw 관측과 실행 결과만 반환하도록 경계를 다시 고정합니다. 모든 변경은 fail-closed를 유지하고, 분기 수와 의미 재해석 지점을 줄이는 방향으로만 수행합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, `control_plane`, `supervisor`, browser plane, JSON evidence snapshots, `pytest`, `py_compile`, Oracle review, project verify skills

**Skill / Review Bundle:**
- 계획 작성/실행 기준: vendor + `superpowers/executing-plans`
- 구현/수정 검토: Oracle first, Oracle verification
- 기본 검증: kimoring-ai-skills + `verify-implementation`
- 오류/테스트 실패 시: `systematic-debugging`
- 완료 직전: `verification-before-completion`
- 큰 변경 후: `requesting-code-review`
- 브라우저/GUI 검증 시: `webapp-testing`
- 새 도메인 발견 시: `find-skills`

---

### Task 1: Event Single Writer Restoration

**Files:**
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_browser_plane.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write failing tests for event ownership**

Ground the current gap first:
- `runtime_v2/supervisor.py` passes `events_file=runtime_config.control_plane_events_file` into `BrowserSupervisor.tick()`
- `runtime_v2/browser/supervisor.py` currently appends directly through `_append_browser_event()`

Update existing tests and add minimal new coverage proving:
- browser supervisor no longer writes directly to `control_plane_events.jsonl`
- browser supervisor returns event candidates or equivalent raw records only
- control plane remains the only final appender for control-plane event evidence
- existing browser-plane tests that currently expect direct file writes are flipped to the new expectation

**Step 2: Run targeted tests to confirm current gap**

Run one by one:
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "event or restart or lock"`
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "event or run_id"`

Expected: at least one regression exposes current multi-writer path

**Step 3: Remove direct browser event writes**

Implement minimal changes so that:
- `runtime_v2/browser/supervisor.py` stops appending directly to the control-plane event file
- `runtime_v2/browser/supervisor.py` returns raw browser event records in a stable payload field
- `runtime_v2/supervisor.py` transports raw browser event records upward without final meaning conversion
- `runtime_v2/control_plane.py` appends those records via `_append_control_event()` / control-plane append path only
- any direct `BrowserSupervisor` usage from `runtime_v2/cli.py` is checked and aligned if the tick contract changes

**Step 4: Re-run targeted regressions**

Run one by one:
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "event or restart or lock"`
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "event or run_id"`

Expected: PASS

**Step 5: Oracle review for single-writer restoration**

Ask Oracle to confirm:
- single writer is restored in code, not only in docs
- browser plane remains raw-health/reporting only
- no new evidence drift path was introduced

---

### Task 2: Failure Contract Unification

**Files:**
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/error_codes.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_error_codes.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write failing tests for preflight/runtime contract consistency**

Add tests proving:
- `restart_exhausted` converges to `BROWSER_RESTART_EXHAUSTED`
- blocked vs failed vs terminal block semantics do not change across supervisor and control plane
- `attempt/backoff` meaning remains aligned for blocked, retryable, terminal paths

**Step 2: Run targeted tests to expose current mismatch**

Run one by one:
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "blocked or exhausted or backoff"`
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "restart or exhausted"`
- `python -m pytest tests/test_runtime_v2_error_codes.py -q`

Expected: current mismatch or missing coverage becomes explicit

**Step 3: Create one canonical preflight contract mapping**

Implement minimal changes so that:
- preflight runtime code -> worker/error/completion meaning is defined in one canonical path only
- supervisor does not invent a parallel semantic layer
- control plane consumes that same canonical mapping instead of re-deriving meaning ad hoc
- choose exactly one canonical owner for this mapping before code changes:
  - preferred: `runtime_v2/control_plane.py`
  - allowed alternative: one shared helper used by both layers

**Step 4: Re-run targeted regressions**

Run one by one:
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "blocked or exhausted or backoff"`
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "restart or exhausted"`
- `python -m pytest tests/test_runtime_v2_error_codes.py -q`

Expected: PASS

**Step 5: Oracle review for failure-contract freeze**

Ask Oracle to confirm:
- same failure axis has one name and one meaning
- supervisor/browser no longer leak policy ownership
- contract remains fail-closed

---

### Task 3: `_run_worker()` Dispatch Simplification

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`
- Test: `tests/test_runtime_v2_dev_loop.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`

**Step 1: Add coverage for worker state cleanup symmetry**

Add tests proving:
- supported workloads all pass through one dispatch path
- worker registry returns to `idle` through one shared cleanup path
- unsupported workload still fails loudly with explicit error

**Step 2: Run focused dispatch tests**

Run one by one:
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "worker or registry"`
- `python -m pytest tests/test_runtime_v2_dev_loop.py -q`
- `python -m pytest tests/test_runtime_v2_stage2_workers.py -q`

Expected: current duplication surface is covered

**Step 3: Replace repeated branch cleanup with shared dispatch path**

Implement minimal changes so that:
- workload function lookup uses a dispatch table or equivalent single registry
- `update_worker_state(... state="idle")` is executed through one shared cleanup path
- cleanup is guaranteed with `try/finally` semantics even on exceptions or early returns
- no worker-specific policy logic is added during the simplification

**Step 4: Re-run focused regressions**

Run one by one:
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "worker or registry"`
- `python -m pytest tests/test_runtime_v2_dev_loop.py -q`
- `python -m pytest tests/test_runtime_v2_stage2_workers.py -q`

Expected: PASS

**Step 5: Request code review**

Run `requesting-code-review` after this task because it is a large structural change inside the main hotspot file.

---

### Task 4: Final Verification Gate

**Files:**
- Read: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Run tests only

**Step 1: Run focused verification set**

Normal path: run file-level checks one by one.

Run one by one:
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q`
- `python -m pytest tests/test_runtime_v2_evidence.py -q`
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q`
- `python -m pytest tests/test_runtime_v2_error_codes.py -q`
- `python -m pytest tests/test_runtime_v2_latest_run.py -q`
- `python -m pytest tests/test_runtime_v2_debug_log.py -q`

Expected: PASS

If chat/UI interruption repeats, downgrade to interrupt-safe execution exactly as the SOP requires:
- one tool at a time only
- pytest at single test-case granularity only
- browser relaunch/recovery commands stay detached or manual

**Step 2: Run compile checks**

Run:
- `python -m py_compile runtime_v2/control_plane.py runtime_v2/supervisor.py runtime_v2/browser/supervisor.py runtime_v2/error_codes.py runtime_v2/latest_run.py runtime_v2/evidence.py runtime_v2/debug_log.py`

Expected: PASS

**Step 3: Run project verification gate**

Run:
- `verify-implementation`
- `verification-before-completion`

Confirm these still hold:
- single writer
- single failure contract
- worker policy-free
- single reference adapter
- `run_id` alignment
- `error_code` meaning alignment
- `attempt/backoff` alignment

**Step 4: Oracle completion review**

Ask Oracle to confirm there is no residual drift before completion claim.

---

### Task 5: Git Completion

**Files:**
- Run git commands only

**Step 1: Review working tree**

Run:
- `git_plain.bat status`
- `git_plain.bat diff --stat`
- `git_plain.bat log -5 --oneline`
- `git_plain.bat branch --show-current`
- `git_plain.bat rev-parse --abbrev-ref @{upstream}`

**Step 2: Commit using repository style**

Suggested commit direction:
- `fix: restore runtime_v2 event and failure ownership`

**Step 3: Push**

Run:
- `git_plain.bat push`

Expected: remote update succeeds without force push

---

Plan complete and saved to `docs/plans/2026-03-11-runtime-v2-residual-drift-remediation-plan.md`.

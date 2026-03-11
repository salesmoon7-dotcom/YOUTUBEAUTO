# Runtime_v2 Conditional Tightening Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`를 현재의 canonical owner 구조는 유지한 채, 남아 있는 문서 상태 drift, event 경계 군더더기, 의미 drift 회귀 공백을 줄여 `조건부 수용` 상태를 더 신뢰 가능한 상태로 잠급니다.

**Architecture:** 이 계획은 구조를 다시 쪼개거나 owner를 재배치하는 배치가 아닙니다. `control_plane`의 canonical owner 역할은 유지하고, `supervisor/browser`는 raw observation only, `latest_run/evidence`는 단일 의미 정규화, 문서는 단일 상태 의미로 수렴시키는 tightening만 수행합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, `control_plane`, `supervisor`, browser plane, latest-run/evidence snapshots, Markdown docs, `pytest`, `py_compile`, Oracle review, project verify skills

## Recommended Execution Order

- Start with `Task 1` only. This task is doc-only and exists to prevent status drift before touching code.
- Insert an Oracle pre-code review gate immediately after `Task 1`. Do not start code changes until Oracle confirms the status model is aligned and no completed unit was implicitly reopened.
- Move to `Task 2` next. Event ownership is the most structural remaining code boundary and should be tightened before any later meaning/readiness interpretation work.
- Run `Task 3` after `Task 2`. `latest_run`/`evidence`/`debug_log` should be tightened only after the event boundary is stable.
- Treat `Task 4` as docs-first by default. Only change code if a newly added regression proves a real fail-closed gap.
- Finish with `Task 5` full verification and Oracle closure, then `Task 6` git-only cleanup if explicitly requested.

## Task Classification

- `Task 1`: doc-only
- `Task 1.5`: Oracle review gate before code changes
- `Task 2`: code-changing + targeted regressions
- `Task 3`: test-first, then narrow code changes only if regressions fail
- `Task 4`: docs-first, code-change only on proven gap
- `Task 5`: verification-only
- `Task 6`: git-only

---

### Task 1: Plan Status And Doc State Alignment

**Files:**
- Modify: `docs/TODO.md`
- Read: `docs/COMPLETED.md`
- Read: `docs/plans/2026-03-11-runtime-v2-architecture-simplification-plan.md`
- Create or Modify: `docs/plans/2026-03-11-runtime-v2-conditional-tightening-plan.md`

**Step 1: Re-read canonical status sources**

Read and compare:
- `docs/TODO.md`
- `docs/COMPLETED.md`
- `docs/plans/2026-03-11-runtime-v2-architecture-simplification-plan.md`

Lock these facts before editing:
- what is already complete
- what is active implementation work
- what is follow-up judgment only

Do not rewrite completion evidence in this task. Completed artifacts stay read-only unless genuinely new completion happens later.

**Step 2: Write a failing doc consistency checklist**

Create a manual checklist in the working notes proving these statements can all be true at once:
- `Task 4 Single Meaning Snapshot Review` is complete in `docs/COMPLETED.md`
- `docs/TODO.md` no longer reads that same task as active implementation
- the new plan is described as a tightening follow-up, not a contradiction of the completed simplification plan

**Step 3: Edit docs to align one status meaning**

Make the smallest wording changes needed so that:
- `docs/TODO.md` treats this plan as a follow-up tightening unit only
- `docs/COMPLETED.md` remains the source of prior completion claims without reopening them
- `docs/plans/2026-03-11-runtime-v2-architecture-simplification-plan.md` remains historical completion evidence, not an editable reopened task list

Do not change technical decisions in this step. Change `docs/TODO.md` status language only.

**Step 4: Re-read edited docs for contradiction**

Read back:
- `docs/TODO.md`
- `docs/COMPLETED.md` (read-only comparison)
- `docs/plans/2026-03-11-runtime-v2-conditional-tightening-plan.md`

Expected: no sentence implies both "complete" and "still implementing" for the same unit.

**Step 5: Oracle pre-code review gate**

Ask Oracle to confirm all of the following before any code change begins:
- document status meaning is aligned
- completed units were not reopened implicitly
- this plan is a follow-up tightening unit, not a contradiction of prior completion records

Expected: Oracle approves moving to `Task 2`

---

### Task 2: Event Boundary Tightening Without Reopening Decomposition

**Files:**
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_browser_plane.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write the failing tests for event ownership**

Add or update tests proving:
- browser plane returns raw event candidates only
- `control_plane` remains the only final appender on the existing control-plane event append path
- changing browser health/recovery behavior does not create a second event meaning owner

Prefer extending existing tests rather than creating a new file.

**Step 2: Run targeted tests to expose current gap**

Run one by one:
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "event or restart or lock"`
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "event or run_id"`

Expected: current directness or ambiguity in the event boundary becomes explicit.

**Step 3: Implement the smallest contract tightening**

Make minimal code changes so that:
- `runtime_v2/browser/supervisor.py` does not own final event writing semantics
- `runtime_v2/supervisor.py` transports raw browser events upward without adding a second meaning layer
- `runtime_v2/control_plane.py` performs the final append through the existing control-plane event path only

Do not extract a new subsystem. Keep the current owner model.

**Step 4: Re-run the targeted tests**

Run one by one:
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "event or restart or lock"`
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q -k "event or run_id"`

Expected: PASS

**Step 5: Run compile checks for touched files**

Run:
- `python -m py_compile runtime_v2/supervisor.py runtime_v2/browser/supervisor.py runtime_v2/control_plane.py`

Expected: PASS

---

### Task 3: Run-Meaning And Mismatch Drift Lock

**Files:**
- Modify: `runtime_v2/latest_run.py`
- Modify: `runtime_v2/evidence.py`
- Modify: `runtime_v2/debug_log.py`
- Test: `tests/test_runtime_v2_latest_run.py`
- Test: `tests/test_runtime_v2_evidence.py`
- Test: `tests/test_runtime_v2_debug_log.py`

**Step 1: Write failing regressions for mixed run meaning**

Add or tighten tests proving:
- `snapshot_run_id` remains one normalized value even when pointer/gui/result disagree
- `warning_worker_error_code_mismatch` stays a warning and does not silently become a new success path
- debug output clearly distinguishes canonical `error_code` from raw worker diagnostics

**Step 2: Run targeted tests to confirm the current boundary**

Run one by one:
- `python -m pytest tests/test_runtime_v2_latest_run.py -q`
- `python -m pytest tests/test_runtime_v2_evidence.py -q`
- `python -m pytest tests/test_runtime_v2_debug_log.py -q`

Expected: either PASS with stronger coverage added, or a narrow failure that identifies residual drift.

**Step 3: Tighten meaning boundaries only if tests demand it**

If any new test fails, make the smallest change needed so that:
- latest-run remains join/index, not semantic owner
- readiness/evidence fail closed on drift
- debug summaries preserve raw-vs-canonical distinction

Do not add parallel state meaning. Prefer narrowing existing fields over new structure.

**Step 4: Re-run the targeted bundle**

Run one by one:
- `python -m pytest tests/test_runtime_v2_latest_run.py -q`
- `python -m pytest tests/test_runtime_v2_evidence.py -q`
- `python -m pytest tests/test_runtime_v2_debug_log.py -q`

Expected: PASS

**Step 5: Re-run compile checks**

Run:
- `python -m py_compile runtime_v2/latest_run.py runtime_v2/evidence.py runtime_v2/debug_log.py`

Expected: PASS

---

### Task 4: Browser Heuristic Changes Stay Evidence-First

**Files:**
- Read: `runtime_v2/browser/manager.py`
- Modify: `tests/test_runtime_v2_browser_plane.py`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/plans/2026-03-10-browser-instability-debug-cost-plan.md`

**Step 1: Add explicit regression coverage for heuristic drift handling**

Update tests or add narrow cases proving:
- ready/login/DOM uncertainty is not upgraded to `OK`
- heuristic failure leads to evidence or blocked/fail-closed behavior
- developers are steered toward evidence strengthening, not ad hoc fallback growth

**Step 2: Run targeted browser tests**

Run:
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "ready or login or blocked or unknown"`

Expected: current intended behavior is explicit.

**Step 3: Tighten docs before heuristics**

If code changes are not strictly required, change docs only so that:
- `runtime_v2/browser/manager.py` remains a hotspot with external UI risk
- future fixes must prefer evidence strengthening over fallback accumulation
- any new heuristic must preserve fail-closed semantics and owner boundaries

Any guardrail wording added here must follow the existing `owner / failure mode / removal` rule from `docs/sop/SOP_runtime_v2_development_guardrails.md`.

**Step 4: Re-run the same test slice**

Run:
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q -k "ready or login or blocked or unknown"`

Expected: PASS

---

### Task 5: Final Verification And Oracle Closure

**Files:**
- Read: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Run tests only

**Step 1: Run the focused verification set**

Run one by one:
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q`
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q`
- `python -m pytest tests/test_runtime_v2_latest_run.py -q`
- `python -m pytest tests/test_runtime_v2_evidence.py -q`
- `python -m pytest tests/test_runtime_v2_debug_log.py -q`

Expected: PASS

If chat interruption repeats, downgrade to interrupt-safe execution exactly as the SOP requires:
- one tool at a time only
- pytest at single-case granularity only
- browser relaunch/recovery stays detached or manual

**Step 2: Run compile checks**

Run:
- `python -m py_compile runtime_v2/control_plane.py runtime_v2/supervisor.py runtime_v2/browser/supervisor.py runtime_v2/latest_run.py runtime_v2/evidence.py runtime_v2/debug_log.py`

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

**Step 4: Ask Oracle for completion review**

Ask Oracle to confirm:
- current structure remains conditionally acceptable
- no change weakened the canonical `control_plane` owner model
- residual drift was reduced rather than redistributed

---

### Task 6: Git Completion

**Files:**
- Run git commands only

**Step 1: Review working tree**

Run:
- `git_plain.bat status`
- `git_plain.bat diff --stat`
- `git_plain.bat log -5 --oneline`

**Step 2: Commit using repository style**

Suggested commit direction:
- `docs: add runtime_v2 conditional tightening plan`
- or `fix: tighten runtime_v2 event and drift boundaries`

**Step 3: Push only if explicitly requested**

Run only on explicit user request:
- `git_plain.bat push`

---

Plan complete and saved to `docs/plans/2026-03-11-runtime-v2-conditional-tightening-plan.md`.

실행 선택지는 두 가지입니다.

1. **Subagent-Driven (이 세션)** - 태스크별로 바로 구현하고 중간 검토를 반복합니다.
2. **Parallel Session (별도 세션)** - `executing-plans` 기준으로 분리된 구현 세션에서 배치 실행합니다.

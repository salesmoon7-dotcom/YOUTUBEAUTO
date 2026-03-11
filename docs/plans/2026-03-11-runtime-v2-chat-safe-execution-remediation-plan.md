# Runtime_v2 Chat-Safe Execution Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2` 검증/운영이 채팅 세션에서 반복적으로 끊기는 문제를 줄이기 위해, 즉시 필요한 `interrupt-safe` 실행 규칙과 근원 완화용 구조 분리를 함께 적용합니다.

**Architecture:** 이번 계획은 두 층으로 나뉩니다. 1차는 코드 변경 없이 바로 효과를 내는 실행 규칙 고정(`interrupt-safe + source-only + detached verification`)이고, 2차는 repo 루트에 공존하는 브라우저 세션/probe/tmp 산출물을 외부 루트로 밀어 execution-tooling interaction의 근원을 줄이는 구조 정리입니다. 오라클 재검토 결론은 “운영 규칙 강화는 필수이고, 근원 완화 구조 변경은 강하게 권장되지만 browser polling/health 로직 대수술은 1차 원인이 아니다”입니다.

**Tech Stack:** Python 3.13, `runtime_v2`, Windows local filesystem, detached PowerShell/CLI execution, Markdown docs/SOP, `py_compile`, targeted `pytest`, Oracle review

---

## Tier Boundary (Non-negotiable)

- **Tier A (Immediate operating rule):** `interrupt-safe + source-only`는 구조 변경(Task 3)과 무관하게 항상 유지합니다.
- **Tier B (Enablement):** detached 실행을 동일 계약/산출물로 재현 가능하게 만드는 최소 도구/문서만 추가합니다(Task 2, 4).
- **Tier C (Root-cause reduction):** repo root generated runtime growth를 외부 루트로 이동합니다(Task 3).

Completion is only valid if Tier A is canonical and Tier B/C converge to one output contract.

---

## Decision Record

- **Oracle verdict:** 주원인은 `execution-tooling interaction`입니다. foreground chat-driven `pytest`/selftest 실행이 wrapper/UI interruption과 충돌하고, repo 루트의 generated runtime tree가 그 마찰을 키웁니다.
- **Immediate rule is mandatory:** 운영 규칙 강화는 선택이 아니라 즉시 채택해야 합니다. 근원 구조 변경이 끝나도 foreground chat pytest는 여전히 취약할 수 있으므로, `interrupt-safe + source-only`는 남겨야 합니다.
- **Root-cause reduction is still warranted:** 사용자가 요구한 “근원 제거”는 과잉이 아닙니다. 다만 broad rewrite가 아니라, 외부 session/probe/tmp 루트 분리와 detached 실행 표준화가 맞는 방향입니다.
- **Mixed-state diagnosis:** 브라우저 세션/probe/scratch 기본값은 대부분 외부 루트로 이동했지만, 런타임 상태/evidence/artifact 기본값은 여전히 repo-root `system/runtime_v2/*`에 많이 남아 있습니다. 두 범주를 같은 문제로 뭉뚱그리지 않습니다.
- **Do not treat as browser-manager rewrite:** `runtime_v2/browser/*` health polling, `/json` timeout, launch loop는 지연 요인일 수 있지만 이번 문제의 1차 원인은 아닙니다. readiness 정확도 축과 chat interruption 축을 섞어 대수술하지 않습니다.

---

### Task 1: Canonicalize Chat-Safe Execution Rules

**Files:**
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/sop/SOP_chat_interruption_repo_triage.md`
- Modify: `docs/INDEX.md`
- Modify: `AGENTS.md`

**Step 1: Record the non-optional default**

Document that `runtime_v2` chat sessions must start with:
- source-only search
- one tool at a time when interruption is suspected
- `pytest` at `::test_name` granularity only
- no foreground real-browser relaunch/recovery

**Step 2: Distinguish tiers more sharply**

State explicitly:
- `safe`: helper/contract/doc verification in chat
- `isolated`: detached/probe-root execution only
- `manual`: operator-controlled shell only

**Step 3: Make the downgrade automatic in docs**

Add wording that any repeated chat interruption immediately forces:
- stop parallel tool calls
- stop file-level pytest bundles
- switch to detached log-producing execution

**Step 4: Verification**

Read back:
- `docs/sop/SOP_runtime_v2_development_guardrails.md`
- `docs/sop/SOP_chat_interruption_repo_triage.md`
- `docs/INDEX.md`

Expected: one consistent rule set, no conflicting execution advice.

**Task 1 execution split (recommended)**

- `Task 1A - Guardrails canonical block`
  - Edit only `docs/sop/SOP_runtime_v2_development_guardrails.md`
  - Goal: add one unmistakable session-start block for `interrupt-safe + source-only`
  - Done when: the file alone clearly says `runtime_v2` chat work starts with source-only search, one-tool-at-a-time on interruption suspicion, `pytest ::test_name` only, and no foreground real-browser recovery.

- `Task 1B - Triage SOP alignment`
  - Edit only `docs/sop/SOP_chat_interruption_repo_triage.md`
  - Goal: make the downgrade path deterministic
  - Done when: the SOP explicitly says repeated interruption forces detached log-producing execution and forbids file-level foreground pytest in chat.

- `Task 1C - Discovery and routing alignment`
  - Edit only `docs/INDEX.md` and `AGENTS.md`
  - Goal: ensure future sessions discover the same rules immediately
  - Done when: both files point `runtime_v2` chat work to the same two SOPs first, with no alternate conflicting entrypoint.

- `Task 1D - Cross-doc consistency check`
  - Read only: `docs/sop/SOP_runtime_v2_development_guardrails.md`, `docs/sop/SOP_chat_interruption_repo_triage.md`, `docs/INDEX.md`, `AGENTS.md`
  - Goal: verify terminology is identical across docs
  - Check terms: `interrupt-safe`, `source-only`, `safe`, `isolated`, `manual`, `detached`
  - Done when: no file implies file-level foreground pytest is acceptable for long `runtime_v2` validation in chat.

---

### Task 2: Standardize Detached Verification Paths

**Files:**
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/config.py`
- Modify: `docs/plans/2026-03-07-runtime-v2-selftest-failure-analysis-and-test-plan.md`
- Modify: `docs/plans/2026-03-08-browser-session-stability-plan.md`

**Step 1: Define the detached output contract (MUST)**

Detached run은 아래 파일 트리를 최소 계약으로 남겨야 합니다.

- `<out_root>/logs/stdout.log`
- `<out_root>/logs/stderr.log`
- `<out_root>/summary.json`

`summary.json` 최소 필드:
- `started_at`
- `finished_at`
- `command`
- `exit_code`
- `kind` (`pytest|selftest|browser_recover`)
- `target` (pytest node/file or cli mode)
- `out_root`

이 계약이 없으면 detached verification으로 인정하지 않습니다.

**Step 2: Prefer detached for long validation**

Document and, if missing, implement a standard invocation pattern for long checks such as:
- browser-plane full-file pytest
- detached selftest
- browser recover probes

The standard must produce files that can be read after the child exits.

**Step 3: Keep manual override**

Preserve explicit output/probe-root override flags so debugging can still target custom roots.

**Step 4: Verification**

Run:

```bash
python -m py_compile runtime_v2/cli.py runtime_v2/config.py
```

Expected: PASS

---

### Task 3: Externalize Generated Runtime Growth From Repo Root

**Files:**
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2_manager_gui.py`
- Modify: `runtime_v2/cli.py`
- Modify: `docs/plans/2026-03-11-chat-interruption-structure-remediation-plan.md`
- Modify: `docs/plans/2026-03-11-chat-interruption-remediation-batches-plan.md`

**Step 1: External session root**

Move default browser session/profile storage out of repo root, for example:

```text
D:\YOUTUBEAUTO_RUNTIME\sessions\
```

**Step 2: External probe root**

Move default `system/runtime_v2_probe` growth to an external root, for example:

```text
D:\YOUTUBEAUTO_RUNTIME\probe\
```

**Step 3: External scratch root**

Move large `tmp_*` runtime/scratch outputs out of the repo root, for example:

```text
D:\YOUTUBEAUTO_RUNTIME\scratch\
```

**Step 4: Preserve migration safety (Explicit behavior)**

Session root:
- default는 external session root를 사용합니다.
- legacy `runtime_v2/sessions/`가 존재하고 external에 해당 세션이 없으면 자동 삭제/무시하지 않습니다.
- 동작은 둘 중 하나로 고정합니다. 둘 다 구현하지 않습니다.
  - A) `--migrate-sessions`가 있을 때만 1회 copy/move 후 external만 사용
  - B) `--allow-legacy-session-root`가 있을 때만 `external 우선 + legacy 차순 조회` 폴백 허용
- 기본값은 fail-closed입니다. 명시 플래그 없이 silent fallback을 두지 않습니다.

Probe root:
- 신규 detached/probe 출력 기본값은 external probe root로 고정합니다.
- legacy evidence 모음 위치는 SOP와 동일 토큰으로 고정합니다.
  - `D:/YOUTUBEAUTO_RUNTIME/probe/legacy_runtime_v2_probe/`

Do not silently discard existing login state.

**Step 5: Verification**

Run:

```bash
python -m py_compile runtime_v2/config.py runtime_v2/browser/manager.py runtime_v2/cli.py runtime_v2_manager_gui.py
```

Expected: PASS

---

### Task 4: Add A Chat-Safe Full-Test Runner Contract

**Files:**
- Create or Modify: `runtime_v2/cli.py`
- Create: `scripts/runtime_v2_detached_pytest.py`
- Modify: `docs/sop/SOP_chat_interruption_repo_triage.md`
- Modify: `docs/INDEX.md`

**Step 1: Add one minimal detached test runner**

Provide one canonical helper that runs:
- a specified pytest node or file
- in a detached child process
- with stdout/stderr redirected to explicit files
- with exit code preserved in a summary file or shell-visible result

This removes the need to improvise PowerShell quoting every session.

**Step 2: Scope the helper narrowly**

Do not build a general task orchestrator. Only support the minimum needed for:
- file-level pytest outside chat foreground
- node-level pytest in detached mode when evidence files are needed

**Step 3: Document examples**

Record canonical examples for:
- `tests/test_runtime_v2_browser_plane.py`
- selftest detached probe
- browser recovery detached run

**Step 4: Verification**

Run a small detached test case and confirm:
- stdout file exists
- stderr file exists or is empty
- exit code is recorded

---

### Task 5: Oracle Re-Review Gate After First Implementation Batch

**Files:**
- Read only: updated docs/code from Tasks 1-4

**Step 1: Ask Oracle whether immediate rules are now enforceable**

Ask Oracle to judge:
- whether `interrupt-safe + source-only` is now unmistakably canonical
- whether detached verification is discoverable enough that engineers will actually use it
- whether generated runtime roots are sufficiently externalized to count as root-cause reduction

**Step 2: Ask Oracle what not to change**

Require a short explicit statement on what still should NOT be rewritten:
- browser health semantics
- failure contract names/meanings
- latest snapshot/control-plane owner model

**Step 3: Apply only Oracle-approved follow-up edits**

If Oracle finds gaps, make only the smallest follow-up changes needed to close them.

---

### Task 6: Final Verification Bundle

**Files:**
- Verify only

**Step 1: Static verification**

Run compile checks for touched Python files.

**Step 2: Targeted interrupt-safe pytest**

Run only case-level or detached file-level verification according to the new rule.

**Step 3: Detached evidence check**

Confirm long-running validation leaves usable artifacts:
- stdout/stderr logs
- result or probe summary
- consistent output root

**Step 4: Re-measure workspace hotspots**

Confirm the biggest runtime growth paths are no longer defaulting under repo root.

**Step 5: Success criteria (Measurable)**

This remediation is complete only when all of the following are true:
1. `interrupt-safe + source-only`가 `docs/sop/SOP_runtime_v2_development_guardrails.md`, `docs/sop/SOP_chat_interruption_repo_triage.md`, `docs/INDEX.md`, `AGENTS.md`에서 상호 모순 없이 동일 문구로 발견됩니다.
2. detached pytest/selftest 1회 실행 후 `<out_root>/summary.json`과 stdout/stderr 로그가 생성되고 `exit_code`가 기록됩니다.
3. 기본 실행이 repo root의 `runtime_v2/sessions/`, `system/runtime_v2_probe/`, `tmp_*/`에 신규 대량 산출물을 만들지 않습니다.
4. `verify-implementation` 관문을 실행해 PASS 증거를 남깁니다.
5. Oracle이 browser health/ready 의미 대수술 없이 root-cause reduction 달성을 명시 확인합니다.

---

## Recommended Order

1. Task 1 - canonicalize chat-safe rules
2. Task 2 - standardize detached verification
3. Task 3 - externalize runtime growth
4. Task 4 - add detached pytest runner helper
5. Task 5 - Oracle re-review gate
6. Task 6 - final verification

## Why This Order

- Task 1 is mandatory immediately because root-cause reduction alone does not remove foreground interruption risk.
- Tasks 2-4 reduce the need for brittle manual shell choreography and remove the biggest execution-tooling friction points.
- Task 3 addresses the user’s “근원을 줄이는 쪽이 더 확실하지 않나” concern directly by shrinking repo-root runtime growth.
- Task 5 ensures we do not confuse readiness logic with interruption logic.
- Task 6 proves the fix changed both the operating rule and the default execution path.

## Delegation Split For 2 Parallel Sessions

Use exactly these two sessions if you want the fastest safe split.

- `Session 1 - Immediate rule hardening`
  - Scope:
    - `docs/sop/SOP_runtime_v2_development_guardrails.md`
    - `docs/sop/SOP_chat_interruption_repo_triage.md`
    - `docs/INDEX.md`
    - `AGENTS.md`
  - Tasks covered:
    - Task 1A
    - Task 1B
    - Task 1C
    - Task 1D
  - Type: docs-only
  - Risk: low
  - Goal: make `interrupt-safe + source-only` unmistakably canonical before touching runtime code.

- `Session 2 - Execution path and root-cause reduction`
  - Scope:
    - `runtime_v2/cli.py`
    - `runtime_v2/config.py`
    - `runtime_v2/browser/manager.py`
    - `runtime_v2_manager_gui.py`
    - `scripts/runtime_v2_detached_pytest.py`
    - related plans/docs that describe detached execution and external roots
  - Tasks covered:
    - Task 2
    - Task 3
    - Task 4
  - Type: code + docs
  - Risk: medium-high
  - Constraint: if Session 1 changes terminology, Session 2 must rebase or manually align wording before merge.

## Recommended 2-Session Order

- Start both sessions in parallel, but keep the contract simple:
  - Session 1 owns wording and canonical rule definition
  - Session 2 owns code paths and detached/external-root implementation
- Merge Session 1 first.
- Reconcile Session 2 against Session 1 wording before final integration.
- After both merge, run Task 5 and Task 6 in the main integration session only.

## Delegation Prompts

- `Session 1 prompt`
  - Lock `runtime_v2` chat-session execution rules across `docs/sop/SOP_runtime_v2_development_guardrails.md`, `docs/sop/SOP_chat_interruption_repo_triage.md`, `docs/INDEX.md`, and `AGENTS.md` so they all say the same thing: `interrupt-safe + source-only` is the mandatory default, repeated interruption forces one-tool-at-a-time plus detached log-producing execution, and long/file-level foreground pytest is not allowed in chat. Do not touch runtime code.

- `Session 2 prompt`
  - Implement the minimum code/doc changes needed to support chat-safe detached validation and root-cause reduction: standardize a detached output contract, externalize default session/probe/scratch roots out of repo root with explicit migration safety, and add a minimal detached pytest helper. Do not rewrite browser health semantics or failure contracts.

Plan complete and saved to `docs/plans/2026-03-11-runtime-v2-chat-safe-execution-remediation-plan.md`.

실행 선택지는 두 가지입니다.

1. **Subagent-Driven (이 세션)** - 태스크별로 바로 구현하고 중간 검토를 반복합니다.
2. **Parallel Session (별도 세션)** - `executing-plans` 기준으로 분리된 구현 세션에서 배치 실행합니다.

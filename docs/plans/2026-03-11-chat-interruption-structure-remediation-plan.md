# Chat Interruption Structure Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `D:\YOUTUBEAUTO`에서 반복되는 채팅/UI interruption을 줄이기 위해, 코드 저장소와 대형 런타임 산출물/브라우저 세션/임시 파일을 구조적으로 분리하고, interrupt-safe 작업 경로를 저장소 기본 운용 규칙으로 고정합니다.

**Architecture:** 이번 작업은 기능 구현이 아니라 저장소 구조 정리입니다. 핵심은 `repo root = 코드/문서`, `external runtime roots = 브라우저 세션/probe/log/artifact`, `chat session = interrupt-safe only`의 3계층 분리를 강제하는 것입니다. 우선순위는 체감 성능에 가장 큰 영향을 주는 대형 디렉터리부터 repo 밖으로 이동시키고, 그 다음 임시 파일과 문서 운영 규칙을 정리하는 순서로 둡니다.

**Tech Stack:** Python 3.13, `runtime_v2`, local filesystem on Windows, Tkinter GUI config, CLI runtime roots, Markdown plans/SOP, `py_compile`, targeted verification

---

## Evidence Base

### Measured size evidence

Measured on 2026-03-11 inside `D:\YOUTUBEAUTO`:

| Path | Observed size | Why it matters |
|---|---:|---|
| `runtime_v2/` | 2,078,886,465 bytes | Primary hotspot. Contains browser session profiles and generated runtime state inside the repo. |
| `system/` | 228,692,726 bytes | Main contributor is probe/output growth under `system/runtime_v2_probe/`; canonical runtime evidence under `system/runtime_v2/` should not be moved blindly. |
| `tmp_geminigen_from_backup/` | 301,808,461 bytes | Large temporary browser/profile-like directory inside repo root. |
| `tmp_gemini_window_test/` | 181,395,286 bytes | Another large temporary runtime directory inside repo root. |
| `docs/` | 560,678 bytes | Not large by itself, but always-read operational docs increase baseline context. |

### Path evidence for structural sprawl

- Browser session directories exist directly under `runtime_v2/sessions/`, including `chatgpt-primary`, `genspark-primary`, `seaart-primary`, `geminigen-primary`, `canva-primary`.
- Probe run directories accumulate under `system/runtime_v2_probe/`, including many `agent-browser-live-*`, `browser-recover-run-*`, and artifacts folders.
- Temporary files and patch artifacts remain in repo root, including `_tmp_stage.patch`, `tmp_task1_*.patch`, `tmp_stage_*.py`.
- Dirty worktree evidence exists now in active code and docs: `runtime_v2/control_plane.py`, multiple tests, and plan files.

### Canonical doc evidence

- `docs/sop/SOP_runtime_v2_development_guardrails.md:43` already defines an `interrupt-safe` downgrade mode when chat/UI interruption repeats.
- `docs/plans/2026-03-08-browser-session-stability-plan.md:85` says chat/UI interruption requires switching to one-tool-at-a-time execution.
- `docs/TODO.md:46` already records stronger interruption-response rules for this repo.

### Structural hypothesis

The interruption problem is not just prompt size. It is the combination of:
1. large non-code runtime trees inside the repository root,
2. repeated generated evidence/probe outputs under `system/`,
3. root-level temporary artifacts and patch files,
4. active docs/plans that encourage broad search over a workspace that is no longer code-only.

---

### Task 1: Move browser session profiles out of the repository root

**Priority:** P0 - highest impact

**Files:**
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2_manager_gui.py`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/INDEX.md`

**Why first:** `runtime_v2/` is the biggest directory, and `runtime_v2/sessions/*` contains browser profile/cache trees with many large binaries and many files. This is the strongest structural candidate for tool/search lag.

**Step 1: Define external session root**

Create one canonical root outside the repo, for example:

```text
D:\YOUTUBEAUTO_RUNTIME\sessions\
```

Add a config path or root derivation that makes browser session storage external by default.

**Step 2: Update browser manager/session path resolution**

Move all session/profile directory creation and lookup to the external root while preserving service names and port mapping.

**Step 3: Add migration-safe carryover for existing sessions**

Before switching defaults, define how existing session directories are handled:
- reuse existing profiles by moving/copying them to the external root, or
- support a one-time fallback lookup so login state is not accidentally discarded.

The migration path must be explicit because losing existing browser login state would make the remediation operationally unsafe.

**Step 4: Expose/confirm path in GUI and CLI**

Make sure `runtime_v2_manager_gui.py` and CLI runtime-root behavior can still point at the same runtime state after session root migration.

**Step 5: Verification**

Run:

```bash
python -m py_compile runtime_v2/config.py runtime_v2/browser/manager.py runtime_v2_manager_gui.py
```

Expected: PASS

---

### Task 2: Move `system/runtime_v2_probe` growth out of the repo root while preserving `system/runtime_v2`

**Priority:** P0 - highest impact

**Files:**
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2_manager_gui.py`
- Modify: `docs/plans/2026-03-08-browser-session-stability-plan.md`
- Modify: `docs/TODO.md`

**Why second:** `system/runtime_v2_probe/*` contains many run directories with artifacts, evidence, logs, and browser attach traces. These are generated data, not source code, but they live under the workspace root and keep growing. By contrast, `system/runtime_v2/` is still part of the active canonical runtime contract and should be reviewed separately instead of being bulk-moved.

**Step 1: Define external probe root**

Create one canonical probe/evidence root outside the repo, for example:

```text
D:\YOUTUBEAUTO_RUNTIME\probe\
```

**Step 2: Repoint default probe/output roots**

Update the runtime config and detached CLI defaults so new `system/runtime_v2_probe`-style runs write outside the repository, while preserving the canonical in-repo `system/runtime_v2/` contract unless a separate follow-up explicitly changes it.

**Step 3: Preserve manual override paths**

Keep explicit `--probe-root` and runtime-root overrides working so old evidence can still be read when needed.

**Step 4: Verification**

Run targeted CLI/compile verification after the path rewrite.

---

### Task 3: Clean root-level temp/patch artifacts and prevent re-accumulation

**Priority:** P1 - high impact, low risk

**Files:**
- Modify: `.gitignore`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/TODO.md`

**Why third:** Root-level temp files and patch artifacts increase directory noise, confuse search results, and make `git status`/workspace scanning heavier. In this repo, some `tmp_*` entries are not tiny patch leftovers but very large scratch directories.

**Observed examples:**
- `_tmp_stage.patch`
- `tmp_task1_browser_tests.patch`
- `tmp_task1_commit1.patch`
- `tmp_task1_control_plane.patch`
- `tmp_stage_control_plane.py`
- `tmp_geminigen_from_backup/` (~301MB)
- `tmp_gemini_window_test/` (~181MB)

**Step 1: Define external scratch root for large `tmp_*` runtime directories**

Create one canonical scratch location outside the repo, for example:

```text
D:\YOUTUBEAUTO_RUNTIME\scratch\
```

Large temporary runtime directories must be created there, not in the repo root.

**Step 2: Expand ignore patterns for transient patch/temp outputs**

Add explicit patterns for transient patch/temp artifacts that are repeatedly created during sessions.

**Step 3: Document cleanup rule**

Record that transient patch/temp outputs must be deleted or moved outside the repo before ending a session.

**Step 4: Verification**

Run `git status --short` and confirm transient patch/temp files no longer appear after cleanup.

---

### Task 4: Reduce default chat-session search scope to code-only paths

**Priority:** P1 - high operational impact

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/INDEX.md`

**Why fourth:** Even after data moves, this repo’s docs explicitly rely on broad search. The chat session needs a default rule: search code/docs first, never generated runtime trees unless explicitly debugging evidence.

**Step 1: Add default search exclusions to working rules**

Document that broad search must exclude:

```text
runtime_v2/sessions/
system/runtime_v2_probe/
tmp_*/
system/runtime_v2/logs/
```

unless the task is explicitly an evidence/probe investigation.

**Step 2: Add interrupt-safe default guidance**

Document that when lag/interruption is suspected, all search must begin with source-only scope (`runtime_v2/`, `tests/`, `docs/`) and exclude generated trees.

---

### Task 5: Shrink always-loaded doc surface and route archive/history more aggressively

**Priority:** P2 - medium impact

**Files:**
- Modify: `docs/INDEX.md`
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`
- Modify: `docs/archive/plans/*` as needed

**Why fifth:** `docs/` is small in bytes, but it is large in operational surface area. Many plans and completed-history entries increase grep/context overhead even when they are not the active canonical reference.

**Step 1: Move non-canonical historical plans further into archive**

Keep only active canonical plans in high-visibility indexes.

**Step 2: Shorten active TODO/COMPLETED entries**

Replace long multi-file prose bullets with one-line index-style references to detailed archived plans where possible.

**Step 3: Verification**

Read `docs/INDEX.md`, `docs/TODO.md`, and `docs/COMPLETED.md` to confirm they remain navigable and shorter.

---

### Task 6: Add a repository-local lag triage SOP

**Priority:** P2 - medium impact, high operational clarity

**Files:**
- Create: `docs/sop/SOP_chat_interruption_repo_triage.md`
- Modify: `docs/INDEX.md`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`

**Why sixth:** The repo already knows interruption is common, but the response is fragmented across TODO/SOP/plan files. One short SOP should centralize the check order.

**Step 1: Define triage order**

Include:
- workspace size check
- generated tree presence check
- dirty worktree check
- broad search ban
- interrupt-safe mode switch

**Step 2: Link it from `docs/INDEX.md` and guardrails**

Make the SOP discoverable so the same analysis does not need to be repeated every session.

---

### Task 7: Final verification and success criteria

**Priority:** P0 gate for completion

**Files:**
- Verify: `runtime_v2/config.py`
- Verify: `runtime_v2/browser/manager.py`
- Verify: `runtime_v2/cli.py`
- Verify: `runtime_v2_manager_gui.py`
- Verify: updated docs files

**Step 1: Run compile verification**

Run:

```bash
python -m py_compile runtime_v2/config.py runtime_v2/browser/manager.py runtime_v2/cli.py runtime_v2_manager_gui.py
```

**Step 2: Run path-focused targeted tests**

Run tests that cover runtime root/probe root/session path resolution.

**Step 3: Re-measure workspace hotspots**

Re-run the directory size measurement and confirm:
- `runtime_v2/` drops materially because session profiles moved out
- `system/` drops materially because probe outputs moved out
- root `tmp_*` and patch artifacts no longer pollute the repo

**Step 4: Success criteria**

The remediation is complete only when:
- browser session data is no longer stored under repo root by default
- probe/log/artifact growth is no longer under repo root by default
- interrupt-safe/source-only search rules are documented canonically
- temp/patch root clutter is controlled
- the repo root is primarily source/docs again, not runtime data

---

## Recommended execution order

1. Task 1 - externalize browser sessions
2. Task 2 - externalize probe/output roots
3. Task 3 - clean temp/patch clutter
4. Task 4 - restrict default search scope
5. Task 5 - shrink active doc surface
6. Task 6 - add lag triage SOP
7. Task 7 - verify and re-measure

## Why this order

- Tasks 1-2 attack the biggest measured byte volume and file-count sprawl first.
- Task 3 removes immediate workspace noise with low risk.
- Tasks 4-6 prevent the same slowdown pattern from reappearing at the process/document level.
- Task 7 proves the remediation changed the actual structure, not just the prose.

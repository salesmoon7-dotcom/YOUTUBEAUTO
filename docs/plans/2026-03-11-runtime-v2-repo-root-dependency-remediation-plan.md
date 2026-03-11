# Runtime_v2 Repo-Root Dependency Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`의 남아 있는 repo-root 의존을 `브라우저 세션`, `런타임 상태파일`, `아티팩트 경로`, `테스트 temp root`로 분해하고, 채팅 interruption 근원 완화 관점에서 무엇을 실제로 옮겨야 하는지 안전하게 정리합니다.

**Architecture:** 이 계획은 기존 `chat-safe execution remediation`의 후속 정밀화입니다. 핵심은 “브라우저 세션 외부화는 상당 부분 완료됐지만, 런타임 상태/아티팩트 기본 경로는 아직 repo-root 중심”이라는 정밀 판정을 코드·문서·검증에 반영하는 것입니다. 브라우저 health semantics나 control-plane owner model은 손대지 않고, 경로 기본값과 상태/아티팩트 의존만 분리합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, Windows filesystem, `RuntimeConfig`, worker runtime path resolution, detached verification artifacts, Markdown docs, `pytest`, `py_compile`, Oracle review

---

## Decision Record

- **Oracle verdict:** 기존 한 줄 결론은 `partially correct`입니다. repo-root 절대경로 의존은 남아 있지만, 브라우저 세션까지 repo-root에 실운영 의존한다고 단정하는 것은 과장입니다.
- **What is already improved:** `runtime_v2/config.py`의 `browser_session_root()`, `probe_runtime_root()`, `runtime_scratch_root()`는 외부 루트를 기본으로 사용합니다. `runtime_v2/browser/manager.py`는 legacy 세션 루트를 explicit opt-in일 때만 fallback 합니다.
- **What still remains:** `RuntimeConfig()` 기본 경로와 worker runtime/artifact 해석은 여전히 `system/runtime_v2/...`와 repo-root 기준 상대경로를 사용합니다. 또한 상태/헬스 파일에는 repo-root 절대경로(예: artifacts 경로)와 repo-root 상대경로(예: logs 경로)가 혼재해 저장됩니다.
- **Do not overcorrect:** browser health polling, browser ready semantics, control-plane owner, failure contract 이름/의미는 이번 계획 범위가 아닙니다.

---

### Task 1: Canonicalize The Mixed-State Diagnosis In Docs

**Files:**
- Modify: `docs/plans/2026-03-11-runtime-v2-chat-safe-execution-remediation-plan.md`
- Modify: `docs/sop/SOP_chat_interruption_repo_triage.md`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`

**Step 1: Replace the over-broad claim**

Update docs so they no longer imply:
- browser session runtime is still fully repo-root bound

Replace with the precise split:
- browser session/probe/scratch defaults are mostly externalized
- runtime state/evidence/artifact defaults still lean on repo-root

**Step 2: Add path-surface categories**

Document four categories explicitly:
- browser session root
- runtime state files
- worker artifact/output paths
- test temp roots

**Step 3: Verification**

Read back the updated docs and confirm they do not collapse all repo-root dependency into one bucket.

---

### Task 2: Externalize Runtime State Root Defaults

**Files:**
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/cli.py`
- Modify: `tests/test_runtime_v2_chat_safe_execution.py`

**Step 1: Add explicit external runtime-state root helper**

Introduce a helper for the default runtime state root, for example:

```python
def runtime_state_root() -> Path:
    ...
```

The default should resolve outside the repo root, parallel to external session/probe/scratch roots.

**Step 2: Move default `RuntimeConfig()` state/evidence paths to external state root**

Update the default `RuntimeConfig` fields so these no longer default under repo root:
- health files
- evidence files
- queue/state files
- artifact root
- inbox root
- logs root

`RuntimeConfig.from_root()` remains as the explicit opt-in for custom/probe roots.
Note: `artifact_root`의 canonical 기본값은 Task 2에서 정하고, Task 3는 worker가 이 canonical 값을 따르도록(repo-root fallback 제거) 정리합니다.

**Step 3: Keep runtime-root override semantics unchanged**

Do not break:
- `--runtime-root`
- `--probe-root`
- detached helper output contract

**Step 3.5: No implicit migration/cleanup**

Do not auto-migrate or delete existing `system/runtime_v2/*` state/artifacts/logs. This work changes defaults only; legacy locations remain usable only via explicit `--runtime-root` / `RuntimeConfig.from_root()`.

**Step 4: Write failing tests first**

Add tests that prove:
- default `RuntimeConfig()` no longer points into `D:\YOUTUBEAUTO\system\runtime_v2`
- explicit `from_root()` still works exactly as before

**Step 5: Verification**

Run:

```bash
python -m pytest tests/test_runtime_v2_chat_safe_execution.py -q
python -m py_compile runtime_v2/config.py runtime_v2/cli.py tests/test_runtime_v2_chat_safe_execution.py
```

Expected: PASS

---

### Task 3: Remove Repo-Root Bias From Worker Artifact Defaults

**Files:**
- Modify: `runtime_v2/workers/job_runtime.py`
- Modify: `runtime_v2/workers/external_process.py`
- Modify: `tests/test_runtime_v2_stage2_contracts.py`
- Modify or Create: focused worker path tests

**Task 3 guardrail**

- Do not start Task 3 by deleting `REPO_ROOT` checks first.
- First define one approved output root only.
- Recommended approved root: `RuntimeConfig.artifact_root` established in Task 2.
- If approved root is not explicit in function signatures and tests, Task 3 is not ready to implement.

**Step 1: Narrow what must stay repo-local**

Separate two concerns:
- security boundary for allowed local inputs
- default artifact/output destination

Do not keep repo-root artifact defaults just because local-input validation uses repo-root.

Also decide this explicitly before coding:
- `resolve_local_input()` remains an input-only boundary helper
- output validation gets its own approved-root contract

**Step 2: Move default artifact root off repo root**

Replace repo-root artifact fallback with the canonical `RuntimeConfig` artifact root established in Task 2 (no new parallel root).

Do not introduce a second canonical artifact root.

**Step 3: Preserve fail-closed output validation**

If output paths must stay inside an approved root, validate against the new canonical root instead of hardcoding repo root.

This step must preserve all of the following:
- outside-root output -> fail closed
- reserved device/output name -> fail closed
- missing output file -> fail closed
- unchanged reused output -> explicit reused code path only

**Step 4: Write failing tests first**

Add tests proving:
- default worker workspace no longer lands under `D:\YOUTUBEAUTO\system\runtime_v2\artifacts`
- output path verification still rejects disallowed/outside-root paths

Required first test split:
- `approved_root` 내부 output -> OK
- `approved_root` 외부 output -> `OUTPUT_OUTSIDE_ROOT`
- reserved output path -> `OUTPUT_PATH_INVALID`
- output 미생성 -> `OUTPUT_NOT_CREATED`

**Step 5: Verification**

Run targeted worker path tests and compile checks.

Minimum verification bundle:

```bash
python -m pytest tests/test_runtime_v2_stage2_contracts.py -q
python -m pytest tests/test_runtime_v2_gpu_workers.py -q
python -m py_compile runtime_v2/workers/job_runtime.py runtime_v2/workers/external_process.py
```

---

## Task 3 Safety Note

- Task 3 is intentionally split after Task 1+2 because it touches both workspace defaults and output security validation.
- The implementation is ready only after approved-root semantics are explicit in tests and function signatures.
- Until then, removing repo-root checks directly is forbidden because it risks fail-open behavior.

---

### Task 4: Reclassify Test Temp-Root Usage

**Files:**
- Modify: `docs/plans/2026-03-08-browser-session-stability-plan.md`
- Modify: `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`
- Optionally modify: selected tests that use `TemporaryDirectory(dir="D:\YOUTUBEAUTO")`

**Step 1: Separate test temp roots from runtime generated roots**

Document explicitly that many test cases still use `D:\YOUTUBEAUTO` as a temp parent for convenience, but that does not by itself mean live runtime state depends on repo root.

**Step 2: Tighten where meaningful**

Only change tests whose temp parent itself pollutes repo-root triage or changes path semantics materially.

Do not mass-edit temp roots just for cosmetic consistency.

**Step 3: Verification**

Run only the tests you changed.

---

### Task 5: Oracle Precision Gate

**Files:**
- Read only: all touched code/docs

**Step 1: Ask Oracle whether the mixed-state diagnosis is now accurate and stable**

Ask Oracle to confirm all of the following:
- browser sessions are no longer overstated as repo-root dependent
- runtime state/artifact defaults are correctly identified and reduced
- no unrelated browser/control-plane semantics were changed

**Step 2: Accept only minimal Oracle-directed edits**

If Oracle finds a gap, apply only the smallest correction needed.

---

### Task 6: Final Verification Bundle

**Files:**
- Verify only

**Step 1: Static verification**

Run `lsp_diagnostics` on touched files and compile checks for touched Python files.

**Step 2: Focused pytest**

Run only targeted tests for:
- new runtime-state root defaults
- worker artifact/output root behavior
- detached helper contract regression

**Step 3: Evidence verification**

Confirm at least one fresh detached/probe or runtime config artifact points outside repo root by default.

**Step 4: Success criteria**

This remediation is complete only when:
- docs no longer overstate browser-session repo-root dependency
- default `RuntimeConfig()` no longer uses repo-root `system/runtime_v2/*`
- default worker artifact/output paths no longer anchor to repo root unless explicitly configured
- detached/test helper contract still passes
- Oracle confirms the revised diagnosis is precise, not overstated

---

## Recommended Order

1. Task 1 - fix the diagnosis in docs
2. Task 2 - externalize runtime-state defaults
3. Task 3 - externalize worker artifact defaults
4. Task 4 - reclassify test temp-root usage
5. Task 5 - Oracle precision gate
6. Task 6 - final verification

## Why This Order

- Task 1 prevents the team from chasing the wrong root cause.
- Task 2 and Task 3 remove the biggest remaining repo-root defaults that still appear in live state/evidence.
- Task 4 avoids wasting effort on temp-root churn that is not actually the primary issue.
- Task 5 ensures the corrected diagnosis remains disciplined.

Plan complete and saved to `docs/plans/2026-03-11-runtime-v2-repo-root-dependency-remediation-plan.md`.

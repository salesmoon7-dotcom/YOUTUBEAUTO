# Runtime_v2 Remediation Priority Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the highest-risk runtime_v2 drift first so later functional verification and weekend soak testing rest on trustworthy signals.

**Architecture:** This plan follows the project guardrails: single writer, single failure contract, worker policy-free, fail-closed. The sequence is intentionally ordered so evidence truthfulness and failure visibility are repaired before any broader stabilization or documentation cleanup.

**Tech Stack:** Python, pytest, runtime_v2 CLI/control-plane/workers, JSON evidence artifacts, agent-browser/CDP integration.

---

## Scope Decision

- Included in this plan:
  1. GeminiGen truthful evidence blocker
  2. stage1 silent fallback paths
  3. CLI child exit/error semantics inconsistency
  4. latest-run single-writer drift
  5. documentation status drift
- Explicitly deferred from this plan:
  - `24h soak verification gap`
  - Reason: user requested this 3rd-priority operational validation to be tested separately on the weekend after the core signal/evidence fixes land.

## Priority Order

### Priority 1. GeminiGen truthful evidence blocker

**Why first:** If GeminiGen can still select a logo instead of a real generated asset, all downstream “success” evidence can be false-green. This blocks trustworthy validation of later fixes.

**Owner layer:** stage2 adapter/evidence selection boundary

**Files:**
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Modify: `runtime_v2/agent_browser/cdp_capture.py`
- Modify: `tests/test_runtime_v2_stage2_workers.py`
- Modify: `docs/plans/2026-03-10-non-gpt-functional-verification-plan.md`
- Modify: `docs/plans/2026-03-10-non-gpt-subprogram-detailed-analysis.md`

**Step 1: Write the failing test**

```python
def test_geminigen_evidence_rejects_logo_like_first_image():
    result = run_geminigen_job(...)
    assert result["status"] == "failed"
    assert result["error_code"] == "artifact_invalid"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k geminigen`
Expected: existing code accepts ambiguous first-image evidence or lacks explicit rejection.

**Step 3: Write minimal implementation**

- Add a truthful selection rule that rejects known non-artifact/logo candidates.
- Keep the worker fail-closed when the selected image cannot be proven to be the generated artifact.
- Do not allow `latest-run` pointer lookup to stand in for same-run proof; evidence must be bound to the current `run_id` or the worker must fail.
- Emit a canonical failure code instead of synthetic success evidence.

**Step 4: Run targeted verification**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k geminigen`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/stage2/geminigen_worker.py runtime_v2/agent_browser/cdp_capture.py tests/test_runtime_v2_stage2_workers.py docs/plans/2026-03-10-non-gpt-functional-verification-plan.md docs/plans/2026-03-10-non-gpt-subprogram-detailed-analysis.md
git commit -m "fix: fail closed on ambiguous GeminiGen evidence"
```

### Priority 2. Silent fallback + CLI child exit semantics hardening

**Why second:** Silent fallback and inconsistent child exit semantics are one hidden-green problem. Fixing only one side leaves “success-looking failure” paths behind.

**Owner layer:** stage1 parser/backend failure contract + CLI child boundary contract

**Files:**
- Modify: `runtime_v2/stage1/gpt_response_parser.py`
- Modify: `runtime_v2/stage1/chatgpt_backend.py`
- Modify: `runtime_v2/stage1/chatgpt_interaction.py`
- Modify: `runtime_v2/cli.py`
- Modify: `tests/test_runtime_v2_stage1_gpt_response_parser.py`
- Modify: `tests/test_runtime_v2_stage1_chatgpt.py`
- Modify: `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py`

**Step 1: Write the failing tests**

```python
def test_parser_reports_canonical_error_when_structured_parse_fails():
    payload, errors = parse_gpt_response_text(topic_spec, broken_response)
    assert payload is None
    assert "artifact_invalid" in errors

def test_backend_records_explicit_degraded_or_failed_reason_when_tab_selection_fails():
    result = run_chatgpt_interaction(...)
    assert result["error_code"] == "CHATGPT_BACKEND_UNAVAILABLE"

def test_adapter_child_returns_nonzero_canonical_exit_code_on_failure():
    exit_code = _run_qwen3_adapter_child(args)
    assert exit_code == exit_codes.CLI_USAGE
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_runtime_v2_stage1_gpt_response_parser.py -q`
Run: `python -m pytest tests/test_runtime_v2_stage1_chatgpt.py -q -k fail_closed`
Run: `python -m pytest tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py -q -k "adapter_child"`
Expected: current code silently falls through to heuristic/fallback behavior.

**Step 3: Write minimal implementation**

- Replace silent `pass`-style parser/backend fallthrough with explicit canonical error/degraded signaling.
- If fallback remains necessary, surface the fallback mode and reason in evidence instead of hiding it.
- Preserve fail-closed behavior for real-live mode.
- Replace raw child helper exit values with canonical `exit_codes.*` mappings.
- Freeze a single failure-contract rule for this trench:
  - child/helper failure => non-zero exit
  - failure reason => canonical `error_code`
  - no success without evidence bound to the active run

**Step 4: Run targeted verification**

Run: `python -m pytest tests/test_runtime_v2_stage1_gpt_response_parser.py -q`
Run: `python -m pytest tests/test_runtime_v2_stage1_chatgpt.py -q -k fail_closed`
Run: `python -m pytest tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py -q -k "adapter_child"`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/stage1/gpt_response_parser.py runtime_v2/stage1/chatgpt_backend.py runtime_v2/stage1/chatgpt_interaction.py runtime_v2/cli.py tests/test_runtime_v2_stage1_gpt_response_parser.py tests/test_runtime_v2_stage1_chatgpt.py tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py
git commit -m "fix: harden fail-closed fallback and child exit contracts"
```

### Priority 3. latest-run single-writer drift

**Why third:** This stays immediately after Priority 2 unless Priority 1 or 2 still read shared latest pointers. If they do, pull this into the same trench before merging. The rule is simple: no repair may validate against another run's evidence.

**Owner layer:** latest-run writer / control-plane evidence ownership

**Files:**
- Modify: `runtime_v2/latest_run.py`
- Modify: `runtime_v2/cli.py`
- Modify: `tests/test_runtime_v2_latest_run.py`
- Modify: `tests/test_runtime_v2_phase2.py`

**Step 1: Write the failing tests**

```python
def test_cli_runtime_snapshot_does_not_overwrite_global_latest_payload_without_pointer_ownership():
    write_cli_runtime_snapshot(...)
    joined = load_joined_latest_run(config, completed=True)
    assert joined["out_of_sync"] is False

def test_control_plane_remains_single_owner_of_latest_completed_pointer():
    ...
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py -q`
Run: `python -m pytest tests/test_runtime_v2_phase2.py -q -k latest`
Expected: current CLI path writes shared payload files without owning the latest pointers.

**Step 3: Write minimal implementation**

- Either move CLI snapshots to isolated probe/runtime-specific outputs, or promote them through the single control-plane owner path only.
- Eliminate any path where shared latest payloads change without the matching pointer owner decision.
- If Priority 1/2 still read latest pointers, change them to same-run `run_id` evidence lookup first.

**Step 4: Run targeted verification**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py -q`
Run: `python -m pytest tests/test_runtime_v2_phase2.py -q -k latest`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/latest_run.py runtime_v2/cli.py tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_phase2.py
git commit -m "fix: restore single-writer ownership for latest-run"
```

### Priority 4. documentation status drift

**Why last:** Documentation should be aligned after the core runtime/evidence/failure signals stop moving. Doing it earlier causes churn and stale plan text.

**Owner layer:** canonical docs and plan status language

**Files:**
- Modify: `docs/plans/2026-03-10-runtime-v2-subprogram-integration-execution-plan.md`
- Modify: `docs/plans/2026-03-10-non-gpt-functional-verification-plan.md`
- Modify: `docs/plans/2026-03-10-non-gpt-subprogram-detailed-analysis.md`
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`

**Step 1: Write the failing documentation checklist**

```text
- GPT real-first gate wording matches actual downstream state
- non-GPT completion wording does not overstate exploratory evidence
- GeminiGen blocker is reflected consistently
- deferred weekend soak is explicitly marked as pending
```

**Step 2: Run plan/doc comparison**

Run: `python -c "from pathlib import Path; ..."`
Expected: mismatched terms like complete / partial / exploratory remain across docs.

**Step 3: Write minimal implementation**

- Normalize status wording (`Implemented`, `Contract-verified`, `Functionally-verified`, `Deferred`).
- Mark weekend `24h soak` as deferred operational gate, not missing implementation work.
- Ensure no document implies full non-GPT completion before truthful evidence exists.

**Step 4: Run documentation verification**

Run: `python -c "from pathlib import Path; ..."`
Expected: all targeted docs use the same status language.

**Step 5: Commit**

```bash
git add docs/plans/2026-03-10-runtime-v2-subprogram-integration-execution-plan.md docs/plans/2026-03-10-non-gpt-functional-verification-plan.md docs/plans/2026-03-10-non-gpt-subprogram-detailed-analysis.md docs/TODO.md docs/COMPLETED.md
git commit -m "docs: align runtime_v2 remediation status language"
```

## Deferred Weekend Gate

### Deferred. 24h soak verification gap

**Status:** intentionally excluded from this plan by user request.

**When to run:** after Priorities 1-4 are merged and verified.

**Pre-weekend minimum gate:**
- run a 30~60 minute short soak before merge/release
- require repeated same-run evidence stability across multiple passes
- do not treat this as equivalent to 24h readiness

**Weekend verification bundle:**
- detached soak runner
- long-running browser recovery observation
- GPU duplicate-run gate verification
- latest-run/evidence drift regression under repeated passes

**Do not do before weekend soak:**
- do not claim operational 24h readiness
- do not treat repeated short pytest success as soak equivalence

## Recommended Execution Sequence

1. GeminiGen truthful evidence blocker
2. silent fallback + CLI child exit semantics hardening
3. latest-run single-writer drift
4. documentation status drift
6. deferred weekend: 24h soak verification gap

## Verification Bundle Per Priority

- Static: `lsp_diagnostics` on all modified Python files
- Compile: `python -m py_compile ...` on modified Python files
- Tests: targeted pytest per priority only
- Guardrail gate:
  - `run_id` meaning unchanged
  - `error_code` naming aligned
  - `attempt/backoff` untouched unless explicitly in scope
- Final session verification before claiming completion:
  - `verification-before-completion`
  - `verify-implementation`

## Notes for Execution Session

- Use `systematic-debugging` immediately if any targeted pytest fails for a reason other than the expected RED phase.
- Use `requesting-code-review` after Priority 4 because that is the first high-blast-radius architectural correction.
- Use `webapp-testing` only if GeminiGen truthfulness or agent-browser evidence selection requires real browser confirmation.

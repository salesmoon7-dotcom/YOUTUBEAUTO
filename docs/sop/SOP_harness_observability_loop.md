# SOP: Harness Observability Feedback Loop

## Purpose
- This document describes the intended harness observability loop and related evidence model.
- In the current workspace, treat it as a reference/target-state SOP until the referenced files and automation paths are verified again.
- Ensure every significant change has machine-readable evidence.
- Keep before/after runtime state inspectable by agents.

## Current Workspace Status
- Note: the `current checkout` annotations in this document record observed status for this checkout only; they do not change policy or requirements.
- The paths below are not the current workspace source of truth unless they are re-verified in this checkout.
- If a referenced file/path is missing, do not assume the harness guardrail is active; record it as unverified and fall back to the runtime evidence that actually exists.
- Some referenced files or procedures may be target-state references that are absent in this checkout or not yet re-verified in this environment.
- Existence and alignment of those references should be checked per checkout/environment rather than assumed from this document alone.
- For current `runtime_v2` execution evidence, prefer:
  - `system/runtime_v2/health/*.json`
  - `system/runtime_v2/evidence/*.json*`
  - `system/runtime_v2_probe/**`
  - `docs/TODO.md`
  - `docs/COMPLETED.md`

## Official Basis
- Anthropic Memory docs: `https://code.claude.com/docs/en/memory`
  - CLAUDE.md is loaded each session; keep always-loaded memory concise and modularize with rules/docs.
- OpenAI AGENTS guide: `https://developers.openai.com/codex/guides/agents-md/`
  - Layered instruction discovery and size limits; split large guidance into structured files.
- OpenAI Harness Engineering: `https://openai.com/ko-KR/index/harness-engineering/`
  - AGENTS.md as map/table-of-contents, docs as system of record, mechanical enforcement + recurring garbage collection.

## Target-State Evidence Files
- [@status: current-checkout] `system/reports/*`: in this checkout, these report paths are unverified, and current `runtime_v2` evidence may instead be recorded under `system/runtime_v2/*` and `system/runtime_v2_probe/*` (additional confirmation may be needed).
- `system/reports/harness_gc_report.json`
- `system/reports/harness_gc_report.md`
- `system/reports/harness_evidence_snapshot.json`
- `system/reports/harness_evidence_snapshot.md`

## Target-State Standard Commands
- [@status: current-checkout] `scripts/harness_*.py`: command availability and alignment with this checkout are unverified.
```bash
python scripts/harness_gc_audit.py --ci
python scripts/harness_collect_evidence.py --tag manual
python scripts/harness_dual_control_gate.py --max-age-minutes 180
python scripts/harness_skill_source_gate.py
```

## Target-State Warning Gate Policy
- [@status: current-checkout] `system/config/harness_policy.json`: presence and alignment with this checkout are unverified.
- Policy file: `system/config/harness_policy.json`
- `fail_on_warnings: true` means CI fails when actionable warnings exist.
- Temporary exceptions must be declared in `allowed_warning_codes` and removed after cleanup.

### Ops Safety Policy (2026-02-27)
- `ops_safety.require_explicit_destructive_approval: true`
  - intent에 `allow_destructive=true`가 없는 상태에서 파괴 명령 토큰 감지 시 `DESTRUCTIVE_COMMAND_BLOCKED`로 fail 처리.
- `ops_safety.require_question_only_mode: true`
  - intent가 `question_only=true`인데 실행 command가 기록되면 `QUESTION_ONLY_EXECUTION`로 fail 처리.
- `ops_safety.require_scope_bound_execution: true`
  - result의 `scopes`가 intent `allowed_scopes`를 벗어나면 `SCOPE_BOUNDARY_VIOLATION`로 fail 처리.

## Target-State CI Integration
- [@status: current-checkout] `.github/workflows/harness-guardrails.yml`: presence and alignment with this checkout are unverified.
- Workflow: `.github/workflows/harness-guardrails.yml`
- CI runs GC audit, collects evidence snapshot, then executes dual-control gate.
- `system/reports/` is uploaded as artifact for traceability.

## Target-State Dual-control Rule
- Independent evidence sources must both pass:
  - `harness_gc_report.json` (quality gate)
  - `harness_evidence_snapshot.json` (observability snapshot)
- `scripts/harness_dual_control_gate.py` fails CI when:
  - errors/warnings/actionable_warnings are non-zero
  - reports are missing or stale
  - evidence snapshot does not confirm GC report existence

## Historical/External Source References
- The references in this section are not verified as active in the current workspace.
- If these paths are restored or intentionally reintroduced, reclassify this SOP from reference mode to active mode and add fresh command evidence.

## Incident Handling
1. Re-run evidence collection with `--tag incident`.
2. Attach generated snapshot files to incident analysis.
3. Compare latest snapshot with previous run to identify drift.

## Done Criteria
- Evidence snapshot exists for the run.
- GC report exists and errors are zero.
- Actionable warnings are zero (or explicitly allowlisted with rationale).
- Dual-control gate returns PASS.
- Skill source gate returns PASS.
- Artifacts are retrievable from CI.
- Ops Safety checks return PASS (`DESTRUCTIVE_COMMAND_BLOCKED`, `QUESTION_ONLY_EXECUTION`, `SCOPE_BOUNDARY_VIOLATION` 미발생).

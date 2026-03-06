# SOP: Harness Observability Feedback Loop

## Purpose
- Ensure every significant change has machine-readable evidence.
- Keep before/after runtime state inspectable by agents.

## Official Basis
- Anthropic Memory docs: `https://code.claude.com/docs/en/memory`
  - CLAUDE.md is loaded each session; keep always-loaded memory concise and modularize with rules/docs.
- OpenAI AGENTS guide: `https://developers.openai.com/codex/guides/agents-md/`
  - Layered instruction discovery and size limits; split large guidance into structured files.
- OpenAI Harness Engineering: `https://openai.com/ko-KR/index/harness-engineering/`
  - AGENTS.md as map/table-of-contents, docs as system of record, mechanical enforcement + recurring garbage collection.

## Required Evidence Files
- `system/reports/harness_gc_report.json`
- `system/reports/harness_gc_report.md`
- `system/reports/harness_evidence_snapshot.json`
- `system/reports/harness_evidence_snapshot.md`

## Standard Commands
```bash
python scripts/harness_gc_audit.py --ci
python scripts/harness_collect_evidence.py --tag manual
python scripts/harness_dual_control_gate.py --max-age-minutes 180
python scripts/harness_skill_source_gate.py
```

## Warning Gate Policy
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

## CI Integration
- Workflow: `.github/workflows/harness-guardrails.yml`
- CI runs GC audit, collects evidence snapshot, then executes dual-control gate.
- `system/reports/` is uploaded as artifact for traceability.

## Dual-control Rule
- Independent evidence sources must both pass:
  - `harness_gc_report.json` (quality gate)
  - `harness_evidence_snapshot.json` (observability snapshot)
- `scripts/harness_dual_control_gate.py` fails CI when:
  - errors/warnings/actionable_warnings are non-zero
  - reports are missing or stale
  - evidence snapshot does not confirm GC report existence

## Vendor/Kimoring Source Application Rule
- Plan source of truth: `vendor/cc-feature-implementer/SKILL.md`
- Verification source of truth: `kimoring-ai-skills/.claude/skills/verify-implementation/SKILL.md`
- Maintenance source of truth: `kimoring-ai-skills/.claude/skills/manage-skills/SKILL.md`
- Active runtime path: `.claude/skills/...`
- `scripts/harness_skill_source_gate.py` enforces source->active hash equality.

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

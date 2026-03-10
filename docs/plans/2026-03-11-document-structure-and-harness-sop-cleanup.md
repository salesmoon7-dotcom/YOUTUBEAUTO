# Document Structure And Harness SOP Cleanup

## Goal
- Reduce documentation drift around top-level routing, skill-loading guidance, and the harness observability SOP without changing runtime policy.

## Scope
- Clarify the role split between `AGENTS.md`, `CLAUDE.md`, and `docs/INDEX.md`.
- Clarify the boundary between skill auto-loading guidance and closed-loop skill bundle guidance.
- Mark `docs/sop/SOP_harness_observability_loop.md` as a target-state/reference SOP for the current checkout and add checkout-status annotations for unverified paths.
- Clarify that `docs/sop/SOP_runtime_v2_development_guardrails.md` functions as a runtime_v2 harness/contract guardrail document, not just a generic development note.

## Files Updated
- `AGENTS.md`
- `docs/INDEX.md`
- `docs/sop/SOP_harness_observability_loop.md`
- `docs/sop/SOP_runtime_v2_development_guardrails.md`
- `docs/sop/SOP_skill_auto_loading.md`
- `docs/sop/SOP_closed_loop_automation_skill_map.md`

## What Changed
- Top-level routing now reads more cleanly:
  - `AGENTS.md` stays a short router.
  - `CLAUDE.md` stays the minimal universal rule map.
  - `docs/INDEX.md` is explicitly the canonical docs navigation entrypoint.
- `docs/sop/SOP_runtime_v2_development_guardrails.md` now states that its real role is to fix runtime_v2 harness/contract invariants.
- `docs/sop/SOP_skill_auto_loading.md` now frames itself as an intent-based auto-loading routing guide.
- `docs/sop/SOP_closed_loop_automation_skill_map.md` now frames itself as a closed-loop bundle map, not the source of intent routing.
- `docs/sop/SOP_harness_observability_loop.md` now:
  - declares itself target-state/reference for this checkout,
  - tells readers to prefer current `runtime_v2` evidence paths,
  - marks `system/reports/*`, `scripts/harness_*.py`, `system/config/harness_policy.json`, and `.github/workflows/harness-guardrails.yml` as current-checkout annotations only,
  - avoids implying deletion, mandatory recovery, or policy change.

## Evidence Basis
- Current runtime evidence repeatedly referenced across canonical docs:
  - `system/runtime_v2/health/*.json`
  - `system/runtime_v2/evidence/*.json*`
  - `system/runtime_v2_probe/**`
  - `docs/TODO.md`
  - `docs/COMPLETED.md`
- Missing harness-reference paths were only directly observed inside `docs/sop/SOP_harness_observability_loop.md` during this cleanup.

## Validation
- Re-read updated documents after each edit.
- Ran LSP diagnostics on:
  - `AGENTS.md`
  - `docs/INDEX.md`
  - `docs/sop/SOP_harness_observability_loop.md`
  - `docs/sop/SOP_runtime_v2_development_guardrails.md`
  - `docs/sop/SOP_skill_auto_loading.md`
  - `docs/sop/SOP_closed_loop_automation_skill_map.md`
- Result: no diagnostics found.

## Outcome
- The repo now distinguishes more clearly between:
  - router docs vs canonical docs index,
  - intent routing vs closed-loop skill bundles,
  - active runtime evidence vs target-state harness references.
- This cleanup intentionally stops short of restoring missing harness scripts/workflows/policy files because current-checkout evidence does not prove they are critical runtime dependencies.

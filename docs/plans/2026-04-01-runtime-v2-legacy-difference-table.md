# Runtime V2 Legacy Difference Table - 2026-04-01

## Purpose

- Satisfy the active closeout retest deliverable for an updated legacy difference table.
- Reduce the larger parity audit into the differences that still matter for the current closeout cycle.
- Separate already-corrected drift from still-open legacy gaps.

## Source Documents

- `docs/plans/2026-03-14-runtime-v2-legacy-parity-audit.md`
- `docs/plans/2026-03-15-runtime-v2-closeout-postmortem-report-v2.md`
- `docs/plans/2026-03-15-runtime-v2-closeout-retest-plan-v2.md`

## Status Legend

| Status | Meaning |
|---|---|
| `CORRECTED` | Previously drifted, now corrected in the current workspace and retained as the current contract. |
| `OPEN` | Still differs from legacy or still lacks pinned proof, so it remains part of the active blocker surface. |
| `ACCEPTED-DIFF` | Implementation differs from legacy, but the current cycle accepts the difference because the observable contract is pinned and evidence-backed. |

## Updated Difference Table

| Area | Legacy expectation | Current runtime_v2 state | Status | Current reading |
|---|---|---|---|---|
| `genspark` prompt text | original request prompt only | browser-side prompt strengthening was removed; current path preserves the original prompt | `CORRECTED` | keep as pass-through only |
| `genspark` ref attach path | pinned UI-specific attach path must succeed before generation | runtime still fail-closes on attach failure, but a fully pinned legacy attach path is not yet proven | `OPEN` | remains a real browser-contract gap |
| `genspark` result tab/card handling | stable legacy capture target | runtime required multiple corrective passes around compose/result/one-tab selection | `OPEN` | recent drift was reduced, but legacy parity is not declared complete |
| `seaart` browser family/profile proof | direct one-to-one legacy browser/profile evidence | prompt/generate/upload contract is aligned, but exact browser/profile parity remains unproven | `OPEN` | contract-verified, not full parity-verified |
| `canva` thumbnail interaction flow | duplicate page -> edit -> download -> cleanup on the intended page | low-page duplicate-page flow and truthful thumbnail export are restored | `CORRECTED` | current closeout cycle treats Canva as functionally recovered |
| `geminigen` first/last frame attach | slot-based image-reference upload before generation | explicit `First Image` / `Last Image` upload actions are emitted in adapter path | `CORRECTED` | attach contract restored at the request/action layer |
| `geminigen` live login/session proof | claim tested state only with current visible evidence | contract fields and attach actions exist, but live login/session proof is still not final | `OPEN` | do not over-claim tested state |
| `qwen3_tts -> rvc` timing | later-stage only after required upstream artifacts are ready | worker-side qwen3->rvc emission is explicit opt-in only | `CORRECTED` | immediate emission is no longer default |
| `rvc` output naming | legacy FLAC export should stay canonical when configured | canonical next-job path now preserves `.flac` for legacy FLAC mode | `CORRECTED` | downstream `.wav` remains compatibility lookup only |
| fallback policy | remove workaround branches once legacy contract is re-pinned | several emergency fallbacks were removed, but some defensive logic remains documented | `OPEN` | follow-up removal table still required |

## What This Table Means Now

- The current cycle does not treat all legacy parity gaps as equally urgent.
- `CORRECTED` items are no longer the next implementation target unless fresh evidence reopens them.
- `OPEN` items are still eligible blocker surfaces, but only one may move next under the simplification-first rule.
- `ACCEPTED-DIFF` is reserved for evidence-backed non-legacy behavior that the current cycle explicitly keeps; none are pinned yet in this table.

## Current Constraint

- This table does not authorize a broad closeout rerun by itself.
- The remaining `OPEN` items must still respect `prompt -> attach -> routing -> order -> closeout` gating from `docs/plans/2026-04-01-runtime-v2-corrected-pipeline-flow.md`.

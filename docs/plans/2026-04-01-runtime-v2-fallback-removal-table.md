# Runtime V2 Fallback Removal Table - 2026-04-01

## Purpose

- Satisfy the active closeout retest deliverable for an updated fallback removal table.
- Record which fallbacks were already removed, which remain temporarily, and what exact trigger allows later removal.
- Prevent undocumented convenience fallbacks from re-entering the current cycle.

## Source Documents

- `docs/plans/2026-03-15-runtime-v2-closeout-retest-plan-v2.md`
- `docs/plans/2026-03-15-runtime-v2-closeout-postmortem-report-v2.md`
- `docs/plans/2026-04-01-runtime-v2-corrected-pipeline-flow.md`

## Status Legend

| Status | Meaning |
|---|---|
| `REMOVED` | Removed from the current default path and should stay out. |
| `RETAINED-TEMP` | Still present, but only as a documented temporary guard tied to a specific upstream contract gap. |
| `DO-NOT-ADD` | Not currently present and explicitly forbidden to reintroduce without pinned legacy evidence. |

## Updated Fallback Removal Table

| Fallback / heuristic | Current status | Why it existed | Why current cycle treats it this way | Explicit expiry / removal trigger |
|---|---|---|---|---|
| `genspark` arbitrary follow-up prompt submit loop in `runtime_v2/cli.py` | `REMOVED` | tried to keep generation moving when service entered question/confirmation states | browser-side semantic strengthening drifted from legacy prompt integrity | keep out unless exact legacy source proves a non-`예` follow-up contract |
| `genspark` regenerate probe / capture retry loop in `runtime_v2/cli.py` | `REMOVED` | tried to recover from unstable result-tab/capture timing | added complexity before pinning legacy interaction order | keep out unless legacy interaction order explicitly requires regenerate |
| `genspark` ref-upload warning-continue branch in `runtime_v2/cli.py` | `REMOVED` | softened attach failure to let the chain continue | fail-open attach behavior had no pinned legacy basis | keep fail-closed unless legacy evidence proves generation without confirmed attach |
| `stage1` cached-target fallback in `runtime_v2/stage1/chatgpt_backend.py` | `REMOVED` | attempted to preserve progress when live target resolution drifted | current cycle now treats target resolution failure as the truthful blocker instead of reusing stale tab state | removed after direct target/session contract was pinned enough to fail closed on `CDP_TARGET_NOT_FOUND` |
| `stage1` `response_not_started` retry in `runtime_v2/stage1/chatgpt_interaction.py` | `REMOVED` | attempted to recover from empty/non-started streaming states | current cycle now records `response_not_started` as evidence but exposes the Stage 1 blocker directly instead of relaunching the browser | removed after Stage 1 target/session contract was pinned enough to fail-close on missing response start |
| `genspark` fresh-result-tab preference logic in `runtime_v2/agent_browser/cdp_capture.py` | `RETAINED-TEMP` | narrowed capture to the newest plausible `agents?id=` result tab while caller/service contract remained broad | caller-side capture now fail-closes when no concrete genspark result tab can be proven, but the capture layer still retains service-specific tab bias until that caller contract is the only path exercised | remove only after caller-side capture is pinned to a single verified `agents?id=` result URL and no compose/stale-tab fallback remains reachable |
| placeholder/probe-style stage2 success scaffolding | `REMOVED` | made browser-stage probes writable even when full service success was absent | current cycle now records explicit failed attach evidence for unsupported/non-truthful stage2 browser paths and forbids placeholder artifacts from being treated as success | removed after stage2 adapter child was changed to fail close with evidence instead of writing placeholder success artifacts |
| any new browser-side semantic strengthening for `genspark` / `seaart` | `DO-NOT-ADD` | historical temptation during unstable attach/generation states | violates legacy-first prompt contract unless directly proven | only revisit with exact legacy source and matching evidence |

## Current Rule

- No hidden fallback remains acceptable.
- Every retained fallback must name the exact upstream contract change that makes removal possible.
- A fallback may not remain merely because it keeps the chain moving.
- If a fallback cannot explain its removal trigger, it is not allowed to stay.

## Current Reading

- The current cycle has already removed the most harmful `genspark` fail-open and semantic-strengthening branches.
- The still-retained fallbacks are now concentrated in `genspark` capture selection, where the caller/capture contract is not yet reduced to a single generic path.
- This table does not authorize new code changes by itself; it defines which fallback classes are already prohibited and which remaining ones still require future removal work.

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
| `stage1` cached-target fallback in `runtime_v2/stage1/chatgpt_backend.py` | `RETAINED-TEMP` | attempted to preserve progress when live target resolution drifted | still documented as defensive logic, not parity proof | remove only after direct legacy-equivalent target/session contract is pinned and proven stable |
| `stage1` `response_not_started` retry in `runtime_v2/stage1/chatgpt_interaction.py` | `RETAINED-TEMP` | attempted to recover from empty/non-started streaming states | empty-response retry remains a defensive stabilizer, not a legacy-pinned rule | remove only after Stage 1 browser contract is simple enough that a single fail-close reproduces the real blocker |
| `genspark` fresh-result-tab preference logic in `runtime_v2/agent_browser/cdp_capture.py` | `RETAINED-TEMP` | narrowed capture to the newest plausible `agents?id=` result tab while caller/service contract remained broad | Oracle already judged removal unsafe before caller/service contract is narrowed enough | remove only after attach/result-tab contract is pinned so capture no longer needs service-specific tab bias |
| placeholder/probe-style stage2 success scaffolding | `RETAINED-TEMP` | made browser-stage probes writable even when full service success was absent | current cycle still needs explicit fail-close evidence files, but they must never count as semantic success | remove when all stage2 browser paths emit truthful success/failure artifacts without probe-style placeholder handling |
| any new browser-side semantic strengthening for `genspark` / `seaart` | `DO-NOT-ADD` | historical temptation during unstable attach/generation states | violates legacy-first prompt contract unless directly proven | only revisit with exact legacy source and matching evidence |

## Current Rule

- No hidden fallback remains acceptable.
- Every retained fallback must name the exact upstream contract change that makes removal possible.
- A fallback may not remain merely because it keeps the chain moving.
- If a fallback cannot explain its removal trigger, it is not allowed to stay.

## Current Reading

- The current cycle has already removed the most harmful `genspark` fail-open and semantic-strengthening branches.
- The still-retained fallbacks are concentrated in `stage1` and `genspark` capture selection, where the upstream browser contract is not yet pinned tightly enough.
- This table does not authorize new code changes by itself; it defines which fallback classes are already prohibited and which remaining ones still require future removal work.

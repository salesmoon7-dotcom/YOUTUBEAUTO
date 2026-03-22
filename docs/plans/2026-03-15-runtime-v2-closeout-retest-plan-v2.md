# Runtime V2 Closeout Retest Plan v2

## Goal

Re-test `runtime_v2` from a legacy-first baseline, explicitly preventing the same drift described in the v2 postmortem.

This plan is not a broad retry plan.
It is a contract-repinning and shortest-path validation plan.

## Scope

This retest plan covers all disputed boundaries raised in the second postmortem:
- prompt integrity
- ref-image attachment method
- 11-category workload assignment vs actual routed execution
- RVC ordering relative to GeminiGen/KenBurns/render
- fallback reduction
- semantic-row closeout evidence

---

## What Changes From The Previous Test Approach

The previous approach drifted because it repeatedly used long closeout reruns to discover the next blocker while legacy interaction contracts were still not pinned.

This v2 plan changes that by enforcing:
- legacy interaction contract confirmation first
- fallback removal/review before rerun
- one failing boundary at a time
- no architecture explanation from blocker order
- explicit compliance with existing handoff/plan guidance before new local judgment

## Execution Discipline Gates

These rules are mandatory and exist specifically to prevent a repeat of the previous 5-hour drift cycle.

### Gate 1. No full closeout rerun before service contract pinning

- If `attach` is not pinned, do not run semantic-row full closeout.
- If `GeminiGen` login/attach/first-frame contract is not pinned, do not run semantic-row full closeout.
- If `RVC` source-mode/order is not pinned, do not run semantic-row full closeout.

In short:
- service contract first
- full closeout last

### Definition of `pinned`

A service contract is **not** considered pinned by description alone.

`Pinned` requires all of the following:
- exact target UI/page identified
- exact input/attach/submit/capture sequence written down
- fail-close condition written down
- one reproducible verification command or procedure
- one evidence artifact proving the currently observed runtime behavior

Without all five, the contract is still unpinned.

### Gate 2. No undocumented fallback additions

- No fallback, heuristic, fail-open branch, or retry policy may be added unless the plan/doc first records:
  - what legacy contract failed,
  - why legacy behavior was insufficient,
  - why the new logic is temporary or contract-justified.

If that note does not exist first, the fallback must not be added.

Fallback documentation must also include:
- expiry/removal condition
- why the legacy path could not be used as-is
- whether the fallback is allowed only for debug/probe or also for production path

No fallback is allowed to become de facto permanent by omission.

### Gate 2A. No test-only logic in the production path

- Do not add probe/debug/test-only logic that changes the normal runtime decision path.
- If a change affects actual runtime behavior, treat it as production logic and require legacy justification.
- Debug helpers may collect evidence, but they must not become hidden prerequisites for success.

### Gate 3. Strict execution order

The implementation and validation order must be fixed as:

1. prompt integrity
2. attach contract
3. routing / assignment correctness
4. ordering (`RVC` / `GeminiGen` / `KenBurns` / `render`)
5. one full closeout run

No later step may be validated while an earlier step is still drifting.

Additional rule:
- production path correction comes before any test convenience logic.
- tests may verify the production path, but they must not redefine it.

### Gate 4. Evidence grade separation

The following are different states and must never be merged in reports or status claims:

- probe green
- attach available
- login confirmed
- service generation passed
- final closeout passed

All future reports and validation notes must preserve this separation.

### Gate 5. Batch execution only

Remaining remediation work must be executed in large coherent batches, not tiny symptom-by-symptom edits.

The remaining implementation is locked into these batches:

- Batch A: legacy attach restoration (`genspark` / `seaart` / `geminigen` UI contracts)
- Batch B: `RVC` / `GeminiGen` / later-stage ordering alignment

Do not split these into repeated single-symptom reruns.

Clarification:
- implementation may be batched,
- but validation and rerun decisions must still be boundary-specific,
- meaning one failing boundary at a time for execution evidence.

### Gate 5A. Minimum-unit-test preservation

- `minimum-unit-test` means: prove at least one truthful artifact per subprogram before treating the semantic row as the validation unit.
- do not let `semantic row full closeout` become the first practical test surface for `qwen3_tts`, `genspark`, `seaart`, `canva`, or `geminigen`.
- if a worker currently materializes as a large batch-style job (for example `qwen3_tts` consuming the full `voice_texts` bundle), that worker must be treated as an unresolved service-boundary blocker before another semantic-row rerun is allowed.
- if gate A (`genspark` / `seaart`) still fails before one truthful scene artifact is proven, stop there; do not spend more hours inside later semantic-row reruns waiting for downstream gates.

### Gate 6. New-session continuation guard

If this work is resumed in a new session, that session must not start implementation immediately.

Before touching code or running a long retest, the new session must first restate and verify:
- which batch is currently active (`attach` or `RVC/GeminiGen/order`)
- which gates are already satisfied
- which gates are still unresolved
- what exact command/evidence ended the previous session
- what single boundary is allowed to move next

If any of the above is missing, the new session must stop and rebuild context first.

### Gate 7. Session-start checklist

Every resumed session must complete this checklist before implementation:

1. read this plan and the v2 postmortem
2. identify the active batch
3. list unresolved gates in `prompt -> attach -> routing -> order -> closeout`
4. identify the last trusted evidence artifact
5. confirm that the next action is boundary-scoped, not broad rerun

If the next action is a broad rerun while any earlier gate is unresolved, the session must not proceed.

---

## Phase 1. Prompt / Request Contract Re-pin

### Acceptance criteria
- `genspark` browser prompt equals the original request prompt only
- no browser-side semantic strengthening text is present
- any structured prompt transformations for other workloads are documented as contract fields, not hidden free-text additions
- all subprograms are classified as pass-through / structural-transform / semantic-injection
- if Genspark requires confirmation, only the legacy-style minimal confirmation path is allowed; no arbitrary follow-up prompt semantics may be added

### Checks
- `runtime_v2/cli.py` review for `genspark`
- `runtime_v2/stage1/chatgpt_runner.py` review for system prompt builder
- `runtime_v2/stage2/request_builders.py` review for prompt-file emission
- targeted tests around `genspark` prompt actions

### Required evidence
- targeted pytest pass
- direct code diff proving removal of unauthorized Genspark text
- one runtime-side artifact capturing the final prompt actually sent to the browser or adapter request contract

---

## Phase 2. Legacy Browser Interaction Re-pin Per Service

### Genspark
- confirm exact legacy target page semantics
- confirm actual legacy ref attach method (user correction: drag-and-drop path must be rechecked and pinned)
- confirm exact result-tab/result-card capture contract
- current workspace note: fail-close is enforced, but service-specific attach restoration is still incomplete

### SeaArt
- confirm legacy prompt input target and generate sequence
- confirm ref attach ordering and actual upload method

### GeminiGen
- confirm legacy login/session contract before claiming tested state
- confirm browser-step equivalence before any pass claim
- current workspace note: explicit `First Image` / `Last Image` upload actions are now generated in the browser adapter path, but live login/session proof is still required before final pass claims

### Acceptance criteria
- each browser service has a pinned legacy interaction checklist before another long closeout rerun
- attach method is not inferred from current runtime generic code when legacy used a more specific UI contract

### Required evidence per service
- one runtime artifact proving target page/tab
- one runtime artifact proving actual attach/input action path
- one runtime artifact proving capture/result target
- explicit fail-close rule if any of the above is unavailable
- current workspace proof point for `geminigen`: adapter child emits explicit `First Image` / `Last Image` upload actions from `first_frame_path`

---

## Phase 3. Flow Re-pin Before Execution

### Acceptance criteria
- flow explanation is derived from the legacy/runtime contract graph, not from recent blocker order
- RVC timing is re-pinned against legacy source and documented before the next broad E2E explanation
- the doc explicitly distinguishes designed flow from observed blocker order
- worker-side qwen3->rvc emission is disabled by default unless an explicit legacy-justified opt-in is present

### Required actions
- compare `qwen3_tts`, `rvc`, `geminigen`, `kenburns`, and `render` ordering against legacy source
- correct any doc/table that still describes flow from observed failure sequence

### Required evidence
- one canonical flow document/table chosen as SSOT
- one runtime timeline artifact or queue trace proving actual execution order for the tested case
- routing summary that distinguishes:
  - mapping-table correctness
  - actual queued workload correctness
  - actual browser/service execution correctness

---

## Phase 4. Fallback Reduction Pass

### Immediate targets
- `runtime_v2/cli.py` genspark follow-up / regenerate / capture retry policy (removed from current default path; keep out)
- `runtime_v2/cli.py` genspark ref-upload warning-continue branch (removed from current default path; keep fail-closed)
- `runtime_v2/stage1/chatgpt_backend.py` cached-target fallback
- `runtime_v2/stage1/chatgpt_interaction.py` empty-response retry (removed; keep out unless legacy evidence justifies restoration)
- `runtime_v2/agent_browser/cdp_capture.py` genspark fresh-tab preference logic (retain until caller/service contract is narrowed enough to remove it safely)

### Acceptance criteria
- every remaining fallback is either removed or explicitly justified by pinned legacy evidence
- no hidden fallback remains undocumented
- no fail-open path remains justified only by convenience or chain-continuation pressure
- no fallback may remain without an explicit expiry/removal trigger
- if a fallback is retained temporarily, the plan must say what upstream caller/contract change will make removal possible

---

## Phase 5. Retest Execution Order

1. readiness only
2. one service-boundary retest for the corrected failing contract
3. only after service contracts are pinned, one semantic-row closeout run

### Phase 5A. Corrected minimum-unit execution order

The previous week drifted because this order was not followed in practice.

The corrected order is:

1. readiness only
2. one service-boundary retest for the current failing service contract
3. prove one truthful artifact for each required subprogram boundary in this order:
   - `chatgpt`
   - `qwen3_tts`
   - `genspark`
   - `seaart`
   - `canva`
   - `geminigen`
4. only after the above proofs exist, one semantic-row closeout run

Clarifications:
- `qwen3_tts` must not be re-used as a multi-hour “whole row voice batch” during minimum-unit verification. If the current contract still does that, that contract itself is the blocker and must be fixed before more semantic-row reruns.
- gate A failure during minimum-unit verification must not be interpreted as proof that semantic-row closeout was meaningfully exercised.
- if one subprogram cannot produce a first truthful artifact in the documented time slice, stop and debug that service only.

### Phase 5B. Canva-only follow-up boundary

Current boundary conclusion:
- `canva` is no longer blocked primarily by upload/download button mismatches.
- the remaining dominant blocker is `template semantics`, currently observed as `clone_ok=false` even when other helper steps proceed.

Therefore the next batch is narrowed to one question only:
- can the runtime reliably duplicate/select the intended Canva thumbnail page before editing/export?

Rules for the next batch:
- no semantic-row rerun
- no multi-service rerun
- no new browser-plane work unless Canva evidence directly proves the browser plane regressed again
- stop once `clone_ok` is either proven true with a truthful thumbnail artifact or replaced by a more precise single blocker

### Time limits and stop conditions

These limits exist to prevent another uncontrolled multi-hour rerun.

- readiness check: stop if not resolved within 10 minutes
- single service-boundary retest: stop if no decisive evidence within 10 minutes
- semantic-row full closeout run: do not start until service-boundary blockers are closed; once started, each monitored boundary must still be judged in 10-minute slices rather than left to run unattended for hours
- if a worker keeps consuming hours before producing its first truthful artifact, that worker is not “in progress”; it is the unresolved service-boundary blocker.

Immediate reassessment triggers:
- attach path unavailable
- login state unproven
- probe/result evidence missing or contradictory
- fallback pressure appears before legacy contract is pinned
- any boundary execution exceeding 10 minutes without a decisive artifact or blocker classification

### semantic-row execution rule
- `python -m runtime_v2.cli --readiness-check`
- if `ready=true`, perform exactly one semantic-row detached/isolated run
- completion is only recognized when the new `probe_root` contains:
  - `probe_result.json`, and
  - either success artifact (`render_final.mp4`) or fail-closed artifact (`failure_summary.json`)

### Hard rules
- no broad Stage 5 / Stage 5B rerun while browser contract is still not pinned
- no new fallback before legacy interaction evidence is written down
- no success claim for GeminiGen/login/browser state without current visible evidence
- no user-stop override, hidden rerun, or background continuation after explicit stop
- no plan drift by local judgment when the plan already explains the failure pattern
- no full closeout run while any earlier gate in `prompt -> attach -> routing -> order` is unresolved
- no semantic-row rerun may be used as a substitute for the missing “one artifact per subprogram” proof
- no claim that "mapping is correct" may stand in for proof that actual runtime routing/execution is correct
- no resumed session may skip the session-start checklist
- no test-only or probe-only helper may be used to "make the test pass" in place of fixing the real service/runtime contract

---

## Deliverables

1. updated legacy difference table
2. updated fallback removal table
3. corrected pipeline flow document
4. one closeout retest result interpreted only by current evidence
5. per-subprogram prompt handling classification table

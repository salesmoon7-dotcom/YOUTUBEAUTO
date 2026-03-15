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

---

## Phase 2. Legacy Browser Interaction Re-pin Per Service

### Genspark
- confirm exact legacy target page semantics
- confirm actual legacy ref attach method (user correction: drag-and-drop path must be rechecked and pinned)
- confirm exact result-tab/result-card capture contract

### SeaArt
- confirm legacy prompt input target and generate sequence
- confirm ref attach ordering and actual upload method

### GeminiGen
- confirm legacy login/session contract before claiming tested state
- confirm browser-step equivalence before any pass claim

### Acceptance criteria
- each browser service has a pinned legacy interaction checklist before another long closeout rerun
- attach method is not inferred from current runtime generic code when legacy used a more specific UI contract

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

---

## Phase 4. Fallback Reduction Pass

### Immediate targets
- `runtime_v2/cli.py` genspark follow-up / regenerate / capture retry policy (removed from current default path; keep out)
- `runtime_v2/cli.py` genspark ref-upload warning-continue branch (removed from current default path; keep fail-closed)
- `runtime_v2/stage1/chatgpt_backend.py` cached-target fallback
- `runtime_v2/stage1/chatgpt_interaction.py` empty-response retry
- `runtime_v2/agent_browser/cdp_capture.py` genspark fresh-tab preference logic

### Acceptance criteria
- every remaining fallback is either removed or explicitly justified by pinned legacy evidence
- no hidden fallback remains undocumented
- no fail-open path remains justified only by convenience or chain-continuation pressure

---

## Phase 5. Retest Execution Order

1. readiness only
2. one service-boundary retest for the corrected failing contract
3. only after service contracts are pinned, one semantic-row closeout run

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

---

## Deliverables

1. updated legacy difference table
2. updated fallback removal table
3. corrected pipeline flow document
4. one closeout retest result interpreted only by current evidence
5. per-subprogram prompt handling classification table

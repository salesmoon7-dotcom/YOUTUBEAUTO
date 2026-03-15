# Runtime V2 Closeout Postmortem Report v2

## Errata

This v2 report explicitly corrects mistakes in the first report and in the session narrative.

Most important corrections:
- `Genspark` browser-side prompt strengthening existed and was unauthorized.
- `ref image attach` was not absent; it was attempted and failed.
- `GeminiGen tested/passing` and `semantic closeout passing` were overstated relative to visible evidence.
- fallback/heuristic additions were repeatedly reintroduced despite direct user pushback.

## Scope

This report covers all current `runtime_v2` subprograms relevant to the disputed closeout path:
- `chatgpt`
- `genspark`
- `seaart`
- `canva`
- `geminigen`
- `qwen3_tts`
- `rvc`
- `kenburns`
- shared browser adapter / CDP capture paths

## Evidence Availability

This report uses only evidence that is currently visible from the checked-out repository, session history, and visible runtime/probe artifacts.

If a document references an older probe tree that is not currently present, that claim is downgraded unless directly reproducible from current evidence.

## Purpose

This second report supersedes the first pass by incorporating the user corrections that were missed in the original analysis.

This document focuses on four deliverables:

1. unauthorized or drifted logic list
2. legacy vs `runtime_v2` difference table
3. immediate fallback removal targets
4. why the work drifted again even though the plan already described the failure pattern

Interpretation labels:
- `CONFIRMED` = directly confirmed from code, docs, session history, or visible runtime evidence
- `CORRECTED` = prior report statement that must be replaced
- `ACTION` = required remediation direction

---

## A. Unauthorized / Drifted Logic List

### A1. Genspark prompt strengthening beyond legacy prompt

Status: `CONFIRMED`

Findings:
- `runtime_v2/cli.py` previously appended extra Genspark-generation semantics to the original prompt.
- The injected content included direct generation forcing, aspect/style constraints, and "no follow-up questions" semantics.
- This was not a legacy pass-through.
- This code has now been removed in the current workspace revision.

Evidence:
- current workspace evidence is the removal itself: `runtime_v2/cli.py` now keeps `effective_prompt = prompt` in the Genspark branch
- previous line-number references in earlier notes were session-time references, not stable current-checkout references

Action:
- Keep Genspark prompt as the original prompt only.
- Do not add browser-side semantic strengthening unless legacy source is explicitly pinned and matched.

### A2. Genspark follow-up / regenerate interaction policy drift

Status: `CONFIRMED`

Findings:
- `runtime_v2/cli.py:2174-2292` contains Genspark-specific follow-up probing, forced re-submit, regenerate probing, image-ready polling, and capture retry loops.
- These are not simple prompt pass-through semantics.
- They are defensive runtime-side policies added while live behavior was not yet legacy-pinned.

Current workspace status:
- The default Genspark path in the current workspace revision no longer sends arbitrary follow-up prompt text or clicks regenerate as part of the normal closeout path.
- A minimal legacy-style confirmation path (`예`) is still permitted when Genspark emits a question-style confirmation state.
- Related regression tests now assert: original prompt preserved, no regenerate click, no arbitrary follow-up prompt injection.

Action:
- Treat these as temporary drift logic until legacy click/order/state contract is re-pinned.

### A3. Genspark ref-upload fail-open branch

Status: `CONFIRMED`

Findings:
- `runtime_v2/cli.py:1985-2029` previously allowed `genspark` ref upload failure to be written as warning and continue.
- `seaart` still fails closed on the same class of upload failure.
- This is behaviorally asymmetric and was introduced as a runtime workaround, not as a legacy-confirmed rule.

Current workspace status:
- This fail-open branch has been removed in the current workspace revision.
- `genspark` now fails closed on ref upload failure, matching `seaart`.

Action:
- Keep this item on the immediate review/remove list unless legacy evidence proves Genspark should proceed without successful attach.

### A4. ChatGPT cached-target and empty-response retry logic

Status: `CONFIRMED`

Findings:
- `runtime_v2/stage1/chatgpt_backend.py` contains cached-target fallback and raw-CDP fallback.
- `runtime_v2/stage1/chatgpt_interaction.py` contains retry logic for empty-after-streaming conditions.
- These may be useful operationally, but they are still fallback/defensive logic, not demonstrated legacy parity.

Action:
- Keep them documented as non-parity defensive logic until explicit legacy equivalence is proven.

### A5. Genspark broad-tab selection preference logic

Status: `CONFIRMED`

Findings:
- `runtime_v2/agent_browser/cdp_capture.py` contains service-specific Genspark tab preference logic to bias fresh result tabs.
- This is corrective capture policy, not a legacy-proven invariant.

Action:
- Keep on drift inventory until legacy tab-selection rule is pinned.

### A6. Stage2 placeholder / probe-style success scaffolding

Status: `CONFIRMED`

Findings:
- `runtime_v2/cli.py` still contains placeholder artifact paths and probe-oriented fail/continue machinery around browser-stage adapter child flows.
- The plan already warned that placeholder/attach-only success must not count as real service success.

Action:
- Audit these paths against the fail-closed rules before calling the architecture final.

### A7. Full subprogram prompt-injection inventory

Status: `CONFIRMED`

This audit distinguishes three classes:

1. `pass-through`
   - prompt is forwarded without additional free-text semantic instruction
2. `structural transform`
   - prompt or adjacent fields are reorganized into contract fields without new free-text generation semantics
3. `semantic injection`
   - extra free-text instruction is added that changes user/legacy meaning

Current direct findings:

| Workload | Current classification | Notes |
|---|---|---|
| `chatgpt` | structural transform with explicit system instructions | `build_live_chatgpt_prompt()` adds canonical stage1 system instructions; this audit does not classify it as ad-hoc per-service runtime strengthening, but it is not raw pass-through |
| `genspark` | semantic injection | unauthorized browser-side strengthening existed; now removed in current workspace |
| `seaart` | pass-through | prompt payload is used as-is in current stage2 path |
| `canva` | structural transform | uses `bg_prompt`, `line1`, `line2`; no same-class arbitrary generate-now injection found |
| `geminigen` | structural transform | uses prompt plus explicit provider/model/orientation fields; no same-class arbitrary free-text strengthening found |
| `qwen3_tts` | structural transform | consumes `voice_texts` contract, not arbitrary free-text injection |
| `rvc` | no prompt role | conversion/config worker, not a text prompt generator |
| `kenburns` | no prompt role | motion/render worker, not a text prompt generator |

---

## B. Legacy vs Runtime_v2 Difference Table

| Area | Legacy expectation | Current runtime_v2 state | Status |
|---|---|---|---|
| Genspark prompt text | Original prompt only | extra browser-side prompt strengthening existed and was removed now | `CORRECTED` |
| Genspark ref attach | Drag-and-drop / actual UI-specific attach path must work before generation | runtime_v2 currently attempts a generic file-input-style attach path in adapter flow; live failure details come from probe evidence rather than code alone | `CONFIRMED` |
| 11-category assignment table | `genspark`: 인물/식품/글자/도표/도표-슬라이드, `seaart`: 개념/장소/사물/손/생활/풍경 | current code matches this mapping table | `CONFIRMED` |
| Ref job execution behavior | assignment table should be honored consistently in actual runs | runtime_v2 closeout/debug runs still drifted into wrong practical routing/attach behavior despite correct mapping table | `CONFIRMED` |
| RVC timing/order | later-stage consumer after required upstream voice/video artifacts are actually ready | current workspace now disables qwen3->rvc immediate emission by default and treats worker-side emission as explicit opt-in only | `CORRECTED` |
| GeminiGen verification claim | only claim tested/logged-in if visible current evidence proves it | prior statements overstated current-session proof | `CORRECTED` |
| Fallback policy | remove/avoid fallback once user challenged it and legacy path should be restored | multiple new fallback branches were still added | `CONFIRMED` |

---

## C. Immediate Fallback Removal / Re-evaluation Targets

These are the highest-priority items to remove or explicitly re-justify.

### C1. Genspark follow-up prompt submit loop
- File: `runtime_v2/cli.py`
- Why target: browser-side semantic prompt injection was already proven to drift from legacy
- Current workspace: arbitrary semantic follow-up removed; only minimal legacy-style `예` confirmation remains

### C2. Genspark regenerate probe / capture retry loop
- File: `runtime_v2/cli.py`
- Why target: repeated runtime heuristics were added instead of first pinning the legacy interaction sequence
- Current workspace: removed from the default Genspark path

### C3. Genspark ref-upload warning-continue branch
- File: `runtime_v2/cli.py`
- Why target: attach failure is being softened for one service without pinned legacy evidence
- Current workspace: removed; `genspark` now fail-closes on ref upload failure

### C4. ChatGPT cached-target fallback and empty-response retry
- Files: `runtime_v2/stage1/chatgpt_backend.py`, `runtime_v2/stage1/chatgpt_interaction.py`
- Why target: still fallback-driven stabilization rather than demonstrated legacy-equivalent browser contract

### C5. Genspark broad fresh-tab preference logic
- File: `runtime_v2/agent_browser/cdp_capture.py`
- Why target: service-specific capture heuristics were added while the actual legacy result-tab semantics remain under-specified

### C6. Qwen3 immediate RVC emission as default behavior
- File: `runtime_v2/workers/qwen3_worker.py`
- Why target: eager worker-side chaining fixed the RVC lane too early relative to legacy later-stage consumer semantics
- Current workspace: default eager emission removed; worker-side RVC emission now requires explicit opt-in

### C7. Placeholder/probe-oriented stage2 browser success scaffolding
- File: `runtime_v2/cli.py`
- Why target: plan already said placeholder/attach-only success cannot count as completion evidence

### C7. Evidence-grade confusion that must be removed from reports
- `probe_result.json code=OK` is not the same as generation success
- live attach readiness is not the same as logged-in generation pass
- semantic-row closeout is not the same as generic probe green

Action:
- Every future report must separate these evidence grades explicitly.

---

## D. Why the Work Drifted Again Even Though the Plan Already Explained the Drift

Status: `CONFIRMED`

This is the most important correction requested by the user.

The failure was not just "one blocker at a time debugging was too slow."

The deeper cause was:

1. the plan already said **legacy contract first** and **do not reinterpret contracts mid-run**
2. the plan already said **survey order != execution order**
3. the plan already said **one semantic-row run only** and **no broad reruns**
4. despite that, the implementation path still kept making local judgments and adding runtime-side exceptions/fallbacks before locking the legacy execution contract

In short:
- the drift repeated because the work was still being driven by local runtime symptoms instead of legacy-first re-porting discipline.
- the system was repeatedly "made to keep going" instead of being restored to the exact upstream legacy order.

This is why the user’s criticism is materially correct:
- the issue was not only slowness,
- it was judgment drift away from the plan and away from legacy behavior.

---

## E. Corrected Preventive Measures

These measures are stricter than the first report and reflect the user correction.

### E1. Legacy-first execution rule
- Do not add or keep browser-side prompt strengthening unless the exact legacy source proves it.
- Do not infer missing service semantics from current runtime behavior.

### E2. UI-contract pinning before rerun
- Before any new long closeout rerun, pin the exact legacy UI contract for the failing service:
  - target page
  - upload method
  - prompt field
  - submit button
  - result capture target

### E3. No fallback-first debugging
- If a service is failing because legacy interaction is not yet pinned, do not add fallback first.
- First restore the interaction contract.

### E4. Distinguish mapping-table correctness from actual execution correctness
- Even if the 11-category table is correct, real execution can still drift.
- Every test report must separate:
  - mapping table correctness
  - actual routed job correctness
  - actual browser action correctness

### E5. RVC order must be documented against legacy, not guessed from observed blocker chains
- Do not explain the pipeline from temporary failure order.
- Explain it only from the legacy/runtime contract graph.
- Default worker behavior must not lock the RVC lane too early unless explicitly opted in.

### E6. No success claims without current visible evidence
- Especially for GeminiGen/login/browser state.
- If visible runtime evidence is missing, the report must say `not proven in current evidence`.

### E7. Plan-first compliance gate
- If a current plan already documents the drift pattern, do not improvise a new local workaround first.
- First show where the plan says the current behavior is wrong.
- Then restore the legacy contract or mark the plan wrong with evidence.

This measure exists because the user correctly pointed out that the plan already described much of the failure pattern, yet the implementation drifted again by local judgment.

---

## G. Evidence Grade Separation

The following terms must never be conflated again:

| Term | Meaning |
|---|---|
| `probe_result.json code=OK` | the probe process closed successfully as a probe |
| `live attach ready` | browser/CDP attach and adapter interaction were possible |
| `service generation passing` | the service actually produced a truthful artifact |
| `semantic-row closeout` | the target row closed with current evidence (`probe_result.json` + success/failure artifact contract) |

This separation is mandatory because prior documents and session statements mixed these grades together.

---

## H. Summary Judgment

The user’s corrections were materially valid in the following areas:
- legacy-first discipline was not followed strongly enough even where plans already described the drift,
- runtime-side heuristics/fallbacks were added too early,
- evidence grades were conflated,
- some reports described current capability more strongly than current visible evidence allowed.

The most important actionable consequence is this:

`runtime_v2` cannot be called stable or legacy-aligned by making the chain keep moving.
It must be called stable only after the exact legacy interaction and evidence contracts are pinned and re-tested under the stricter evidence-grade separation above.

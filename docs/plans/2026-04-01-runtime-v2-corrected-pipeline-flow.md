# Runtime V2 Corrected Pipeline Flow - 2026-04-01

## Purpose

- Lock one canonical flow document for the current `runtime_v2` closeout-retest cycle.
- Distinguish designed execution order from observed blocker order.
- Keep future sessions from treating recent failure sequence as the intended pipeline.

## Canonical Sources

- Active execution index: `docs/TODO.md`
- Active closeout gate plan: `docs/plans/2026-03-15-runtime-v2-closeout-retest-plan-v2.md`
- This document: corrected pipeline flow SSOT for `prompt -> attach -> routing -> order -> closeout`

## Corrected Flow

| Stage | Contract question | Designed order | Proof grade expected before moving on |
|---|---|---|---|
| `prompt` | Is the emitted request truthful to the current row contract? | `stage1 -> parsed_payload -> stage1_handoff -> video_plan` | request/payload artifact |
| `attach` | Does each browser service use the pinned legacy-style target page/input path? | boundary-scoped per service | attach evidence or fail-close artifact |
| `routing` | Are stage2 workloads derived from the current `video_plan` and local asset graph only? | `json_builders -> control_plane queue` | queue/job contract evidence |
| `order` | Are later-stage consumers queued only after required upstream artifacts are ready? | `genspark/seaart -> canva/geminigen -> qwen3/rvc/kenburns -> render` by gate, not by recent failure order | queue trace / canonical job ids |
| `closeout` | Can one semantic-row run be judged from current evidence only? | exactly one run after earlier gates are pinned | `probe_result.json` plus success or fail-close artifact |

## What This Flow Explicitly Means

- `survey order != execution order`
- `recent blocker order != designed runtime order`
- `service existence != truthful artifact proof`
- `mapping-table correctness != queue correctness != real browser/service execution correctness`

## Current Ordering Contract

| Boundary | Current contract |
|---|---|
| `qwen3_tts -> rvc` | worker-side emission is explicit opt-in only; not a default proof surface |
| `rvc source priority` | `gemi-video-source` outranks `tts-source` for the same run |
| `rvc canonical output path` | preserve worker-provided canonical suffix: `.flac` when legacy export format is FLAC, `.wav` otherwise |
| `kenburns` | later-stage GPU consumer; not evidence that earlier browser gates were truthful |
| `render` | terminal closeout stage only after upstream artifact contracts are already pinned |

## Current Gate Interpretation

- `prompt` unresolved means no boundary/service rerun should be treated as meaningful progress.
- `attach` unresolved means only the failing service boundary may move next.
- `routing` unresolved means queue or payload drift must be fixed before another semantic-row explanation.
- `order` unresolved means later-stage timing/source-mode/canonical path drift must be fixed before closeout.
- `closeout` is allowed only after `prompt`, `attach`, `routing`, and `order` are all pinned for the current target path.

## Current Session-End Reading

- Browser-plane drift for `genspark` result-tab path was narrowed and corrected.
- `RVC` later-stage ordering drift was narrowed and corrected, including canonical suffix preservation.
- The next broad runtime action is still **not** a generic rerun.
- If a future session resumes execution, it must first restate which single boundary is still unresolved before touching runtime execution.

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
| `genspark` ref attach path | pinned UI-specific attach path must succeed before generation | source path now targets `textarea.j-search-input`, creates hidden `runtime-v2-genspark-file-input-N` inputs, calls `set_input_files`, dispatches `DataTransfer` `dragenter`/`dragover`/`drop`, avoids filechooser/`button.upload-button`, and fail-closes upload/Playwright errors as `NO_FILE_INPUT`; covered by commit `2f3cea44b7fd34b1f12036efadf7a7f7c988209a` | `SOURCE-CONTRACT-MATCHED` | source/test-level parity only; live browser closeout evidence was not exercised in chat |
| `genspark` result tab/card handling | stable legacy capture target | result-tab drift is now pinned to latest/exact `agents?id=` capture and fails closed with `GENSPARK_RESULT_TAB_UNPINNED` when the result URL is unproven | `CORRECTED` | keep exact-result capture tests as the guard against stale compose/result-tab drift |
| `seaart` browser family/profile proof | direct one-to-one legacy browser/profile evidence | source fallback now resolves SeaArt to `browser_family=chrome`, `port=9225`, and `profile=C:/chrome_seaart`, covered by `test_checked_in_seaart_session_matches_legacy_chrome_contract` in commit `0f844423373fa9140b4ef1aefa38b457785692bd` | `CORRECTED` | source/test-level parity only; live browser relaunch was not exercised in chat |
| `canva` Product Background flow | duplicate page -> edit -> Product Background -> upload/prompt/generate on the intended page | duplicate-page routing, page2 skip, asset-manifest ref fallback, OOPIF diagnostics, and upload-attempt evidence are restored, but fresh latest evidence still closes at `CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED` | `OPEN` | current blocker is the live Canva OOPIF credit purchase gate, not a settled legacy-equivalent success path |
| `geminigen` first/last frame attach | slot-based image-reference upload before generation | explicit `First Image` / `Last Image` upload actions are emitted in adapter path | `CORRECTED` | attach contract restored at the request/action layer |
| `geminigen` live login/session proof | claim tested state only with current visible evidence | hidden legacy `repair_session` replay, reboot-safe browser recover, bounded page-context fetch fallback, and failed-asset render pruning remained in place, and fresh logged-in proof `D:\YOUTUBEAUTO_RUNTIME\probe\geminigen-login-proof-20260519-a\probe_result.json` now closes as `OK` with live GeminiGen output | `CORRECTED` | active migration range may now treat GeminiGen as evidence-backed |
| `qwen3_tts -> rvc` timing | later-stage only after required upstream artifacts are ready | worker-side qwen3->rvc emission is explicit opt-in only | `CORRECTED` | immediate emission is no longer default |
| `rvc` output naming | legacy FLAC export should stay canonical when configured | canonical next-job path now preserves `.flac` for legacy FLAC mode | `CORRECTED` | downstream `.wav` remains compatibility lookup only |
| fallback policy | remove workaround branches once legacy contract is re-pinned | the removal table is now present, harmful fallback classes are marked removed/do-not-add, and stage2 probe placeholder fallback success is fail-closed by `22d1a54` | `CORRECTED` | keep the removal table as the active guard against reintroducing fallback OK paths |

## What This Table Means Now

- The current cycle does not treat all legacy parity gaps as equally urgent.
- `CORRECTED` items are no longer the next implementation target unless fresh evidence reopens them.
- `OPEN` items are still eligible blocker surfaces, but only one may move next under the simplification-first rule.
- `ACCEPTED-DIFF` is reserved for evidence-backed non-legacy behavior that the current cycle explicitly keeps; none are pinned yet in this table.

## Current Constraint

- This table does not authorize a broad closeout rerun by itself.
- The remaining `OPEN` items must still respect `prompt -> attach -> routing -> order -> closeout` gating from `docs/plans/2026-04-01-runtime-v2-corrected-pipeline-flow.md`.

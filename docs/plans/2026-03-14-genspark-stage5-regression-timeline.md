# Genspark Stage5 Regression Timeline

## Purpose

This note records where the current `Stage 5` Genspark live blocker came from, using git history and fresh runtime evidence.

The goal is to avoid repeating a full day of broad re-testing by preserving the exact wrong assumptions and the fixes already applied.

## Bottom line

The current blocker did **not** start from the recent retry/instrumentation commits.

The earliest meaningful faulty assumption starts at `d41570c` (`fix: drive stage2 browser prompts through agent-browser`).
That commit introduced a single-pass Genspark model:

- fill prompt once
- click generate once
- poll for an image
- capture immediately

That assumption was too optimistic for real Genspark live behavior.

Later commits widened or sharpened the same model, but did not create the original mismatch:

- `4561aa3` unified target selection around Genspark page contracts
- `23c25cd` preferred `agents?id=` result tabs during action-time reselection
- `0a246ef` corrected initial compose-tab selection and newer result-tab capture preference
- `5fdae73`, `ba970a0`, `a4f6adb` added prompt hardening, diagnostics, and retries around the same boundary

## Git-based timeline

### 1. Initial simplifying assumption

Commit: `d41570c`
Message: `fix: drive stage2 browser prompts through agent-browser`

What changed:

- first introduced Genspark-specific stage2 browser actions in `runtime_v2/cli.py`
- prompt fill + generate click became the assumed complete interaction model
- `capture_primary_image_asset()` started to rely on limited Genspark image selectors
- after attach, the child treated successful prompt/click plus image-ready polling as enough to capture a truthful artifact

Why this matters:

- this is where the automation started assuming Genspark behaves like a simple image generator
- real live behavior later proved more complex: stale result tabs, interrupted requests, clarification replies, delayed result cards, and non-top-level image placement

### 2. Target contract unification without deeper live-state handling

Commit: `4561aa3`
Message: `feat: centralize genspark browser targets`

What changed:

- unified Genspark URL/title contract in `runtime_v2/browser/manager.py`
- `runtime_v2/stage2/agent_browser_adapter.py` and `runtime_v2/agent_browser/cdp_capture.py` began sharing that source of truth

Why this matters:

- this made the system more consistent, but still assumed the target contract alone was enough
- it did not solve the difference between compose tab vs. fresh result tab vs. stale result tab

### 3. Explicit stale result-tab preference during action reselection

Commit: `23c25cd`
Message: `feat: preserve agent browser action compatibility`

What changed:

- `runtime_v2/workers/agent_browser_worker.py` introduced `_prefer_service_specific_tab()`
- for `genspark`, it preferred any `https://www.genspark.ai/agents?id=` tab after steps like `clicked_generate`

Why this mattered:

- in live runs with stale tabs already open, action flow could jump into an old result tab
- this was a concrete later misstep, but not the original assumption

### 4. Today’s fixes already applied

These commits are corrective, not the origin of the problem:

- `e642453` `fix: ignore idle runtime health blockers`
- `ecdd134` `fix: remove qwen adapter workspace-root drift`
- `5292b24` `fix: default real row stage2 services to agent browser`
- `0a246ef` `fix: align genspark tab and capture selection`
- `5fdae73` `fix: harden stage5 genspark adapter flow`
- `ba970a0` `feat: record genspark adapter failure state`
- `a4f6adb` `fix: retry genspark adapter recovery actions`

These narrowed the blocker from broad Stage5 failure to a single Genspark live interaction boundary.

## What today proved

Fresh current-session rows now reliably reach:

- `chatgpt`
- `qwen3_tts`
- `rvc`
- `genspark_adapter`

The remaining blocker is no longer preflight, routing, or stale latest-run drift.

Fresh failure-time `adapter_debug_state.json` now proves:

- compose-tab attach is correct
- fresh result-tab selection is correct
- current failure still happens inside the fresh result tab
- the page body can remain in `요청이 중단되었습니다` / `Thinking...` / agent-like state
- at least some live pages later expose a real `generated-images` card and a valid `/api/files/...` image URL
- manual `write_functional_evidence_bundle(...)` on a fresh live page can succeed even while the automated child path fails

## Wrong assumptions to avoid repeating

1. **“Genspark opens a new tab by itself.”**
   - Not proven as a service invariant.
   - What we actually observed is that the browser session often contains both a compose tab and one or more result tabs, and our automation must choose correctly.

2. **“If prompt fill + click generate succeeded, image capture is next.”**
   - False in live runs.
   - Real Genspark can move through interrupted/tool-usage/clarification states first.

3. **“Top-level `document.images` is enough to find the final image.”**
   - False in several runs.
   - Result cards may exist while top-level images only show icons/tracking pixels.

4. **“One retry dimension is enough.”**
   - False.
   - Prompt semantics, tab selection, CTA clicking, and image capture timing all turned out to be separate axes.

## Current state after today

The problem is now localized to the last live Genspark interaction boundary.

Specifically:

- the fresh result tab is selected correctly
- the current page state is instrumented to `adapter_debug_state.json`
- recovery prompts / regenerate CTAs are partially attempted
- the remaining question is **which exact CTA / state transition must be driven so the fresh result tab settles into a stable generated-image state before child fail-close**

## Recommended next step

Do not restart from broad Stage5 testing.

Use the current instrumentation-first approach:

1. run one fresh row only
2. inspect `attach_evidence.json` and `adapter_debug_state.json`
3. make one minimal Genspark interaction-policy change
4. rerun one fresh row

The evidence now supports narrow iteration rather than large exploratory retries.

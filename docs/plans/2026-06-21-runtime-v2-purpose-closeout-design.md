# Runtime V2 Purpose Closeout Design

## Purpose

`runtime_v2` is not a rewrite for its own sake. It exists because the legacy automation surface made it too easy to lose the answer to three questions:

1. Which Excel row is running?
2. Which exact boundary failed?
3. Which evidence proves the answer?

The development target is therefore not "make every script look ported". The target is a user-visible Excel-driven run where every boundary is tied to one `run_id`, and where a failure stops at the first unproven boundary with a machine-readable reason.

## Design Decision

Future closeout work must prioritize fresh execution evidence over historical artifact interpretation.

The accepted `Sheet1!row15` run remains valid as historical row15-only evidence, but the next development loop must prove the product is currently runnable by creating a new run and joining the evidence chain from Excel seed through terminal render or fail-closed blocker.

## Required Evidence Shape

Every new closeout attempt must produce one of these outcomes:

- `CURRENT_RUN_ACCEPTED`: one new `run_id` has Excel seed evidence, Stage1 artifacts, Stage2 worker artifacts, and terminal render success.
- `CURRENT_RUN_BLOCKED`: one new `run_id` stops at the first failed boundary and records `status`, `error_code`, `attempt/backoff`, and boundary artifact paths.

Anything else is not a development-purpose result.

## Boundary Order

The run advances only in this order:

1. Excel seed
2. GPT browser attach/capture
3. Stage1 artifacts
4. Stage2 routing queue
5. `qwen3_tts`
6. `genspark`
7. `seaart`
8. `geminigen`
9. `rvc`
10. `kenburns`
11. `render`

`Canva` remains an external hold while `CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED` is the truthful blocker. It must not be used to block the non-Canva purpose gate unless credit/session availability changes.

## Non-Goals

- Do not claim all rows are complete from one row.
- Do not claim browser reliability from source-level tests.
- Do not claim Excel sync-back unless `excel_sync_updated=true` and the workbook state is verified.
- Do not add fallback or fail-open logic to make a boundary look green.
- Do not continue downstream after a boundary lacks decisive evidence.

## Completion Meaning

The updated plan succeeds only when it can answer, with fresh evidence:

- what ran,
- which row it ran for,
- which run_id owns the evidence,
- which boundary succeeded or failed,
- and whether the result is terminal success or a truthful blocker.

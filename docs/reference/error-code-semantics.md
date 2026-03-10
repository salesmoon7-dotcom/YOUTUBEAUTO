# Error Code Semantics

## Scope

This document defines the meaning of the following runtime_v2 fields only:

- `error_code`
- `worker_error_code`
- `raw_error_code`
- `warning_worker_error_code_mismatch`

Other result fields and service-specific error taxonomies are out of scope.

## Field Definitions

- `error_code`
  - The runtime/result-level code carried by the current payload.
  - This is the stable code consumers usually read first unless a more specific
    contract says otherwise.

- `worker_error_code`
  - The canonical worker-level error code.
  - This field applies precedence and placeholder filtering rules.
  - If `worker_error_code` is blank or a placeholder, it falls back to
    `error_code`.

- `raw_error_code`
  - A raw diagnostic value for debug-oriented summaries.
  - This field is not a stable routing key and must not be used as the primary
    decision key for retries, blockers, or policy branching.
  - When `worker_result` is absent, it may fall back to the resolved
    `error_code` for observability continuity.

- `warning_worker_error_code_mismatch`
  - A warning string emitted when raw `worker_error_code` and raw `error_code`
    are both present and differ.
  - This is an observability signal, not a policy key.

## Precedence Rules

Default operator/developer reading order:

1. `worker_error_code` for canonical worker-level interpretation
2. `error_code` for runtime/result-level interpretation
3. `raw_error_code` for raw worker/debug inspection only

If `worker_error_code` and `error_code` disagree, the canonical interpretation
follows `worker_error_code`, and the disagreement should be treated as a warning
condition rather than a tie.

## Generation Rules

- Canonical handoff metadata is built in `runtime_v2/latest_run.py`.
- Canonical worker-code selection is centralized in
  `runtime_v2/error_codes.py` via `select_worker_error_code()`.
- Manager GUI and control-plane snapshots reuse the same helper so
  `worker_error_code` semantics stay aligned.
- Debug summaries in `runtime_v2/debug_log.py` expose `raw_error_code` for
  diagnostics and keep `error_code` for compatibility.
- `warning_worker_error_code_mismatch` is emitted when canonical handoff sees
  conflicting raw values and is surfaced in latest-run metadata, manager GUI,
  and control-plane debug logs.

## Examples

### Example A: Normal Match

```json
{
  "error_code": "BROWSER_RESTART_EXHAUSTED",
  "worker_error_code": "BROWSER_RESTART_EXHAUSTED",
  "raw_error_code": "BROWSER_RESTART_EXHAUSTED"
}
```

Interpretation:
- No mismatch warning is emitted.
- Canonical and raw views agree.

### Example B: Placeholder Worker Value

```json
{
  "error_code": "BROWSER_RESTART_EXHAUSTED",
  "worker_error_code": "-",
  "raw_error_code": "-"
}
```

Interpretation:
- Raw worker output is `-`.
- Canonical selection must ignore the placeholder and use
  `BROWSER_RESTART_EXHAUSTED` as the effective worker error meaning.

### Example C: Canonical Mismatch Warning

```json
{
  "error_code": "BROWSER_RESTART_EXHAUSTED",
  "worker_error_code": "BROWSER_BLOCKED",
  "warning_worker_error_code_mismatch": "worker_error_code=BROWSER_BLOCKED error_code=BROWSER_RESTART_EXHAUSTED"
}
```

Interpretation:
- Consumers treat this as a warning-bearing mismatch case.
- Canonical worker interpretation follows `worker_error_code`.
- The warning exists to preserve observability of the disagreement.

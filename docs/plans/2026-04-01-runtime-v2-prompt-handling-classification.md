# Runtime V2 Prompt Handling Classification - 2026-04-01

## Purpose

- Satisfy the Phase 1 deliverable for per-subprogram prompt handling classification.
- Record which services are `pass-through`, `structural-transform`, or `semantic-injection`.
- Prevent future sessions from reintroducing hidden browser-side prompt strengthening.

## Classification Rules

| Class | Meaning |
|---|---|
| `pass-through` | Runtime forwards the caller-provided prompt text without adding semantic content. |
| `structural-transform` | Runtime reshapes the prompt into explicit contract fields or task JSON, but does not add new semantic intent. |
| `semantic-injection` | Runtime adds new free-text semantic intent beyond the pinned contract fields or legacy prompt wrapper. |

## Current Classification

| Subprogram | Class | Current contract evidence |
|---|---|---|
| `chatgpt` | `pass-through` | `runtime_v2/stage1/chatgpt_runner.py` `build_live_chatgpt_prompt()` now forwards the topic text itself, matching the legacy custom-GPT input path. |
| `genspark` | `pass-through` | `runtime_v2/stage2/request_builders.py` `build_image_prompt_file()` writes `payload.prompt` directly into `native_prompt.json`; `runtime_v2/cli.py` fills the browser input from the same prompt value without extra semantic text. |
| `seaart` | `pass-through` | same `build_image_prompt_file()` path as `genspark`; no service-specific semantic strengthening layer is added before adapter execution. |
| `geminigen` | `structural-transform` | `runtime_v2/stage2/request_builders.py` `build_geminigen_prompt_file()` places `payload.prompt` into `video_tasks[].prompt` and carries `first_frame_path` as a separate contract field. |
| `canva` | `structural-transform` | `runtime_v2/stage2/request_builders.py` `build_canva_thumb_file()` derives `bg_prompt`, `line1`, and `line2` from structured `thumb_data` and prompt-backed fields rather than sending one raw prompt string straight through. |

## Current Interpretation

- `genspark` and `seaart` must stay `pass-through` unless legacy evidence proves a minimal confirmation step is required.
- `geminigen` and `canva` may remain `structural-transform` because the transform is explicit in contract fields, not hidden free-text injection.
- `chatgpt` now stays `pass-through` at the browser input boundary because the legacy custom GPT already owns the longform production contract.
- historical `genspark` semantic injection existed in older runtime drift, but it is not part of the current default path.

## Guardrails

- No browser-side semantic strengthening may be added to `genspark` or `seaart` outside explicit legacy evidence.
- Any future transform for `geminigen` or `canva` must be represented as named fields in request artifacts, not hidden prompt concatenation.
- If `chatgpt` prompt semantics change, both this table and the Stage 1 prompt contract must be updated together.

# Runtime V2 Closeout Retest Result - 2026-04-01

## Purpose

- Satisfy the active closeout retest deliverable for `one closeout retest result interpreted only by current evidence`.
- Record the current `row15` closeout reading without pretending that probe/process success equals semantic-row completion.
- Freeze the latest target-row judgment using only current evidence, without overstating deferred `Canva` hold scope beyond what this row actually exercised.

## Target

- semantic target row: `Sheet1!row15`
- CLI mapping: `--row-index 14`

## Required Closeout Contract

The active plan recognizes closeout only when a new target-row `probe_root` contains both:

1. `probe_result.json`
2. either `render_final.mp4` or `failure_summary.json`

Anything less is not a closed retest result.

## Current Evidence Reading

| Evidence item | What it proves | What it does not prove |
|---|---|---|
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-rerun-03\probe_result.json` + `render_final.mp4` | generic row1 stage5 path once produced a closed success artifact | does not prove `row15` closeout |
| `D:\YOUTUBEAUTO_RUNTIME\probe\semantic-row-closeout-20260318-02\probe_result.json` | one row15 semantic rerun failed with `CHATGPT_RESPONSE_TIMEOUT` | not a successful closeout |
| `D:\YOUTUBEAUTO_RUNTIME\probe\semantic-row-closeout-20260318-03\probe_result.json` | a later row15 semantic rerun failed with `ADAPTER_TIMEOUT` | not a successful closeout |
| `D:\YOUTUBEAUTO_RUNTIME\probe\semantic-row-closeout-20260411-02\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\semantic-row-closeout-20260411-02\evidence\failure_summary.json` | an older row15 detached closeout once satisfied the terminal failure artifact contract and closed as a failed retest with `missing_scene_prompts` | no longer represents the latest row15 closeout truth |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-b\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-b\evidence\failure_summary.json` | one fresh sequential row15 rerun advanced through `chatgpt -> qwen3_tts -> genspark ref-1 -> seaart ref-2 -> genspark main -> seaart main` and then closed at `canva / CANVA_PRODUCT_BACKGROUND_NO_PROMPT_INPUT` | does not prove that the latest closeout truth stays pinned at Canva under all fresh reruns |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-e\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-e\evidence\failure_summary.json` | a later truly sequential row15 rerun still closed contractually, but failed earlier at `genspark / BROWSER_UNHEALTHY` | does not disprove the later Canva boundary; it shows the closeout truth was still oscillating between pinned single boundaries |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-h\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-h\evidence\failure_summary.json` | one fresh truly sequential row15 rerun advanced through `chatgpt -> qwen3_tts -> genspark ref-1 -> seaart ref-2 -> genspark main -> seaart main` and then closed at `canva / CANVA_PRODUCT_BACKGROUND_NO_PROMPT_INPUT` | no longer represents the latest row15 closeout truth |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\evidence\failure_summary.json` | an earlier fresh truly sequential row15 rerun advanced through `chatgpt -> qwen3_tts -> genspark ref-1 -> seaart ref-2 -> genspark main -> seaart main` and then closed at `canva / CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED` | no longer represents the latest closeout truth |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-h-port-poll.jsonl` | during that earlier rerun, Genspark port `9333` kept serving `/json/version` and tabs continuously, and its top tab moved from compose to result (`agents?id=...`) mid-run | does not prove Genspark can never regress again, but it does show that row15 could advance without the browser port disappearing |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-target-16-18` partial voice outputs only | some downstream files were emitted during a hidden rerun | does not count as closeout because `probe_result.json`, `qwen3_result.json`, `failure_summary.json`, and final render evidence were missing |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260524-a\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260524-a\artifacts\chatgpt\chatgpt-sheet1-15\a0840661-17a0-44bf-afb7-b68657bd1ece\assets\output\render_final.mp4` | latest fresh detached semantic-row rerun left a closed success artifact with `status=ok`, `code=OK`, `probe_success=true`, `readiness.ready=true`, and a concrete final render | does not prove that the separately deferred `Canva` account-credit hold is solved for standalone thumbnail/background-generation work |

## Result

Current closeout retest result for `Sheet1!row15` is reclassified by user correction:

- `status`: `E2E_UNVERIFIED`
- `reading`: probe/process artifact only, not accepted Excel-driven E2E completion
- `why`: the existing `probe_result.json` and final artifact path may describe a detached probe/process result, but they must not be used as proof that the user-visible Excel row -> GPT -> image services -> GeminiGen -> local voice/TTS/RVC -> render pipeline actually ran to completion.

## Interpretation Rules

- `probe_result.json code=OK` is only probe/process success, not row15 closeout success.
- generic row evidence is not semantic target-row evidence.
- partial downstream artifacts without `probe_result.json` + terminal success/failure artifact do not count as closeout.
- standalone `Canva` hold evidence must not be back-projected into the broader Excel-driven E2E status.

## Next Allowed Meaning

- This result does **not** prove user-visible Excel-driven E2E execution completion.
- The next allowed meaning is: the current E2E target remains `OPEN / UNVERIFIED`; any future completion claim must be backed by an accepted end-to-end run from Excel input through final render artifact.
- `Canva` remains a separate external credit-hold boundary and must not be reopened without credit/session availability changing.

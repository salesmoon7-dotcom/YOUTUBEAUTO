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
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-post-closeout-state-fix-20260620-173718\probe_result.json` + `evidence\result.json` + `evidence\closeout_state.json` | accepted same-run `Sheet1!row15` final closeout for run `8e8a0813-5113-4c1c-ba8b-9e7a16d1ff89`: Stage1 artifacts, downstream service artifacts, render final output, and closeout state are aligned | does not prove all rows, Excel sync-back, standalone Canva/Product Background, or broad browser reliability |
| `D:\YOUTUBEAUTO_RUNTIME\probe\current-run-row15-quoted-20260621-114016\probe_result.json` + `evidence\result.json` + `evidence\closeout_state.json` | fresh `CURRENT_RUN_ACCEPTED` same-run `Sheet1!row15` final closeout for run `b311b5b3-c358-4f31-acc7-6209ed4ddea0`: Stage1 artifacts, downstream service artifacts, render final output, and closeout state are aligned | does not prove all rows, Excel sync-back, standalone Canva/Product Background, or broad browser reliability |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-legacy-video-lane-ulw-20260622-043726\probe_result.json` + `evidence\result.json` + `assets\output\render_final.mp4` | latest fresh `CURRENT_RUN_ACCEPTED` same-run `Sheet1!row15` final closeout for run `8c2f4b5b-4d4d-4695-9ba7-eb021736928f`: `probe_result.json` is `status=ok`, `code=OK`, `exit_code=0`, `probe_success=true`, `ticks=30`; render metadata is `worker_stage=render`, `worker_error_code=OK`, `attempts=0`, `backoff_sec=0.0`, `completion_state=succeeded`, `final_output=true`, `final_artifact=render_final.mp4`, `size=2108944`, `sha256=FA13FD7BD7F1EE5A483C03C3EEC5CC838FCDABFA711D413F2C6662E3E1825EB5` | does not prove all rows, Excel sync-back, standalone Canva/Product Background, or broad browser reliability |

## Result

Current closeout retest result for `Sheet1!row15` is reclassified by the accepted fresh detached run:

- `status`: `CURRENT_RUN_ACCEPTED`
- `reading`: accepted only for same-run detached run `8c2f4b5b-4d4d-4695-9ba7-eb021736928f` at `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-legacy-video-lane-ulw-20260622-043726`
- `why`: the accepted run has `Sheet1!row15` seed evidence, Stage1 GPT artifacts, same-run downstream artifacts for `qwen3_tts`, `rvc`, `kenburns`, `genspark`, `seaart`, `geminigen`, terminal `render_final.mp4`, and render metadata aligned to the same `run_id` with `worker_error_code=OK`, `attempts=0`, and `backoff_sec=0.0`.

## Interpretation Rules

- `probe_result.json code=OK` is only accepted as row15 closeout success when it is paired with same-run terminal render or failure artifact and aligned closeout state.
- generic row evidence is not semantic target-row evidence.
- partial downstream artifacts without `probe_result.json` + terminal success/failure artifact do not count as closeout.
- standalone `Canva` hold evidence must not be back-projected into the broader Excel-driven E2E status.
- Browser popup/modal/iframe handling remains code-and-test evidence unless a specific same-run browser evidence artifact proves that boundary.
- Excel sync-back remains unproven for the accepted run because `excel_sync_updated=false` and `stage1_excel_merged=false`.

## Next Allowed Meaning

- This result proves only the accepted `Sheet1!row15` final closeout boundary for run `8c2f4b5b-4d4d-4695-9ba7-eb021736928f`.
- The next allowed meaning is not broader than `CURRENT_RUN_ACCEPTED` for `Sheet1!row15`; any all-row, Excel sync-back, standalone Canva, or broad browser reliability claim requires separate accepted evidence.
- `Canva` remains a separate external credit-hold boundary and must not be reopened without credit/session availability changing.

# Runtime V2 Closeout Retest Result - 2026-04-01

## Purpose

- Satisfy the active closeout retest deliverable for `one closeout retest result interpreted only by current evidence`.
- Record the current `row15` closeout reading without pretending that probe/process success equals semantic-row completion.
- Freeze the present judgment until the simplification-first gate permits a new closeout attempt.

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
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\evidence\failure_summary.json` | the latest fresh truly sequential row15 rerun advanced through `chatgpt -> qwen3_tts -> genspark ref-1 -> seaart ref-2 -> genspark main -> seaart main` and then closed at `canva / CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED` | does not prove successful closeout, render correctness, or that the Canva boundary is solved |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-h-port-poll.jsonl` | during that latest rerun, Genspark port `9333` kept serving `/json/version` and tabs continuously, and its top tab moved from compose to result (`agents?id=...`) mid-run | does not prove Genspark can never regress again, but it does show the latest chain did not fail because the browser port disappeared |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-target-16-18` partial voice outputs only | some downstream files were emitted during a hidden rerun | does not count as closeout because `probe_result.json`, `qwen3_result.json`, `failure_summary.json`, and final render evidence were missing |
| current 2026-04-01 truthful rerun reading | blocker surface moves across `chatgpt`, `qwen`, `genspark`, and `seaart` | does not justify another broad rerun |

## Result

Current closeout retest result for `Sheet1!row15` is:

- `status`: `closed`
- `reading`: `failed retest`
- `why`: the latest fresh sequential evidence `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260520-j\evidence\failure_summary.json` satisfies the closeout artifact contract, but it closes truthfully at `canva / CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED` after the non-Canva chain has already advanced through `genspark` and `seaart`.

## Interpretation Rules

- `probe_result.json code=OK` is only probe/process success, not row15 closeout success.
- generic row evidence is not semantic target-row evidence.
- partial downstream artifacts without `probe_result.json` + terminal success/failure artifact do not count as closeout.
- while the runtime remains under `runtime simplification reset`, additional fresh closeout reruns are not considered meaningful progress signals unless the next single blocker has changed.

## Next Allowed Meaning

- This result does **not** authorize a new broad closeout rerun.
- The next allowed execution is the single latest blocker exposed by the now-closed failed retest: continue narrowing the `Canva Product Background` OOPIF credit-purchase gate boundary without treating generic probe/process success as row15 closeout success.

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
| `D:\YOUTUBEAUTO_RUNTIME\probe\semantic-row-closeout-20260411-02\probe_result.json` + `D:\YOUTUBEAUTO_RUNTIME\probe\semantic-row-closeout-20260411-02\evidence\failure_summary.json` | one row15 detached closeout rerun now satisfies the terminal failure artifact contract and closes as a failed retest with `missing_scene_prompts` | does not prove successful closeout or downstream render correctness |
| `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-target-16-18` partial voice outputs only | some downstream files were emitted during a hidden rerun | does not count as closeout because `probe_result.json`, `qwen3_result.json`, `failure_summary.json`, and final render evidence were missing |
| current 2026-04-01 truthful rerun reading | blocker surface moves across `chatgpt`, `qwen`, `genspark`, and `seaart` | does not justify another broad rerun |

## Result

Current closeout retest result for `Sheet1!row15` is:

- `status`: `closed`
- `reading`: `failed retest`
- `why`: `D:\YOUTUBEAUTO_RUNTIME\probe\semantic-row-closeout-20260411-02\` now contains `probe_result.json` and terminal failure evidence (`evidence\failure_summary.json`), so the closeout contract is satisfied, but the current target-row result is a truthful failed closeout with `missing_scene_prompts`.

## Interpretation Rules

- `probe_result.json code=OK` is only probe/process success, not row15 closeout success.
- generic row evidence is not semantic target-row evidence.
- partial downstream artifacts without `probe_result.json` + terminal success/failure artifact do not count as closeout.
- while the runtime remains under `runtime simplification reset`, additional fresh closeout reruns are not considered meaningful progress signals unless the next single blocker has changed.

## Next Allowed Meaning

- This result does **not** authorize a new broad closeout rerun.
- The next allowed execution is the single blocker exposed by the now-closed failed retest: fix `missing_scene_prompts` at the earliest truthful stage1 boundary before another target-row closeout run.

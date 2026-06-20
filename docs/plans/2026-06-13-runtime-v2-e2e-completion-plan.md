# Runtime V2 E2E Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the accepted Excel-driven runtime_v2 pipeline from `Sheet1!row15` through GPT, image services, GeminiGen, local voice/TTS/RVC, and final render artifact without treating probe/component success as E2E completion.

**Architecture:** Work from the earliest unproven boundary forward: `prompt -> attach -> routing -> order -> closeout`. Each boundary must produce a same-`run_id` artifact or a fail-closed artifact before the next boundary is allowed to move.

**Tech Stack:** Python 3.13, pytest, runtime_v2 control plane, agent-browser CDP adapters, Excel row seeding, local GPU/voice workers, FFmpeg render worker.

---

## Current Truth

- Superseding status as of 2026-06-20: `Sheet1!row15` Stage5 final closeout is verified only for accepted post-fix detached run `8e8a0813-5113-4c1c-ba8b-9e7a16d1ff89` at `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-post-closeout-state-fix-20260620-173718`. This does not mean all rows are complete and does not clear Canva or other external blockers.
- Historical pre-fix status was `E2E_UNVERIFIED` until the accepted post-fix detached run above satisfied the same-`run_id` terminal closeout contract for `Sheet1!row15`.
- Historical `OK`, browser health, login proof, component tests, detached probe artifacts, and downstream render artifacts remain rejected as user-visible E2E completion evidence when Stage1 GPT output fails the parser contract.
- Active semantic target is `Sheet1!row15`, CLI `--row-index 14`.
- Canva remains excluded/held unless credit/session availability changes.
- For `Sheet1!row15`, the previously unproven Stage1-through-render boundary is superseded by the accepted post-fix detached run above; future rows or external blockers require their own same-`run_id` evidence.

## Completion Evidence Required

One accepted run must leave a single `run_id` chain with:

1. Excel seed evidence for `Sheet1!row15`.
2. Stage1 GPT artifacts:
   - `raw_output.json`
   - `parsed_payload.json`
   - `stage1_handoff.json`
   - `video_plan.json`
3. First truthful local voice artifact from `qwen3_tts` and RVC output when its source prerequisites are present.
4. First truthful image artifacts from `genspark` and `seaart`.
5. First truthful GeminiGen video artifact.
6. Terminal closeout evidence:
   - `probe_result.json`
   - and either `render_final.mp4` or `failure_summary.json`.

Do not claim completion unless all required success artifacts exist for the same accepted `run_id`.

Rejected evidence as of 2026-06-18:

- Probe root: `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-post-qwen-image-readiness-quoted-20260618-193028`.
- Same-run id: `4be627f1-9738-487c-af52-efbcc53eed42`.
- Old `probe_result.json`: `status=ok`, `code=OK`, `exit_code=0`, `probe_success=true`.
- Terminal artifact exists at `artifacts\chatgpt\chatgpt-sheet1-15\4be627f1-9738-487c-af52-efbcc53eed42\assets\output\render_final.mp4`, but this is rejected as E2E completion evidence because Stage1 GPT output revalidates to `invalid_voice_groups`.
- Stage1 blocker: `raw_output.json` contains an unnumbered `[Voice]` blob that was duplicated across multiple scenes; parser owner must fail closed before downstream jobs are accepted.

---

## Task 1: Stage1 GPT Contract Fails Closed On Missing Structured Artifacts

**Files:**
- Modify: `tests/test_runtime_v2_stage1_chatgpt.py`
- Modify only if RED proves a production gap: `runtime_v2/stage1/chatgpt_runner.py`

**Step 1: Write the failing test**

Add a test proving that a live ChatGPT capture with partial/unstructured text for `Sheet1!row15` does not create `parsed_payload.json`, `stage1_handoff.json`, or `video_plan.json`, and returns `CHATGPT_RESPONSE_TIMEOUT` or the precise worker error from `gpt_capture.error_code`.

Expected test shape:

```python
def test_stage1_live_capture_partial_text_does_not_emit_structured_artifacts(self) -> None:
    # Build topic_spec with run_id, row_ref=Sheet1!row15, browser_evidence requiring live capture,
    # and gpt_capture={"status":"failed","error_code":"CHATGPT_RESPONSE_TIMEOUT"}.
    # Run run_stage1_chatgpt_job(...).
    # Assert status failed, error_code CHATGPT_RESPONSE_TIMEOUT.
    # Assert raw_output.json exists.
    # Assert parsed_payload.json, stage1_handoff.json, video_plan.json do not exist.
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_runtime_v2_stage1_chatgpt.py::RuntimeV2Stage1ChatGPTTests::test_stage1_live_capture_partial_text_does_not_emit_structured_artifacts
```

Expected: FAIL if current code emits structured artifacts or maps the error incorrectly. If it already passes, record this gate as already implemented and do not change production code.

**Step 3: Write minimal implementation**

If RED fails, adjust only `runtime_v2/stage1/chatgpt_runner.py` so live-capture failure exits before parsed payload/handoff/video plan emission.

Do not add fallback parsing, synthetic success, or retry broadening.

**Step 4: Run test to verify it passes**

Run the same test again.

Expected: PASS.

**Step 5: Commit**

Commit only if production or test files changed:

```bash
.\git_plain.bat add tests/test_runtime_v2_stage1_chatgpt.py runtime_v2/stage1/chatgpt_runner.py
.\git_plain.bat commit -m "fix: fail closed stage1 partial gpt output"
```

---

## Task 2: Stage1 Current-Row Artifact Proof Command

**Files:**
- Modify: `tests/test_runtime_v2_stage1_chatgpt.py`
- Modify only if RED proves a production gap: `runtime_v2/stage1/chatgpt_runner.py`, `runtime_v2/excel/source.py`, or seed path identified by the failing test.

**Step 1: Write the failing test**

Add a focused test that builds a current-row `topic_spec` with `row_ref="Sheet1!row15"` and a valid structured GPT response, then proves all four Stage1 artifacts are generated with matching `run_id` and `row_ref`.

Expected assertions:

```python
assert raw_output_path.exists()
assert parsed_payload_path.exists()
assert handoff_path.exists()
assert video_plan_path.exists()
assert parsed_payload["run_id"] == run_id
assert parsed_payload["row_ref"] == "Sheet1!row15"
assert video_plan["run_id"] == run_id
assert video_plan["row_ref"] == "Sheet1!row15"
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_runtime_v2_stage1_chatgpt.py::RuntimeV2Stage1ChatGPTTests::test_stage1_current_row_generates_same_run_artifact_bundle
```

Expected: FAIL only if a real current-row contract gap exists. If it passes, record this as Stage1 contract proof and do not edit production code.

**Step 3: Write minimal implementation**

If needed, repair the exact contract drift surfaced by the RED test. Do not change downstream workers in this task.

**Step 4: Run test to verify it passes**

Run the same test again.

Expected: PASS.

**Step 5: Commit**

```bash
.\git_plain.bat add tests/test_runtime_v2_stage1_chatgpt.py runtime_v2/stage1/chatgpt_runner.py runtime_v2/excel/source.py
.\git_plain.bat commit -m "test: pin stage1 current row artifact bundle"
```

---

## Task 3: Boundary Proof For Local Voice Before Image/Video Work

**Files:**
- Modify: `tests/test_runtime_v2_control_plane_chain.py`
- Modify only if RED proves a production gap: `runtime_v2/control_plane.py`, `runtime_v2/workers/qwen3_worker.py`, `runtime_v2/workers/rvc_worker.py`

**Step 1: Write the failing test**

Add or tighten a test proving a Stage1 result with `stage1_handoff.contract.voice_texts` emits exactly one bounded `qwen3_tts` proof job in probe/minimum-unit mode, and does not pretend a full row voice batch is progress.

Expected:

```python
assert qwen_job["workload"] == "qwen3_tts"
assert qwen_job["payload"]["run_id"] == run_id
assert qwen_job["payload"]["row_ref"] == "Sheet1!row15"
assert len(qwen_job["payload"]["voice_texts"]) == 1
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_stage1_probe_mode_emits_single_qwen_truthful_artifact_job
```

Expected: FAIL if qwen emits multi-hour/full-batch default work in minimum-unit proof mode.

**Step 3: Write minimal implementation**

If needed, keep the existing probe/minimum-unit behavior bounded at control-plane job declaration. Do not alter production full-run voice behavior unless the test proves it is currently conflated.

**Step 4: Run test to verify it passes**

Run the same test again.

Expected: PASS.

**Step 5: Commit**

```bash
.\git_plain.bat add tests/test_runtime_v2_control_plane_chain.py runtime_v2/control_plane.py runtime_v2/workers/qwen3_worker.py runtime_v2/workers/rvc_worker.py
.\git_plain.bat commit -m "fix: bound qwen proof job for stage1 probes"
```

---

## Task 4: Routing Proof For Image And GeminiGen Jobs

**Files:**
- Modify: `tests/test_runtime_v2_stage2_contracts.py`
- Modify only if RED proves a production gap: `runtime_v2/stage2/json_builders.py`

**Step 1: Write the failing test**

Add a test using a same-run `video_plan` with `stage1_handoff`, `scene_plan`, `videos`, and `asset_plan.common_asset_folder`. Assert routing emits same-`run_id` jobs for `genspark`, `seaart`, and `geminigen`, and each payload includes the Stage1 handoff when required.

Expected:

```python
workloads = [job["workload"] for job in jobs]
assert "genspark" in workloads
assert "seaart" in workloads
assert "geminigen" in workloads
for job in jobs:
    assert job["payload"]["run_id"] == run_id
    assert job["payload"]["row_ref"] == "Sheet1!row15"
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_runtime_v2_stage2_contracts.py::RuntimeV2Stage2ContractsTests::test_same_run_video_plan_routes_required_image_and_geminigen_jobs
```

Expected: FAIL only if routing loses run identity or omits required workloads.

**Step 3: Write minimal implementation**

Repair only `json_builders.py` routing identity or payload omissions surfaced by RED.

**Step 4: Run test to verify it passes**

Run the same test again.

Expected: PASS.

**Step 5: Commit**

```bash
.\git_plain.bat add tests/test_runtime_v2_stage2_contracts.py runtime_v2/stage2/json_builders.py
.\git_plain.bat commit -m "test: pin same-run image and geminigen routing"
```

---

## Task 5: Detached Boundary Execution, One Service At A Time

**Files:**
- No production edits unless a boundary produces a deterministic code defect.
- Evidence roots under `D:\YOUTUBEAUTO_RUNTIME\probe\...`.

**Step 1: Run readiness only**

Run a short readiness check using the existing CLI command documented in the active plan.

Expected: a readiness artifact, not a completion claim.

**Step 2: Run Stage1-only or first-boundary detached proof**

Use a detached/log-producing execution path. Do not run a broad semantic-row closeout as the first diagnostic.

Expected if successful:

- same `run_id`
- `raw_output.json`
- `parsed_payload.json`
- `stage1_handoff.json`
- `video_plan.json`

Expected if failed:

- fail-closed `probe_result.json` or worker `result.json`
- exact `error_code`
- no downstream success claim

**Step 3: Advance one boundary only after decisive artifact**

Order:

1. `chatgpt`
2. `qwen3_tts`
3. `genspark`
4. `seaart`
5. `geminigen`
6. `rvc`
7. `render`

Canva stays excluded/held unless credit/session availability changes.

**Step 4: Stop on first blocker**

If a boundary fails or exceeds the documented 10-minute decisive-evidence window, stop and write the blocker. Do not continue to downstream services.

**Step 5: Commit only code/doc changes**

Do not commit generated probe artifacts. Commit code fixes and plan/status docs only after focused verification.

**Evidence note: 2026-06-15 row15 SeaArt fail-closed blocker**

- Evidence root: `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-seaart-propagation-20260615`.
- Same-run id: `4346121b-74ce-4ec5-94bb-c6e1530d8b87`.
- Historical status for this 2026-06-15 run was `E2E_UNVERIFIED`; this was not final E2E completion evidence.
- Boundary reached: `chatgpt` completed, `genspark` `ref-1` completed, then `seaart` `ref-2` failed.
- Terminal blocker: `SEAART_VISIBLE_INPUT_TIMEOUT` at worker stage `seaart_adapter`.
- Contract alignment verified:
  - `probe_result.json`: `status=failed`, `code=SEAART_VISIBLE_INPUT_TIMEOUT`, `exit_code=2`.
  - `evidence/result.json`: `worker_error_code=SEAART_VISIBLE_INPUT_TIMEOUT`, `attempts=1`, `chain_depth=1`, `final_output=false`.
  - worker `result.json`: `error_code=SEAART_VISIBLE_INPUT_TIMEOUT`, `retryable=false`, `details.returncode=70`.
  - `attach_evidence.json`: `current_url` is the SeaArt `/ko/create/image` page, `details.selector=textarea.el-textarea__inner:not(#easyGenerateInput):visible`, `details.source_error_code=AGENT_BROWSER_COMMAND_FAILED`, `recovery_attempted=false`.
- Oracle classified the next action as `EVIDENCE_ONLY`: do not broaden SeaArt selectors or add fallback paths without a DOM snapshot proving a concrete alternate prompt input contract.

---

## Task 6: Final Semantic-Row Closeout

**Files:**
- No source edit unless a focused RED test proves a defect.
- Evidence root: new `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-<date>-<suffix>`.

**Step 1: Preconditions**

Confirm all prior boundary proofs exist for the same intended path or have been repaired with TDD.

**Step 2: Start exactly one detached closeout run**

Use the documented detached CLI form:

```bash
python -m runtime_v2.cli --stage5-row1-detached --excel-path "D:\YOUTUBEAUTO\4 머니.xlsx" --sheet-name Sheet1 --row-index 14 --max-control-ticks 80 --probe-root "<new_probe_root>"
```

**Step 3: Monitor by evidence files**

Check only:

- child PID status
- `<probe_root>\probe_result.json`
- `<probe_root>\logs\<run_id>.jsonl`
- current boundary artifact folder

Do not relaunch browser/recovery in chat.

**Step 4: Accept only terminal contract**

Completion requires:

- `probe_result.json`
- and `render_final.mp4` for success, or `failure_summary.json` for fail-closed blocker classification.

**Step 5: Verification before completion**

Run:

```bash
python -m py_compile runtime_v2/stage1/chatgpt_runner.py runtime_v2/stage2/json_builders.py runtime_v2/control_plane.py
```

Run only focused pytest cases touched in earlier tasks.

Run `verify-implementation` and confirm:

- `run_id` alignment
- `error_code` meaning alignment
- `attempt/backoff` contract alignment

**Step 6: Commit and push**

Commit only intended source/test/doc changes.

Push after `git status`, `git diff`, and focused verification are clean for intended files.

---

## Reporting Rules

- Say `complete` only when the final semantic-row closeout produces the terminal success artifact for the same accepted `run_id`.
- Say `blocked` when a boundary produces fail-closed evidence.
- Never convert `probe_success=true`, browser health, login proof, or component tests into whole-program completion.
- Preserve the phrase `E2E_UNVERIFIED` until final evidence satisfies this document.

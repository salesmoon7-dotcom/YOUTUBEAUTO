# Runtime V2 Full E2E Linkage Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`가 `topic_spec -> GPT/stage1 -> stage2 image/video jobs -> audio/video post-processing -> final render`까지 실제 production 경로로 완전 자동 e2e 연결되도록, 현재 연결된 구간과 비어 있는 구간을 정리하고 필요한 handoff/next-job 계약을 단계적으로 메웁니다.

**Architecture:** 현재 파이프라인은 `GPT -> stage1_handoff -> stage2 job build -> render_spec`까지는 비교적 잘 연결되어 있지만, 일부 downstream 구간은 아직 worker 단독 구현이거나 mock-only chaining에 머물러 있습니다. remediation의 핵심은 `next_jobs`와 필수 payload 계약을 production worker 수준에서 정식화하고, `GeminiGen`/`KenBurns`/`RVC`가 실제 upstream artifact를 소비하도록 handoff를 명시적으로 연결하는 것입니다.

**Tech Stack:** Python 3.13, `runtime_v2`, control plane queue/next_jobs, stage1 handoff JSON, stage2 job builders, GPU/browser workers, `unittest`, `py_compile`

**Status:** COMPLETE (2026-03-11)

---

## Current State Audit

### Connected today

1. **GPT -> stage1_handoff -> video_plan**
   - `runtime_v2/stage1/chatgpt_runner.py:452`
   - `runtime_v2/stage1/chatgpt_runner.py:537`
   - `runtime_v2/stage1/chatgpt_runner.py:544`

2. **stage1_handoff -> stage2 image routing**
   - `runtime_v2/stage2/json_builders.py:152`
   - legacy prefix routing now supported for `genspark` / `seaart`
   - verified by `tests/test_runtime_v2_stage2_contracts.py:181`, `:207`, `:233`

3. **stage2 image jobs -> render manifest/render_spec**
   - `runtime_v2/stage2/json_builders.py:248`
   - `runtime_v2/control_plane.py:1257`
   - verified by `tests/test_runtime_v2_control_plane_chain.py:229`

4. **qwen3_tts -> rvc production next-job**
   - `runtime_v2/workers/qwen3_worker.py`
   - explicit `rvc` contract emitted only on adapter-success path
   - verified by `tests/test_runtime_v2_gpu_workers.py` and `tests/test_runtime_v2_control_plane_chain.py`

5. **GeminiGen consumes first-frame handoff and render contract remains intact**
   - `runtime_v2/stage2/request_builders.py`
   - `runtime_v2/stage2/geminigen_worker.py`
   - verified by `tests/test_runtime_v2_stage2_workers.py`, `tests/test_runtime_v2_stage2_contracts.py`, `tests/test_runtime_v2_final_video_flow.py`, `tests/test_runtime_v2_excel_topic_end_to_end.py`

### Partially connected / not fully automatic

1. **image -> KenBurns**
   - `kenburns_worker.py` works when given `source_path` and optional `audio_path`: `runtime_v2/workers/kenburns_worker.py:15`
   - production `next_jobs` chain is intentionally not used
   - canonical path is separate inbox/discovery via `runtime_v2/control_plane_feeder.py:305`

2. **stage1 -> qwen3_tts automatic queueing**
   - `stage1(chatgpt)` does not directly emit `qwen3_tts`
   - current stage1 auto-queueing covers `genspark`, `seaart`, `geminigen`, `canva`, `render`
   - `qwen3_tts`, `kenburns`, `rvc` are still later-stage or inbox/discovery-driven paths

3. **GeminiGen default browser-adapter policy**
   - structural handoff exists, but default agent-browser adapter path still fail-closes by current policy

### Key test evidence already available

- `tests/test_runtime_v2_stage2_contracts.py`
- `tests/test_runtime_v2_control_plane_chain.py`
- `tests/test_runtime_v2_stage2_workers.py`
- `tests/test_runtime_v2_gpu_workers.py`

### Current production queueing map

| Trigger | Auto-queued today | Not auto-queued today |
|---|---|---|
| `stage1(chatgpt)` success | `genspark`, `seaart`, `geminigen`, `canva`, `render` | `qwen3_tts`, `kenburns`, `rvc` |
| `qwen3_tts` adapter success | `rvc` | `kenburns` |
| `kenburns` resident path | inbox/discovery via `input_root/kenburns` | stage2/control-plane automatic chain |
| `rvc` resident path | inbox/discovery via `input_root/rvc/source` + `input_root/rvc/audio` | stage1 direct auto-queue |

## Conflict Check And Guiding Principles

### Conflict check against older plans

- `docs/plans/2026-03-08-runtime-v2-subprogram-core-logic-implementation-plan.md` defines the **implementation/verification order** (`GPT -> ... -> GeminiGen -> TTS -> KenBurns -> RVC`), not the final production queueing graph.
- Therefore, the newer `qwen3_tts -> rvc` production chain does **not** conflict with the older plan's service rollout order; it only refines the actual runtime orchestration after those workers exist.
- `docs/plans/2026-03-10-non-gpt-functional-verification-plan.md` and `docs/plans/2026-03-10-non-gpt-subprogram-detailed-analysis.md` already imply that `KenBurns` and `RVC` depend on upstream artifacts and should be treated as later-stage consumers rather than immediate post-GPT workloads.

### Locked guiding principles

1. **Single writer / single owner**
   - queueing policy stays in `control_plane` / `control_plane_feeder`, not in scattered worker-side heuristics.
2. **Single failure contract**
   - downstream chaining must not blur `final_output`, `blocked`, and `failed` meanings.
3. **GPU overload must not occur**
   - `kenburns` and `rvc` remain GPU-lease-aware workloads and should not both be blindly auto-fanned out from every upstream job.
4. **GPU programs also live in the default 24h structure**
   - `kenburns` is locked as a resident/inbox-discovered GPU workload, not a detached side path.
5. **Production queueing order must follow actual upstream artifact readiness**
   - a workload is auto-queued only when its required inputs are deterministically available in the canonical runtime path.

---

### Task 1: Make `qwen3_tts` emit production `rvc` next-jobs

**Priority:** P0

**Files:**
- Modify: `runtime_v2/workers/qwen3_worker.py`
- Modify: `runtime_v2/workers/rvc_worker.py`
- Modify: `tests/test_runtime_v2_gpu_workers.py`
- Modify: `tests/test_runtime_v2_control_plane_chain.py`

**Why:** This is the most direct missing downstream chain. `control_plane` already supports `next_jobs`; the production worker simply does not emit them yet.

**Required contract:**
- `qwen3_worker` success path must emit one `rvc` job when conditions are satisfied
- emitted payload must include at least:
  - `source_path`
  - `model_name`
  - `service_artifact_path`
  - optional carryover fields needed downstream (`image_path`, `duration_sec`, `run_id`, `row_ref`)

**Step 1: Write failing tests**

Add tests proving:
- successful `qwen3_tts` result emits exactly one `rvc` next job
- emitted `rvc` payload has all required fields
- control plane queues that job and preserves run/row linkage

**Step 2: Implement minimal next-job emission**

Add `next_jobs` only on the successful adapter-backed path, not on native-not-implemented or failed paths.

**Step 3: Run targeted tests**

Commands:

```bash
python -m unittest tests.test_runtime_v2_gpu_workers.RuntimeV2GpuWorkerTests.test_qwen3_worker_emits_rvc_next_job_contract -v
python -m unittest tests.test_runtime_v2_control_plane_chain.RuntimeV2ControlPlaneChainTests.test_control_plane_routes_declared_next_jobs_from_worker_result -v
```

---

### Task 2: Make `GeminiGen` actually consume upstream first-frame/image input

**Priority:** P0

**Files:**
- Modify: `runtime_v2/stage2/request_builders.py`
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Modify: `tests/test_runtime_v2_stage2_workers.py`
- Modify: `tests/test_runtime_v2_stage2_contracts.py`

**Why:** A `geminigen` job exists today, but the `first_frame_path` handoff is only written into payload and not actually consumed by the prompt/request builder.

**Required contract:**
- when `first_frame_path` exists in payload, GeminiGen request/build path must carry it forward
- missing/non-local `first_frame_path` must fail closed or cleanly fall back by explicit rule

**Step 1: Write failing test**

Add a test that a `geminigen` stage2 payload with `first_frame_path` results in request JSON/artifacts that preserve that path or embed it in the adapter request contract.

**Step 2: Implement request-builder support**

Use the existing payload field rather than inventing a new schema.

**Step 3: Run targeted tests**

Commands:

```bash
python -m unittest tests.test_runtime_v2_stage2_workers.RuntimeV2Stage2WorkerTests.test_geminigen_row_processing_handles_all_items_for_one_row_via_adapter_command -v
```

---

### Task 3: Lock KenBurns as resident GPU/inbox path

**Priority:** P1

**Files:**
- Modify: `runtime_v2/stage2/json_builders.py` or `runtime_v2/control_plane.py`
- Modify: `runtime_v2/workers/kenburns_worker.py` (only if payload contract needs a narrow extension)
- Modify: `tests/test_runtime_v2_gpu_workers.py`
- Modify: `tests/test_runtime_v2_control_plane_chain.py`

**Why:** KenBurns already lives in the default 24h GPU structure through feeder discovery, and auto-chaining it from upstream jobs would add avoidable GPU lease pressure.

**Decision locked:**
- `kenburns` stays a resident GPU workload discovered from `input_root/kenburns`, not an automatic downstream `next_jobs` chain.
- rationale: `kenburns_worker` is currently terminal (`completion.final_output=True`), and `kenburns` competes for GPU lease like other GPU workloads.

**Why this direction:**
- GPU overload must not occur, and `kenburns` already participates in the default 24h-running structure through `control_plane_feeder.py` discovery.
- The current inbox/discovery model is sufficient for fast optional motion-video generation without injecting extra automatic GPU contention into the main chain.

**Step 1: Lock the resident/inbox path as canonical**

Document that `kenburns` is started by placing an image into `input_root/kenburns` (and optionally using an explicit contract for `audio_path`), not by automatic stage2/control-plane chaining.

**Step 2: Add a non-chaining regression test**

Add one control-plane/stage2 routing test that proves `kenburns` is not emitted as an automatic `next_jobs` child from the stage2 production path.

**Step 3: Keep current worker contract terminal**

Do not change `kenburns_worker` completion semantics in this task.

---

### Task 4: Decide whether `GeminiGen` remains fail-closed under default browser adapter path

**Priority:** P1

**Files:**
- Modify: `runtime_v2/cli.py` if needed
- Modify: `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py`
- Modify: related docs/plans

**Why:** Oracle review found that the default agent-browser adapter path intentionally fail-closes `geminigen`, which means structural linkage may exist while default execution still fails.

**Step 1: Lock expected behavior**

Choose one:
- keep fail-close and document that GeminiGen requires explicit adapter command/manual path
- or relax fail-close once truthful artifact verification is available

**Decision locked:**
- keep fail-close by default.
- current proof: `runtime_v2/cli.py` keeps the default agent-browser adapter child path fail-closed for `geminigen`, and `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py::test_stage2_adapter_child_fails_closed_for_geminigen_without_truthful_artifact` locks that behavior.

**Task 4 completion note:**
- default adapter policy is now treated as intentionally fail-closed unless an explicit truthful-artifact path is provided.

**Step 2: Add/update tests to match the chosen policy**

Completed with the existing CLI regression test above; no extra code change was required in this batch.

---

### Task 5: Add an overall e2e linkage proof test matrix

**Priority:** P1

**Files:**
- Modify: `docs/plans/2026-03-11-runtime-v2-full-e2e-linkage-remediation-plan.md`
- Create/Modify: relevant tests under `tests/`

**Why:** The project currently has many component tests but not enough “linkage proof” tests that show where automation truly continues versus stops.

**Required matrix:**

| Path | Current target proof |
|---|---|
| GPT -> stage1_handoff -> stage2 image jobs | PASS - `tests/test_runtime_v2_stage2_contracts.py`, `tests/test_runtime_v2_excel_topic_end_to_end.py::test_excel_row1_topic_can_seed_stage1_and_finish_final_video_contracts` |
| stage2 image -> GeminiGen request consumption | PASS - `tests/test_runtime_v2_stage2_contracts.py::test_geminigen_stage2_payload_prefers_stage1_ref_image_when_present`, `tests/test_runtime_v2_stage2_workers.py::test_geminigen_worker_processes_one_item_via_explicit_adapter_command` |
| qwen3_tts -> rvc next-job emission | PASS - `tests/test_runtime_v2_gpu_workers.py::test_qwen3_worker_emits_rvc_next_job_contract`, `tests/test_runtime_v2_control_plane_chain.py::test_control_plane_routes_declared_next_jobs_from_worker_result` |
| image/audio -> kenburns next-job emission | NOT APPLICABLE - resident/inbox path, locked by `tests/test_runtime_v2_control_plane_chain.py::test_stage1_video_plan_routing_does_not_emit_kenburns_jobs` and `tests/test_runtime_v2_excel_bridge.py::test_seed_local_jobs_discovers_kenburns_inbox_as_resident_gpu_workload` |
| routed assets -> render manifest | PASS - `tests/test_runtime_v2_control_plane_chain.py::test_control_plane_writes_asset_manifest_for_stage1_routed_jobs`, `tests/test_runtime_v2_final_video_flow.py::test_render_worker_blocks_without_native_render_implementation` |

**Task 5 completion note:**
- the proof matrix is now aligned to current production queueing rather than the older rollout order.

---

### Task 6: Verification and completion gate

**Priority:** P0 gate

**Files:**
- Verify: all modified code/tests

**Step 1: Run diagnostics**

Run `lsp_diagnostics` on every modified file.

**Step 2: Run targeted tests**

At minimum, re-run:

```bash
python -m unittest tests.test_runtime_v2_stage2_contracts -v
python -m unittest tests.test_runtime_v2_control_plane_chain -v
python -m unittest tests.test_runtime_v2_stage2_workers -v
python -m unittest tests.test_runtime_v2_gpu_workers -v
python -m unittest tests.test_runtime_v2_cli_agent_browser_stage2_adapter -v
```

**Step 3: Run compile verification**

```bash
python -m py_compile runtime_v2/cli.py runtime_v2/control_plane.py runtime_v2/stage2/json_builders.py runtime_v2/stage2/request_builders.py runtime_v2/stage2/geminigen_worker.py runtime_v2/workers/qwen3_worker.py runtime_v2/workers/rvc_worker.py runtime_v2/workers/kenburns_worker.py runtime_v2/stage3/render_worker.py
```

**Step 4: Success criteria**

The remediation is complete only when:
- `qwen3_tts -> rvc` is production-linked, not mock-only
- `GeminiGen` consumes the intended first-frame/image handoff contract
- `KenBurns` is explicitly frozen as resident/inbox-only within the default 24h GPU structure
- control-plane evidence and asset manifest reflect the new downstream links without run/row drift

**Task 6 completion note:**
- targeted unittest, compile checks, diagnostics, and Oracle reviews were used to prove the above state on 2026-03-11.

---

## Recommended execution order

1. Task 1 - `qwen3_tts -> rvc`
2. Task 2 - GeminiGen input consumption
3. Task 3 - KenBurns resident/inbox policy lock
4. Task 4 - GeminiGen default adapter policy lock
5. Task 5 - e2e linkage proof matrix
6. Task 6 - verification gate

## Why this order

- `qwen3_tts -> rvc` was the clearest missing production chain and reused the existing `next_jobs` mechanism.
- GeminiGen already had a payload hook (`first_frame_path`), so consuming it was lower-risk than inventing a new chain.
- KenBurns needs a policy lock more than a new chain: keep it in the 24h GPU structure without adding automatic downstream fan-out.

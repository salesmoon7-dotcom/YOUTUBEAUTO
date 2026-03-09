# Runtime V2 Legacy Carryover Top 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 레거시에서 지금도 차용 가치가 큰 3가지(`thumb/ref image 계약`, `역할 기반 asset manifest`, `reused success marker`)를 현재 `runtime_v2` 가드레일 안에서 안전하게 흡수합니다.

**Architecture:** Excel을 owner로 되돌리거나 legacy fallback 구조를 재도입하지 않습니다. 모든 결정은 `stage2 payload builder`와 `control plane`의 단일 writer/단일 failure contract 안에서만 수행하고, worker는 입력을 받아 실행만 하도록 유지합니다.

**Tech Stack:** Python 3.13, `runtime_v2/stage2/json_builders.py`, `runtime_v2/control_plane.py`, `runtime_v2/contracts/*`, `runtime_v2/stage2/*_worker.py`, pytest, py_compile, LSP diagnostics

**Document Status:** COMPLETED - top3 carryover safe batch implemented on 2026-03-09.

---

## Why This Plan Exists

- legacy에서 지금도 가져올 가치가 높은 것은 구조가 아니라 품질/운영 usability입니다.
- Oracle 최종 top3:
  1. `thumb_data` + ref image selection rule
  2. 역할 기반 `asset_manifest`
  3. artifact exists -> `reused` success marker
- 이 3가지는 `single writer`, `single failure contract`, `fail-closed`를 깨지 않고 현재 프로그램 품질을 높일 수 있습니다.

## Guardrails

- Excel은 canonical owner로 복귀시키지 않습니다.
- worker 내부에서 ref image 선택, success marker 의미 결정, asset role 결정 로직을 늘리지 않습니다.
- `control_plane` 또는 상위 builder/helper만 의미를 결정합니다.
- 기존 `error_code`, `completion.state`, `retryable` 의미를 늘리지 않습니다.

---

## Task 1. Thumb contract + ref image selection baseline 고정

**Files:**
- Read: `docs/plans/2026-03-09-legacy-post-gpt-service-contract-survey.md`
- Read: `runtime_v2/stage2/json_builders.py`
- Read: `runtime_v2/stage2/canva_worker.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`

**Step 1: Write failing tests**

- add a test proving `canva` payload includes structured `thumb_data`
- add a test proving `ref_img` selection follows deterministic priority

**Step 2: Run tests to verify they fail**

Run:
```bash
python -m pytest tests/test_runtime_v2_stage2_contracts.py -q
```

**Step 3: Implement minimal builder logic**

- populate `thumb_data` from `stage1_handoff.contract.title_for_thumb`
- choose `ref_img` from deterministic candidate priority inside `runtime_v2/stage2/json_builders.py`
- do not let `runtime_v2/stage2/canva_worker.py` invent the policy

**Step 4: Run tests to verify they pass**

Run:
```bash
python -m pytest tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_stage2_workers.py -q
```

### Task 2. Asset manifest를 control-plane 단일 writer로 도입

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/result_router.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write failing tests**

- add a test proving a logical role->path manifest is written by control-plane only
- add a test proving workers return data for manifest update but do not write manifest themselves

**Step 2: Run tests to verify they fail**

Run:
```bash
python -m pytest tests/test_runtime_v2_control_plane_chain.py -q
```

**Step 3: Implement minimal manifest writing**

- define `asset_manifest.json` at the orchestration layer
- map logical roles such as `thumb_primary`, `image_primary`, `video_primary`, `voice_json`
- keep worker output passive; control-plane writes the manifest

**Step 4: Run tests to verify they pass**

Run:
```bash
python -m pytest tests/test_runtime_v2_control_plane_chain.py -q
```

### Task 3. Reused success marker를 공통 helper로 표준화

**Files:**
- Modify: `runtime_v2/workers/job_runtime.py`
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/stage3/render_worker.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_final_video_flow.py`

**Step 1: Write failing tests**

- add tests proving existing artifact can produce `ok(reused)` style success without re-running expensive work
- keep `blocked/failed/retryable` meanings unchanged

**Step 2: Run tests to verify they fail**

Run:
```bash
python -m pytest tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_final_video_flow.py -q
```

**Step 3: Implement minimal shared helper**

- introduce shared helper for `artifact exists -> reused success`
- expose the result as a normal success with explicit reused evidence
- do not let each worker improvise different meanings

**Step 4: Run tests to verify they pass**

Run:
```bash
python -m pytest tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_final_video_flow.py -q
```

### Task 4. Docs and verification bundle

**Files:**
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`
- Modify: `docs/plans/2026-03-09-runtime-v2-legacy-carryover-top3-plan.md`

**Step 1: Update docs**

- record what was implemented
- record what was intentionally not borrowed from legacy

**Step 2: Run final verification**

Run:
```bash
python -m py_compile runtime_v2/stage2/json_builders.py runtime_v2/control_plane.py runtime_v2/workers/job_runtime.py runtime_v2/stage2/genspark_worker.py runtime_v2/stage2/seaart_worker.py runtime_v2/stage2/canva_worker.py runtime_v2/stage3/render_worker.py
```

- run LSP diagnostics on modified files

---

## Not In Scope

- Excel을 다시 owner/state store로 복귀시키는 것
- legacy browser script를 직접 import/call 하는 것
- `control_plane` 2차 구조 분해를 재개하는 것
- service별 임시 fallback/retry 분기 추가

## Done Definition

- `canva` payload가 richer `thumb_data`와 deterministic ref image를 사용합니다.
- asset role -> actual path 관계를 `control plane`이 단일 writer로 기록합니다.
- reused success marker가 worker마다 다르지 않고 공통 helper semantics를 따릅니다.
- 모든 변경은 기존 failure contract를 유지합니다.

## Completion Note

- Task 1 완료:
  - `runtime_v2/stage2/json_builders.py`가 `canva` payload에 `thumb_data`와 deterministic `ref_img`를 채웁니다.
  - `thumb_data`는 `stage1_handoff.contract.title_for_thumb`를 반영하고, `ref_img`는 `genspark -> seaart` 우선순위로 선택합니다.
- Task 2 완료:
  - `runtime_v2/control_plane.py`가 `stage1 -> stage2` 라우팅 순간 `common_asset_folder/asset_manifest.json`을 단일 writer로 기록합니다.
  - 초기 role key는 `voice_json`, `image_primary`, `stage2.scene_{NN}.{workload}`, `thumb.scene_{NN}.canva`, `thumb_primary` 최소 집합으로 고정했습니다.
- Task 3 완료:
  - `runtime_v2/workers/external_process.py`가 `artifact exists -> reused success`를 공통 helper semantics로 처리합니다.
  - 적용 범위는 현재 adapter-backed worker(`genspark`, `seaart`, `geminigen`, `canva`, `qwen3_tts`, `rvc`)입니다.
  - `render_worker`는 아직 native 경계(`native_render_not_implemented`)이므로 이번 배치에서 제외했습니다.

## Fresh Verification

- `python -m pytest tests/test_runtime_v2_stage2_contracts.py::RuntimeV2Stage2ContractTests::test_canva_payload_includes_thumb_data_and_deterministic_ref_img -q`
- `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_control_plane_writes_asset_manifest_for_stage1_routed_jobs -q`
- `python -m pytest tests/test_runtime_v2_stage2_workers.py::RuntimeV2Stage2WorkerTests::test_genspark_worker_reuses_existing_output_as_success -q`
- `python -m pytest tests/test_runtime_v2_gpu_workers.py::RuntimeV2GpuWorkerTests::test_qwen3_worker_requires_adapter_command_to_create_fresh_output -q`
- `python -m py_compile runtime_v2/stage2/json_builders.py runtime_v2/control_plane.py runtime_v2/workers/external_process.py runtime_v2/stage2/genspark_worker.py runtime_v2/stage2/seaart_worker.py runtime_v2/stage2/canva_worker.py runtime_v2/stage2/geminigen_worker.py runtime_v2/workers/qwen3_worker.py runtime_v2/workers/rvc_worker.py tests/test_runtime_v2_stage2_contracts.py tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_stage2_workers.py tests/test_runtime_v2_gpu_workers.py`

# Runtime V2 Subprogram Core Logic Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`의 하부프로그램 핵심 로직을 `gpt -> seaart -> genspark -> canva -> geminigen` 순서로 하나씩 구현해, 1행 테스트 전에 각 프로그램이 최소 happy-path 산출물과 표준 evidence를 남기도록 만듭니다.

**Architecture:** 각 프로그램의 core logic는 `입력 계약 검증 -> 단일 실행 adapter 호출 -> 산출물 존재 검증 -> 표준 worker_result 반환`까지만 포함합니다. 재시도, backoff, 로그인 복구, queue 정책, latest-run writer는 상위 owner가 계속 소유하며, 워커는 fail-closed와 관측 가능한 evidence만 보장합니다.

**Document Status:** 이 문서는 구현 완료 보고가 아니라 실행 계획입니다. 아래 task/command/expected 항목은 앞으로 검증할 절차이며, 실제 완료 판정은 각 단계의 코드 변경과 명령 증거가 확인된 뒤에만 내립니다.

**Reference Boundary:** `D:\YOUTUBE_AUTO`의 기존 구현은 핵심 기능을 이해하기 위한 참고 입력만 제공합니다. `runtime_v2`는 자체 계약과 자체 adapter를 기준으로 재구성하며, 참고 저장소의 모듈/클래스/함수/상태모델을 직접 재사용, 포팅, 호출하지 않습니다.

**Tech Stack:** Python 3.13, `runtime_v2`, browser manager/supervisor, JSON contracts, file-based evidence, existing `tests/test_runtime_v2_stage1_chatgpt.py`, `tests/test_runtime_v2_stage2_workers.py`, `tests/test_runtime_v2_stage2_contracts.py`

---

## Current Audit

- `runtime_v2/stage1/chatgpt_runner.py`는 이미 `topic_spec -> video_plan.json -> next_jobs[]`까지의 최소 GPT core logic를 수행합니다.
- `runtime_v2/stage2/genspark_worker.py`, `runtime_v2/stage2/seaart_worker.py`, `runtime_v2/stage2/canva_worker.py`, `runtime_v2/stage2/geminigen_worker.py`는 현재 모두 `native_not_implemented_result(...)`로 종료합니다.
- `runtime_v2/stage2/json_builders.py`는 stage2 payload와 산출물 경로만 만들고, 실제 서비스 핵심 로직은 아직 비어 있습니다.
- 전용 참고 개발문서는 확인되지 않았습니다. 따라서 core logic 기준은 `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py`, `D:\YOUTUBE_AUTO\scripts\seaart_automation.py`, `D:\YOUTUBE_AUTO\scripts\genspark_automation.py`, `D:\YOUTUBE_AUTO\scripts\canva_automation.py`, `D:\YOUTUBE_AUTO\scripts\geminigen_automation.py`, `D:\YOUTUBE_AUTO\tests\test_geminigen_json_contract.py`의 docstring/테스트에서 참조 전용으로 추출합니다.

## Core Logic Definition (Locked)

각 하부프로그램의 core logic는 아래 4개만 포함합니다.

1. 입력 계약 검증 (`prompt`, `scene_index`, `service_artifact_path`, 추가 필수 필드)
2. 단일 실행 경로 호출 (서비스별 core function 1개)
3. 기대 산출물 파일 존재/확장자 검증
4. `worker_result` 표준 필드와 workspace evidence 기록

아래는 core logic에 포함하지 않습니다.

- 로그인 복구, 세션 교체, browser health 판정
- retry/backoff/circuit 정책
- Excel 직접 갱신
- placeholder 성공, fallback OK, 침묵 보정

## Non-Goals

- 참고 저장소의 모듈/클래스/함수 시그니처를 `runtime_v2`에 복제하지 않습니다.
- 참고 저장소 경로를 runtime 경로, adapter 경로, worker 경로에 의존성으로 연결하지 않습니다.
- 참고 저장소의 상태/에러/재시도 모델을 그대로 가져오지 않고 `runtime_v2` 계약으로 다시 정의합니다.

## Reference-Only Core Responsibilities (Reduced)

- GPT (`D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py`): topic을 구조화된 영상 계획으로 바꾸고, 다음 단계 입력(voice/scene/thumbnail seed)을 만든다.
- SeaArt (`D:\YOUTUBE_AUTO\scripts\seaart_automation.py`): 프롬프트를 받아 이미지 1개를 생성하고 다운로드한다.
- Genspark (`D:\YOUTUBE_AUTO\scripts\genspark_automation.py`): 프롬프트를 받아 이미지 1개를 생성하고 다운로드한다.
- Canva (`D:\YOUTUBE_AUTO\scripts\canva_automation.py`): `thumb_data`를 해석해 썸네일 PNG 1개를 만든다.
- GeminiGen (`D:\YOUTUBE_AUTO\scripts\geminigen_automation.py`, `D:\YOUTUBE_AUTO\tests\test_geminigen_json_contract.py`): 선택된 장면 입력을 바탕으로 mp4 1개를 만든다.

## Order Policy

구현 순서는 반드시 아래 순서를 지킵니다.

1. GPT
2. SeaArt
3. Genspark
4. Canva
5. GeminiGen

한 프로그램이 `contract + artifact + evidence + error_code`를 닫기 전에는 다음 프로그램으로 넘어가지 않습니다.

### Task 1: GPT Core Logic Audit And Hardening

**Files:**
- Modify: `runtime_v2/stage1/chatgpt_runner.py`
- Test: `tests/test_runtime_v2_stage1_chatgpt.py`

**Step 1: GPT core logic 완료 기준을 실패 테스트로 고정합니다**

```python
def test_stage1_chatgpt_emits_video_plan_and_next_jobs_without_placeholder_success():
    result = run_stage1_chatgpt_job(topic_spec, workspace, debug_log="logs/run.jsonl")
    assert result["status"] == "ok"
    assert Path(result["result_path"]).exists()
    assert result["next_jobs"]
```

**Step 2: 테스트를 실행해 현재 동작을 사실로 확정합니다**

Run: `python -m pytest tests/test_runtime_v2_stage1_chatgpt.py -q`
Expected: 현재 구현이 이미 core logic를 충족하면 PASS, 아니면 FAIL

**Step 3: GPT는 신규 구현보다 hardening만 적용합니다**

```python
video_plan = build_video_plan_from_topic_spec(topic_spec, workspace)
next_jobs, _ = route_video_plan(video_plan)
return finalize_worker_result(..., next_jobs=next_jobs)
```

**Step 4: 완료 기준을 문서화합니다**

- GPT는 browser automation 자체가 아니라 `topic_spec -> video_plan -> next_jobs`가 core logic임을 유지합니다.
- Stage1에서 Excel write나 browser 제어를 추가하지 않습니다.

### Task 2: SeaArt Core Logic Implementation

**Files:**
- Modify: `runtime_v2/stage2/seaart_worker.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`

**Step 1: SeaArt 성공 산출 계약 테스트를 추가합니다**

```python
def test_seaart_worker_writes_service_artifact_and_returns_ok(tmp_path):
    result = run_seaart_job(job, tmp_path / "artifacts")
    assert result["status"] == "ok"
    assert Path(job.payload["service_artifact_path"]).exists()
```

**Step 2: 테스트를 실행해 실패를 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k seaart`
Expected: 처음에는 `native_seaart_not_implemented`로 FAIL

**Step 3: SeaArt core function을 최소 구현합니다**

```python
artifact_path = Path(str(job.payload["service_artifact_path"]))
artifact_path.parent.mkdir(parents=True, exist_ok=True)
service_result = run_seaart_core(prompt=str(job.payload["prompt"]), output_path=artifact_path)
if not artifact_path.exists():
    return fail_closed_result(..., error_code="seaart_artifact_missing")
return finalize_worker_result(..., status="ok", artifacts=[artifact_path])
```

**Step 4: 재검증합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k seaart`
Expected: PASS

### Task 3: Genspark Core Logic Implementation

**Files:**
- Modify: `runtime_v2/stage2/genspark_worker.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`

**Step 1: Genspark 성공 산출 계약 테스트를 추가합니다**

```python
def test_genspark_worker_writes_service_artifact_and_returns_ok(tmp_path):
    result = run_genspark_job(job, tmp_path / "artifacts")
    assert result["status"] == "ok"
    assert Path(job.payload["service_artifact_path"]).exists()
```

**Step 2: 테스트를 실행해 실패를 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k genspark`
Expected: 처음에는 `native_genspark_not_implemented`로 FAIL

**Step 3: Genspark core function을 최소 구현합니다**

```python
artifact_path = Path(str(job.payload["service_artifact_path"]))
service_result = run_genspark_core(prompt=str(job.payload["prompt"]), output_path=artifact_path)
if not artifact_path.exists():
    return fail_closed_result(..., error_code="genspark_artifact_missing")
return finalize_worker_result(...)
```

**Step 4: 재검증합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k genspark`
Expected: PASS

### Task 4: Canva Core Logic Implementation

**Files:**
- Modify: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Modify: `runtime_v2/stage2/request_builders.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`

**Step 1: Canva 성공 산출 계약 테스트를 추가합니다**

```python
def test_canva_worker_creates_thumbnail_png_from_thumb_data(tmp_path):
    result = run_canva_job(job, tmp_path / "artifacts")
    assert result["status"] == "ok"
    assert Path(job.payload["service_artifact_path"]).suffix == ".png"
```

**Step 2: 테스트를 실행해 실패를 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k canva`
Expected: 처음에는 `native_canva_not_implemented`로 FAIL

**Step 3: Canva core function을 최소 구현합니다**

```python
thumb = build_canva_thumb_file(workspace, job.payload)
artifact_path = Path(str(job.payload["service_artifact_path"]))
service_result = run_canva_core(thumb_data_path=thumb, output_path=artifact_path)
if not artifact_path.exists():
    return fail_closed_result(..., error_code="canva_artifact_missing")
return finalize_worker_result(...)
```

**Step 4: 재검증합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k canva`
Expected: PASS

### Task 5: GeminiGen Input Contract First

**Files:**
- Modify: `runtime_v2/stage2/json_builders.py`
- Modify: `runtime_v2/contracts/stage2_contracts.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`

**Step 1: GeminiGen 입력 계약 테스트를 먼저 추가합니다**

```python
def test_stage2_contract_includes_geminigen_source_frame_reference(tmp_path):
    jobs, _ = build_stage2_jobs(video_plan)
    geminigen_job = next(job for job in jobs if job["job"]["worker"] == "geminigen")
    assert "source_frame_path" in geminigen_job["job"]["payload"]
```

**Step 2: 테스트를 실행해 현재 공백을 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py -q -k geminigen`
Expected: 현재 payload에 `source_frame_path`가 없어 FAIL

**Step 3: 계약을 최소 확장합니다**

```python
return {
    "run_id": run_id,
    "row_ref": row_ref,
    "scene_index": scene_index,
    "prompt": prompt,
    "asset_root": asset_root,
    "reason_code": reason_code,
    "source_frame_path": source_frame_path,
}
```

**Step 4: 계약 테스트를 다시 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py -q -k geminigen`
Expected: PASS

### Task 6: GeminiGen Core Logic Implementation

**Files:**
- Modify: `runtime_v2/stage2/geminigen_worker.py`
- Test: `tests/test_runtime_v2_stage2_workers.py`

**Step 1: GeminiGen 성공 산출 계약 테스트를 추가합니다**

```python
def test_geminigen_worker_creates_mp4_from_source_frame(tmp_path):
    result = run_geminigen_job(job, tmp_path / "artifacts")
    assert result["status"] == "ok"
    assert Path(job.payload["service_artifact_path"]).suffix == ".mp4"
```

**Step 2: 테스트를 실행해 실패를 확인합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k geminigen`
Expected: 처음에는 `native_geminigen_not_implemented`로 FAIL

**Step 3: GeminiGen core function을 최소 구현합니다**

```python
artifact_path = Path(str(job.payload["service_artifact_path"]))
service_result = run_geminigen_core(
    prompt=str(job.payload["prompt"]),
    source_frame_path=Path(str(job.payload["source_frame_path"])),
    output_path=artifact_path,
)
if not artifact_path.exists():
    return fail_closed_result(..., error_code="geminigen_artifact_missing")
return finalize_worker_result(...)
```

**Step 4: 재검증합니다**

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q -k geminigen`
Expected: PASS

### Task 7: Cross-Service Verification Gate

**Files:**
- Test: `tests/test_runtime_v2_stage2_workers.py`
- Test: `tests/test_runtime_v2_stage2_contracts.py`
- Test: `tests/test_runtime_v2_stage1_chatgpt.py`

**Step 1: 프로그램별 테스트를 모두 순차 실행합니다**

Run: `python -m pytest tests/test_runtime_v2_stage1_chatgpt.py -q`
Expected: PASS

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py -q`
Expected: PASS

Run: `python -m pytest tests/test_runtime_v2_stage2_workers.py -q`
Expected: PASS

**Step 2: guardrail 증거를 확인합니다**

Run: `python -m py_compile runtime_v2/stage1/chatgpt_runner.py runtime_v2/stage2/genspark_worker.py runtime_v2/stage2/seaart_worker.py runtime_v2/stage2/canva_worker.py runtime_v2/stage2/geminigen_worker.py runtime_v2/stage2/json_builders.py runtime_v2/contracts/stage2_contracts.py`
Expected: PASS

**Step 3: 완료 판정을 고정합니다**

- 각 프로그램은 `native_*_not_implemented`가 제거되어야 합니다.
- 각 프로그램은 `service_artifact_path`에 실제 파일을 남겨야 합니다.
- `run_id`, `error_code`, `attempt/backoff` 의미 drift가 없을 때만 다음 프로그램으로 진행합니다.

## Anti-Patterns (Do Not Reintroduce)

- 참고 저장소 스크립트 직접 호출 금지
- 워커 내부 retry/backoff/login recovery 금지
- 성공 산출물 없이 `ok` 반환 금지
- Excel 직접 쓰기 금지
- 서비스별 예외 분기 누적 금지

## Recommended Execution Mode

- 실제 구현은 한 세션에 한 프로그램만 진행합니다.
- 순서는 반드시 `gpt -> seaart -> genspark -> canva -> geminigen`입니다.
- 프로그램 하나 완료 후에만 다음 프로그램 계획을 활성화합니다.

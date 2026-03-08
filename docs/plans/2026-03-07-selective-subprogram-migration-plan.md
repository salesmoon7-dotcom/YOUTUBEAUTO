# Selective Subprogram Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 외부 참고 저장소의 브라우저/GPU 하부프로그램에서 꼭 필요한 장점만 선별해 `D:\YOUTUBEAUTO`의 `runtime_v2`에 이식하되, 새 프로그램은 디버깅이 쉽고 파이프라인이 단순하며 참고 구현의 장점만 유지하도록 만듭니다.

**Architecture:** 신규 프로그램의 단일 진실은 `runtime_v2/`와 `system/runtime_v2/`의 계약입니다. 외부 참고에서는 거대 오케스트레이션을 버리고, 세션 재사용 규칙, 감시형 subprocess, 아티팩트 계약, GPU 게이트 같은 정책/함수 단위만 추출하여 Control Plane -> Browser Plane -> GPU Leaf Worker -> Evidence Plane 구조 안에만 재배치합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, JSON contract/evidence, file lease/lock, FFmpeg, PowerShell TTS, browser registry/health, `unittest`, `python -m py_compile`

---

## 0) Locked Decisions

1. **직접 이식 금지:** `pipeline.py`, `master_manager.py`, `chatgpt_automation.py` 같은 대형 파일은 통째로 복사하지 않습니다.
2. **단순 파이프라인 고정:** seed는 상태가 아니라 queue를 채우는 단계로만 취급하고, control plane 상태는 `queued -> running -> completed|failed|retry`와 `next_jobs[]` 라우팅만 담당합니다.
3. **디버깅 우선:** 실패는 침묵 보정하지 않고 `debug_log`, `result.json`, `gui_status.json`, `control_plane_events.jsonl` 증거를 남긴 뒤 hard-fail 합니다.
4. **브라우저는 세션 인프라로만 이식:** 브라우저 로직은 job별 직접 실행기가 아니라 `registry`, `health`, `manager`, `probe` 정책으로 이식합니다.
5. **GPU는 leaf worker로만 이식:** GPU/미디어 프로그램은 모두 `runtime_v2/workers/*.py`와 `external_process.py` 뒤에 숨기고, control plane이 세부 명령을 직접 다루지 않게 합니다.
6. **선별 기준 3개:** 새 기능이 `디버깅 용이성`, `파이프라인 단순성`, `외부 참고 장점 유지`를 동시에 만족하지 못하면 이식하지 않습니다.
7. **`run_id` 단일성 유지:** browser/GPU/GPT/GUI/result snapshot은 control tick 기준 `run_id`를 공유하고, `job_id`는 별도 추적 필드로만 사용합니다.
8. **계획 정본 경로 고정:** 저장소 기준 계획 정본은 `docs/plans/`이고, `.sisyphus/plans/`는 리뷰용 미러로만 사용합니다.

## 1) Approach Options

### Option A: 외부 참고 흐름 직접 포팅
- 장점: 초기 체감 속도는 빠를 수 있습니다.
- 단점: 복잡도와 디버깅 실패 패턴까지 같이 이식됩니다.
- 판정: **금지**

### Option B: 외부 참고를 서브프로세스로 감싸는 어댑터 중심 방식
- 장점: 단기 연결은 쉽습니다.
- 단점: 새 프로그램 안에 블랙박스가 남고, debug/evidence 일관성이 깨집니다.
- 판정: **비상 백업용으로만 허용**

### Option C: 정책/계약/leaf worker만 선택 이식
- 장점: 새 프로그램의 경계를 유지하면서 외부 참고 장점만 흡수할 수 있습니다.
- 단점: 기능별 선별과 계약화 작업이 필요합니다.
- 판정: **권장안**

## 2) Reference Reuse Matrix

| Reference Source | 가져올 것 | 버릴 것 | New Target |
|---|---|---|---|
| `pipeline_common.py` | 상태 전이 표준, 결과 정규화 개념 | 대형 파이프라인 결합 가정 | `runtime_v2/state_machine.py`, `runtime_v2/result_router.py` |
| `json_generator.py` | 경로 계산/검증 규칙, atomic JSON 작성 패턴 | 엑셀/채널 결합 로직 | `runtime_v2/contracts/artifact_contract.py`, `runtime_v2/result_router.py` |
| `scripts/supervisor.py` | 24h 감시, 헬스 기반 선택 교체, 보호 포트/재기동 쿨다운 | n8n/cloudflared 특화 분기 | `runtime_v2/browser/supervisor.py`, `runtime_v2/recovery_policy.py` |
| `sub_runners.py` | stall 감지, stdout 캡처, evidence append 패턴 | GUI 결합, 범용 러너 비대화 | `runtime_v2/workers/external_process.py` |
| `scripts/chatgpt_automation.py` | 세션 보존 관점, canonical guard 발상, 브라우저 헬스 판단 단서 | giant Selenium 흐름, 엑셀 직접 갱신 | `runtime_v2/browser/manager.py`, `runtime_v2/browser/health.py`, `runtime_v2/browser/registry.py` |
| `scripts/qwen3_tts_automation.py` | 입력/출력/result json 규칙 | 거대 설정/로그 초기화 | `runtime_v2/workers/qwen3_worker.py` |
| `scripts/rvc_voice_convert.py` | 입력 staging, 모델 선택 규칙, 결과 메타 구조 | Applio 직접 제어 결합 | `runtime_v2/workers/rvc_worker.py` |
| `scripts/ken_burns_effect.py` | ffmpeg 품질 옵션, NVENC 감지 아이디어 | 효과 다양성 과다 옵션 | `runtime_v2/workers/kenburns_worker.py` |

## 2-1) Browser Feature Candidate Matrix

### 유지/축소 이식 후보

| 기능 후보 | 외부 참고 장점 | 적용 방식 | 단일 책임 소유자 | 디버깅 근거 |
|---|---|---|---|---|
| 디버그 포트 고정 세션 | 브라우저 세션 재사용과 attach 안정성 | 포트/프로필/서비스 기본값을 세션 객체에 고정 | `runtime_v2/browser/manager.py` | `browser_session_registry.json` |
| 절대경로 프로필 디렉터리 | 세션 경로 혼선 방지 | profile_dir을 항상 절대경로로 정규화 | `runtime_v2/browser/manager.py` | registry snapshot의 `profile_dir` |
| 헬스 스냅샷 생성 | 로그인/포트/세션 상태를 한 번에 요약 가능 | 세션별 healthy/unhealthy를 health payload로 기록만 수행 | `runtime_v2/browser/health.py` | `browser_health.json` |
| 헬스 요약 판정 | unhealthy service 목록과 availability 계산 | health payload 해석과 요약만 수행 | `runtime_v2/browser/probe.py` | summary output |
| unhealthy 세션만 교체 | 정상 브라우저를 괜히 재기동하지 않음 | restart threshold + cooldown 조건에서만 개별 재시작 | `runtime_v2/browser/supervisor.py` | `restarted_services`, health delta |
| 서비스별 세션 구분 | ChatGPT/Genspark/SeaArt/GeminiGen 책임 분리 | service/group/session_id를 세션 기본키로 유지 | `runtime_v2/browser/manager.py` | registry의 `service`, `group`, `session_id` |
| 브라우저 실행 전 probe | 이미 떠 있는 세션 재사용 가능 | 포트 probe 성공 시 launch 생략 | `runtime_v2/browser/manager.py` | launch 전후 상태 비교 |
| 강제 비정상 주입 테스트 | 복구 정책 회귀 테스트 가능 | `force_unhealthy_service` 기반 테스트 유지 | `runtime_v2/browser/supervisor.py` | test evidence + health snapshot |

### 버릴 기능 후보

| 버릴 기능 | 버리는 이유 | 금지 방식 | 대체 경계 |
|---|---|---|---|
| 거대 Selenium 작업 흐름 | 새 프로그램을 다시 외부 참고처럼 복잡하게 만듦 | `chatgpt_automation.py`류 직접 포팅 금지 | browser plane은 세션 인프라만 담당 |
| 엑셀 직접 갱신/상태 보정 | 파이프라인 단순성과 증거 일관성을 깨뜨림 | browser code에서 외부 상태 저장 금지 | control plane + evidence 계약 |
| 서비스별 특수 예외 누적 | 디버깅이 어려워지고 분기 폭증 | browser module에 서비스별 하드코딩 예외 추가 금지 | 공통 health/registry/restart 정책 |
| 브라우저 내부에서 job 실행 | control plane 경계를 무너뜨림 | browser module에서 worker/job routing 금지 | control plane의 `next_jobs[]`만 사용 |
| 묵시적 로그인 복구 | 실패 원인 추적을 어렵게 만듦 | 로그인 보정 자동화 금지 | unhealthy 판정 후 명시적 교체 |
| 무제한 재시작 | 장애 은폐와 세션 오염 위험 | threshold/cooldown 없는 restart 금지 | `BrowserSupervisor.tick()` 정책 |
| GUI 결합 로직 | 테스트와 재현성을 떨어뜨림 | browser module에서 GUI 직접 업데이트 금지 | snapshot 파일을 통해 GUI 반영 |

### 브라우저 표 차단 조건

1. 한 기능이 둘 이상의 browser 모듈에 동시에 소유되면 차단합니다.
2. `manager.py` 외 모듈이 세션/포트/profile_dir 생성 또는 browser launch를 담당하면 차단합니다.
3. `health.py`가 재시작, 세션 상태 변경, registry 변경까지 수행하면 차단합니다.
4. `registry.py`가 health 판정이나 restart 트리거까지 맡으면 차단합니다.
5. `supervisor.py`가 unhealthy 선택 교체를 넘어 스케줄러/정책 엔진처럼 비대해지면 차단합니다.

## 3) Execution Phases

### Task 1: 기능 선별 헌법과 금지 목록 고정

**Files:**
- Modify: `docs/plans/2026-03-07-selective-subprogram-migration-plan.md`
- Modify: `docs/plans/2026-03-06-separate-24h-runtime-rebuild-plan.md`
- Modify: `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md`

**Step 1: 실패 기준 테스트 문장 추가**

성공 기준을 문서에 아래처럼 고정합니다.

```md
- control plane이 브라우저/GPU 명령 세부를 직접 호출하면 실패
- 증거 파일 없이 자동 보정하면 실패
- 외부 참고 write 경로 접근이 생기면 실패
```

**Step 2: 문서 반영 후 드리프트 확인**

Run: `python -m compileall -q runtime_v2`
Expected: compile success

**Step 3: 설계 체크리스트 재검토**

아래 체크리스트를 모두 통과해야 합니다.

```md
- control plane이 `run_gated` 외에 브라우저/GPU 세부를 직접 호출하지 않는다
- 외부 참고 경로 write가 없다
- worker 계약 생성이 단일 함수로 통일된다
- evidence 없이 자동 보정하지 않는다
```

### Task 2: Browser Plane에 이식할 기능만 축소 정의

**Files:**
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/browser/health.py`
- Modify: `runtime_v2/browser/registry.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Test: `tests/test_runtime_v2_phase2.py`
- Create: `tests/test_runtime_v2_browser_plane.py`

**Step 1: 실패 테스트 작성**

```python
def test_browser_manager_replaces_only_unhealthy_sessions() -> None:
    ...

def test_registry_persists_absolute_profile_dir() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: 처음에는 FAIL일 수 있고, 이미 구현되어 있으면 PASS일 수 있습니다. PASS면 구현은 최소 변경으로 두고 테스트를 회귀 방지용으로 유지합니다.

**Step 3: 최소 구현**

```python
if session.healthy:
    return keep_existing
return replace_session
```

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: PASS

### Task 3: 감시형 subprocess 래퍼를 외부 참고 장점만 남기도록 강화

**Files:**
- Modify: `runtime_v2/workers/external_process.py`
- Modify: `runtime_v2/debug_log.py`
- Modify: `runtime_v2/result_router.py`
- Test: `tests/test_runtime_v2_phase2.py`
- Create: `tests/test_runtime_v2_external_process.py`

**Step 1: 실패 테스트 작성**

```python
def test_external_process_captures_stdout_stderr_timeout_and_command() -> None:
    ...

def test_external_process_writes_debug_evidence_on_failure() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_external_process -v`
Expected: 처음에는 FAIL일 수 있고, 이미 구현되어 있으면 PASS일 수 있습니다. PASS면 구현은 최소 변경으로 두고 테스트를 회귀 방지용으로 유지합니다.

**Step 3: 최소 구현**

```python
return {
    "exit_code": exit_code,
    "stdout": stdout,
    "stderr": stderr,
    "timed_out": timed_out,
    "timeout_sec": timeout_sec,
    "duration_sec": duration_sec,
    "command": command,
    "cwd": str(cwd),
}
```

타임아웃이나 예외가 발생해도 `TimeoutExpired`를 그대로 raise하지 말고, 위 계약 형태로 hard-fail 결과를 반환해야 합니다.

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_external_process -v`
Expected: PASS

### Task 4: GPU leaf worker를 계약 중심으로 재정렬

**Files:**
- Modify: `runtime_v2/workers/qwen3_worker.py`
- Modify: `runtime_v2/workers/rvc_worker.py`
- Modify: `runtime_v2/workers/kenburns_worker.py`
- Modify: `runtime_v2/contracts/artifact_contract.py`
- Test: `tests/test_runtime_v2_phase2.py`
- Create: `tests/test_runtime_v2_gpu_workers.py`

**Step 1: 실패 테스트 작성**

```python
def test_qwen3_worker_emits_rvc_next_job_contract() -> None:
    ...

def test_rvc_worker_emits_final_output_or_next_job_only() -> None:
    ...

def test_kenburns_worker_marks_final_output_true() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_gpu_workers -v`
Expected: 처음에는 FAIL일 수 있고, 이미 구현되어 있으면 PASS일 수 있습니다. PASS면 구현은 최소 변경으로 두고 테스트를 회귀 방지용으로 유지합니다.

**Step 3: 최소 구현**

```python
next_job = build_explicit_job_contract(...)
completion = {"state": "succeeded", "final_output": True}
```

워커별 로컬 `_next_job_contract` 복제를 금지하고, 다음 job 계약은 `runtime_v2/contracts/job_contract.py`의 단일 빌더 함수로만 생성합니다.

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_gpu_workers -v`
Expected: PASS

### Task 5: 파이프라인을 더 단순한 체인으로 고정

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/queue_store.py`
- Modify: `runtime_v2/state_machine.py`
- Modify: `runtime_v2/contracts/job_contract.py`
- Test: `tests/test_runtime_v2_phase2.py`
- Create: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: 실패 테스트 작성**

```python
def test_control_plane_reads_only_job_contract_and_next_jobs() -> None:
    ...

def test_control_plane_never_calls_browser_or_gpu_detail_directly() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_control_plane_chain -v`
Expected: 처음에는 FAIL일 수 있고, 이미 구현되어 있으면 PASS일 수 있습니다. PASS면 구현은 최소 변경으로 두고 테스트를 회귀 방지용으로 유지합니다.

**Step 3: 최소 구현**

```python
job = queue.next_runnable()
worker_result = run_worker(job)
seed(worker_result["next_jobs"])
```

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_control_plane_chain -v`
Expected: PASS

### Task 6: detached probe 기반 디버깅 경험을 고정

**Files:**
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/gui_adapter.py`
- Modify: `runtime_v2/browser/probe.py`
- Modify: `docs/sop/SOP_runtime_v2_detached_soak_readiness.md`
- Test: `tests/test_runtime_v2_phase2.py`

**Step 1: 실패 테스트 작성**

```python
def test_detached_probe_outputs_same_run_id_across_gui_result_browser_health() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_phase2 -v`
Expected: 처음에는 FAIL일 수 있고, 이미 구현되어 있으면 PASS일 수 있습니다. PASS면 구현은 최소 변경으로 두고 테스트를 회귀 방지용으로 유지합니다.

**Step 3: 최소 구현**

```python
payload["run_id"] = control_tick_run_id
payload["job_id"] = job.job_id
```

`run_id`는 control tick 기준으로 고정하고, `job_id`는 추적 메타데이터로만 분리합니다.

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_phase2 -v`
Expected: PASS

## 4) Pipeline Simplification Rules

1. Control plane 상태는 `queued`, `running`, `completed`, `failed`, `retry`만 허용합니다.
2. 브라우저 plane은 `세션 생성`, `세션 재사용`, `헬스 판정`, `비정상 교체`만 담당합니다.
3. 워커는 `입력 검증`, `workspace staging`, `외부 실행`, `worker_result 계약 반환`만 담당합니다.
4. 후속 체인은 `next_jobs[]`로만 연결합니다.
5. GUI와 evidence는 같은 `run_id`와 latest-run 의미를 공유해야 합니다.

## 5) Debuggability Requirements

1. 모든 실패에는 `error_code`, `stage`, `stdout`, `stderr`, `command`, `cwd`, `run_id`가 남아야 합니다.
2. 브라우저 교체 판단은 `browser_health.json`과 `browser_session_registry.json`만 보면 재현 가능해야 합니다.
3. GPU 락 실패는 `gpu_scheduler_health.json`에서 `event`, `workload`, `lock_key`, `lease`로 설명 가능해야 합니다.
4. control plane의 최종 판정은 `control_plane_events.jsonl`, `result.json`, `gui_status.json` 세 파일로 역추적 가능해야 합니다.

## 6) Verification Gates

### Commands

```bash
python -m unittest tests.test_runtime_v2_phase2 -v
python -m unittest tests.test_runtime_v2_browser_plane -v
python -m unittest tests.test_runtime_v2_external_process -v
python -m unittest tests.test_runtime_v2_gpu_workers -v
python -m unittest tests.test_runtime_v2_control_plane_chain -v
python -m compileall -q runtime_v2
```

### Must Pass

- browser unhealthy instance만 교체되고 healthy session은 유지됨
- GPU duplicate run = 0 유지
- worker 결과는 `next_jobs[]` 또는 `final_output=true` 중 하나로만 종결됨
- control plane은 브라우저/GPU 세부 구현을 직접 다루지 않음
- detached evidence의 `run_id`와 latest-run 의미가 끝까지 일치함

## 7) Done Definition

1. 새 프로그램이 외부 참고보다 디버깅이 쉬워졌다고 evidence 파일만으로 설명 가능합니다.
2. 새 프로그램의 제어 흐름을 `control_plane.py`와 워커 계약만 읽고 이해할 수 있습니다.
3. 외부 참고의 장점은 유지되지만, 외부 참고의 거대 오케스트레이션과 암묵적 보정은 사라집니다.
4. Oracle과 Momus 검토에서 “외부 참고 복잡도 재유입” 경고가 남지 않습니다.

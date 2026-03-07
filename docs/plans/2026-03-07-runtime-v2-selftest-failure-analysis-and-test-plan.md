# Runtime V2 Selftest Failure Analysis And Test Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** detached selftest 실패 원인을 증거 기준으로 고정하고, 이후 테스트를 어떤 순서로 재현/분리/검증해야 하는지 안전하게 정의합니다.

**Architecture:** 현재 detached selftest는 끝까지 실행되며, 실패 원인은 tool interruption이 아니라 browser health gate입니다. 따라서 다음 테스트는 `도구 안정성`이 아니라 `브라우저 포트 가용성 -> browser summary -> selftest check` 순서로 분리해서 확인해야 합니다.

**Tech Stack:** Python 3.13, `runtime_v2/cli.py`, `runtime_v2/supervisor.py`, `runtime_v2/browser/manager.py`, `runtime_v2/browser/supervisor.py`, detached probe result collection

---

## 1. 증거 기반 실패 분석

### 확인된 사실

1. 포그라운드 `python -m runtime_v2.cli --selftest`는 wrapper 환경에서 `KeyboardInterrupt`로 끊길 수 있습니다.
2. 그러나 detached/isolated probe는 실제로 끝까지 실행되어 `system/runtime_v2_probe/probe_result.json`을 남깁니다.
3. detached probe 결과는 `SELFTEST_FAIL`이며, 핵심 실패는 browser health 관련 check입니다.

### 핵심 증거

**Files:**
- `system/runtime_v2_probe/probe_result.json`
- `system/runtime_v2_probe/health/browser_health.json`
- `system/runtime_v2_probe/health/browser_session_registry.json`
- `runtime_v2/supervisor.py`
- `runtime_v2/browser/manager.py`
- `runtime_v2/browser/supervisor.py`
- `runtime_v2/browser/probe.py`

### 압축된 원인 진술

현재 가장 강한 원인 가설은 아래와 같습니다.

1. detached selftest 자체는 정상 종료됩니다.
2. selftest 내부 `run_once()`는 browser health gate를 통과해야 합니다.
3. `runtime_v2/browser/manager.py`는 `127.0.0.1:9222/9333/9444/9555` 포트를 직접 probe합니다.
4. probe 결과가 전부 unhealthy여서 `runtime_v2/browser/probe.py`의 `all_healthy`가 `false`로 계산됩니다.
5. 그 결과 `runtime_v2/supervisor.py`는 browser fail path를 따라가고, detached selftest 전체가 `SELFTEST_FAIL`이 됩니다.

### 이 문서 시점의 판정

- `도구 중단` 문제: detached probe로 우회 가능
- `코드 무한대기` 문제: 현재 증거상 아님
- `실제 selftest 실패` 문제: browser availability 미충족이 가장 유력

---

## 2. 테스트 원칙

### Rule 1
- 운영 경로 `system/runtime_v2/`를 직접 쓰지 말고, 우선 `--selftest-detached --probe-root ...`로 격리 실행합니다.

### Rule 2
- 한 번에 하나만 확인합니다.
- 먼저 브라우저 포트 가용성, 다음 browser registry/health summary, 마지막 selftest 전체 결과를 봅니다.

### Rule 3
- `SELFTEST_FAIL`만 보면 안 되고, 반드시 아래 3개를 함께 읽습니다.
  - `probe_result.json`
  - `health/browser_health.json`
  - `health/browser_session_registry.json`

---

## 3. 테스트 단계

### Task 1: Detached Probe 재현

**Files:**
- Run: `runtime_v2/cli.py`
- Evidence: `<probe_root>/probe_result.json`
- Evidence: `<probe_root>/logs/selftest_stdout.log`
- Evidence: `<probe_root>/logs/selftest_stderr.log`

**Step 1: 새 probe root를 준비합니다**

예시:

```bash
python -m runtime_v2.cli --selftest-detached --probe-root "system/runtime_v2_probe/recheck-01"
```

**Step 2: 생성 파일을 확인합니다**

- `probe_result.json` 존재
- `logs/selftest_stdout.log` 존재
- `logs/selftest_stderr.log` 존재

**Pass Criteria:**
- detached probe가 정상 spawn되고 결과 파일이 남음

### Task 2: 브라우저 포트 가용성 분리 확인

**Files:**
- Reference: `runtime_v2/browser/manager.py`
- Evidence: `<probe_root>/health/browser_health.json`

**Step 1: 다음 포트의 실제 상태를 확인합니다**

- `9222`
- `9333`
- `9444`
- `9555`

**Step 2: `browser_health.json`의 `healthy_count`, `unhealthy_count`, `sessions[].healthy`와 대조합니다**

**Pass Criteria:**
- 포트 상태와 `browser_health.json`이 일치함

### Task 3: Browser Restart 경로 확인

**Files:**
- Reference: `runtime_v2/browser/supervisor.py`
- Evidence: `<probe_root>/health/browser_session_registry.json`

**Step 1: `restart_count`, `consecutive_failures`, `last_restart_at`를 확인합니다**

**Step 2: 아래를 판정합니다**

- restart가 전혀 일어나지 않았는지
- restart는 일어났지만 probe는 계속 unhealthy인지

**Pass Criteria:**
- 실패가 “restart 미실행”인지 “restart 후에도 unhealthy 유지”인지 분명히 분리됨

### Task 4: Selftest Check 단위 판정

**Files:**
- Reference: `runtime_v2/supervisor.py`
- Evidence: `<probe_root>/probe_result.json`

**Step 1: `checks[]`를 이름별로 분리합니다**

핵심 체크:
- `gpu_lease_contention`
- `lease_release_then_run`
- `browser_health_fail_path`
- `gpt_floor_fail_path`

**Step 2: 어떤 체크가 pass/fail인지 표로 정리합니다**

**Pass Criteria:**
- selftest 전체 실패가 어떤 check 조합 때문인지 분명히 보임

### Task 5: 브라우저 준비 후 재검증

**Files:**
- Run: `runtime_v2/cli.py`
- Evidence: 새 `<probe_root>/probe_result.json`

**Step 1: 브라우저 포트가 실제로 열려 있는 상태를 먼저 만듭니다**

**Step 2: detached probe를 다시 실행합니다**

```bash
python -m runtime_v2.cli --selftest-detached --probe-root "system/runtime_v2_probe/recheck-02"
```

**Step 3: 이전 probe와 비교합니다**

비교 항목:
- `healthy_count`
- `all_healthy`
- `SELFTEST_FAIL` -> `OK` 변경 여부

**Pass Criteria:**
- 브라우저 준비 상태가 selftest 결과를 실제로 바꾸는지 입증됨

---

## 4. 테스트 결과 해석 규칙

### Case A: 포트가 닫혀 있고 health도 unhealthy
- 코드 문제보다 환경/브라우저 미기동 문제로 판정합니다.

### Case B: 포트는 열려 있는데 health가 unhealthy
- probe/registry/summary 경로를 추가 분석 대상으로 올립니다.

### Case C: 포트가 열리고 health가 healthy인데 selftest가 계속 실패
- browser gate 이후의 다른 check(`GPU`, `GPT`)를 다음 원인으로 넘깁니다.

---

## 5. 이 문서 시점의 최우선 가설

현재 최우선 가설은 다음 한 줄입니다.

> detached selftest 실패의 직접 원인은 browser health gate이며, 그 근본 원인은 selftest probe 시점에 기대 포트(9222/9333/9444/9555)가 실제로 열려 있지 않아서 `all_healthy=false`가 유지되는 것입니다.

이 가설은 아래 증거로 지지됩니다.

- `probe_result.json`에서 브라우저 관련 observed payload가 모두 unhealthy
- `browser_health.json`에서 `healthy_count=0`, `unhealthy_count=4`
- `browser_session_registry.json`에서 restart 이후에도 각 세션이 unhealthy
- `browser/manager.py`가 health를 실제 로컬 포트 probe로 계산함

---

## 6. 해결 결과

- `runtime_v2/browser/manager.py`에서 브라우저 `profile_dir`를 절대경로로 정규화하도록 수정해 `--user-data-dir=runtime_v2\sessions\...` 상대경로 런치 실패를 제거했습니다.
- `runtime_v2/supervisor.py`에서 acquire 직후 즉시 `renew()`를 다시 호출하던 경로를 제거해 Windows 파일 락 타이밍 때문에 `GPU_LEASE_BUSY`로 오판하던 selftest 실패를 없앴습니다.
- `runtime_v2/gpu/lease.py`에서 현재 프로세스 PID의 lease를 stale로 보지 않도록 보강해 selftest의 `gpu_lease_contention` 체크가 안정적으로 유지되게 했습니다.
- detached 재검증 증거:
  - `system/runtime_v2_probe/selftest-run-06/probe_result.json` -> `status=ok`, `code=OK`, `exit_code=0`
  - `system/runtime_v2_probe/selftest-run-06/health/browser_health.json` -> `healthy_count=4`, `unhealthy_count=0`
  - `system/runtime_v2_probe/selftest-run-06/logs/selftest_stdout.log` -> `run_finished`, `code=OK`

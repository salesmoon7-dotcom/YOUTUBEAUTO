# Runtime V2 Console Debug Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`의 콘솔 출력은 핵심 상태만 보여주고, 상세 디버깅 정보는 별도 로그 파일에 구조적으로 남기도록 고정합니다.

**Architecture:** 공통 debug log writer를 추가해 `cli`, `control_plane`, `runtime_v2_manager_gui`가 같은 JSONL 로그 파일을 사용합니다. 콘솔과 GUI 최근 실행 문구는 요약 정보만 노출하고, 원인 분석에 필요한 상세 payload는 debug log 및 기존 worker result/manifest 경로로 연결합니다.

**Tech Stack:** Python 3.13, JSONL append logging, existing runtime_v2 config/evidence contracts

---

### Task 1: 공통 debug log writer 추가

**Files:**
- Create: `runtime_v2/debug_log.py`
- Modify: `runtime_v2/config.py`

**Steps:**
1. `system/runtime_v2/logs/runtime_v2_debug.jsonl` 기본 경로를 `RuntimeConfig`에 추가합니다.
2. JSONL append writer와 예외 trace 수집 helper를 `runtime_v2/debug_log.py`에 추가합니다.
3. control/cli/gui가 공통으로 쓸 수 있는 요약 함수도 같은 파일에 둡니다.

### Task 2: 콘솔 출력 축소 + 상세 로그 파일 기록

**Files:**
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/control_plane.py`

**Steps:**
1. CLI stdout 이벤트는 `run_id`, `mode`, `status`, `code`, `exit_code`, `job_id`, `workload`, `stage`, `debug_log` 중심의 짧은 JSON만 출력합니다.
2. CLI가 출력하던 전체 payload/result/callback 내용은 debug log 파일에 기록합니다.
3. control plane은 idle/seeded/job-run 결과를 debug log에 상세 기록해, worker_result/recovery/invalid_reason/result_path 등을 중앙 로그에서 추적 가능하게 합니다.

### Task 3: GUI 최근 실행 문구 축약 + 예외 로그 보강

**Files:**
- Modify: `runtime_v2_manager_gui.py`

**Steps:**
1. GUI 최근 실행/로그 버퍼에는 핵심 상태만 남기도록 문자열 요약을 교체합니다.
2. control loop 예외와 dashboard refresh 예외는 debug log 파일에도 기록합니다.
3. operator가 로그 파일 경로를 추적할 수 있도록 요약 문구에 debug log 위치를 포함합니다.

### Task 4: 검증

**Files:**
- Verify: `runtime_v2/debug_log.py`
- Verify: `runtime_v2/config.py`
- Verify: `runtime_v2/cli.py`
- Verify: `runtime_v2/control_plane.py`
- Verify: `runtime_v2_manager_gui.py`

**Steps:**
1. 수정 파일 전체 `lsp_diagnostics` 0건을 확인합니다.
2. `python -m py_compile`로 관련 파일 문법 검증을 수행합니다.
3. 프로젝트 verify 스킬을 실행해 추가 규칙 위반이 없는지 확인합니다.

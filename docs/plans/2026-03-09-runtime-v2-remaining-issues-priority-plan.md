# Runtime V2 Remaining Issues Priority Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 남아 있는 `runtime_v2` 문제를 `지금 바로 고칠 것`, `운영 환경 정리 후 할 것`, `지금은 건드리지 말 것`으로 나눠 실행 우선순위를 고정합니다.

**Architecture:** 코드 구조 자체보다 운영 readiness와 의미 해석의 혼선을 먼저 줄입니다. 즉시 실행 항목은 `placeholder probe 성공`과 `real readiness`를 출력/문서에서 분리하는 작업이고, 환경 blocker(`seaart`, `geminigen`)와 richer stage1 parity는 후속 단계로 남깁니다.

**Tech Stack:** Python 3.13, runtime_v2 CLI/probe output, docs/TODO/COMPLETED, pytest, py_compile, LSP diagnostics

---

## Priority Matrix

### 1. 지금 바로 고칠 것

- `placeholder probe 성공`과 `실제 운영 readiness`를 출력/문서에서 더 명확히 분리
- 근거:
  - `runtime_v2/cli.py:819`-`runtime_v2/cli.py:845`
  - `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py:116`
  - `docs/plans/2026-03-09-agent-browser-live-readiness-report.md:43`-`docs/plans/2026-03-09-agent-browser-live-readiness-report.md:48`
- 이유:
  - 지금은 `probe_result.json`이 `code=OK`여도 placeholder fallback이 섞일 수 있어, 운영 준비 상태를 읽는 사람이 혼동하기 쉽습니다.
  - 이건 코드 버그보다 의미/증거 해석 문제라서 대전제(디버깅 용이성, 단일 의미 권한)에 직접 연결됩니다.

### 2. 운영 환경 정리 후 할 것

- `seaart:9444`, `geminigen:9555` CDP attach 환경 blocker 해결
- stage1 richer field parity(`title/title_for_thumb/description/keywords/bgm/#01...`) 보강
- 근거:
  - `docs/TODO.md:24`-`docs/TODO.md:27`
  - `docs/plans/2026-03-09-agent-browser-live-readiness-report.md:70`-`docs/plans/2026-03-09-agent-browser-live-readiness-report.md:79`
  - `docs/plans/2026-03-09-runtime-v2-legacy-pipeline-feasibility-plan.md:197`
- 이유:
  - 둘 다 가치가 크지만, 현재는 코드만 수정해도 닫히지 않거나 운영 환경/실브라우저 증거가 필요합니다.

### 3. 지금은 건드리지 말 것

- `control_plane.py` 2차 구조 분해(특히 worker dispatch 분리)
- 근거:
  - `docs/plans/2026-03-09-control-plane-feeder-decomposition-plan.md:13`
- 이유:
  - Oracle 판단상 현재 남은 복잡도는 의미 drift보다 응집된 orchestration에 가깝고, 지금 더 쪼개면 디버깅 파일 점프만 늘어날 가능성이 큽니다.

---

## Immediate Execution Plan

### Task 1. Probe/readiness semantics 명시 테스트 추가

**Files:**
- Modify: `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py`
- Modify: `runtime_v2/cli.py`

**Do:**
- `stage2_row1` probe report가 다음을 명시하도록 테스트를 추가합니다.
  - probe scope
  - placeholder 사용 서비스 목록
  - live attach ready 서비스 목록
  - overall live readiness level

### Task 2. CLI probe output에 semantics 필드 추가

**Files:**
- Modify: `runtime_v2/cli.py`

**Do:**
- 기존 `status/code/exit_code`는 유지하되, `probe_result.json`에
  - `readiness_scope`
  - `live_readiness`
  - `placeholder_services`
  - `live_ready_services`
  - `probe_success`
  를 추가합니다.

### Task 3. 문서에서 probe success와 readiness를 분리 서술

**Files:**
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`
- Modify: `docs/plans/2026-03-09-agent-browser-live-readiness-report.md`
- Modify: `docs/plans/2026-03-09-runtime-v2-remaining-issues-priority-plan.md`

**Do:**
- `detached row1 probe code=OK`는 probe success일 뿐, 전체 live readiness `Go`와 같지 않다고 문구를 고정합니다.

## Done Definition

- `probe_result.json`만 보고도 placeholder 경유인지, live attach 준비가 얼마나 되었는지 분리해서 읽을 수 있습니다.
- 문서와 출력이 같은 의미를 사용합니다.
- 환경 blocker와 코드 blocker가 더 이상 같은 문장으로 섞이지 않습니다.

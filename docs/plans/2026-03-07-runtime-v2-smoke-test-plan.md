# Runtime V2 Smoke Test Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`를 실제 스모크테스트에 올리기 전에 준비 체크, 실행 순서, 통과 기준, 증거 수집 경로를 고정합니다.

**Architecture:** 스모크테스트는 가장 가벼운 순서로 진행합니다. 먼저 `--selftest`로 진입 경로와 스냅샷 기록을 확인하고, 다음으로 `--control-once`로 queue/control loop를 확인한 뒤, 마지막으로 explicit inbox contract 기반 단일 체인(`qwen3_tts -> rvc -> kenburns`)을 확인합니다. 현재는 테스트 중단 상태이므로 이 문서는 실행 계획과 증거 기준만 고정합니다.

**Tech Stack:** Python 3.13, `runtime_v2/cli.py`, `runtime_v2_manager_gui.py`, ffmpeg, Windows SAPI, JSON snapshots, JSONL evidence

---

### Task 1: 사전 준비 체크

**Files:**
- Reference: `docs/sop/SOP_runtime_v2_inbox_contract.md`
- Reference: `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- Reference: `runtime_v2/config.py`
- Reference: `tests/test_runtime_v2_phase2.py`

**Steps:**
1. `system/runtime_v2/health/`, `system/runtime_v2/evidence/`, `system/runtime_v2/inbox/`, `system/runtime_v2/artifacts/`, `system/runtime_v2/logs/` 존재 여부를 확인합니다.
2. `ffmpeg` 접근 가능 여부를 확인합니다.
3. Windows SAPI 음성 출력이 가능한 환경인지 확인합니다.
4. 브라우저/GPT/GPU 관련 최신 snapshot 경로를 메모합니다.

**Pass Criteria:**
- 필수 디렉터리와 실행 파일 접근 경로가 모두 준비됨
- 스모크테스트가 레거시 경로를 건드리지 않음

### Task 2: CLI Selftest 스모크

**Files:**
- Reference: `runtime_v2/cli.py`
- Reference: `runtime_v2/supervisor.py`
- Evidence: `system/runtime_v2/health/gui_status.json`
- Evidence: `system/runtime_v2/health/gpu_scheduler_health.json`
- Evidence: `system/runtime_v2/logs/*.jsonl`

**Steps:**
1. 아래 명령으로 selftest를 실행합니다.

```bash
python -m runtime_v2.cli --selftest
```

2. 종료 코드와 stdout 요약 JSON을 기록합니다.
3. 생성된 per-run debug log 경로를 기록합니다.
4. `gui_status.json`, `gpu_scheduler_health.json`이 최신 run 기준으로 갱신됐는지 확인합니다.

**Pass Criteria:**
- CLI가 비정상 예외 없이 종료됨
- stdout에는 요약 정보만 표시됨
- debug log 파일에 상세 payload가 남음

### Task 3: Control Loop 단건 스모크

**Files:**
- Reference: `runtime_v2/control_plane.py`
- Evidence: `system/runtime_v2/state/job_queue.json`
- Evidence: `system/runtime_v2/evidence/control_plane_events.jsonl`
- Evidence: `system/runtime_v2/health/gui_status.json`
- Evidence: `system/runtime_v2/evidence/result.json`

**Steps:**
1. 아래 명령으로 control loop 단건 실행을 수행합니다.

```bash
python -m runtime_v2.cli --control-once
```

2. `job_queue.json` 상태와 `control_plane_events.jsonl`에 `queued -> running -> completed|failed|retry` 또는 `stale_running_recovered`/`job_summary` 이벤트가 기록되는지 확인합니다.
3. `gui_status.json`과 `result.json`이 같은 latest-run 의미로 갱신되는지 확인합니다.

**Pass Criteria:**
- queue/control loop 진입이 정상 동작함
- transition evidence와 latest-run snapshot이 함께 갱신됨

### Task 4: Explicit Inbox Contract 스모크

**Files:**
- Reference: `docs/sop/SOP_runtime_v2_inbox_contract.md`
- Evidence: `system/runtime_v2/inbox/accepted/`
- Evidence: `system/runtime_v2/inbox/invalid/`
- Evidence: `system/runtime_v2/artifacts/`
- Evidence: `system/runtime_v2/logs/*.jsonl`

**Steps:**
1. `system/runtime_v2/inbox/qwen3_tts/`에 유효한 `*.job.json` 1개를 준비합니다.
2. 필요 시 연결 이미지 입력을 함께 준비해 `qwen3_tts -> rvc -> kenburns` 체인을 확인합니다.
3. 아래 명령으로 control loop를 실행합니다.

```bash
python -m runtime_v2.cli --control-once
```

mock chain probe를 쓰는 경우 예시:

```bash
python -m runtime_v2.cli --control-once-detached --seed-mock-chain --probe-root "system/runtime_v2_probe/mock-chain-01"
```

4. 입력이 `accepted/` 또는 `invalid/`로 아카이브되는지 확인합니다.
5. 산출물이 `system/runtime_v2/artifacts/`에 남고, `result.json` metadata에 `chain_depth`, `routed_from`, `next_jobs_count`, `routed_count`, `completion_state`, `worker_error_code`가 반영되는지 확인합니다.

**Pass Criteria:**
- explicit inbox contract 해석이 정상 동작함
- 체인과 evidence metadata가 함께 갱신됨
- detached mock chain에서는 `probe_result.json`, `result.json`, `control_plane_events.jsonl`, `_mock/` artifact가 같은 probe root 아래 정렬됨

### Task 5: GUI 스모크 확인

**Files:**
- Reference: `runtime_v2_manager_gui.py`
- Evidence: `system/runtime_v2/health/gui_status.json`
- Evidence: `system/runtime_v2/evidence/control_plane_events.jsonl`
- Evidence: `system/runtime_v2/logs/*.jsonl`

**Steps:**
1. `python runtime_v2_manager_gui.py`로 GUI를 실행합니다.
2. 실패 발생 시 `stage`, `error_code`, `result_path` 또는 `manifest_path`가 즉시 보이는지 확인합니다.
3. Logs 패널에서 `job_summary`, `stale_running_recovered`, `next_job_rejected`가 사람이 읽는 한 줄로 보이는지 확인합니다.

**Pass Criteria:**
- GUI가 latest-run 상태를 즉시 반영함
- 실패 원인과 파일 위치를 GUI에서 바로 찾을 수 있음

### Task 6: 스모크테스트 판정 및 후속 분기

**Files:**
- Evidence: `system/runtime_v2/health/*.json`
- Evidence: `system/runtime_v2/evidence/result.json`
- Evidence: `system/runtime_v2/evidence/control_plane_events.jsonl`
- Evidence: `system/runtime_v2/logs/*.jsonl`

**Steps:**
1. 각 단계별 종료 코드, stdout 요약, debug log 경로를 표로 정리합니다.
2. 실패 시 `error_code`, `stage`, `result_path`, `manifest_path`, `debug_log`를 묶어 원인 분석 티켓을 만듭니다.
3. 전 단계 PASS인 경우에만 장시간 soak 준비 단계로 넘깁니다.

**Pass Criteria:**
- 실행 증거가 경로 단위로 정리됨
- 스모크 PASS/FAIL를 명확히 판단할 수 있음

---

## Current Completion Note

- detached selftest 증거는 `system/runtime_v2_probe/selftest-run-07/`에서 `probe_result.json`, `evidence/result.json`, `health/browser_health.json`이 같은 `run_id`를 공유하는 상태로 정렬되었습니다.
- detached control idle 증거는 `system/runtime_v2_probe/control-idle-run-01/`에서 `probe_result.json`, `health/gui_status.json`, `evidence/result.json`, `health/browser_health.json`이 같은 `run_id`를 공유합니다.
- detached mock chain 증거는 `system/runtime_v2_probe/mock-chain-run-05/`에서 `probe_result.json`, `health/gui_status.json`, `evidence/result.json`, `control_plane_events.jsonl`이 같은 latest-run 의미를 유지하며, 체인 완료 이력은 `job_summary` 이벤트로 남습니다.
- soak/실운영 준비용 분리 체크리스트는 `docs/sop/SOP_runtime_v2_detached_soak_readiness.md`를 기준으로 사용합니다.

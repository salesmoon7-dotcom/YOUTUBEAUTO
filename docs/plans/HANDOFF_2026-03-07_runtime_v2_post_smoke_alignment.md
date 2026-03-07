# HANDOFF: Runtime V2 Post Smoke Alignment

## 1. Current State

- `runtime_v2` 코드 구현 범위는 완료 상태입니다.
- detached selftest, detached control idle, detached mock chain 증거 정렬까지 끝났습니다.
- 현재 남은 것은 코드 수정이 아니라 실제 장시간 운영 실행 후 `soak_24h_report.md`를 채우는 단계뿐입니다.

## 2. What Was Completed In This Session

- browser unhealthy/selftest 실패를 해결했습니다.
  - `runtime_v2/browser/manager.py`에서 browser `profile_dir`를 절대경로로 정규화했습니다.
  - `runtime_v2/supervisor.py`, `runtime_v2/gpu/lease.py`에서 lease 오판과 stale 판정을 정리했습니다.
- detached evidence metadata를 정렬했습니다.
  - `runtime_v2/control_plane.py`, `runtime_v2/cli.py`, `runtime_v2/browser/health.py`, `runtime_v2/browser/registry.py`, `runtime_v2/browser/supervisor.py`, `runtime_v2/bootstrap.py`, `runtime_v2/gui_adapter.py` 수정
  - `probe_result.json`, `evidence/result.json`, `health/gui_status.json`, `health/browser_health.json`이 같은 `run_id`와 latest-run 의미를 공유하도록 맞췄습니다.
- GUI에서 latest-run idle 상태와 마지막 final output 완료 상태를 더 명확히 보이도록 했습니다.
  - `runtime_v2_manager_gui.py`에서 `Result` 패널이 latest-run과 latest final artifact를 함께 표시합니다.
- soak 준비 체크리스트를 smoke 계획에서 분리했습니다.
  - `docs/sop/SOP_runtime_v2_detached_soak_readiness.md` 추가
  - `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md`, `docs/plans/2026-03-07-runtime-v2-smoke-test-plan.md`, `docs/INDEX.md`, `docs/TODO.md`, `docs/COMPLETED.md` 정리

## 3. Key Evidence To Trust

### 3.1 Selftest PASS

- `system/runtime_v2_probe/selftest-run-07/probe_result.json`
  - `code=OK`
  - `exit_code=0`
- `system/runtime_v2_probe/selftest-run-07/evidence/result.json`
  - `metadata.run_id`가 selftest UUID와 일치
- `system/runtime_v2_probe/selftest-run-07/health/browser_health.json`
  - 같은 `run_id`
  - `healthy_count=4`

### 3.2 Control Idle Latest-Run Alignment

- `system/runtime_v2_probe/control-idle-run-01/probe_result.json`
  - `status=idle`
  - `code=NO_JOB`
- `system/runtime_v2_probe/control-idle-run-01/evidence/result.json`
  - same `run_id`
- `system/runtime_v2_probe/control-idle-run-01/health/gui_status.json`
  - same `run_id`
- `system/runtime_v2_probe/control-idle-run-01/health/browser_health.json`
  - same `run_id`

### 3.3 Mock Chain Final Output Proof

- `system/runtime_v2_probe/mock-chain-run-05/evidence/control_plane_events.jsonl`
  - 마지막 `job_summary`에서:
    - `completion_state=completed`
    - `final_output=true`
    - `final_artifact=kenburns-rvc-mock-chain-qwen3.mp4`
    - `final_artifact_path=system\\runtime_v2_probe\\mock-chain-run-05\\artifacts\\_mock\\kenburns\\kenburns-rvc-mock-chain-qwen3.mp4`

## 4. Canonical Docs

- `docs/TODO.md`
- `docs/COMPLETED.md`
- `docs/INDEX.md`
- `docs/plans/2026-03-06-separate-24h-runtime-rebuild-plan.md`
- `docs/plans/2026-03-07-runtime-v2-smoke-test-plan.md`
- `docs/sop/SOP_runtime_v2_inbox_contract.md`
- `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- `docs/sop/SOP_runtime_v2_detached_soak_readiness.md`

## 5. Files Most Recently Touched

- `runtime_v2/browser/manager.py`
- `runtime_v2/browser/health.py`
- `runtime_v2/browser/registry.py`
- `runtime_v2/browser/supervisor.py`
- `runtime_v2/supervisor.py`
- `runtime_v2/gpu/lease.py`
- `runtime_v2/control_plane.py`
- `runtime_v2/cli.py`
- `runtime_v2/bootstrap.py`
- `runtime_v2/gui_adapter.py`
- `runtime_v2_manager_gui.py`
- `docs/TODO.md`
- `docs/COMPLETED.md`
- `docs/INDEX.md`
- `docs/plans/2026-03-07-runtime-v2-smoke-test-plan.md`
- `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- `docs/sop/SOP_runtime_v2_detached_soak_readiness.md`

## 6. Verification Already Completed

- Oracle review completed for the final minimal batch
  - session/task reference: `bg_fcee0fa7`
- `lsp_diagnostics`
  - modified Python files were verified clean at the end of the session
- `python -m py_compile`
  - runtime files and `runtime_v2_manager_gui.py` compiled successfully
- detached runtime evidence
  - selftest PASS: `selftest-run-07`
  - control idle alignment PASS: `control-idle-run-01`
  - mock chain final output PASS: `mock-chain-run-05`

## 7. Only Remaining Work

- 실제 장시간 운영 실행 후 `system/runtime_v2/evidence/soak_24h_report.md` 또는 대응 리포트를 채우는 것
- 즉, 코드 수정이 아니라 운영 실행/관찰/보고 단계입니다.

## 8. Recommended Next Step

1. `docs/sop/SOP_runtime_v2_detached_soak_readiness.md` 기준으로 detached smoke 증거를 다시 빠르게 확인합니다.
2. 그 다음 `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md` 기준으로 장시간 soak 운영을 시작합니다.
3. 운영 결과를 `soak_24h_report.md`에 기록하면 현재 TODO가 닫힙니다.

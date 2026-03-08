# SOP: Runtime V2 Detached Soak Readiness

> 버전: 1.0
> 상태: Active
> 적용 범위: `runtime_v2` detached probe 기반 soak/실운영 준비 점검

## 1. 목적

- detached probe 기준으로 smoke 통과 증거를 다시 확인하고, soak/실운영 준비 전환 조건을 고정합니다.
- 외부 참고 경로를 건드리지 않고 `D:\YOUTUBEAUTO` 내부 증거만으로 준비 상태를 판정합니다.

## 2. 준비 완료 기준

1. selftest detached 증거가 `OK`여야 합니다.
2. control idle/latest-run snapshot이 같은 `run_id`를 공유해야 합니다.
3. mock chain detached 증거에서 `job_summary` 최종 이벤트가 `final_output=true`여야 합니다.
4. 브라우저 `profile_dir`은 절대경로로 기록되어야 합니다.

## 3. 확인 파일

- `system/runtime_v2_probe/selftest-run-07/probe_result.json`
- `system/runtime_v2_probe/selftest-run-07/evidence/result.json`
- `system/runtime_v2_probe/selftest-run-07/health/browser_health.json`
- `system/runtime_v2_probe/control-idle-run-01/probe_result.json`
- `system/runtime_v2_probe/control-idle-run-01/evidence/result.json`
- `system/runtime_v2_probe/control-idle-run-01/health/gui_status.json`
- `system/runtime_v2_probe/control-idle-run-01/health/browser_health.json`
- `system/runtime_v2_probe/mock-chain-run-05/evidence/control_plane_events.jsonl`

## 4. 판정 절차

### 4.1 Selftest Gate

- `probe_result.json`에서 `code=OK`, `exit_code=0` 확인
- `evidence/result.json` metadata의 `run_id`가 `probe_result.json.run_id`와 같은지 확인
- `browser_health.json`에서 `run_id`가 같고 `healthy_count=4`인지 확인

### 4.2 Control Idle Snapshot Gate

- `probe_result.json`, `evidence/result.json`, `health/gui_status.json`, `health/browser_health.json`의 `run_id`가 모두 같은지 확인
- idle 상태에서는 `code=NO_JOB`, `queue_status=idle`로 판정

### 4.3 Mock Chain Final Output Gate

- `control_plane_events.jsonl` 마지막 `job_summary`에서 `completion_state=completed` 확인
- 같은 이벤트에서 `final_output=true`와 `final_artifact_path` 존재 확인
- detached mock chain 루트 안에서 `_mock/kenburns/*.mp4` 산출물 위치 확인

## 5. Soak 진입 전 체크리스트

- `runtime_v2` 관련 detached evidence가 최신 run 기준으로 서로 조인 가능함
- GUI `Result` 패널에서 idle/latest-run과 최종 산출 완료를 구분 가능함
- smoke 증거만으로 브라우저/GPU/GPT 원인 축을 다시 분리할 수 있음
- 외부 참고 경로 쓰기 흔적이 없음

## 6. 실패 시 기록 항목

- `run_id`
- `code`
- `debug_log`
- `result_path`
- `manifest_path`
- `final_artifact_path`
- 관련 probe root 경로

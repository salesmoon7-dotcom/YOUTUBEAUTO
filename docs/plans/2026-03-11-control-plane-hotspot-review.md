# Control Plane Hotspot Review

## Purpose

- `runtime_v2/control_plane.py`의 현재 hotspot을 사실 기준으로 기록합니다.
- 범위는 현재 책임, 유지해야 할 canonical 책임, 향후 분해 후보, 재오픈 조건으로 제한합니다.
- 이 문서는 새 구현 계획이 아니라 review artifact입니다.

## Decision

- 결론: `runtime_v2/control_plane.py`는 여전히 크고 다책임 hotspot이지만, 지금 당장 새 분해 unit을 열지는 않습니다.
- 결론: 현재 파일에 남겨야 할 canonical 책임은 control-plane의 최종 의미 결정, recovery/backoff 정책 집행, latest snapshot/event single writer 역할입니다.
- 결론: 향후 분해 후보는 worker dispatch 표면과 next-job/asset-manifest 보조 로직이지만, 실제 재오픈 조건이 발생하기 전에는 현 구조를 유지합니다.

## Current Responsibility Map

### Canonical responsibilities that should stay

- `run_control_loop_once()`는 queue 상태를 읽고 다음 job을 선택하며, 실행 결과를 최종 `status/code` 의미로 수렴합니다.
- `_evaluate_recovery()`와 `_next_status_for_recovery()`는 retry, blocked, failed의 정책 결정을 control-plane owner 아래에 둡니다.
- `_seed_declared_next_jobs()`는 downstream chaining에서 `run_id`, `row_ref`, `chain_depth`, local payload 제약을 강제합니다.
- `write_control_plane_runtime_snapshot()`, `_append_transition_record()`, `_append_control_event()` 호출 경로는 latest snapshot과 event evidence의 single writer 역할을 유지합니다.

### Future decomposition candidates

- `_run_worker()`의 workload별 dispatch table은 파일 크기와 추적 비용을 키우는 대표 hotspot입니다.
- `_seed_declared_next_jobs()` 내부의 asset-manifest 보조 경로와 next-job validation 묶음은 별도 helper 경계 후보입니다.

## Contract Facts Locked By Current Code And Tests

### run_id

- control-plane에는 최소 두 개의 `run_id` 스코프가 공존합니다.
- `run_control_loop_once(..., run_id=...)`의 `run_id`는 latest snapshot, debug log, transition/event evidence를 쓰는 control run id입니다.
- job chain의 `run_id`는 `parent_job.payload["run_id"]`를 기준으로 유지되며, `_seed_declared_next_jobs()`는 mismatch를 reject하고 부모 run id로 정렬합니다.
- 근거: `runtime_v2/control_plane.py`의 `_seed_declared_next_jobs()` 구현과 `tests/test_runtime_v2_control_plane_chain.py`의 asset-manifest run id, control-run-id debug log/event 회귀들.

### error_code

- control-plane snapshot 메타데이터는 최종 `code`와 canonical `worker_error_code`를 함께 기록합니다.
- worker raw error와 runtime error가 다를 때 `warning_worker_error_code_mismatch`는 최소 debug log evidence에 남습니다.
- 이 review는 mismatch warning이 latest-run/GUI 어디에나 항상 surface 된다고 확장 해석하지 않습니다.
- 근거: `tests/test_runtime_v2_control_plane_chain.py`의 mismatch warning 회귀와 `runtime_v2/control_plane.py`의 `control_loop_result` debug event.

### attempt/backoff

- blocked failure는 queue 상태를 `retry`로 두되 `attempts`를 증가시키지 않고 fixed backoff를 남깁니다.
- restart exhausted와 non-retryable failure는 terminal path로 수렴하며 `attempts` 증가와 `backoff_sec=0`이 함께 남습니다.
- browser unhealthy runtime preflight 같은 retryable failure는 `attempts`를 증가시키고 positive backoff를 남깁니다.
- 근거: `tests/test_runtime_v2_control_plane_chain.py`의 blocked / restart exhausted / browser unhealthy / gpt floor / gpu busy 회귀들.

## Why This File Stays Central

- guardrails 기준으로 control-plane은 final owner, worker는 policy-free, latest snapshot은 single writer를 유지해야 합니다.
- 현재 hotspot은 비용이 높지만, 의미 결정과 증거 기록을 여러 레이어로 다시 흩뜨리는 분해는 drift 위험이 더 큽니다.
- 따라서 현 시점의 기본 결정은 "구조 불만"보다 "owner/failure contract 보존"을 우선하는 유지입니다.

## Reopen Conditions For Future Decomposition

- `_run_worker()` 왕복 디버깅이 반복될 때
- workload 3개 이상 추가로 dispatch 충돌이 실제 발생할 때
- worker 선택 정책 자체를 교체해야 할 때

## Recommendation

- 유지: 현재 `control_plane.py`는 canonical owner 책임을 계속 보유합니다.
- 금지: 이번 review를 근거로 새 implementation unit이나 선제 분해를 열지 않습니다.
- 재개: 위 재오픈 조건이 실제 evidence로 발생할 때만 별도 decomposition review/plan을 다시 엽니다.

# TODO

- 현재 canonical plan 기준 판정은 `No-Go`입니다. `1행 smoke`와 soak/실운영 진입 전에 아래 remediation이 먼저 닫혀야 합니다.
- 1순위: `GPT floor` 복구 기준과 latest health 신뢰성 고정
  - 대상: `runtime_v2/gpt_pool_monitor.py`, `runtime_v2/gpt_autospawn.py`, `runtime_v2/gpt/floor.py`
- 2순위: latest-run evidence join 규칙 고정
  - 대상: `runtime_v2/control_plane.py`, `runtime_v2/result_router.py`, `runtime_v2/gui_adapter.py`, `runtime_v2/supervisor.py`
- 3순위: browser canonical ownership / stale-busy-unknown recovery 규칙 고정
  - 대상: `runtime_v2/browser/manager.py`, `runtime_v2/browser/supervisor.py`
- 4순위: blocked/backoff semantics 재정의
  - 목표: `worker_error_code` 공백 제거, browser/gpu/worker blocked 계약 일치, 즉시 재루프 금지
- 5순위: reference carryover 적용/미적용 표 확정
  - 기준: 실제 호출 경로 + 안전장치 + evidence/test 동시 확인
- 위 5개가 닫힌 뒤에만 `1행 smoke` 준비 완료 판정을 수행합니다.
- `soak_24h_report.md`를 채우는 운영 실행은 위 readiness gate 통과 후 최종 단계에서만 진행합니다.
- 테스트 실행은 `docs/plans/2026-03-08-browser-session-stability-plan.md`의 `Test Tier Execution Contract`를 따릅니다. 채팅 세션 기본 검증은 `safe`만 허용하고, `isolated`는 개별 실행, `manual`은 채팅 세션 밖에서만 다룹니다.

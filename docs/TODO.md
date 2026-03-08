# TODO

- 현재 canonical plan 기준의 1순위 remediation은 모두 닫혔습니다.
- `1행 smoke` readiness 재판정은 완료되었습니다.
  - detached browser recovery run `system/runtime_v2_probe/browser-recover-run-01/probe_result.json`이 `code=OK`로 종료됐습니다.
  - `python -m runtime_v2.cli --readiness-check` 기준 `ready=true`, `code=OK`를 확인했습니다.
- 다음 active unit: `docs/plans/2026-03-09-agent-browser-closed-loop-development-plan.md` 후속 운영 정리
  - 현재 최소 closed loop(`dev_plan -> dev_implement -> agent_browser_verify -> dev_replan`)와 safe-tier fail-closed, probe-root smoke는 구현됨
  - 남은 일은 detached/manual tier에서 실제 브라우저 attach evidence를 더 쌓는 것입니다.
- 채팅 interruption 대응 규칙 강화:
  - 채팅 세션에서는 실브라우저 relaunch/recovery를 실행하지 않습니다.
  - readiness blocker가 실브라우저 복구를 요구하면 detached 또는 수동 smoke 단계에서만 수행합니다.
- 테스트 실행은 `docs/plans/2026-03-08-browser-session-stability-plan.md`의 `Test Tier Execution Contract`를 따릅니다. 채팅 세션 기본 검증은 `safe`만 허용하고, `isolated`는 개별 실행, `manual`은 채팅 세션 밖에서만 다룹니다.

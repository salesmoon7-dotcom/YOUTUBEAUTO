# Browser Health Subprogram Review

## Purpose

- `runtime_v2`에서 브라우저 건강 관리 프로그램이 `supervisor` 하부프로그램으로 필요한지 검토합니다.
- 범위는 브라우저 가동상태 파악, 복구 책임, 상위 `supervisor`와의 경계, 향후 분리 필요 조건으로 제한합니다.

## Decision

- 결론: 브라우저 건강 관리 기능은 반드시 필요합니다.
- 결론: 다만 현 시점에는 `supervisor` 산하의 전용 브라우저 health/recovery 모듈이면 충분하며, 별도의 독립 프로세스나 별도 서비스로 추가 분리할 단계는 아닙니다.
- 결론: 현재 코드의 `runtime_v2/browser/supervisor.py`가 사실상 그 하부프로그램 역할을 이미 수행하고 있습니다.

## Why This Decision

- `runtime_v2/browser/manager.py`는 브라우저별 포트, 프로필, CDP 탭, ready marker, profile lock을 직접 관리합니다.
- `runtime_v2/browser/supervisor.py`는 `login_required`, `busy_lock`, `unknown_lock`, `stale_lock_recovered`를 상태로 분류하고, recovery/escalation 이벤트를 기록합니다.
- `runtime_v2/supervisor.py`는 위 상태를 `BROWSER_BLOCKED` 또는 `BROWSER_UNHEALTHY`로 번역해 workload gate를 닫습니다.
- 즉 현재 구조는 이미 `manager -> browser supervisor -> runtime supervisor`의 3단 책임 분리를 가지고 있으므로, 브라우저 상태 판단을 위해 새 프로그램을 하나 더 겹쳐 둘 이유는 약합니다.

## Current Capability Assessment

### What the code can determine now

- 서비스별 디버그 포트 open 여부
- CDP `/json` 기반 탭 존재 여부
- 서비스별 ready URL 충족 여부
- 로그인 페이지 유입 여부
- `session_ready.json` 존재 여부와 false-positive 제거
- profile lock 상태 `free|busy|stale|unknown|owned`
- stale lock 회수 여부와 recovery/restart 이벤트
- browser plane owner의 stale/busy takeover 여부

### What that means operationally

- 현재 코드는 각 브라우저가 "작업 진행 가능 상태인지"를 서비스별로 판정할 수 있습니다.
- 이 판정은 단순 포트 체크가 아니라 로그인/ready/lock 상태까지 포함한 운영 가능 상태 판정입니다.
- 따라서 "각 브라우저의 가동상태를 파악할 수 있는가"라는 질문에는 예라고 답할 수 있습니다.

### What is not covered yet

- 프로세스 메모리 사용량 상한/누수 추적
- 브라우저 핸들 수, 탭 수, 렌더러 hung의 장기 추세 감시
- OS 레벨 좀비 프로세스 정리 자동화
- supervisor 자체가 멈췄을 때 복구하는 외부 watchdog
- GPU/브라우저 복합 장애의 원인 분리 자동 판정

## Code Evidence

- `runtime_v2/browser/manager.py`
  - `_evaluate_session_health()`는 포트, 탭 URL, 로그인 패턴, ready marker, lock 상태를 합쳐 세션 상태를 판정합니다.
  - `acquire_profile_lock()`와 `inspect_profile_lock()`는 `busy/stale/unknown`을 구분합니다.
  - `_launch_debug_browser()`는 프로필 lock과 디버그 포트를 묶어 launch ownership을 유지합니다.
- `runtime_v2/browser/supervisor.py`
  - `_emit_browser_session_events()`는 `login_required`, `busy_lock`, `unknown_lock`, `stale_lock_recovered`를 이벤트로 남깁니다.
  - `tick()`은 unhealthy 세션만 재기동하고, busy lock은 escalation으로 처리합니다.
- `runtime_v2/supervisor.py`
  - `_required_browser_summary()`는 필수 서비스 중 blocked/unhealthy를 구분합니다.
  - `run_once()`는 blocked 상태를 `BROWSER_BLOCKED`, 그 외 unhealthy를 `BROWSER_UNHEALTHY`로 반영합니다.
- `tests/test_runtime_v2_browser_plane.py`
  - login required, stale recovery, busy escalation, unknown lock fail-close, ready marker 판정 회귀가 이미 존재합니다.

## External Evidence

- Playwright `Browser.isConnected()`, `BrowserServer.close()`, `BrowserServer.kill()` 문서는 연결 상태와 프로세스 종료를 별도 신호로 다뤄야 함을 보여줍니다.
- Puppeteer `BrowserEvent.Disconnected` 문서는 브라우저 종료/크래시와 연결 해제를 별도 감지 신호로 다룹니다.
- Microsoft Edge DevTools Protocol 문서는 `--remote-debugging-port`, `--user-data-dir`, `/json/list`를 브라우저 attach/health 확인의 기본 경로로 제시합니다.
- 이 프로젝트의 현재 구현은 위 공식 패턴과 일치하게 포트 + CDP target + 전용 profile을 핵심 health signal로 사용하고 있습니다.

## Recommendation

- 유지: 브라우저 health/recovery는 계속 `supervisor` 하부 모듈로 유지합니다.
- 금지: 지금 단계에서 동일 책임의 별도 "브라우저 건강 관리 프로그램"을 추가로 만들지 않습니다.
- 강화: 부족한 축은 새 서브프로세스 추가보다 현재 browser plane에 메트릭과 evidence를 보강하는 방식으로 메웁니다.

## Conditions That Would Justify Further Separation

- 브라우저 메모리/핸들/GPU hung까지 자동 복구해야 할 때
- 여러 런타임이 하나의 브라우저 health 정책을 공유해야 할 때
- health check가 무거워져 `supervisor` 이벤트 루프를 방해할 때
- `supervisor` 자체 장애까지 감시할 외부 watchdog이 필요할 때

## Immediate Follow-up

- 현재 구조는 유지합니다.
- 이후 브라우저 health 확장은 "새 프로그램 추가"보다 "현재 browser plane의 관측 항목 확대"로 다룹니다.
- 우선순위가 높은 추가 관측 항목은 메모리, renderer hang, orphan process, restart budget입니다.

# SOP: runtime_v2 Development Guardrails

## Purpose

- 이 문서는 사용자 체크리스트가 아니라, 에이전트가 `runtime_v2` 작업 세션을 시작할 때 기본으로 따라야 하는 개발 대명제입니다.
- 문서명에 `Development`가 들어가지만, 실제 역할은 구현 팁 모음보다 `runtime_v2`의 하니스/계약 불변식을 고정하는 canonical guardrail에 가깝습니다.
- 목표는 두 가지입니다.
  - 디버깅 용이성
  - 파이프라인 단순성

## Development Thesis

- 디버깅을 쉽게 하려면 상태와 증거가 한 점으로 모여야 합니다.
- 파이프라인을 단순하게 유지하려면 의미 결정권도 한 점으로 모여야 합니다.
- `runtime_v2` 파이프라인은 처음부터 견고하고 효율적으로 설계되어야 합니다. 여기서 효율은 처리량 최적화가 아니라, `의미 결정권`, `증거 흐름`, `실패 계약`이 단순하고 일관되어 검증이 빠르고 drift가 누적되지 않는 상태를 뜻합니다.
- 새 기능이나 서비스 추가로 `owner 경계`, `writer 수`, `failure axis 이름/의미`, `evidence 경로/포맷`이 늘어나거나 갈라지면, 구현 진행보다 아키텍처 재검토로 승격하는 것을 기본값으로 삼습니다.
- 따라서 `runtime_v2`는 `관측 기반`, `단일 writer`, `단일 failure contract`, `단일 reference adapter`를 기본 원칙으로 유지합니다.

## Session-Start Obligations

- `runtime_v2` 계획/구현/디버깅 작업을 시작하면, 사용자 재명령이 없어도 이 문서를 먼저 기준으로 삼습니다.
- 그 다음 현재 canonical plan과 관련 SOP를 읽고, 이번 세션 범위를 그 안에서만 정합니다.
- 이 문서와 plan/SOP가 충돌하면 새 원칙을 임의로 만들지 말고, canonical 문서를 먼저 갱신합니다.

## Session-End Verification Gate

- `runtime_v2` 작업 세션에서는 완료 주장 전에 `verify-implementation`을 기본 검증 관문으로 실행합니다.
- 이 관문은 선택 사항이 아니라 기본 종료 절차입니다.
- 관문 실행 전후로 아래 3개를 최소 증거로 확인합니다.
  - `run_id` 정렬
  - `error_code` 의미 일치
  - `attempt/backoff` 계약 일치
- 위 3개 중 하나라도 틀리면, 세션 종료보다 contract/evidence drift 수정이 우선입니다.

### Growth Gate Bundle

- 성장 단계 기본 검증은 아래 4개를 함께 유지합니다.
  - static diagnostics / compile check
  - targeted pytest bundle
  - `verify-implementation`
  - readiness regression
- `24h`는 이 번들의 즉시 완료 기준이 아니라 later soak stage로 유지합니다.
- 채팅/UI interruption이 반복되면 즉시 `interrupt-safe` 모드로 강등합니다.
  - 병렬 도구 호출 중단
  - 한 번에 도구 1개만 사용
  - pytest는 테스트 케이스 단위로만 실행
  - 파일 단위/대묶음 검증은 채팅 세션 밖 또는 더 안정적인 실행 경로로 미룹니다
  - 실브라우저 relaunch/recovery 명령은 채팅 세션에서 직접 실행하지 않고 detached/수동 경로로 미룹니다

## Non-Negotiable Guardrails

- 관측되지 않은 정상은 정상으로 취급하지 않습니다. `unknown`, 빈 상태, 누락 상태를 `OK`로 합성하지 않습니다.
- latest-run snapshot의 writer는 하나만 둡니다. 최종 latest 의미는 control plane이 소유합니다.
- 같은 failure axis는 한 이름, 한 의미만 가집니다. browser/gpt/gpu/worker가 같은 blocked를 다르게 기록하면 안 됩니다.
- worker는 자기 결과만 반환하고, 재시도/blocked/backoff 정책은 상위 orchestration에서만 결정합니다.
- 외부 참고 호출은 adapter 경로 하나로만 통과시키고, 직접 분산 호출을 늘리지 않습니다.
- fail-open보다 fail-closed를 우선합니다. 판단 불가면 진행보다 보류/차단을 선택합니다.

## Guardrail Addition Acceptance Criteria

- 새 guardrail은 "문제가 생겼으니 규칙 하나 더 추가" 방식으로 누적하지 않습니다. 추가 전 반드시 canonical 문서에 아래 3가지를 함께 기록합니다.
  - owner: 어떤 owner layer가 이 guardrail을 최종 소유하고 집행하는지 명시합니다.
  - failure mode: 이 guardrail이 정확히 어떤 failure mode 하나를 줄이거나 막는지 적습니다.
  - removal: 어떤 조건이 충족되면 이 guardrail을 제거하거나 더 넓은 canonical contract로 흡수할지 적습니다.
- 위 3가지 중 하나라도 비어 있으면 새 guardrail을 받지 않고, 기존 owner/failure contract 재정렬 또는 evidence 보강을 먼저 검토합니다.
- 임시 보정, 예외 분기, fallback guardrail은 removal 조건 없이 carryover하지 않습니다.

## 10 Mandatory Session Rules

1. 수정 전에 이번 이슈의 single owner 레이어를 먼저 정합니다.
2. 같은 문제를 여러 레이어에서 동시에 보정하지 않습니다.
3. 새 분기를 추가하기 전에 기존 failure axis에 편입 가능한지 먼저 확인합니다.
4. `run_id` 없이 latest/evidence 의미를 추가하지 않습니다.
5. latest-run 결과가 두 파일에서 다른 의미로 남으면 기능 작업보다 `evidence drift` 수정이 우선입니다.
6. `status`, `error_code`, `completion.state`는 contract 필드로만 해석하고 임의 파생 의미를 늘리지 않습니다.
7. blocked 상태는 `hold` 또는 `fixed backoff` 중 하나로만 처리하고 즉시 재루프를 만들지 않습니다.
8. 외부 참고 기능은 `호출 경로`, `안전장치`, `evidence/test` 3개가 함께 있을 때만 carryover로 인정합니다.
9. 디버그를 위해 임시 예외 분기나 fallback OK를 추가하지 않습니다. 필요하면 evidence를 늘리고 owner 레이어에서 고칩니다.
10. 한 세션에서 하나의 logical change만 수행하고, drift가 보이면 새 기능보다 아키텍처 재검토를 우선합니다. 효율/견고성 저하(분기 증가, 중복 writer, 계약 의미 확장, 증거 포맷 난립) 징후도 동일한 drift로 취급합니다.

## Required Working Model

- Control plane: 최종 판정, queue 상태, latest snapshot writer의 단일 owner
- Health plane: browser/gpt/gpu 상태 관측과 raw health 반환만 담당
- Worker plane: artifact/result contract만 반환, 정책 결정 금지
- Reference adapter plane: 외부 참고 스크립트 호출과 근거 필드 표준화만 담당

## Drift Escalation Triggers

- 동일 failure axis 분기가 manager/supervisor/control_plane에 중복으로 늘어날 때
- latest-run evidence가 같은 실행을 서로 다른 의미로 기록할 때
- blocked semantics가 browser/gpt/gpu/worker 축마다 달라질 때
- 외부 참고 carryover가 호출만 있고 안전장치/evidence 없이 누적될 때
- 1행 smoke 전제 조건이 문서나 코드에서 다르게 적힐 때

- 위 항목 중 하나라도 보이면, 계속 땜질하지 말고 canonical plan 기준으로 아키텍처 재검토로 승격합니다.

## Minimum Verification Focus

- 수정 후 최소한 아래 3가지는 항상 맞아야 합니다.
  - `run_id` 정렬
  - `error_code` 의미 일치
  - `attempt/backoff` 계약 일치

- 이 3개 중 하나라도 틀리면 다음 기능으로 넘어가지 않습니다.

## warning_worker_error_code_mismatch

- 성격: 런타임(컨트롤러)에서 기대한 에러 코드와 워커가 보고한 에러 코드가 불일치하는 "분류 경고"입니다.
- 차단 여부:
  - 기본은 non-blocking입니다.
  - 단, 동일 경고가 반복되거나, 워커 실패/재시도 폭증/작업 중단과 함께 나타나면 blocking으로 승격하고 원인 분석 전까지 진행을 멈춥니다.
- 담당자:
  - 1차: `runtime_v2` 온콜/담당 개발자가 즉시 분류합니다.
  - 2차: 워커 구현 담당자가 에러 enum/레지스트리/매핑 정합성을 수정합니다.
- 신뢰 우선순위:
  1. Oracle과 재현 가능한 실제 실행 증거(워커 raw 로그, stack trace, 원본 에러 코드)
  2. 워커 측 에러 코드 정의(공식 enum, 상수, 레지스트리)
  3. 런타임 측 매핑/해석 로직
- 문서는 최종 정리와 기록의 기준점이며, 1차 판단 근거로 쓰지 않습니다.
- 커밋/푸시 전에는 동일 시나리오 재실행으로 mismatch가 사라졌는지, 또는 의도된 코드로 정렬됐는지를 Oracle 근거로 다시 확인합니다.

### Documented Runtime_v2 Error Code IDs

아래 ID는 문서와 코드가 같은 토큰으로 유지되어야 합니다.

`OK`, `BROWSER_BLOCKED`, `BROWSER_RESTART_EXHAUSTED`, `BROWSER_UNHEALTHY`, `GPU_LEASE_BUSY`, `GPT_FLOOR_FAIL`, `QUEUE_STORE_INVALID`, `GPT_STATUS_MISSING`, `GPT_STATUS_INVALID`, `GPT_STATUS_STALE`, `BROWSER_HEALTH_MISSING`, `BROWSER_HEALTH_INVALID`, `BROWSER_REGISTRY_MISSING`, `BROWSER_REGISTRY_INVALID`, `BROWSER_REGISTRY_DRIFT`

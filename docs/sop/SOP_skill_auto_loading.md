# SOP: Skill Auto-Loading For Prompt Intent

## Purpose

- 이 문서는 새 세션에서도 프롬프트 의도에 맞춰 설치된 스킬을 자동 선택하도록 고정하는 기준입니다.
- 목표는 사용자가 스킬 이름을 몰라도, 에이전트가 현재 프로젝트 워크플로우에 맞는 스킬을 먼저 불러오게 하는 것입니다.
- 본 문서는 사용자 의도/요청 유형에 따른 스킬 자동 로딩 라우팅 가이드입니다.
- 닫힌루프 자동화에서 사용하는 스킬 번들(조합) 맵은 `docs/sop/SOP_closed_loop_automation_skill_map.md`를 참고합니다.

## Default Rule

- 모든 세션은 사용자 프롬프트를 해석한 직후, 구현/탐색/디버깅/검증/브라우저 작업 여부를 먼저 분류합니다.
- 분류가 끝나면, 아래 매핑표를 기준으로 설치된 스킬을 우선 검토하고 자동 호출합니다.
- 사용자가 스킬 이름을 직접 말하지 않아도, 작업 의도가 명확하면 스킬을 먼저 적용합니다.
- 질문이 짧아도 동일합니다. 예: "이거 왜 깨져?"는 설명 요청이 아니라 디버깅 의도로 보고 대응합니다.

## Installed Skill Routing Table

| Skill | Default trigger in this project | Notes |
|------|------|------|
| `find-skills` | 새로운 외부 도메인, 새로운 툴체인, 기존 6개 스킬로 커버되지 않는 작업 | 검색 후 설치 후보만 좁히고, 기존 스킬로 해결 가능하면 남용하지 않습니다 |
| `executing-plans` | `runtime_v2` 계획 문서 기반 구현, 단계형 작업, task-by-task 실행 | canonical plan이 있으면 기본 시작점으로 사용합니다 |
| `systematic-debugging` | 테스트 실패, 예상과 다른 동작, evidence drift, contract mismatch | 추측 수정 전에 먼저 호출합니다 |
| `verification-before-completion` | 완료 보고 직전, 커밋 직전, 성공 주장 직전 | fresh verification evidence 없이 완료를 주장하지 않습니다 |
| `requesting-code-review` | 큰 변경 완료 후, worker/control-plane/contracts 수정 후, merge 전 자체 점검 | 구조적 누락 탐지용으로 사용합니다 |
| `webapp-testing` | 브라우저/GUI/로컬 웹앱/Playwright 검증 | 설치되어 있으면 우선 사용하고, 미설치면 `playwright`로 동일 역할을 대체합니다 |

## Project-Specific Defaults

- `runtime_v2` 작업은 먼저 `docs/sop/SOP_runtime_v2_development_guardrails.md`를 읽고, 관련 plan이 있으면 `executing-plans`를 기본값으로 사용합니다.
- 테스트 실패, `run_id`/`error_code`/`attempt/backoff` 의미 불일치, worker fail-closed 문제는 `systematic-debugging`을 먼저 사용합니다.
- 브라우저 health, GUI, local web flow 검증은 `webapp-testing`을 우선 사용하고, 미설치 세션에서는 `playwright`를 fallback으로 사용합니다.
- 완료 직전에는 항상 `verification-before-completion`을 사용하고, `runtime_v2`에서는 추가로 `verify-implementation` 게이트를 유지합니다.
- 큰 구현 배치가 끝나면 `requesting-code-review`를 호출해 누락을 줄입니다.

## Recommended Skill Bundles

### 1. Plan execution bundle

- `executing-plans` -> implementation -> `verification-before-completion`

### 2. Bugfix bundle

- `systematic-debugging` -> fix -> `verification-before-completion`

### 3. Large change bundle

- `executing-plans` -> implementation -> `requesting-code-review` -> `verification-before-completion`

### 4. Browser validation bundle

- `webapp-testing` -> if needed `systematic-debugging` -> `verification-before-completion`
- 미설치면 `playwright` -> if needed `systematic-debugging` -> `verification-before-completion`

### 5. New domain discovery bundle

- `find-skills` -> narrow candidates -> install only if existing installed skills are insufficient

## Anti-Patterns

- 사용자가 스킬 이름을 안 말했다고 해서 스킬 검토를 생략하지 않습니다.
- `runtime_v2` 계획 문서가 있는데 ad-hoc 구현부터 시작하지 않습니다.
- 실패 증거가 있는데 `systematic-debugging` 없이 추측 패치를 먼저 넣지 않습니다.
- 브라우저/GUI 문제를 텍스트 추론만으로 끝내지 않습니다. `webapp-testing`이 없으면 `playwright` fallback을 사용합니다.
- 검증 스킬 없이 완료를 주장하지 않습니다.

## Session-Start Checklist

- 프롬프트 의도를 구현/디버깅/검증/브라우저/탐색 중 어디에 가까운지 분류합니다.
- 위 라우팅표에 맞는 스킬이 있으면 먼저 호출하고, 미설치 항목은 표에 정의된 fallback으로 대체합니다.
- `runtime_v2` 관련이면 guardrail SOP와 plan 문서를 먼저 읽습니다.
- 새 도메인이면 `find-skills`로 추가 스킬 필요성만 판단합니다.

## Session-End Checklist

- 완료 주장 전 `verification-before-completion`을 실행합니다.
- `runtime_v2` 작업이면 `verify-implementation`까지 포함해 종료 게이트를 닫습니다.
- 큰 구조 변경이면 `requesting-code-review`를 거쳤는지 확인합니다.

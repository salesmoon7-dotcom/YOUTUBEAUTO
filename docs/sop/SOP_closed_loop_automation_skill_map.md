# SOP: Closed Loop Automation Skill Map

## Purpose

- 이 문서는 이 프로젝트에서 `closed loop automation`을 수행할 때 어떤 스킬을 어떤 순서와 조건으로 적용해야 하는지 고정합니다.
- 목표는 `계획 -> 구현 -> 검증 -> 실패 시 수정/재계획 -> 완료 판정`을 스킬 조합으로 일관되게 닫는 것입니다.
- 본 문서는 닫힌루프 자동화 실행 시 권장되는 스킬 번들(조합) 맵입니다.
- 사용자 의도 판별과 스킬 자동 로딩 라우팅 규칙은 `docs/sop/SOP_skill_auto_loading.md`가 다룹니다.

## Definition

- 이 프로젝트에서 `closed loop automation`은 다음 순환을 의미합니다.
  - 요구사항/계획 해석
  - 구현
  - 검증
  - 실패 증거 수집
  - 수정 또는 재계획
  - 재검증
  - 완료 판정

## Core Rule

- 단일 스킬 하나가 모든 단계를 끝내는 구조가 아닙니다.
- 이 프로젝트의 closed loop는 아래 스킬 번들을 조합해서 닫습니다.

## Canonical Skill Map

| Phase | Primary skill | When to load | Role |
|------|------|------|------|
| 계획 실행 시작 | `executing-plans` | canonical plan 문서가 있을 때 | 계획을 task-by-task로 실행하는 기본 축 |
| 구현 중 오류 분석 | `systematic-debugging` | 테스트 실패, contract drift, unexpected behavior | 추측 수정 대신 root cause 분석 |
| 브라우저/GUI 검증 | `webapp-testing` | 브라우저/GUI/로컬 웹 흐름 검증 시 | 브라우저 검증 축 |
| 브라우저 fallback | `playwright` | `webapp-testing` 미설치 시 | 브라우저 검증 대체 경로 |
| 큰 변경 후 자체 리뷰 | `requesting-code-review` | worker/control-plane/contracts 등 구조 변경 후 | 구조적 누락 탐지 |
| 완료 직전 검증 | `verification-before-completion` | 완료 주장 전, 커밋 전, push 전 | fresh evidence 강제 |
| 새 도메인 탐색 | `find-skills` | 기존 설치 스킬로 커버 안 되는 새 도메인 | 추가 스킬 필요성만 판단 |

## Canonical Bundles

### 1. Plan-Driven Closed Loop

- `executing-plans`
- implementation
- if failure: `systematic-debugging`
- re-run verification
- if large structural change: `requesting-code-review`
- before completion: `verification-before-completion`

## 2. Bugfix Closed Loop

- `systematic-debugging`
- minimal fix
- re-run failing verification
- before completion: `verification-before-completion`

## 3. Browser Program Closed Loop

- `executing-plans`
- implementation
- `webapp-testing`
- if browser verification fails: `systematic-debugging`
- before completion: `verification-before-completion`

- `webapp-testing`이 미설치면 아래로 대체합니다.
  - `playwright`
  - if needed `systematic-debugging`
  - `verification-before-completion`

## 4. Large Change Closed Loop

- `executing-plans`
- implementation
- `requesting-code-review`
- if review or tests fail: `systematic-debugging`
- before completion: `verification-before-completion`

## Project-Specific Rules

- `runtime_v2` 작업은 먼저 `docs/sop/SOP_runtime_v2_development_guardrails.md`를 읽습니다.
- `runtime_v2` 계획 문서가 있으면 `executing-plans`를 기본 시작점으로 사용합니다.
- `run_id`, `error_code`, `attempt/backoff`, fail-closed 의미가 어긋나면 구현보다 먼저 `systematic-debugging`으로 되돌립니다.
- 완료 주장 전에는 항상 `verification-before-completion`을 실행합니다.
- `runtime_v2`에서는 종료 직전 `verify-implementation` 게이트도 유지합니다.

## Decision Table

| Situation | Required skills |
|------|------|
| canonical plan 기반 구현 | `executing-plans` |
| 테스트 실패 | `systematic-debugging` |
| 브라우저/GUI 검증 | `webapp-testing` or `playwright` |
| 큰 구조 변경 완료 | `requesting-code-review` |
| 새 툴/새 도메인 | `find-skills` |
| 완료 직전 | `verification-before-completion` |

## Anti-Patterns

- plan 문서가 있는데 `executing-plans` 없이 ad-hoc 구현부터 시작하지 않습니다.
- 실패 증거가 있는데 `systematic-debugging` 없이 패치를 누적하지 않습니다.
- 브라우저 검증을 텍스트 추론만으로 끝내지 않습니다.
- `verification-before-completion` 없이 완료를 주장하지 않습니다.
- 단일 스킬 하나로 closed loop 전체가 끝난다고 가정하지 않습니다.

## Current Best-Fit Closed Loop For This Repo

- 기본 구현 루프
  - `executing-plans` -> implement -> `verification-before-completion`
- 오류가 끼면
  - `systematic-debugging` -> fix -> `verification-before-completion`
- 큰 변경이면
  - `executing-plans` -> implement -> `requesting-code-review` -> `verification-before-completion`
- 브라우저 프로그램이면
  - `executing-plans` -> implement -> `webapp-testing` or `playwright` -> `verification-before-completion`

## References

- `docs/sop/SOP_skill_auto_loading.md`
- `docs/sop/SOP_runtime_v2_development_guardrails.md`
- `docs/plans/2026-03-09-agent-browser-closed-loop-development-plan.md`
- `docs/TODO.md`
- `docs/COMPLETED.md`

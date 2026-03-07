---
name: verify-implementation
description: 프로젝트의 모든 verify 스킬을 순차 실행하여 통합 검증 보고서를 생성합니다. 기능 구현 후, PR 전, 코드 리뷰 시 사용.
disable-model-invocation: true
argument-hint: "[선택사항: 특정 verify 스킬 이름]"
---

# 구현 검증

## 목적

프로젝트에 등록된 모든 `verify-*` 스킬을 순차적으로 실행하여 통합 검증을 수행합니다:

- 각 스킬의 Workflow에 정의된 검사를 실행
- 각 스킬의 Exceptions를 참조하여 false positive 방지
- 발견된 이슈에 대해 수정 방법을 제시
- 사용자 승인 후 수정 적용 및 재검증

## 실행 시점

- 새로운 기능을 구현한 후
- `runtime_v2` 계획/구현/디버깅 세션에서 완료를 주장하기 직전
- Pull Request를 생성하기 전
- 코드 리뷰 중
- 코드베이스 규칙 준수 여부를 감사할 때

## runtime_v2 Guardrails Gate

- `runtime_v2` 작업에서는 이 스킬을 세션 종료 전 기본 검증 관문으로 취급합니다.
- 실행 전 `docs/sop/SOP_runtime_v2_development_guardrails.md`를 다시 확인하고, 아래 3개 축을 최소 검증 대상으로 고정합니다.
  1. `run_id` 정렬
  2. `error_code` 의미 일치
  3. `attempt/backoff` 계약 일치
- 위 3개 중 하나라도 어긋나면 완료 주장을 중단하고, 기능 추가보다 contract/evidence drift 수정을 우선합니다.

## 실행 대상 스킬

이 스킬이 순차 실행하는 검증 스킬 목록입니다. `/manage-skills`가 스킬을 생성/삭제할 때 이 목록을 자동 업데이트합니다.

현재 등록표는 비어 있을 수 있지만, `runtime_v2` 작업에서는 위 `runtime_v2 Guardrails Gate`를 먼저 실행한 뒤에만 하위 `verify-*` 스킬 실행 여부를 판단합니다.

(아직 등록된 스킬이 없습니다)

<!-- 스킬이 추가되면 아래 형식으로 등록:
| # | 스킬 | 설명 |
|---|------|------|
| 1 | `verify-example` | 예시 검증 설명 |
-->

## 워크플로우

### Step 1: 소개

위의 **실행 대상 스킬** 섹션에 나열된 스킬을 확인합니다.

`runtime_v2` 작업인 경우, 먼저 `docs/sop/SOP_runtime_v2_development_guardrails.md`를 다시 확인한 뒤 검증을 시작합니다.

선택적 인수가 제공된 경우, 해당 스킬만 필터링합니다.

**등록된 스킬이 0개인 경우:**

```markdown
## 구현 검증

하위 검증 스킬 등록은 비어 있습니다.

단, `runtime_v2` 작업이면 guardrails gate(`run_id` / `error_code` / `attempt/backoff`)는 기본 검증으로 계속 수행합니다.

추가 하위 검증이 필요하면 `/manage-skills`를 실행하여 프로젝트에 맞는 검증 스킬을 정렬하세요.
```

이 경우 워크플로우를 종료합니다.

**등록된 스킬이 1개 이상인 경우:**

실행 대상 스킬 테이블의 내용을 표시합니다:

```markdown
## 구현 검증

다음 검증 스킬을 순차 실행합니다:

| # | 스킬 | 설명 |
|---|------|------|
| 1 | verify-<name1> | <description1> |
| 2 | verify-<name2> | <description2> |

검증 시작...
```

### Step 2: 순차 실행

**실행 대상 스킬** 테이블에 나열된 각 스킬에 대해 다음을 수행합니다:

#### 2a. 스킬 SKILL.md 읽기

해당 스킬의 `.claude/skills/verify-<name>/SKILL.md`를 읽고 다음 섹션을 파싱합니다:

- **Workflow** — 실행할 검사 단계와 탐지 명령어
- **Exceptions** — 위반이 아닌 것으로 간주되는 패턴
- **Related Files** — 검사 대상 파일 목록

#### 2b. 검사 실행

Workflow 섹션에 정의된 각 검사를 순서대로 실행합니다:

1. 검사에 명시된 도구(Grep, Glob, Read, Bash)를 사용하여 패턴 탐지
2. 탐지된 결과를 해당 스킬의 PASS/FAIL 기준에 대조
3. Exceptions 섹션에 해당하는 패턴은 면제 처리
4. FAIL인 경우 이슈를 기록:
   - 파일 경로 및 라인 번호
   - 문제 설명
   - 수정 권장 사항 (코드 예시 포함)

#### 2c. 스킬별 결과 기록

각 스킬 실행 완료 후 진행 상황을 표시합니다:

```markdown
### verify-<name> 검증 완료

- 검사 항목: N개
- 통과: X개
- 이슈: Y개
- 면제: Z개

[다음 스킬로 이동...]
```

### Step 3: 통합 보고서

모든 스킬 실행 완료 후, 결과를 하나의 보고서로 통합합니다:

```markdown
## 구현 검증 보고서

### 요약

| 검증 스킬 | 상태 | 이슈 수 | 상세 |
|-----------|------|---------|------|
| verify-<name1> | PASS / X개 이슈 | N | 상세... |
| verify-<name2> | PASS / X개 이슈 | N | 상세... |

**발견된 총 이슈: X개**
```

**모든 검증 통과 시:**

```markdown
모든 검증을 통과했습니다!

구현이 프로젝트의 모든 규칙을 준수합니다:

- verify-<name1>: <통과 내용 요약>
- verify-<name2>: <통과 내용 요약>

코드 리뷰 준비가 완료되었습니다.
```

**이슈 발견 시:**

각 이슈를 파일 경로, 문제 설명, 수정 권장 사항과 함께 나열합니다:

```markdown
### 발견된 이슈

| # | 스킬 | 파일 | 문제 | 수정 방법 |
|---|------|------|------|-----------|
| 1 | verify-<name1> | `path/to/file.ts:42` | 문제 설명 | 수정 코드 예시 |
| 2 | verify-<name2> | `path/to/file.tsx:15` | 문제 설명 | 수정 코드 예시 |
```

### Step 4: 사용자 액션 확인

이슈가 발견된 경우 `AskUserQuestion`을 사용하여 사용자에게 확인합니다:

```markdown
---

### 수정 옵션

**X개 이슈가 발견되었습니다. 어떻게 진행할까요?**

1. **전체 수정** - 모든 권장 수정사항을 자동으로 적용
2. **개별 수정** - 각 수정사항을 하나씩 검토 후 적용
3. **건너뛰기** - 변경 없이 종료
```

### Step 5: 수정 적용

사용자 선택에 따라 수정을 적용합니다.

**"전체 수정" 선택 시:**

모든 수정을 순서대로 적용하며 진행 상황을 표시합니다:

```markdown
## 수정 적용 중...

- [1/X] verify-<name1>: `path/to/file.ts` 수정 완료
- [2/X] verify-<name2>: `path/to/file.tsx` 수정 완료

X개 수정 완료.
```

**"개별 수정" 선택 시:**

각 이슈마다 수정 내용을 보여주고 `AskUserQuestion`으로 승인 여부를 확인합니다.

### Step 6: 수정 후 재검증

수정이 적용된 경우, 이슈가 있었던 스킬만 다시 실행하여 Before/After를 비교합니다:

```markdown
## 수정 후 재검증

이슈가 있었던 스킬을 다시 실행합니다...

| 검증 스킬 | 수정 전 | 수정 후 |
|-----------|---------|---------|
| verify-<name1> | X개 이슈 | PASS |
| verify-<name2> | Y개 이슈 | PASS |

모든 검증을 통과했습니다!
```

**여전히 이슈가 남은 경우:**

```markdown
### 잔여 이슈

| # | 스킬 | 파일 | 문제 |
|---|------|------|------|
| 1 | verify-<name> | `path/to/file.ts:42` | 자동 수정 불가 — 수동 확인 필요 |

수동으로 해결한 후 `/verify-implementation`을 다시 실행하세요.
```

---

## 예외사항

다음은 **문제가 아닙니다**:

1. **등록된 스킬이 없는 프로젝트** — 오류가 아닌 안내 메시지를 표시하고 종료
2. **스킬의 자체적 예외** — 각 verify 스킬의 Exceptions 섹션에 정의된 패턴은 이슈로 보고하지 않음
3. **verify-implementation 자체** — 실행 대상 스킬 목록에 자기 자신을 포함하지 않음
4. **manage-skills** — `verify-`로 시작하지 않으므로 실행 대상에 포함되지 않음

## Related Files

| File | Purpose |
|------|---------|
| `.claude/skills/manage-skills/SKILL.md` | 스킬 유지보수 (이 파일의 실행 대상 스킬 목록을 관리) |
| `docs/sop/SOP_runtime_v2_development_guardrails.md` | runtime_v2 세션 시작/종료 가드레일 |
| `CLAUDE.md` | 프로젝트 지침 |

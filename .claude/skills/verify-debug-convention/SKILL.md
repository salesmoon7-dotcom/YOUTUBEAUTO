---
name: verify-debug-convention
description: CLAUDE.md §4 디버그 코드 규약 검증. 디버깅용 코드에 @DEBUG_PIPELINE 태그가 있는지, 태그 없는 디버그 코드가 남아있는지 탐지합니다. 코드 수정 후 사용.
---

# 디버그 코드 규약 검증

## Purpose

CLAUDE.md §4 "Debug Code Convention"을 기계적으로 검증합니다:

1. **태그 부착 확인** — 디버깅용 코드에 `# @DEBUG_PIPELINE` 태그가 있는지
2. **미태그 디버그 코드 탐지** — 태그 없이 남아있는 `print()`, 임시 로깅, 디버그 변수
3. **DEBUG 플래그 상태** — `DEBUG_PIPELINE = True/False` 설정 확인

## When to Run

- 디버깅 코드를 추가한 후
- 버그 수정 완료 후 (디버그 코드 정리 확인)
- PR 전 최종 검증 시
- 안정화 완료 후 디버그 코드 일괄 제거 시

## Related Files

| File | Purpose |
|------|---------|
| `scripts/seaart_automation.py` | SeaArt 자동화 — 현재 디버그 코드 포함 가능 |
| `scripts/claude_automation.py` | Claude 자동화 |
| `scripts/genspark_automation.py` | Genspark 자동화 |
| `scripts/grok_automation.py` | Grok 자동화 |
| `master_manager.py` | 메인 오케스트레이터 |
| `pipeline.py` | 파이프라인 |
| `sub_runners.py` | 서브프로세스 러너 |
| `CLAUDE.md` | 프로젝트 규칙 §4 |

## Workflow

### Step 1: @DEBUG_PIPELINE 태그 현황 수집

```bash
grep -rn "@DEBUG_PIPELINE" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null
```

태그된 디버그 코드의 파일, 라인, 내용을 수집합니다.

### Step 2: 미태그 디버그 코드 탐지

다음 패턴에 매칭되지만 `@DEBUG_PIPELINE`이 없는 라인을 찾습니다:

```bash
# 디버그 print문 (log_error/log_info/log_debug 제외)
grep -n "^\s*print(" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null | grep -v "@DEBUG_PIPELINE" | grep -v "_backup_"

# 디버그 변수
grep -n "debug\s*=\s*True\|DEBUG\s*=\s*True" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null | grep -v "@DEBUG_PIPELINE" | grep -v "DEBUG_PIPELINE"
```

**PASS 기준:** 미태그 디버그 코드 0건
**FAIL 기준:** `@DEBUG_PIPELINE` 없이 디버그성 `print()` 또는 디버그 변수가 존재

### Step 3: DEBUG_PIPELINE 플래그 확인

```bash
grep -rn "DEBUG_PIPELINE" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null
```

`DEBUG_PIPELINE = True`인 파일이 있으면 경고 (안정화 후 False로 전환 필요)

### Step 4: 결과 보고

```markdown
## verify-debug-convention 결과

| 검사 | 상태 | 발견 |
|------|------|------|
| @DEBUG_PIPELINE 태그 현황 | INFO | N개 |
| 미태그 디버그 코드 | PASS/FAIL | N건 |
| DEBUG_PIPELINE 플래그 | INFO/WARN | True/False |
```

## Output Format

| 파일 | 라인 | 태그 유무 | 내용 | 상태 |
|------|------|-----------|------|------|
| `path:line` | N | YES/NO | 코드 | PASS/WARN/FAIL |

## Exceptions

다음은 **위반이 아닙니다**:

1. **프로그레스 print문** — `print(f"\r  [{idx}...]", end="", flush=True)` 형태의 진행률 표시는 디버그가 아님
2. **로깅 함수** — `log_error()`, `log_info()`, `log_debug()`, `log_warning()` 호출은 정식 로깅
3. **메인 함수의 print** — `if __name__ == "__main__":` 블록 내 print는 CLI 출력용
4. **백업 파일** — `*_backup_*.py` 파일은 검사 대상 아님

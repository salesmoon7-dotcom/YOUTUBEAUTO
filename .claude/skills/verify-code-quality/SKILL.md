---
name: verify-code-quality
description: CLAUDE.md §2 코드 품질 규칙 검증. type 억제, 빈 catch, 임시방편 코드, 하드코딩 등을 탐지합니다. 코드 수정 후 사용.
---

# 코드 품질 규칙 검증

## Purpose

CLAUDE.md §2 "Code Quality Rules"를 기계적으로 검증합니다:

1. **타입 억제 금지** — `as any`, `@ts-ignore`, `@ts-expect-error`, `# type: ignore` 탐지
2. **빈 catch 블록 금지** — `except:` 또는 `except Exception:` 뒤에 `pass`만 있는 블록
3. **임시방편 코드 탐지** — `TODO`, `FIXME`, `HACK`, `WORKAROUND`, `TEMPORARY` 주석
4. **하드코딩 탐지** — 비밀번호, API 키, 절대경로 등의 하드코딩

## When to Run

- Python 파일을 수정한 후
- 새 함수를 추가한 후
- 버그 수정 후
- PR 전 최종 검증 시

## Related Files

| File | Purpose |
|------|---------|
| `scripts/seaart_automation.py` | SeaArt 자동화 (1,763줄) |
| `scripts/claude_automation.py` | Claude 자동화 |
| `scripts/genspark_automation.py` | Genspark 자동화 |
| `scripts/grok_automation.py` | Grok 자동화 |
| `scripts/ken_burns_effect.py` | Ken Burns 효과 |
| `scripts/qwen3_tts_automation.py` | TTS 자동화 |
| `scripts/vrew_web_automation.py` | Vrew 웹 자동화 |
| `scripts/geminigen_automation.py` | GeminiGen 자동화 |
| `scripts/render.py` | 렌더링 |
| `master_manager.py` | 메인 오케스트레이터 |
| `pipeline.py` | 파이프라인 |
| `sub_runners.py` | 서브프로세스 러너 |
| `manager_gui.py` | GUI |
| `CLAUDE.md` | 프로젝트 규칙 |

## Workflow

### Step 1: 타입 억제 패턴 탐지

변경된 Python 파일에서 다음 패턴을 검색합니다:

```bash
grep -rn "# type: ignore" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null
grep -rn "# noqa" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null
```

**PASS 기준:** 매칭 0건
**FAIL 기준:** 1건 이상 매칭

### Step 2: 빈 catch 블록 탐지

```bash
grep -Pn "except.*:\s*$" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null
grep -An1 "except" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null | grep -B1 "pass$"
```

**주의:** `except Exception:` 후 `log_error()` + `continue`는 허용 (유효한 에러 처리)
**FAIL 기준:** `except:` 뒤에 `pass`만 있고 로깅이 없는 경우

### Step 3: 임시방편 코드 탐지

```bash
grep -rn "# TODO\|# FIXME\|# HACK\|# WORKAROUND\|# TEMPORARY\|# 임시" scripts/*.py master_manager.py pipeline.py sub_runners.py 2>/dev/null
```

**PASS 기준:** 매칭 0건 (또는 `@DEBUG_PIPELINE` 태그가 함께 있으면 허용)
**FAIL 기준:** 태그 없는 임시 코드 존재

### Step 4: py_compile 검증

변경된 모든 Python 파일의 구문 오류를 검사합니다:

```bash
python -m py_compile scripts/seaart_automation.py
python -m py_compile master_manager.py
python -m py_compile pipeline.py
python -m py_compile sub_runners.py
```

**PASS 기준:** 모든 파일 exit code 0
**FAIL 기준:** 구문 오류 발생

### Step 5: 결과 보고

```markdown
## verify-code-quality 결과

| 검사 | 상태 | 발견 |
|------|------|------|
| 타입 억제 | PASS/FAIL | N건 |
| 빈 catch 블록 | PASS/FAIL | N건 |
| 임시방편 코드 | PASS/FAIL | N건 |
| py_compile | PASS/FAIL | N개 파일 오류 |
```

## Output Format

| 검사 항목 | 파일 | 라인 | 내용 | 상태 |
|-----------|------|------|------|------|
| `type-suppress` | `path:line` | N | 패턴 | PASS/FAIL |

## Exceptions

다음은 **위반이 아닙니다**:

1. **`@DEBUG_PIPELINE` 태그가 있는 임시 코드** — 의도적 디버깅 코드이므로 허용 (§4와 연동)
2. **백업 파일 내 패턴** — `*_backup_*.py` 파일은 검사 대상 아님
3. **except + log_error + continue/return** — 에러를 기록하고 흐름을 제어하는 것은 유효한 패턴
4. **vendor/ 디렉토리** — 외부 코드는 검사 대상 아님
5. **테스트 파일의 TODO** — 테스트 파일 내 TODO 주석은 허용

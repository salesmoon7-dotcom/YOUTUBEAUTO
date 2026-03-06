---
name: verify-multilingual
description: CLAUDE.md §3 다국어 UI 처리 검증. UI 텍스트 감지/매칭에서 영어/한국어를 모두 대응하는지 확인합니다. 브라우저 자동화 코드 수정 후 사용.
---

# 다국어 UI 처리 검증

## Purpose

CLAUDE.md §3 "Multilingual UI Handling"을 기계적으로 검증합니다:

1. **양방향 대응 확인** — UI 텍스트를 감지할 때 영어와 한국어를 모두 처리하는지
2. **단일 언어 감지 탐지** — 영어만 또는 한국어만 감지하는 패턴이 있는지
3. **알려진 쌍 검증** — Stop/중지, Send/보내기, Thinking/생각해보기 등

## When to Run

- 브라우저 자동화 스크립트(`*_automation.py`)를 수정한 후
- UI 요소 선택자(selector)를 추가/변경한 후
- 텍스트 기반 요소 탐지 로직을 수정한 후

## Related Files

| File | Purpose |
|------|---------|
| `scripts/claude_automation.py` | Claude 자동화 — 다국어 대응 필수 |
| `scripts/seaart_automation.py` | SeaArt 자동화 — 영어 UI (다국어 불필요) |
| `scripts/genspark_automation.py` | Genspark 자동화 — 영어 UI |
| `scripts/grok_automation.py` | Grok 자동화 — 다국어 대응 필요 |
| `scripts/vrew_web_automation.py` | Vrew 자동화 — 한국어 UI |
| `scripts/canva_automation.py` | Canva 자동화 |
| `CLAUDE.md` | 프로젝트 규칙 §3 |

## Workflow

### Step 1: 텍스트 기반 요소 탐지 패턴 수집

변경된 자동화 스크립트에서 텍스트로 UI 요소를 찾는 패턴을 검색합니다:

```bash
# 텍스트 포함 검색 패턴
grep -n "\.text\s*==\|\.text\s*in\|contains.*text\|text()\s*==\|'Stop'\|'Send'\|'Thinking'" scripts/claude_automation.py scripts/grok_automation.py 2>/dev/null

# XPath text() 패턴
grep -n "text()" scripts/claude_automation.py scripts/grok_automation.py 2>/dev/null

# 버튼 텍스트 매칭
grep -n "button.*text\|\.text.*button" scripts/claude_automation.py scripts/grok_automation.py 2>/dev/null
```

### Step 2: 단일 언어 감지 확인

수집된 패턴에서 영어만 또는 한국어만 사용하는 경우를 탐지합니다:

**알려진 필수 쌍:**
| 영어 | 한국어 |
|------|--------|
| Stop | 중지 |
| Send | 보내기 |
| Thinking | 생각해보기 |
| Copy | 복사 |
| Edit | 편집 |
| Delete | 삭제 |
| Cancel | 취소 |
| Confirm | 확인 |
| Submit | 제출 |
| Generate | 생성 |

```bash
# Stop이 있으면 중지도 있어야 함
grep -n "'Stop'" scripts/claude_automation.py 2>/dev/null
grep -n "'중지'" scripts/claude_automation.py 2>/dev/null
```

**PASS 기준:** 텍스트 매칭에 영어/한국어가 모두 포함됨 (or/in/리스트)
**FAIL 기준:** 한 언어만 감지하고 다른 언어는 누락

### Step 3: 결과 보고

```markdown
## verify-multilingual 결과

| 파일 | 텍스트 매칭 | 영어 | 한국어 | 상태 |
|------|-------------|------|--------|------|
| claude_automation.py:L123 | "Stop" | YES | YES | PASS |
| claude_automation.py:L456 | "Send" | YES | NO | FAIL |
```

## Output Format

| 파일 | 라인 | 텍스트 | 영어 | 한국어 | 상태 |
|------|------|--------|------|--------|------|
| `path:line` | N | 감지 텍스트 | YES/NO | YES/NO | PASS/FAIL |

## Exceptions

다음은 **위반이 아닙니다**:

1. **영어 전용 사이트의 스크립트** — SeaArt, Genspark 등 영어만 지원하는 사이트는 한국어 불필요
2. **한국어 전용 사이트의 스크립트** — Vrew 등 한국어만 지원하는 사이트는 영어 불필요
3. **CSS 셀렉터/XPath 속성** — `class`, `id`, `data-*` 등 속성 기반 선택은 언어 무관
4. **로깅 텍스트** — `log_error("메시지")` 등은 사용자에게 보이지 않으므로 단일 언어 허용
5. **일본어 제외** — CLAUDE.md §3에 명시: 일본어는 제외

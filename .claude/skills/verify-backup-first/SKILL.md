---
name: verify-backup-first
description: CLAUDE.md §1 백업 우선 규칙 검증. 변경된 파일에 대응하는 백업이 존재하는지, 백업과의 diff를 확인했는지 검증합니다. 코드 수정 후 사용.
---

# 백업 우선 규칙 검증

## Purpose

CLAUDE.md §1 "ABSOLUTE RULE: Backup First Protocol"을 기계적으로 검증합니다:

1. **백업 존재 확인** — 변경된 스크립트 파일에 대응하는 백업이 backup/, backups/, system/backup/ 중 하나에 존재하는지
2. **백업 참조 확인** — 변경 내용이 백업의 검증된 패턴을 기반으로 했는지 (새 로직을 처음부터 만들지 않았는지)
3. **복원/확장 패턴** — 새로 만든 것이 아니라 백업 로직을 복원/확장했는지

## When to Run

- 스크립트 파일(`.py`)을 수정한 후
- 버그를 수정한 후
- 새 기능을 추가한 후
- PR 전 최종 검증 시

## Related Files

| File | Purpose |
|------|---------|
| `backup/` | 날짜별 주요 백업 (2026-02-07_pre-test, 2026-02-08_pre-stage2 등) |
| `backup/2026-02-07_pre-test/` | Phase1 테스트 전 백업 |
| `backup/2026-02-08_pre-stage2/` | Stage2 전 백업 |
| `backup/2026-02-12_pre-flac-review/` | FLAC 리뷰 전 백업 |
| `backup/voice_merge_20260211/` | 음성 병합 백업 |
| `backup/pipeline_20260213_2322/` | 파이프라인 백업 |
| `backups/` | 구조 변경 백업 |
| `system/backup/` | 시스템 백업 |
| `scripts/seaart_automation_backup_20260202.py` | SeaArt 순차처리 원본 백업 |
| `scripts/genspark_automation_backup_20260202.py` | Genspark 원본 백업 |
| `scripts/geminigen_automation_backup_20260210.py` | GeminiGen 원본 백업 |
| `scripts/vrew_web_automation_backup_20260213.py` | Vrew 원본 백업 |
| `scripts/grok_automation_backup_20260201_integration_ready.py` | Grok 통합 전 백업 |
| `claude_automation.py` | 루트 원본 (6733줄) — scripts/ 파일의 참조용 |
| `CLAUDE.md` | 프로젝트 규칙 |

## Workflow

### Step 1: 변경된 파일 수집

현재 세션에서 변경된 파일 목록을 수집합니다:

```bash
git diff HEAD --name-only 2>/dev/null
git diff --cached --name-only 2>/dev/null
```

변경된 `.py` 파일만 필터링합니다. 백업 폴더(backup/, backups/, system/backup/) 내 파일은 제외합니다.

### Step 2: 각 변경 파일의 백업 존재 확인

변경된 각 `.py` 파일에 대해, 대응하는 백업 파일이 아래 위치 중 하나에 존재하는지 확인합니다:

**검색 순서 (CLAUDE.md §1 우선순위):**

1. `backup/` 내 가장 최신 날짜 폴더에서 동일 파일명
2. `backups/` 내에서 동일 파일명
3. `system/backup/` 내에서 동일 파일명
4. `scripts/` 내 `*_backup_*.py` 파일 (인라인 백업)
5. 루트 `claude_automation.py` (scripts/claude_automation.py 전용)

```bash
# 예: scripts/seaart_automation.py 변경 시
ls backup/*/scripts/seaart_automation.py 2>/dev/null
ls backup/*/seaart_automation.py 2>/dev/null
ls scripts/seaart_automation_backup_*.py 2>/dev/null
```

**PASS 기준:** 변경된 파일에 대응하는 백업이 1개 이상 존재
**FAIL 기준:** 백업이 하나도 없는 파일을 수정함

### Step 3: 변경 내용과 백업의 diff 비교

변경된 파일과 가장 가까운 백업 간 diff를 확인합니다:

```bash
# 예시
diff scripts/seaart_automation.py scripts/seaart_automation_backup_20260202.py | head -50
```

**확인 사항:**
- 변경된 함수가 백업에도 존재하는지
- 백업의 로직을 기반으로 수정했는지 vs 완전히 새로 작성했는지
- 백업에 있는 검증된 패턴(예: `wait_for_image_generation`)을 무시하지 않았는지

**PASS 기준:** 변경된 함수가 백업 로직을 기반으로 복원/확장됨
**FAIL 기준:** 백업에 검증된 구현이 있는데 완전히 다른 새 로직을 작성함

### Step 4: 결과 보고

```markdown
## verify-backup-first 결과

| 변경 파일 | 백업 위치 | 상태 |
|-----------|-----------|------|
| scripts/seaart_automation.py | scripts/seaart_automation_backup_20260202.py | PASS/FAIL |
| scripts/claude_automation.py | backup/2026-02-07_pre-test/scripts/ | PASS/FAIL |
```

## Output Format

| 파일 | 백업 존재 | Diff 확인 | 복원 기반 | 상태 |
|------|-----------|-----------|-----------|------|
| `path` | YES/NO | YES/NO | YES/NO | PASS/FAIL |

## Exceptions

다음은 **위반이 아닙니다**:

1. **새 파일 생성** — 기존에 없는 완전히 새로운 파일은 백업이 없는 것이 정상
2. **설정 파일 변경** — `.json`, `.bat`, `.md` 등 비-코드 파일은 백업 의무 대상 아님
3. **테스트 파일** — `test_*.py`, `*_test.py` 파일은 백업 불필요
4. **백업 파일 자체** — `*_backup_*.py` 파일은 검증 대상 아님

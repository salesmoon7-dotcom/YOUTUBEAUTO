# Chat Interruption Remediation Batches Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `docs/plans/2026-03-11-chat-interruption-structure-remediation-plan.md`를 실제 실행 순서 기준으로 `즉시 실행 배치`와 `후속 배치`로 나눠, 먼저 체감 개선이 큰 구조 정리를 수행하고 그 뒤 운영 문서/검증 체계를 정리합니다.

**Architecture:** 1차 배치는 저장소 루트에 쌓인 대형 런타임 데이터와 임시 산출물을 repo 밖으로 이동시키는 구조 변경에 집중합니다. 2차 배치는 검색 범위, 문서 표면, SOP를 정리해 같은 문제가 다시 누적되지 않도록 운영 규칙을 고정합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, local filesystem on Windows, Markdown docs/SOP, `py_compile`, targeted verification

---

## Batch 1: 즉시 실행 배치

**목적:** 채팅 끊김 체감에 가장 크게 기여하는 대형 런타임 디렉터리와 root clutter를 먼저 제거합니다.

### Task 1: 브라우저 세션 루트 외부화

**Files:**
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2_manager_gui.py`

**Step 1: External session root 상수/기본값 정의**

예시 기본 경로:

```text
D:\YOUTUBEAUTO_RUNTIME\sessions\
```

**Step 2: 기존 `runtime_v2/sessions/*` 참조를 외부 루트 기반으로 변경**

서비스명(`chatgpt-primary`, `genspark-primary` 등)은 유지하고 실제 저장 위치만 변경합니다.

**Step 3: 기존 세션 migration 절차를 먼저 정의**

기존 로그인 상태를 잃지 않도록 다음 중 하나를 명시합니다.
- 기존 세션 디렉터리를 외부 루트로 이동/복사
- 한시적 fallback lookup으로 외부 루트 우선, 기존 repo 경로 차순 조회

**Step 4: GUI/CLI에서 같은 루트를 바라보도록 정렬**

`runtime root` 또는 session root 해석 경로가 어긋나지 않도록 맞춥니다.

**Step 5: 검증**

Run:

```bash
python -m py_compile runtime_v2/config.py runtime_v2/browser/manager.py runtime_v2_manager_gui.py
```

Expected: PASS

### Task 2: Probe 출력 루트 외부화

**Files:**
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/config.py`
- Modify: 관련 docs

**Step 1: `system/runtime_v2_probe/*` 대신 외부 probe root 정의**

예시 기본 경로:

```text
D:\YOUTUBEAUTO_RUNTIME\probe\
```

**Step 2: detached/probe 경로 기본값을 외부 root로 변경**

단, `system/runtime_v2/` canonical evidence는 그대로 둡니다.

**Step 3: 기존 evidence 조회는 override로 유지**

`--probe-root` 수동 지정은 계속 허용합니다.

**Step 4: 검증**

Run path-focused compile/tests.

### Task 3: 대형 `tmp_*` 및 patch/temp 파일 정리

**Files:**
- Modify: `.gitignore`
- Modify: docs cleanup rule files

**Step 1: 외부 scratch root 정의**

예시:

```text
D:\YOUTUBEAUTO_RUNTIME\scratch\
```

**Step 2: 대형 `tmp_*` 디렉터리와 patch/temp 산출물이 repo root에 생성되지 않게 규칙화**

**Step 3: 현재 남아 있는 root clutter 정리**

대상 예시:
- `_tmp_stage.patch`
- `tmp_task1_*.patch`
- `tmp_stage_*.py`
- `tmp_geminigen_from_backup/`
- `tmp_gemini_window_test/`

**Step 4: 검증**

Run:

```bash
git status --short
```

Expected: transient clutter disappears or is reduced to active source changes only

---

## Batch 2: 후속 배치

**목적:** 같은 구조 문제가 반복되지 않도록 검색 규칙, 문서 표면, triage SOP를 정리합니다.

### Task 4: 기본 검색 범위를 source-only로 제한

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/INDEX.md`

**Step 1: broad search 제외 경로를 canonical rule로 기록**

제외 대상:

```text
runtime_v2/sessions/
system/runtime_v2_probe/
tmp_*/
system/runtime_v2/logs/
```

**Step 2: interruption 의심 시 `interrupt-safe + source-only`를 기본값으로 고정**

### Task 5: active 문서 표면 축소

**Files:**
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`
- Modify: `docs/INDEX.md`
- Move/Modify: `docs/archive/plans/*`

**Step 1: active 문서에서 긴 다중 파일 bullet을 줄이고 canonical 링크 중심으로 정리**

**Step 2: 역사성 문서는 archive로 더 이동**

### Task 6: repo 전용 lag triage SOP 추가

**Files:**
- Create: `docs/sop/SOP_chat_interruption_repo_triage.md`
- Modify: `docs/INDEX.md`
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`

**Step 1: 진단 순서 문서화**

필수 체크 순서:
1. workspace size
2. runtime data under repo root
3. dirty worktree clutter
4. broad search suppression
5. interrupt-safe mode switch

**Step 2: INDEX/guardrails에서 링크**

### Task 7: 재측정 및 종료 검증

**Files:**
- Verify: modified code/docs

**Step 1: 주요 디렉터리 크기 재측정**

비교 대상:
- `runtime_v2/`
- `system/`
- `tmp_*`

**Step 2: compile + targeted verification**

**Step 3: 성공 기준 확인**

- repo root가 다시 코드/문서 중심 구조가 되었는지
- 대형 browser/probe/scratch 데이터가 repo 밖으로 빠졌는지
- 문서상 interrupt-safe/source-only 규칙이 canonical reference에 고정됐는지

---

## Recommended Order

1. Batch 1 / Task 1
2. Batch 1 / Task 2
3. Batch 1 / Task 3
4. Batch 2 / Task 4
5. Batch 2 / Task 5
6. Batch 2 / Task 6
7. Batch 2 / Task 7

## Why This Split

- Batch 1만 끝나도 채팅 끊김 체감은 크게 줄 가능성이 높습니다.
- Batch 2는 재발 방지와 작업 규칙 고정이 목적입니다.
- 즉시 체감 개선과 장기 운영 규칙을 분리하면, 중간 성과를 빠르게 확인할 수 있습니다.

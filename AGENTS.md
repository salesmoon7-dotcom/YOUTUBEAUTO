# AGENTS.md

This file is a router, not a full manual.

## Core Rules
- Read `CLAUDE.md` first. It contains universal safety and execution rules.
- Keep top-level files short; use `docs/INDEX.md` as the main navigation map for deeper project context.
- Prefer deterministic checks (lint/test/type/build) over prompt-only guidance.

## Canonical Docs (System of Record)
- `docs/INDEX.md` - canonical entrypoint and navigation
- `docs/TODO.md` - active work index
- `docs/COMPLETED.md` - completed work index
- `docs/plans/` - execution plans and decision logs
- `docs/sop/` - operational procedures
- `docs/sop/SOP_skill_auto_loading.md` - 프롬프트 의도별 설치 스킬 자동 호출 기준
- `docs/sop/SOP_git_online_commit_workflow.md` - 온라인 Git 연결/커밋 표준 절차
- `docs/sop/SOP_runtime_v2_development_guardrails.md` - runtime_v2 개발 대명제, 세션 시작 가드레일, 단순화/디버깅 우선 규칙
- `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md` - 24h 브라우저 상시가동, GPU 중복실행 금지, GPT floor 자동복구 기준

## Task Routing
- For any prompt, load the skill routing defaults from `docs/sop/SOP_skill_auto_loading.md` first and use `docs/INDEX.md` for deeper canonical links.
- For closed-loop development automation, use `docs/sop/SOP_closed_loop_automation_skill_map.md` as the canonical skill bundle map.
- For ANY Git work related to remote setup, status review, staging, commit, rebase, or push: read `docs/sop/SOP_git_online_commit_workflow.md` first.
- For `runtime_v2` planning, implementation, and debugging: read `docs/sop/SOP_runtime_v2_development_guardrails.md` first, then the relevant `docs/plans/*.md` or `docs/sop/*.md`.
- For `runtime_v2` chat-session interruption, search scope, or validation execution decisions: read `docs/sop/SOP_chat_interruption_repo_triage.md` together with `docs/sop/SOP_runtime_v2_development_guardrails.md` before acting.
- For `runtime_v2` resumed sessions after interruption or handoff: identify the active plan from `docs/TODO.md`, read that retest/repair plan first, restate the active batch and unresolved gates, and do NOT start with a broad rerun before confirming the next boundary-scoped action.
- For implementation tasks: read relevant `docs/plans/*.md` first.
- For operations/incidents: read relevant `docs/sop/*.md` first.
- For project policy updates: update docs first, keep `CLAUDE.md` minimal.

## Search Scope Default
- In chat sessions, default search scope is source-only: start with code/docs paths and exclude generated runtime trees unless the task is explicitly an evidence/probe investigation.
- Default exclude set: `runtime_v2/sessions/`, `system/runtime_v2_probe/`, `system/runtime_v2/logs/`, `tmp_*/`.
- `system/runtime_v2/` is not part of broad search by default; treat it as an operational snapshot surface and read specific files there only when needed.
- For `runtime_v2`, treat `docs/sop/SOP_runtime_v2_development_guardrails.md` and `docs/sop/SOP_chat_interruption_repo_triage.md` as the canonical search-scope rules.
- For `runtime_v2`, long/file-level foreground pytest and real-browser relaunch/recovery are not default chat-session actions; use case-level pytest only, and escalate longer validation to detached or manual execution.
- For `runtime_v2`, treat semantic-row/full closeout reruns as verification of a pinned boundary only, not as broad "relevant tests" for discovering the next issue.

## Verification
- After edits, run diagnostics + relevant tests + build/typecheck when applicable.
- For `runtime_v2` work, run `verify-implementation` as the default code-change verification gate before claiming code-level completion; do not treat it as proof of final closeout success.
- Search must converge: after confirming 2 relevant signatures/patterns, propose exactly 1 fix path and execute it immediately.
- For `runtime_v2`, never treat probe green, attach available, login confirmed, service generation passed, and final closeout passed as equivalent evidence grades.
- For `runtime_v2`, do not add fallback/fail-open logic unless the active plan records the failing legacy contract, why the legacy path was insufficient, the removal/expiry condition, and whether the fallback is debug-only or allowed on the production path.

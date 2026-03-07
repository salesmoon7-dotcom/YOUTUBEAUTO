# AGENTS.md

This file is a router, not a full manual.

## Core Rules
- Read `CLAUDE.md` first. It contains universal safety and execution rules.
- Keep instructions concise in top-level files; store details in `docs/`.
- Prefer deterministic checks (lint/test/type/build) over prompt-only guidance.

## Canonical Docs (System of Record)
- `docs/INDEX.md` - canonical entrypoint and navigation
- `docs/TODO.md` - active work index
- `docs/COMPLETED.md` - completed work index
- `docs/plans/` - execution plans and decision logs
- `docs/sop/` - operational procedures
- `docs/sop/SOP_git_online_commit_workflow.md` - 온라인 Git 연결/커밋 표준 절차
- `docs/sop/SOP_runtime_v2_development_guardrails.md` - runtime_v2 개발 대명제, 세션 시작 가드레일, 단순화/디버깅 우선 규칙
- `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md` - 24h 브라우저 상시가동, GPU 중복실행 금지, GPT floor 자동복구 기준

## Task Routing
- For ANY Git work related to remote setup, status review, staging, commit, rebase, or push: read `docs/sop/SOP_git_online_commit_workflow.md` first.
- For `runtime_v2` planning, implementation, and debugging: read `docs/sop/SOP_runtime_v2_development_guardrails.md` first, then the relevant `docs/plans/*.md` or `docs/sop/*.md`.
- For implementation tasks: read relevant `docs/plans/*.md` first.
- For operations/incidents: read relevant `docs/sop/*.md` first.
- For project policy updates: update docs first, keep `CLAUDE.md` minimal.

## Verification
- Do not claim completion without command evidence.
- After edits, run diagnostics + relevant tests + build/typecheck when applicable.
- For `runtime_v2` work, run `verify-implementation` as the default session-end verification gate before claiming completion.
- Search must converge: after confirming 2 relevant signatures/patterns, propose exactly 1 fix path and execute it immediately.

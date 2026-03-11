# Docs Index

## Top-Level Routing
- `AGENTS.md` is the repo router.
- `CLAUDE.md` is the minimal universal rule map.
- This file is the canonical docs navigation entrypoint.

## Single Classification Rule
- 문서 상태 분류는 `TODO` 또는 `COMPLETED` 두 가지로만 관리합니다.
- 분류 진입점은 아래 두 문서만 사용합니다.
  - `TODO.md`
  - `COMPLETED.md`

## Active Status Docs
- `TODO.md` - 현재 진행 중이거나 운영 검증이 남은 작업 목록
- `COMPLETED.md` - 코드 구현이 끝난 작업 목록

## Reference Directories (Structure Only)
- `plans/`
- `reference/`
- `sop/`
- `archive/`

## Archive Notes
- Older handoff/session-context documents that are no longer current canonical references may be moved under `archive/plans/`.
- Current first-pass archive set: `archive/plans/HANDOFF_2026-03-06_runtime_v2_phase1_to_phase2.md`, `archive/plans/HANDOFF_2026-03-07_runtime_v2_git_blocked_next_session.md`, `archive/plans/HANDOFF_2026-03-07_runtime_v2_post_smoke_alignment.md`, `archive/plans/2026-03-08-runtime-v2-handoff.md`, `archive/plans/2026-03-09-agent-browser-implementation-handoff.md`

## Operations Priority SOP
- `sop/SOP_git_online_commit_workflow.md`
- `sop/SOP_closed_loop_automation_skill_map.md`
- `sop/SOP_runtime_v2_development_guardrails.md`
- `sop/SOP_chat_interruption_repo_triage.md`
- `sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- `sop/SOP_runtime_v2_inbox_contract.md`
- `sop/SOP_runtime_v2_detached_soak_readiness.md`

## Search Default
- 채팅 세션 기본 검색은 source-only입니다. 자세한 제외 경로와 lag triage 절차는 `sop/SOP_runtime_v2_development_guardrails.md`와 `sop/SOP_chat_interruption_repo_triage.md`를 기준으로 봅니다.

## Current Runtime_v2 Canonical References
- `sop/SOP_runtime_v2_development_guardrails.md`
- `reference/error-code-semantics.md`
- `plans/2026-03-09-runtime-v2-guardrail-drift-remediation-plan.md`
- `plans/2026-03-08-browser-session-stability-plan.md`
- `plans/2026-03-07-runtime-v2-staged-test-plan.md`
- `plans/2026-03-07-runtime-v2-blocker-fix-plan.md`
- `sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- `sop/SOP_runtime_v2_inbox_contract.md`
- `sop/SOP_runtime_v2_detached_soak_readiness.md`
- `system/runtime_v2/health/gui_status.json` - control-loop latest-run GUI snapshot (운영 스냅샷 확인용, broad search 기본 범위 아님)
- `system/runtime_v2/evidence/result.json` - latest-run result snapshot (운영 스냅샷 확인용, broad search 기본 범위 아님)
- `system/runtime_v2/evidence/control_plane_events.jsonl` - control-plane transition evidence (운영 스냅샷 확인용, broad search 기본 범위 아님)

## Session-Start Rule
- `runtime_v2` 관련 작업은 사용자 재지시가 없어도 먼저 `sop/SOP_runtime_v2_development_guardrails.md`를 기준으로 읽고 진행합니다.
- 이 문서는 라우팅과 canonical 링크만 유지합니다. 세부 절차는 각 `sop/`와 `plans/` 문서에서 관리합니다.

위 디렉터리는 저장 위치일 뿐이며, 상태 분류 기준은 `TODO.md` / `COMPLETED.md`의 링크 상태를 따릅니다.

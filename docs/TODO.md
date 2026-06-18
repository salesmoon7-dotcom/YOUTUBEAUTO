# TODO

- `docs/plans/2026-04-23-legacy-program-inventory-map.md`, `docs/plans/2026-04-23-legacy-runtime-coverage-map.md` - legacy inventory / coverage 기준 정본입니다.
- `Vrew`, `ACE BGM`, `Google Sheets sync` - 사용자 지시로 폐기 축으로 고정합니다. 레거시 인벤토리에는 남기되 active migration/완료 범위 계산에서는 제외합니다.
- 현재 개발 대상인 Excel row -> GPT text/plan -> image generation services -> GeminiGen video -> local voice/TTS/RVC -> render/final artifact까지 이어지는 Excel-driven end-to-end automation pipeline은 `Sheet1!row15` 기준 다시 `E2E_UNVERIFIED`입니다. `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-post-qwen-image-readiness-quoted-20260618-193028\artifacts\chatgpt\chatgpt-sheet1-15\4be627f1-9738-487c-af52-efbcc53eed42\raw_output.json`의 Stage1 GPT 응답은 새 parser 기준 `invalid_voice_groups`로 fail-closed 되어야 하며, 기존 render success는 완료 증거로 사용하지 않습니다.
- pending external blocker: `Canva`는 `D:\YOUTUBEAUTO_RUNTIME\probe\canva-boundary-20260524-e\runtime\latest_completed_run.json` 기준 `CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED`로 닫혀 있으며, 크레딧 충전 또는 크레딧이 있는 다른 계정 세션 제공 전까지 보류 축입니다.

- 이 문서는 active index입니다. 긴 다중 파일 설명/세부 절차는 plan/SOP에 두고, 여기에는 1줄 상태와 canonical 링크를 우선 남깁니다.
- 위 원칙은 점진적으로 적용합니다. 기존 긴 evidence/history 블록은 후속 정리 배치에서 축소합니다.
- interruption/search 규칙의 정본은 `docs/sop/SOP_runtime_v2_development_guardrails.md`와 `docs/sop/SOP_chat_interruption_repo_triage.md`입니다.
- `docs/plans/2026-04-01-runtime-v2-closeout-retest-result.md`, `docs/COMPLETED.md` - active closeout baseline / historical bundle 정본 entrypoint입니다.
- `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`, `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-rerun-03\probe_result.json` - generic `1행 smoke` 최소 단계 테스트는 완료되었습니다. semantic target row reference는 `Sheet1!row15`(CLI `--row-index 14`)입니다.
- `docs/plans/2026-06-13-runtime-v2-e2e-completion-plan.md`, `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-post-qwen-image-readiness-quoted-20260618-193028\artifacts\chatgpt\chatgpt-sheet1-15\4be627f1-9738-487c-af52-efbcc53eed42\raw_output.json` - latest accepted `Sheet1!row15` proof is `E2E_UNVERIFIED`; run_id `4be627f1-9738-487c-af52-efbcc53eed42` must be reclassified at Stage1 as `invalid_voice_groups` because unnumbered `[Voice]` text was duplicated across multiple scenes.
- historical note bundle: `runtime simplification reset`, `2026-03-20 drift analysis`, detailed `Canva` chronology, old `semantic row 1회 rerun` guidance, `agent-browser` attach history, stage1/GPT/backend/비-GPT detailed evidence 연대기는 모두 historical/completed scope입니다. active 판단 SSOT는 상단 status bullets, `docs/plans/2026-04-01-runtime-v2-closeout-retest-result.md`, `docs/plans/2026-04-23-legacy-runtime-coverage-map.md`, `docs/COMPLETED.md`입니다.

# TODO

- `docs/plans/2026-04-23-legacy-program-inventory-map.md`, `docs/plans/2026-04-23-legacy-runtime-coverage-map.md` - legacy inventory / coverage 기준 정본입니다.
- `Vrew`, `ACE BGM`, `Google Sheets sync` - 사용자 지시로 폐기 축으로 고정합니다. 레거시 인벤토리에는 남기되 active migration/완료 범위 계산에서는 제외합니다.
- `D:\YOUTUBEAUTO_RUNTIME\probe\stage2-noncanva-20260521-a\probe_result.json` - stage2 핵심 비-Canva 체인(`genspark`, `seaart`, `geminigen`)은 모두 `OK` 상태입니다.
- `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260524-a\probe_result.json` - semantic target row closeout은 성공 닫힘 상태입니다.
- pending external blocker: `Canva`는 `D:\YOUTUBEAUTO_RUNTIME\probe\canva-boundary-20260524-e\runtime\latest_completed_run.json` 기준 `CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED`로 닫혀 있으며, 크레딧 충전 또는 크레딧이 있는 다른 계정 세션 제공 전까지 보류 축입니다.

- 이 문서는 active index입니다. 긴 다중 파일 설명/세부 절차는 plan/SOP에 두고, 여기에는 1줄 상태와 canonical 링크를 우선 남깁니다.
- 위 원칙은 점진적으로 적용합니다. 기존 긴 evidence/history 블록은 후속 정리 배치에서 축소합니다.
- interruption/search 규칙의 정본은 `docs/sop/SOP_runtime_v2_development_guardrails.md`와 `docs/sop/SOP_chat_interruption_repo_triage.md`입니다.
- `docs/plans/2026-04-01-runtime-v2-closeout-retest-result.md` - active closeout baseline 해석 정본입니다. current reading은 semantic row success evidence 기준입니다.
- `docs/COMPLETED.md` - historical/completed plan bundle 정본 entrypoint입니다.
- `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`, `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-rerun-03\probe_result.json` - generic `1행 smoke` 최소 단계 테스트는 완료되었습니다. 현재 해석은 `generic Stage 5 minimum rerun complete`, `Stage 5B complete`, `24h soak deferred`입니다.
- semantic target row reference: `Sheet1!row15`(CLI `--row-index 14`)를 success closeout 기준점으로 유지합니다.
- historical note bundle: `runtime simplification reset`, `2026-03-20 drift analysis`, detailed `Canva` chronology, old `semantic row 1회 rerun` guidance, `agent-browser` attach history, stage1/GPT/backend/비-GPT detailed evidence 연대기는 모두 historical/completed scope입니다. active 판단은 상단 status bullets와 `docs/plans/2026-04-01-runtime-v2-closeout-retest-result.md`, `docs/plans/2026-04-23-legacy-runtime-coverage-map.md`, `docs/COMPLETED.md`를 SSOT로 사용합니다.

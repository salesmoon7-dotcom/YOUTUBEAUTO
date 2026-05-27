# TODO

- `docs/plans/2026-04-23-legacy-program-inventory-map.md` - 레거시 실제 프로그램 목록을 `D:\YOUTUBE_AUTO\scripts` 기준으로 다시 고정한 인벤토리 문서입니다. 앞으로 legacy 분석/완료 판정은 이 문서의 프로그램 지도를 기준으로 비교합니다.
- `docs/plans/2026-04-23-legacy-runtime-coverage-map.md` - 레거시 프로그램 인벤토리와 현재 `runtime_v2` 대응 범위를 대조한 문서입니다. 앞으로 non-Canva 완료 주장이나 잔여 범위 판단은 이 커버리지 맵까지 함께 비교합니다.
- `Vrew`, `ACE BGM`, `Google Sheets sync` - 사용자 지시로 폐기 축으로 고정합니다. 레거시 인벤토리에는 남기되 active migration/완료 범위 계산에서는 제외합니다.
- `D:\YOUTUBEAUTO_RUNTIME\probe\stage2-noncanva-20260521-a\probe_result.json` - stage2 핵심 비-Canva 체인(`genspark`, `seaart`, `geminigen`)은 detached 단일 boundary에서 모두 `status=ok`, `code=OK`, `final_output=true`로 닫혀 있습니다.
- `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row15-20260524-a\probe_result.json` - semantic target row closeout은 `status=ok`, `code=OK`, `probe_success=true` 기준으로 성공 닫힘 상태입니다.
- pending external blocker: `Canva`는 `D:\YOUTUBEAUTO_RUNTIME\probe\canva-boundary-20260524-e\runtime\latest_completed_run.json` 기준 `CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED`로 닫혀 있으며, 크레딧 충전 또는 크레딧이 있는 다른 계정 세션 제공 전까지 보류 축으로 유지합니다.

- 이 문서는 active index입니다. 긴 다중 파일 설명/세부 절차는 plan/SOP에 두고, 여기에는 1줄 상태와 canonical 링크를 우선 남깁니다.
- 위 원칙은 점진적으로 적용합니다. 기존 긴 evidence/history 블록은 후속 정리 배치에서 축소합니다.
- interruption/search 규칙의 정본은 `docs/sop/SOP_runtime_v2_development_guardrails.md`와 `docs/sop/SOP_chat_interruption_repo_triage.md`입니다.
- `docs/plans/2026-04-01-runtime-v2-closeout-retest-result.md` - active closeout baseline 해석 정본입니다. current reading은 semantic row success evidence 기준입니다.
- `docs/COMPLETED.md` - chat-safe execution, guardrail drift, control-plane hotspot review, architecture simplification, conditional tightening, feeder decomposition 1차 관련 historical/completed plan bundle의 정본 entrypoint입니다. 개별 plan의 재오픈 조건과 후속 제한은 `docs/COMPLETED.md`에서 연결된 canonical plan 기준으로 읽습니다.
- `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`, `D:\YOUTUBEAUTO_RUNTIME\probe\browser-recover-minimum-02\probe_result.json`, `D:\YOUTUBEAUTO_RUNTIME\probe\stage5-row1-rerun-03\probe_result.json` - generic `1행 smoke` 최소 단계 테스트는 완료되었습니다. staged-test plan 기준 현재 해석은 `generic Stage 5 minimum rerun complete`, `Stage 5B complete`, `24h soak deferred`입니다.
- semantic target row reference: `Sheet1!row15`(엑셀 UI 16행, CLI `--row-index 14`, 주제 `요양 시설 비용 현실과 준비해야 할 금액`)를 success closeout 기준점으로 유지합니다.
- historical note bundle: `runtime simplification reset`, `2026-03-20 drift analysis`, detailed `Canva` chronology, old `semantic row 1회 rerun` guidance, `agent-browser` attach history, stage1/GPT/backend/비-GPT detailed evidence 연대기는 모두 historical/completed scope입니다. active 판단은 이 TODO 상단 status bullets와 `docs/plans/2026-04-01-runtime-v2-closeout-retest-result.md`, `docs/plans/2026-04-23-legacy-runtime-coverage-map.md`, `docs/COMPLETED.md`를 SSOT로 사용하고, 채팅 세션 실행 규칙은 `docs/sop/SOP_runtime_v2_development_guardrails.md`, `docs/sop/SOP_chat_interruption_repo_triage.md`, `docs/plans/2026-03-08-browser-session-stability-plan.md`를 SSOT로 유지합니다.

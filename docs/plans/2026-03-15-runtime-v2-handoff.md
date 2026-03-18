# Runtime V2 Handoff - 2026-03-15

## Purpose

- 다음 세션 작업자가 현재 `runtime_v2` 상태를 오해 없이 이어받도록 합니다.
- 특히 이번 세션에서 확인된 실패 원인, 수정 완료 항목, 그리고 **다음 세션에서 절대 하면 안 되는 것**을 명시합니다.

## Canonical Plan / TODO Sources

다음 두 문서를 현재 SSOT로 사용합니다.

1. `docs/TODO.md`
2. `docs/plans/2026-03-12-runtime-v2-full-legacy-subprogram-port-plan.md`

이 handoff는 위 두 문서의 실행 요약본입니다.

## What Was Actually Fixed In This Session

- stage1 `topic_spec_fallback` 거짓 성공 누수 차단
- stage1 Excel writeback stale-snapshot bug 수정
- stage1 declared next-job fan-out limit `12 -> 128`
- ChatGPT same-tab lifecycle reset 적용
  - `Page.navigate(CHATGPT_LONGFORM_URL)`
  - `Page.reload(ignoreCache=true)`
- detached launcher에 `CREATE_NO_WINDOW` 적용
- legacy voice grouping 계약 복원
  - `Voice 13-16(4)` -> one grouped mapping with `original_voices=[13,14,15,16]`
- qwen output contract를 `speech.wav` 가정에서 `speech.flac` / `voice/#NN.flac` 기준으로 수정
- live ChatGPT prompt에서 잘못 들어간
  - `"[Ref Img 1], [Ref Img 2], [Video1], [Video2] ... 블록도 함께 채우세요."`
  문구 제거

## What Is NOT Closed Yet

- semantic target row (`Sheet1` row 16 / CLI `--row-index 14`)의 final closeout evidence는 아직 없습니다.
- 이번 세션의 hidden rerun들은 `probe_result.json`, `failure_summary.json`, `render/` final artifact를 남기지 못한 채 중단/미완료 상태로 끝났습니다.
- 따라서 **semantic target row(Sheet1 row 16 / CLI `--row-index 14`) closeout 완료를 주장하면 안 됩니다.**

## Most Important Lessons / Hard Rules For Next Session

다음 세션은 아래 규칙을 반드시 지켜야 합니다.

1. **Legacy contracts first**
   - 실행 전에 레거시 계약을 먼저 잠급니다.
   - 실행 중간에 계약을 재해석하지 않습니다.

2. **Survey order != execution order**
   - 조사 순서, 문서 나열 순서, 구현 체크리스트 순서를 실행 순서처럼 사용하지 않습니다.
   - 실행 순서는 dependency gate / required artifact 기준으로만 결정합니다.

3. **One semantic-row run only**
   - closeout 단계에서는 semantic row를 broad rerun 하지 않습니다.
   - 원칙적으로 clean detached run **1회만** 수행합니다(단, 비결정적 환경 실패에 한해 1회 추가 허용, 그 외 rerun 금지).

4. **Readiness first**
   - `python -m runtime_v2.cli --readiness-check`
   - readiness fail이면 semantic row run을 시작하지 않습니다.
   - readiness blocker 1개만 먼저 고칩니다.

5. **No broad reruns**
   - generic Stage 5 rerun 금지
   - Stage 5B rerun 금지
   - 24h soak 금지
   - broad pytest rerun 금지

6. **User stop means stop**
   - 사용자 중단 지시 후 같은 세션에서 hidden/background rerun 금지
   - 상태는 `interrupted`로 기록하고 다음 세션으로 넘깁니다.

## Shortest-Path Test Strategy For Next Session

오라클 검수 기준 다음 세션의 shortest path는 이것뿐입니다.

1. `python -m runtime_v2.cli --readiness-check`
2. `ready=true`일 때만 semantic row detached run **1회** 실행
3. 새 `probe_root`에 아래 중 하나가 생길 때까지만 확인
   - `probe_result.json` + `render_final.mp4`
   - `probe_result.json` + `failure_summary.json`

## Completion Criteria

다음 세션에서만 closeout(= 1회 실행이 증거로 닫힘)을 주장할 수 있습니다.

- 공통(성공/실패): 새 `probe_root`에 `probe_result.json` 존재
- 성공 closeout: `probe_success=true`, `code=OK`, 그리고 `render_final.mp4` 존재
- 실패 closeout(= fail-closed로 닫힘): `probe_success=false`(또는 비-OK), 그리고 `failure_summary.json` 존재

위 조건을 만족하지 못하면 상태는 `interrupted / not closed`입니다.

## Stop / Escalation Rule

- semantic row 1회 실행이 deterministic contract/logic failure로 끝나면 rerun 금지
- 그 실패 1개만 blocker로 수정
- 비결정적 환경 실패에서만 단 1회 rerun 허용

## Current Session End State

- runtime-related Python processes were force-stopped on user request
- this session ended as `verification interrupted`, not `verification complete`
- no further runtime execution should be inferred from this handoff

## One-Line Handoff

- **다음 세션은 semantic row `1회 detached run`만 목표로 하고, readiness fail이면 그 blocker 1개만 고치고, 사용자 stop 이후엔 절대 rerun하지 마세요.**

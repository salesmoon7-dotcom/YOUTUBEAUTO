# Runtime V2 Staged Test Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers/executing-plans` to execute this plan stage-by-stage.

**Goal:** `runtime_v2`를 현재 로컬 계약 테스트 통과 상태에서 실제 가동 가능 상태까지, 단계별 stop/go 게이트를 가진 테스트 절차로 검증합니다.

**Architecture:** 테스트는 `순수 로컬 계약 -> Excel/Stage1 로컬 -> Stage2/Final 로컬 -> 자원 의존 로컬 -> detached smoke -> 실서비스 수동 smoke(엑셀 1개 행 성공) -> soak readiness -> 24h soak` 순서로 진행합니다. 각 단계는 정확한 실행 명령, 필수 산출물, `run_id` 일치, failure summary, latest-run snapshot을 기준으로 통과/중단을 판정합니다. 24시간 검증은 개발 최종 단계에서만 수행합니다.

**Tech Stack:** Python `unittest`, `openpyxl`, `runtime_v2` CLI/control plane, detached probe, browser health/gpu lease/gpt floor evidence files.

---

## Canonical Plan Link

- 이 문서는 테스트 실행/판정 절차 전용 보조 문서입니다.
- `docs/plans/2026-03-08-browser-session-stability-plan.md`를 `1행 smoke 전까지의 단일 canonical remediation plan`으로 사용합니다.
- 새로운 문제/게이트/중단 기준이 생기면 이 문서를 먼저 늘리지 않고, 먼저 canonical plan에 병합한 뒤 이 문서의 Stage gate에만 반영합니다.
- 이 문서와 canonical plan이 충돌하면 canonical plan을 우선합니다.

## Execution Target Map

| 오늘 실행 대상 | canonical stage | tier | 현재 해석 |
|---|---|---|---|
| `e2e mock test` | Stage 4 | `isolated` | detached mock chain evidence 검증 |
| `비GPT 프로그램 단건 연결 테스트` | Stage 4B | `manual` | mock 이후 비GPT 프로그램을 1개씩 붙여 기능/flow 연결만 검증 |
| `e2e 1행 테스트` | Stage 5 | `manual` | 실서비스 단건 smoke (`1개 행 성공`) |
| `e2e 5행 테스트` | Stage 5B | `manual` | Stage 5 통과 후 5개 준비 행 순차 반복 |

- `e2e 1행 테스트`와 `e2e 5행 테스트`는 `docs/plans/2026-03-08-browser-session-stability-plan.md`의 `No-Go`가 해제되기 전에는 실행하지 않습니다.

## Pre-Stage Global Stop Conditions

- 아래 중 하나라도 성립하면 Stage 진행 전에 중단합니다.
  1. `system/runtime_v2/health/gpt_status.json`에서 `OK < 1`
  2. `system/runtime_v2/evidence/result.json`, `system/runtime_v2/health/gui_status.json`, `system/runtime_v2/evidence/control_plane_events.jsonl`의 latest-run 의미가 서로 조인되지 않음
  3. browser canonical profile ownership 계약이 미확정 상태임
  4. blocked/backoff semantics가 browser/gpu/worker 축에서 서로 다르게 해석됨
  5. canonical plan의 `No-Go` 판정이 아직 해제되지 않음

### Exception For Stage 0 Safe Path

- 단, Stage 0은 `safe` test path 안정화 검증을 위해 예외적으로 먼저 실행할 수 있습니다.
- 이 예외는 운영 readiness를 주장하기 위한 것이 아니라, `run_once()`/`run_control_loop_once()`가 브라우저 start, detached spawn, bootstrap, GPT tick 같은 운영 side effect 없이도 순수 계약 테스트를 통과하는지 확인하기 위한 것입니다.
- 따라서 Stage 0 `safe` 경로에서는 운영 브라우저/GPT 상태를 readiness gate로 해석하지 않고, `side-effect-free path가 실제로 부작용을 건너뛰는지`만 확인합니다.
- 여기서 `allow_runtime_side_effects=False`는 완전한 dry-run이 아닙니다. 운영 canonical 경로를 건드리지 않으려면 임시 `RuntimeConfig` 또는 probe root를 같이 써야 하며, GPT 상태가 없으면 fail-closed로 실패해야 합니다.

## Scope

- 포함: `runtime_v2/`, `system/runtime_v2/`, `system/runtime_v2_probe/` 기준 테스트
- 제외: 외부 참고 `runtime/`, `system/runtime/` 직접 수정/검증
- 원칙:
  - 하부 워커는 Excel 직접 접근 금지
  - Manager만 Excel row와 final status를 갱신
  - Supervisor는 health/gate/recovery만 담당
  - 브라우저 workload는 GPU lease를 잡지 않음
  - 모든 최신 증거는 canonical latest-run 경로에 남아야 함

- 주의: 이 문서에서 `system/runtime_v2/*` 예시는 legacy/historical canonical 경로 표기일 수 있습니다. Task 2 이후 기본 runtime-state root는 `D:/YOUTUBEAUTO_RUNTIME/runtime_state/`이며, 명시적 `--runtime-root` 또는 `RuntimeConfig.from_root()`를 쓰는 경우에만 다른 루트를 사용합니다.

## Test Temp-Root Interpretation Rule

- 다수 테스트가 `TemporaryDirectory(dir="D:\\YOUTUBEAUTO")`를 사용하지만, 이는 기본적으로 test temp-parent convenience입니다.
- 이 패턴만으로 실운영 runtime root가 repo root라고 결론내리지 않습니다.
- 단, temp-root가 실제 latest evidence 해석, runtime root 판정, artifact/output root 검증을 오염시키는 경우에는 해당 테스트만 선택적으로 수정합니다.

## Stage 0: 순수 로컬 계약 게이트

**목적:** 외부 브라우저/GPU/ffmpeg 상태와 무관하게 실행 가능한 순수 계약/로컬 테스트만 먼저 통과시킵니다.

**검증 항목:**
- Python 실행 가능
- `runtime_v2` import 가능
- `system/runtime_v2/` 쓰기 가능
- 외부 참고 경로 쓰기 흔적 없음
- probe 경로와 운영 경로를 분리해도 로컬 테스트가 통과함
- `run_once()`/`run_control_loop_once()`의 `safe` 경로가 browser start/bootstrap/autospawn 없이 동작함

**명령:**
```bash
python -m compileall -q runtime_v2 tests
python -m unittest tests.test_runtime_v2_excel_bridge tests.test_runtime_v2_stage1_chatgpt tests.test_runtime_v2_stage1_excel_merge tests.test_runtime_v2_stage2_contracts tests.test_runtime_v2_stage2_workers tests.test_runtime_v2_final_video_flow tests.test_runtime_v2_excel_topic_end_to_end tests.test_runtime_v2_control_plane_chain -v
```

**LSP 확인:**
- 대상 파일:
  - `runtime_v2/manager.py`
  - `runtime_v2/cli.py`
  - `runtime_v2/control_plane.py`
  - `runtime_v2/supervisor.py`
  - `tests/test_runtime_v2_excel_topic_end_to_end.py`
  - `tests/test_runtime_v2_final_video_flow.py`
- 판정 도구: `lsp_diagnostics`
- 통과 기준: 대상 파일 모두 error 0건

**통과 기준:**
- compileall 성공
- 전체 로컬 회귀 테스트 성공
- 수정 파일 LSP 에러 0건
- `safe` 경로 검증 테스트가 `BrowserManager.start`, detached child, bootstrap, GPT tick을 호출하지 않음을 증명

**중단 조건:**
- 여기서 실패하면 detached/probe/실서비스 테스트로 넘어가지 않음

## Stage 1: Excel-Stage1 로컬 계약 테스트

**목적:** Excel seed, TopicSpec, VideoPlan 경계가 로컬에서 안정적인지 확인합니다.

**명령:**
```bash
python -m unittest tests.test_runtime_v2_excel_bridge tests.test_runtime_v2_stage1_chatgpt tests.test_runtime_v2_stage1_excel_merge -v
```

**필수 산출물:**
- unittest 출력 PASS
- Excel row state transition assertion
- `topic_spec`, `video_plan`, stale snapshot 차단 assertion

**확인 포인트:**
- `--excel-once`가 `no_work/seeded`를 올바르게 처리하는지
- Stage1이 `topic_spec` 버전/voice mapping mismatch를 fail-closed 하는지
- stale Excel snapshot이면 merge가 차단되는지
- terminal row를 덮어쓰지 않는지

**통과 기준:**
- `topic_spec -> video_plan` 생성 성공
- `excel_path`가 하부 워커 계약에 들어가지 않음
- `run_id`, `row_ref`, `reason_code`, `debug_log`가 Stage1 결과에 남음

**중단 조건:**
- 여기서 실패하면 Stage 2 이상 금지

## Stage 2: Stage2/Final 로컬 계약 테스트

**목적:** Stage2/Final worker 경계와 final sync가 실제 계약대로 동작하는지 확인합니다.

**명령:**
```bash
python -m unittest tests.test_runtime_v2_stage2_contracts tests.test_runtime_v2_stage2_workers tests.test_runtime_v2_final_video_flow tests.test_runtime_v2_excel_topic_end_to_end -v
```

**필수 산출물:**
- unittest 출력 PASS
- `render_spec`, `result.json`, `failure_summary.json`, final sync assertion
- `worker_stalls`, `run_id`, `final_output`, `final_artifact_path` assertion

**확인 포인트:**
- `video_plan -> stage2 job/render_spec` 생성
- browser workload는 browser gate만 사용하고 GPU lease를 잡지 않음
- resident worker registry/stall report가 supervisor 결과로 노출됨
- manager가 최종 completion을 Excel `Done/partial`과 latest-run `result.json`으로 동기화함
- `failure_summary.json`과 `result.json`이 연결됨

**통과 기준:**
- final worker completion에 `final_output`, `final_artifact_path`, `reason_code` 반영
- `result.json`, `failure_summary.json`이 canonical schema와 경로를 사용

**중단 조건:**
- 여기서 실패하면 Stage 3 이상 금지

## Stage 3: 자원 의존 로컬 런타임 게이트

**목적:** 브라우저 plane/GPU worker 같은 자원 의존 테스트를 실제 detached/prod smoke 전에 따로 검증합니다.

**명령:**
```bash
python -m unittest tests.test_runtime_v2_browser_plane tests.test_runtime_v2_gpu_workers -v
```

**통과 기준:**
- browser plane 테스트 성공
- GPU worker 테스트 성공
- 브라우저 workload와 GPU workload의 게이트 분리가 테스트로 증명됨
- stale browser profile lock이 남아도 `busy`/`stale` 구분과 자동 복구 경로가 테스트로 증명됨
- `unknown` lock metadata 결손 케이스는 fail-closed로 처리되고 자동 해제되지 않음이 테스트로 증명됨
- 장기 `busy_lock`이 운영 장애/에스컬레이션 이벤트로 surfaced 됨이 테스트로 증명됨
- 브라우저 오류 복구 후에만 control/workload가 계속 진행되고, `login_required|busy_lock|unknown_lock`에서는 continue하지 않음이 테스트로 증명됨

**중단 조건:**
- 여기서 실패하면 detached/prod smoke 금지

## Stage 4: Detached Smoke 테스트

**목적:** 실제 런타임 loop를 건드리되, 본 운영 루트가 아닌 probe 루트에서 detached smoke를 검증합니다.

**실행 순서:**
1. selftest detached
2. control idle detached
3. mock chain detached

**명령 예시:**
```bash
python -m runtime_v2.cli --selftest-detached --probe-root system/runtime_v2_probe/selftest-run-01
python -m runtime_v2.cli --control-once-detached --probe-root system/runtime_v2_probe/control-idle-run-01
python -m runtime_v2.cli --control-once-detached --seed-mock-chain --probe-root system/runtime_v2_probe/mock-chain-run-01
```

**확인 파일:**
- selftest run:
  - `system/runtime_v2_probe/<run>/probe_result.json`
  - `system/runtime_v2_probe/<run>/evidence/result.json`
  - `system/runtime_v2_probe/<run>/health/browser_health.json`
- control idle run:
  - `system/runtime_v2_probe/<run>/probe_result.json`
  - `system/runtime_v2_probe/<run>/evidence/result.json`
  - `system/runtime_v2_probe/<run>/health/gui_status.json`
- mock chain run:
  - `system/runtime_v2_probe/<run>/probe_result.json`
  - `system/runtime_v2_probe/<run>/evidence/result.json`
  - `system/runtime_v2_probe/<run>/evidence/control_plane_events.jsonl`

**통과 기준:**
- selftest: `code=OK`, `exit_code=0`, `probe_result.run_id == result.metadata.run_id == browser_health.run_id`
- control idle: `code=NO_JOB`, `queue_status=idle`, `probe_result.run_id == result.metadata.run_id == gui_status.run_id`
- mock chain: 마지막 `job_summary`에서 `completion_state=completed`, `final_output=true`, `probe_result.run_id == result.metadata.run_id`

**중단 조건:**
- detached에서 `run_id` 조인 실패 시 실서비스 smoke 금지

## Stage 5: 실서비스 수동 Smoke 테스트

**목적:** 실제 브라우저/음성/ffmpeg 자원에서 가장 작은 단건 흐름을 수동으로 점검합니다.

**입력 범위:**
- Excel 1개 행 성공 기준
- 실제 브라우저 세션 health 확보 후 실행
- 공통 asset folder 존재 확인 후 실행

**해석 고정:**
- `엑셀 1행`은 `row-index=1`을 뜻하지 않습니다.
- canonical 의미는 `실제 Excel 테스트 행 1개를 seed -> stage1 -> stage2 -> final까지 성공시키는 것`입니다.
- 따라서 실행 row-index는 준비된 테스트 행 위치에 맞춰 선택하며, 문서상 acceptance는 `1개 행 성공`으로 판정합니다.

**실행 순서:**
1. 브라우저 health 확인 (`chatgpt/genspark/seaart/geminigen/canva`)
2. GPT floor 확인
3. 준비된 테스트 행 1개 seed
4. browser supervisor가 `continue 가능한 상태`를 확인한 경우에만 control loop 1회씩 단계적으로 실행
5. final output 생성과 latest-run evidence 확인

**명령 예시:**
```bash
python -m runtime_v2.cli --excel-once --excel-path "D:\YOUTUBEAUTO\4 머니.xlsx" --sheet-name "Sheet1" --row-index 0
python -m runtime_v2.cli --control-once
python -m runtime_v2.cli --control-once
python -m runtime_v2.cli --control-once
```

`--row-index 0`는 예시일 뿐이며, acceptance는 `index 값`이 아니라 `성공한 테스트 행 수 = 1`입니다.

**수집 증거:**
- `system/runtime_v2/health/gui_status.json`
- `system/runtime_v2/evidence/result.json`
- `system/runtime_v2/evidence/control_plane_events.jsonl`
- `system/runtime_v2/evidence/failure_summary.json` (실패 시)
- `system/runtime_v2/logs/<run_id>.jsonl`
- `system/runtime_v2/health/gpt_status.json`
- `system/runtime_v2/health/gpu_scheduler_health.json`

**통과 기준:**
- 동일 `run_id`가 seed -> stage1 -> stage2 -> final evidence까지 이어짐
- final output 또는 failure summary가 한 번에 판정 가능함
- Excel 상태가 manager-only로 `OK/Voice OK/Done/partial` 중 하나로 일관 갱신됨
- browser workload는 GPU lease를 잡지 않음
- GPT floor는 `OK >= 1`을 유지함
- GPU duplicate run은 0건이어야 함
- browser supervisor가 `running` 판정 시에만 다음 작업이 진행되고, `login_required|busy_lock|unknown_lock`이면 중단/보류 evidence가 남아야 함

**중단 조건:**
- `gpt_status.json`에서 `OK < 1`
- `gpu_scheduler_health.json`에서 duplicate run 정황 발생
- `result.json`과 `gui_status.json`의 latest-run 의미 불일치
- `failure_summary.json`이 필요했는데 생성되지 않음

## Stage 4B: 비GPT 프로그램 단건 기능/Flow 연결 테스트

**목적:** `e2e mock test` 직후, GPT 의존 구간으로 넘어가기 전에 비GPT 프로그램들이 실제로 기능적으로 동작하고 control-plane flow에 정상 연결되는지 1개씩 검증합니다.

**검증 범위:**
- GPT floor 성공 여부를 요구하지 않는 비GPT 프로그램만 대상
- 한 번에 하나의 프로그램만 추가
- 목표는 `최종 산출물 완성`이 아니라 `기능 호출 성공 + flow 연결 증거 확보`

**실행 순서:**
1. Stage 4 mock chain evidence가 정상인지 먼저 확인합니다.
2. 비GPT 프로그램 후보를 1개만 선택합니다.
3. 해당 프로그램만 실제 실행 경로에 연결한 뒤 seed/control을 최소 횟수로 실행합니다.
4. 프로그램 기능 호출 흔적과 control-plane 연결 흔적을 확인합니다.
5. 성공하면 다음 비GPT 프로그램을 같은 방식으로 하나씩 추가합니다.

**대상 예시:**
- `rvc`
- `kenburns`
- `render`
- 그 외 GPT floor를 직접 요구하지 않는 local/gpu workload

**수집 증거:**
- canonical runtime-state root의 `evidence/result.json`
- canonical runtime-state root의 `health/gui_status.json`
- canonical runtime-state root의 `evidence/control_plane_events.jsonl`
- canonical runtime-state root의 `logs/<run_id>.jsonl`
- 프로그램별 산출물/중간 산출물 경로

**프로그램별 통과 기준:**
- 선택한 비GPT 프로그램이 실제로 호출되었다는 증거가 남음
- `run_id`가 seed -> worker dispatch -> result/gui/control-plane evidence에서 이어짐
- 해당 프로그램이 expected stage로 진입하고, `job_summary` 또는 동등 종료 이벤트가 남음
- flow가 다음 단계로 전달되거나, fail-closed 구조화 실패로 닫힘
- GPT floor가 없어도 되는 프로그램인데 GPT 의존 때문에 막히지 않음

**프로그램별 중단 조건:**
- 프로그램 호출 증거가 전혀 없음
- `run_id` 조인이 끊김
- `result.json`, `gui_status.json`, `control_plane_events.jsonl`의 의미가 다름
- worker stage는 바뀌었는데 프로그램 기능 결과물/중간 산출물이 전혀 없음
- 구조화 실패가 필요한데 `failure_summary.json` 또는 동등 실패 흔적이 없음

**Stage 4B 완료 기준:**
- 비GPT 프로그램을 한 번에 하나씩 추가해도 기능 호출과 flow 연결이 해석 가능함
- 각 프로그램별로 `연결됨/실패함`을 증거 기반으로 판정할 수 있음
- 여기서 확인한 비GPT 프로그램 연결이 안정적일 때만 Stage 5 `e2e 1행 테스트`로 넘어감

## Stage 5B: e2e 5-Row Batch Smoke

**목적:** Stage 5 단건 성공 이후, 준비된 테스트 행 5개를 같은 계약으로 순차 검증합니다.

**사전 조건:**
- Stage 5 `1개 행 성공` evidence 확보
- `docs/plans/2026-03-08-browser-session-stability-plan.md`의 `No-Go` 해제
- `manual` tier 실행 경로 사용

**실행 순서:**
1. 준비된 테스트 행 5개를 순차로 선택합니다.
2. 각 행마다 `--excel-once`로 seed합니다.
3. 각 행마다 `--control-once`를 final output 또는 구조화 실패(`failure_summary.json`)까지 반복 실행합니다.
4. 각 행마다 latest-run evidence와 per-run log를 묶어 기록합니다.

**명령 예시:**
```bash
python -m runtime_v2.cli --excel-once --excel-path "D:\YOUTUBEAUTO\4 머니.xlsx" --sheet-name "Sheet1" --row-index <prepared-row>
python -m runtime_v2.cli --control-once
python -m runtime_v2.cli --control-once
python -m runtime_v2.cli --control-once
```

**행별 통과 기준:**
- 같은 행의 `run_id`가 seed -> stage1 -> stage2 -> final evidence까지 정렬됨
- `error_code` 의미가 `result.json`, `gui_status.json`, `control_plane_events.jsonl`에서 일치함
- blocked/retry/failure의 `attempt/backoff` 계약이 drift 없이 해석 가능함
- final output 또는 구조화 실패(`failure_summary.json`) 중 하나로 한 번에 판정 가능함
- browser workload는 GPU lease를 잡지 않음

**행별 중단 조건:**
- `gpt_status.json`에서 `OK < 1`
- `gpu_scheduler_health.json`에서 duplicate run 정황 발생
- `result.json`과 `gui_status.json`의 latest-run 의미 불일치
- `failure_summary.json`이 필요했는데 생성되지 않음
- `run_id` 정렬, `error_code` 의미, `attempt/backoff` 3축 중 하나라도 해석 불가

**배치 통과 기준:**
- 5개 행이 모두 위 행별 통과 기준을 만족함
- 5개 행 모두 manager-only Excel 상태 갱신과 latest evidence 해석이 가능함

## Stage 6: 24h Soak 준비 검증

**목적:** 장시간 soak를 돌릴 자격이 있는지, smoke 증거와 운영 게이트만으로 판정합니다.

**위치 고정:**
- 24시간 검증은 개발의 최종 단계입니다.
- Stage 5 단건 smoke(엑셀 1개 행 성공)가 끝나기 전에는 24h soak로 넘어가지 않습니다.

**사전 조건:**
- Stage 0~4 전부 통과
- detached readiness SOP 만족

**확인 항목:**
- browser health latest snapshot 정상
- stale browser profile lock 자동 복구 가능
- `unknown` lock 상태 fail-closed 보장
- 장기 `busy_lock` 에스컬레이션 동작
- GPU duplicate run 0건
- GPT floor breach 지속 0건
- latest-run snapshot과 failure summary 조인 가능
- stall worker가 `worker_stalls`로 surfaced 됨

**수집 증거:**
- `system/runtime_v2/health/browser_health.json`
- `system/runtime_v2/health/browser_session_registry.json`
- `system/runtime_v2/health/gpu_scheduler_health.json`
- `system/runtime_v2/health/gpt_status.json`
- `system/runtime_v2/health/gui_status.json`
- `system/runtime_v2/evidence/result.json`
- `system/runtime_v2/evidence/control_plane_events.jsonl`

**판정 규칙:**
- `browser_health.json`: latest snapshot이 정상이고 unhealthy session이 0이거나 복구 가능 상태여야 함
- `browser_health.json` 또는 동등 evidence: `busy_lock`과 `stale_lock_recovered`가 구분 기록되고, stale lock은 자동 복구 가능해야 함
- `unknown` 상태는 fail-closed 경고로 남아야 하며 자동 해제 흔적이 없어야 함
- 장기 `busy_lock`은 운영 장애로 승격된 evidence가 있어야 함
- `gpu_scheduler_health.json`: duplicate run 정황이 없어야 함
- `gpt_status.json`: `OK >= 1`이 유지되어야 함
- `result.json`/`gui_status.json`: 같은 latest-run 의미로 해석 가능해야 함
- `control_plane_events.jsonl`: final chain 결과 또는 failure chain 결과를 추적할 수 있어야 함

**통과 기준:**
- detached readiness gate 4개 통과
  - selftest `OK`
  - control idle same-`run_id` snapshot
  - mock chain `final_output=true`
  - browser `profile_dir` 절대경로
- 아래 최신 증거 파일이 같은 run 의미로 해석 가능
  - `system/runtime_v2/health/browser_health.json`
  - `system/runtime_v2/health/browser_session_registry.json`
  - `system/runtime_v2/health/gpu_scheduler_health.json`
  - `system/runtime_v2/health/gpt_status.json`
  - `system/runtime_v2/health/gui_status.json`
  - `system/runtime_v2/evidence/result.json`
  - `system/runtime_v2/evidence/control_plane_events.jsonl`

## Stage 7: 24h Soak 실행 계획

**목적:** 실제 24시간 운영 테스트를 안전하게 수행합니다.

**운영 규칙:**
- 브라우저는 정상 세션 재기동 금지
- health fail 세션만 선택 복구
- GPU duplicate 0건 유지
- 실패 시 즉시 `run_id`, `code`, `debug_log`, `result_path`, `manifest_path`, `final_artifact_path` 기록

**실행 결과 문서:**
- `system/runtime_v2/evidence/soak_24h_report.md`

**실행 명령(예시):**
```bash
python -m runtime_v2.cli --once
```

**연속 실행 방식:**
- 운영 세션 또는 작업 스케줄러에서 `runtime_v2`를 24시간 유지 실행합니다.
- 프로세스 교체/재시작이 발생하면 같은 soak 윈도우로 기록하되, `soak_24h_report.md`에 재시작 시각과 원인을 남깁니다.

**관찰 주기:**
- 시작 직후 1회
- 1시간 간격 24회
- 장애 발생 시 즉시 1회 추가

**통과 기준:**
- 24시간 동안 browser availability 99.5% 이상
- GPU duplicate run 0건
- GPT floor breach 2분 초과 지속 0건
- 장애 발생 시 `run_id`, `code`, `debug_log`, `result_path`, `manifest_path`, `final_artifact_path`가 남음
- 종료 시 `system/runtime_v2/evidence/soak_24h_report.md`에 요약, 실패 건수, 복구 건수, 최종 판정이 기록됨

**근거 파일:**
- `system/runtime_v2/health/browser_health.json`
- `system/runtime_v2/health/gpu_scheduler_health.json`
- `system/runtime_v2/health/gpt_status.json`
- `system/runtime_v2/health/gui_status.json`
- `system/runtime_v2/evidence/result.json`
- `system/runtime_v2/evidence/control_plane_events.jsonl`
- `system/runtime_v2/evidence/soak_24h_report.md`

**중단 조건:**
- duplicate GPU run 감지
- GPT floor breach 장기 지속
- latest-run 증거/실패 요약이 해석 불가
- 브라우저 세션 전면 비정상으로 자동복구 실패

## Stop/Go Gates 요약

1. Stage 0 실패 -> 모든 후속 테스트 중단
2. Stage 1 실패 -> Stage 2 이상 금지
3. Stage 2 실패 -> Stage 3 이상 금지
4. Stage 3 실패 -> Stage 4 이상 금지
5. Stage 4 `run_id` 조인 실패 -> Stage 4B 이상 금지
6. Stage 4B에서 비GPT 프로그램 기능/flow 연결 해석 실패 -> Stage 5 이상 금지
7. Stage 5 final evidence/failure summary 해석 실패 -> Stage 6 이상 금지
8. Stage 6 gate 미충족 -> Stage 7 금지

## 실행 우선순위

1. 로컬 회귀 전체 재실행
2. browser plane/GPU worker 자원 의존 테스트
3. detached selftest/control-idle/mock-chain
4. 비GPT 프로그램 단건 기능/flow 연결 테스트
5. 실서비스 단건 smoke
6. soak readiness 판정
7. 24h soak

## 실패 시 기록 템플릿

- `run_id`:
- `stage`:
- `code`:
- `debug_log`:
- `result_path`:
- `manifest_path`:
- `final_artifact_path`:
- `failure_summary_path`:
- `probe_root`:
- `root_cause_axis`: browser / gpu / gpt / contract / excel / stage2 / render

## 오류 추적 순서

1. `result.json`, `gui_status.json`, `control_plane_events.jsonl`의 latest-run `run_id`를 먼저 맞춥니다.
2. 같은 `run_id`의 `system/runtime_v2/logs/<run_id>.jsonl`를 읽어 entry layer 이벤트를 확인합니다.
3. 브라우저 축이면 `browser_health.json`, GPT 축이면 `gpt_status.json`, GPU 축이면 `gpu_scheduler_health.json`으로 내려갑니다.
4. `code`, `worker_error_code`, `completion_state`, `backoff_sec`가 서로 다른 의미로 drift하면 테스트 실패보다 계약 수정이 우선입니다.

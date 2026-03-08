# Runtime V2 1-Row Readiness Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** `runtime_v2`를 실제 1행 smoke를 시작해도 되는 상태까지 정리합니다. 범위는 브라우저 세션 안정화뿐 아니라 GPT floor, latest-run evidence 일관성, blocked/backoff 계약, 외부 참고 기능 이행 확인, 패치 누적형 복잡화 방지 기준까지 포함하며, 24시간 검증은 개발 최종 단계에서만 별도로 진행합니다.

**Architecture:** 이 문서를 `runtime_v2` 1행 smoke 진입 전 remediation의 단일 canonical plan으로 사용합니다. 브라우저 관련 변경은 `runtime_v2/browser/`를 단일 제어면으로 두고, manager는 브라우저 프로세스/프로필/포트만 관리하며 supervisor는 health/recovery만 담당합니다. 여기에 GPT floor, evidence join, blocked/backoff, 외부 참고 carryover 점검을 같은 stop/go 체계 안에 묶어 1행 smoke 전 readiness gate로 운영합니다.

**Tech Stack:** Python `unittest`, `runtime_v2` browser manager/supervisor, external reference implementations for browser handling, Chrome/Edge/UC Browser, CDP `/json`, filelock-style profile locking, detached probe, Stage 5 smoke evidence.

---

## Canonical Plan Rule

- 이 문서는 `runtime_v2`의 `1행 smoke 시작 전까지 필요한 전체 조치계획`의 단일 기준 문서입니다.
- `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`는 이 문서의 테스트 실행/판정 절차를 담당하는 보조 문서입니다.
- `docs/plans/2026-03-07-runtime-v2-blocker-fix-plan.md`는 이 문서의 구현 blocker를 세분화한 보조 문서입니다.
- 새로운 상위 계획 문서를 추가로 만들지 않습니다. 새로운 문제/조치/게이트는 먼저 이 문서에 병합하고, 그 다음 필요한 경우에만 보조 문서를 동기화합니다.
- 계획 간 충돌이 보이면 보조 문서를 맞추는 것이 아니라, 먼저 이 문서를 수정한 뒤 다른 문서를 따라가게 합니다.

## Current Program Problems (Unified)

1. `GPT floor`가 현재 깨져 있어, 브라우저가 일부 준비돼 있어도 실제 1행 smoke를 시작할 수 없습니다.
2. `result.json`, `gui_status.json`, `control_plane_events.jsonl`의 latest-run 의미가 완전히 단일화되지 않아, 실패 원인 축을 한 번에 판정하기 어렵습니다.
3. 브라우저 profile lock이 stale recovery에는 진전이 있었지만, canonical profile 단일 writer 보장이 아직 완전히 닫히지 않았습니다.
4. blocked job의 `queued`/`backoff`/`failed` 계약이 원인 축별로 완전히 정리되지 않아 장시간 재시도 누적 위험이 남아 있습니다.
5. 외부 참고 하부 기능 호출은 연결됐지만, 외부 참고의 `실제 안전장치 묶음`까지 전부 이행된 것은 아닙니다.
6. 계획 문서와 테스트 파일/운영 evidence 사이에 일부 drift가 있어, 준비 완료로 오판할 위험이 있습니다.

## 1-Row Smoke Go/No-Go Rule

- 현재 판정은 `No-Go`입니다.
- 아래 4축이 모두 닫히기 전에는 실제 1행 smoke를 시작하지 않습니다.
  1. `GPT floor` 정상화 (`OK >= 1`)
  2. latest-run evidence 해석 일관성
  3. browser canonical profile ownership / recovery contract 고정
  4. blocked/backoff semantics 고정

## Reference Carryover Decision Rule

- 외부 참고 기능은 `이름만 대응`이면 이행으로 보지 않습니다.
- 아래 3가지를 모두 만족해야 `적용됨`으로 판정합니다.
  1. runtime_v2에서 실제 호출 경로가 존재함
  2. 외부 참고의 핵심 안전장치(login check / session reuse / fail-closed)가 같이 존재함
  3. 최신 evidence나 테스트에서 그 계약을 읽을 수 있음

## Patchwork Risk Rule

- 다음 중 하나라도 성립하면 `계획 계속`이 아니라 `아키텍처 재검토`로 승격합니다.
  1. 동일 failure axis를 처리하는 분기가 manager/supervisor/control_plane에 중복으로 늘어남
  2. latest-run evidence가 같은 실패를 서로 다른 의미로 기록함
  3. blocked semantics가 축(browser/gpu/worker)마다 다르게 drift함
  4. 외부 참고 carryover가 실제 호출만 있고 안전장치가 빠진 상태로 누적됨
  5. 1행 smoke 전제 조건이 문서마다 다르게 적힘

## Immediate Stabilization Rule

- 채팅/CLI 세션 불안정의 현재 최우선 원인 축은 `run_once()`/`run_control_loop_once()`가 순수 검증 경로에서도 브라우저 start, detached spawn, bootstrap, GPT tick 같은 운영 side effect를 바로 밟는 구조입니다.
- 따라서 다음 구현 순서는 canonical remediation 전체를 대체하지 않고, 그 앞에 붙는 `safe test path stabilization`로 고정합니다.
  1. `run_once()`에 테스트 전용 side-effect-free 경로를 추가해 Stage 0/로컬 계약 테스트에서 browser start를 밟지 않게 함
  2. `run_control_loop_once()`에 pure control contract 경로를 추가해 bootstrap/GPT autospawn을 Stage 0에서 분리함
  3. 위 두 경로를 `safe` test tier로 고정한 뒤에만 browser ownership / blocked semantics remediation을 계속함
- 이 규칙은 운영 경로의 의미를 바꾸기 위한 것이 아니라, `safe` 테스트가 외부 bootstrap 없이 반복 가능하도록 만드는 최소 안정화 조치입니다.
- 여기서 `allow_runtime_side_effects=False`는 완전한 무기록 dry-run이 아니라, browser start/bootstrap/autospawn 같은 외부 side effect를 건너뛰는 test path입니다. canonical latest 경로를 쓰지 않으려면 반드시 격리된 `RuntimeConfig` 또는 probe root를 함께 사용합니다.

## Test Tier Execution Contract

- 현재부터 `runtime_v2` 테스트는 `무엇을 검증하느냐`보다 `외부 side effect를 밟느냐` 기준으로 `safe`, `isolated`, `manual` 3계층으로 운영합니다.
- 채팅/UI interruption이 발생하면 즉시 `interrupt-safe` 실행 모드로 전환합니다.
  - 병렬 도구 호출 금지
  - pytest는 `::test_name` 단위 단건 실행만 허용
  - 한 번에 도구 1개만 사용하고, 긴 출력/파일 단위 대묶음 실행은 피합니다
- `safe`
  - 허용 조건: `allow_runtime_side_effects=False`, 순수 helper/contract/evidence 조합, temp root 사용, 실제 browser launch/detached spawn/bootstrap/autospawn 없음
  - `cli.main()` 재진입, `_launch_debug_browser()` 호출, detached contract 검증은 patch 유무와 관계없이 포함하지 않습니다.
  - 채팅 세션에서 반복 실행 가능한 기본 검증 경로입니다.
- `isolated`
  - 허용 조건: `main()` 재진입, `probe_root` 기반 evidence 생성, local `HTTPServer`/thread 사용, browser launch contract 검증, temp/isolated root 쓰기
  - 채팅 세션에서는 개별 테스트만 순차 실행합니다. 대묶음 실행은 금지합니다.
  - 단, 현재 wrapper 증거상 파일 단위 `python -m pytest tests/test_runtime_v2_browser_plane.py -q` 같은 단일 명령도 중단될 수 있으므로, 채팅에서는 파일 전체가 아니라 테스트 케이스 단위로 더 잘게 나눠 실행합니다.
- `manual`
  - 판정 조건: 기본 `system/runtime_v2/` 경로 사용, 실제 `ensure_runtime_bootstrap()`/`run_selftest()`/`run_control_loop_once()` 운영 경로 진입, real browser launch, detached child contract 자체, live Stage 5 evidence 의존
  - 채팅 세션에서는 실행 금지입니다. 별도 통제 환경 또는 detached/probe root로만 다룹니다.

## Current Test Tier Map

- `tests/test_runtime_v2_phase2.py`
  - `safe`
    - `test_exit_code_mapping_includes_callback_fail`
    - `test_n8n_payload_preserves_required_schema`
    - `test_gui_status_write_is_atomic_json`
    - `test_stale_lease_is_recovered_from_persisted_file`
    - `test_run_once_uses_existing_gpt_status_source_instead_of_fake_ok_endpoint`
    - `test_run_once_side_effect_free_mode_skips_browser_bootstrap`
    - `test_run_once_side_effect_free_mode_fail_closes_when_gpt_status_is_missing`
    - `test_latest_join_flags_out_of_sync_when_gui_and_result_run_ids_diverge`
  - `isolated`
    - `test_post_callback_retries_until_success` (`HTTPServer` + `threading.Thread`)
    - `test_selftest_probe_child_keeps_run_id_aligned_across_outputs` (`main()` 재진입 + `probe_root`)
    - `test_control_once_probe_child_seed_mock_chain_runs_to_final_output` (`main()` 재진입 + `probe_root` + control loop evidence)
  - `manual`
    - `test_main_returns_callback_fail_when_post_fails` (`main()` + default runtime bootstrap + non-probe canonical path)
    - `test_run_once_and_selftest_use_persistent_paths` (`run_selftest()`가 실제 side-effect 경로를 밟음)
    - `test_control_once_detached_propagates_seed_mock_chain_flag` (`DETACHED_PROCESS` 계약 축 자체가 채팅 세션 최상위 리스크)
- `tests/test_runtime_v2_browser_plane.py`
  - `safe`
    - inventory/start-url/profile-policy helper 검증 전부
    - `acquire_profile_lock` stale/busy/unknown 계약 테스트 전부
    - `_refresh_session_ready_marker` login/ready marker 테스트 전부
  - `isolated`
    - `_launch_debug_browser` 계열 전부 (`subprocess.Popen`이 patch되어도 launch contract 자체를 검증함)
    - `BrowserSupervisor.tick()` / `run_once()` 계약 테스트 중 browser 상태/launch path patch에 의존하는 케이스
    - `test_supervisor_recovers_only_unhealthy_session` (repo 하위 `runtime_v2/sessions/*`에 ready marker 기록)
    - `test_stage5_latest_run_has_interpretable_failure_or_success_evidence` (live latest evidence 해석 의존)
  - `manual`
    - 현재 파일에는 없음. 단, patch를 제거해 real browser/process를 만지는 순간 즉시 `manual`로 승격합니다.

## Entry Path Tier Map

- `safe`
  - `run_once(... allow_runtime_side_effects=False)`
  - 향후 `run_control_loop_once(... allow_runtime_side_effects=False)`가 들어오면 같은 tier에 포함
- `isolated`
  - `main()` with `--selftest-probe-child` or `--control-once-probe-child` and explicit `--probe-root`
  - `_launch_debug_browser()` / browser supervisor contract tests with patched launch/port/tab hooks
- `manual`
  - `main()` with `--once`, `--selftest`, `--control-once`, `--excel-once` on default paths
  - `main()` with `--control-once-detached` / `--selftest-detached`
  - `_spawn_detached_probe()` contract tests even when `subprocess.Popen` is patched
  - `_launch_debug_browser()` without patched `subprocess.Popen`
- 파일별 분류표에 아직 적지 않은 테스트라도, `main()`, `run_once()`, `run_control_loop_once()`를 browser workload와 함께 호출하면서 `allow_runtime_side_effects=False`, `probe_root`, patch 격리를 명시하지 않으면 기본값은 `manual`로 간주합니다.

## Execution Order (Current Rule)

- 1. 채팅 세션에서는 `safe`만 기본 검증으로 실행합니다.
- 2. `isolated`는 한 번에 하나씩만 실행하고, 각 테스트는 temp root 또는 `probe_root`를 사용해야 합니다.
- 2-1. 채팅 세션에서는 `isolated`라도 파일 단위 전체 실행은 피하고, `::test_name` 수준의 단일 케이스만 실행합니다.
- 3. `manual`은 채팅 세션에서 실행하지 않습니다. 실제 검증이 필요하면 별도 셸/세션에서 detached 또는 운영자 통제 하에 수행합니다.
- 4. `safe` 통과 전에는 `isolated`와 `manual`로 내려가지 않습니다.
- 5. `isolated` 실패 시 원인 추적은 `probe_result.json`, `browser_health.json`, `result.json`, `control_plane_events.jsonl` 순으로 고정합니다.

## Test Failure Trace Method

- `safe`에서 오류가 나면
  - 호출 진입점을 먼저 확인합니다. `run_once(... allow_runtime_side_effects=False)` 또는 pure helper만 탔는지 봅니다.
  - 그다음 temp root 기준으로 `gpt_status.json`, `gui_status.json`, latest pointer를 같은 `run_id`로 묶어 확인합니다.
  - 여기서 browser/bootstrap/autospawn 흔적이 보이면 test tier 오분류로 간주하고 `isolated` 또는 `manual`로 즉시 승격합니다.
- `isolated`에서 오류가 나면
  - `probe_result.json` -> `browser_health.json` -> `result.json` -> `control_plane_events.jsonl` -> debug log 순서로 고정 추적합니다.
  - `run_id`, `code`, `status`, `completion_state`, `action`, `action_result`를 한 묶음으로 읽고, 어느 레이어에서 의미가 갈라졌는지 찾습니다.
  - local `HTTPServer`, patched launch, `probe_root` 증거가 없으면 격리 조건 위반으로 보고 실행 방식을 먼저 수정합니다.
- `manual`에서 오류가 나면
  - 채팅 세션 안에서 재시도하지 않습니다.
  - `system/runtime_v2/health/*`, `system/runtime_v2/evidence/*`, `system/runtime_v2/logs/<run_id>.jsonl`를 같은 실행 단위로 묶어 확인합니다.
  - detached child, live browser, canonical profile lock이 얽힌 경우에는 `busy|stale|unknown` 판정과 `BROWSER_BLOCKED|BROWSER_UNHEALTHY|GPT_FLOOR_FAIL` 의미 일치부터 먼저 검토합니다.
- 공통 규칙
  - 오류 추적의 목표는 fallback 추가가 아니라 single owner 레이어를 찾는 것입니다.
  - 같은 문제를 `manager/supervisor/control_plane`에서 동시에 보정하지 않습니다.
  - `run_id`, `error_code`, `attempt/backoff` 중 하나라도 어긋나면 기능 수정 전에 contract drift부터 정리합니다.

## Error Trace Method

- 오류가 나면 증상만 보지 말고 아래 4층으로 추적합니다.
  1. entry layer: `runtime_v2/cli.py`, `runtime_v2/control_plane.py`, `runtime_v2/supervisor.py`
  2. health layer: `browser_health.json`, `gpt_status.json`, `gpu_scheduler_health.json`
  3. latest-run layer: `result.json`, `gui_status.json`, `control_plane_events.jsonl`
  4. per-run layer: `system/runtime_v2/logs/<run_id>.jsonl`, 필요 시 `failure_summary.json`
- 추적 기본 순서:
  - 같은 `run_id`가 4층에서 일치하는지 먼저 확인
  - `code`, `worker_error_code`, `completion_state`, `backoff_sec`를 같은 failure axis로 묶어 확인
  - 브라우저 축이면 `status`, `lock_state`, `action`, `action_result`를 같이 읽음
- 오류 추적의 목적은 새 fallback을 추가하는 것이 아니라, single owner 레이어를 찾고 그 한 곳만 고치는 것입니다.

## Unified Remediation Order

1. `GPT floor` 복구 기준과 latest health 신뢰성 고정
2. latest-run evidence join 규칙 고정
3. browser canonical ownership / stale-busy-unknown recovery 규칙 고정
4. blocked/backoff semantics 재정의
5. reference carryover 적용/미적용 표 확정
6. 이 5개가 닫힌 뒤에만 1행 smoke 준비 완료 판정을 수행

## Scope Lock

- 포함:
  - 브라우저를 사용하는 프로그램 목록 정리
  - 수동 로그인 가능한 브라우저 오픈 경로 설계
  - 로그인 후 세션 저장/ready marker/health 기준 설계
  - GeminiGen의 UC Browser 전환 계획
  - 24시간 상시가동 + 프로필 충돌 방지 구조 설계
  - 현재 profile 저장 위치 점검과 정리 계획
  - Stage 5 실서비스 smoke 재검증 계획 (엑셀 1개 행 성공 기준)
- 제외:
  - 영상 생성 품질 개선
  - Stage2/Final 비브라우저 워커 리팩터링
  - soak 자동 실행기 자체 구현

## Current Evidence Snapshot

- 현재 `runtime_v2/browser/manager.py`는 browser start URL, runtime-owned port/profile alignment, external profile override, live tab 기반 `session_ready.json` 생성까지 반영되어 있습니다.
- 최종 검증 run:
  - `system/runtime_v2/health/browser_health.json` → `run_id=browser-verify-final-1772978011`
  - `healthy_count=5`, `unhealthy_count=0`, `availability_percent=100.0`
- 최종 healthy 세션:
  - `chatgpt` → `D:/YOUTUBEAUTO/runtime_v2/sessions/chatgpt-primary` on `9222`
  - `genspark` → `C:/edge_debug` on `9333`
  - `seaart` → `C:/chrome_seaart` on `9444`
  - `geminigen` → `D:/YOUTUBE_AUTO/system/geminigen_chrome_userdata` on `9555`
  - `canva` → `C:/chrome_canva` on `9666`
- 운영 확인 사항:
  - 다섯 debug port(`9222/9333/9444/9555/9666`)가 모두 open 상태였습니다.
  - non-GPT 브라우저 로그인 세션 단절 이슈는 외부 profile override 복구 후 재기동/재관측으로 해소되었습니다.
- 최신 Stage 5 latest-run evidence:
  - `system/runtime_v2/evidence/result.json` → `code=GPT_FLOOR_FAIL`
  - 즉 현재 latest blocker는 브라우저만이 아니라 GPT floor도 포함합니다.

## Browser Program Inventory (Current + Reference)

- 현재 `runtime_v2`
  - `runtime_v2/browser/manager.py` — ChatGPT/GenSpark/SeaArt/GeminiGen/Canva 브라우저 프로세스, profile, port, ready marker 관리
  - `runtime_v2/browser/supervisor.py` — browser health snapshot/recovery
  - `runtime_v2/supervisor.py` — workload gate에서 browser health 사용
- 외부 참고 저장소
  - `master_manager.py` — ChatGPT/Edge/SeaArt/Canva 브라우저 디버그 세션 기동
  - `sub_runners.py` — `run_genspark_automation`, `run_seaart_automation`, `run_canva_automation`에서 로그인 사전 체크 + 브라우저 재사용
  - `scripts/geminigen_automation.py` — UC(undetected-chromedriver) 기반, `system/geminigen_chrome_userdata` 세션 유지/복구/백업
  - `scripts/chrome_session_backup.py` — 세션 백업/복원/filelock 기반 충돌 방지

## Structural Risks To Address

1. `runtime_v2`와 외부 참고 구현이 브라우저/프로필 관리 책임을 나눠 가져 충돌하기 쉬움
2. 같은 profile을 여러 프로세스가 동시에 열 수 있는 구조가 남아 있음
3. GeminiGen은 외부 참고 구현에서 UC Browser를 전제로 하는데 현재 `runtime_v2`는 이를 자체 경로로 고정해야 함
4. 현재 profile 저장 위치가 `runtime_v2/sessions/*`와 외부 설정 경로로 분산될 수 있음
5. Stage 5는 browser health뿐 아니라 GPT floor도 통과해야 하므로 브라우저 계획과 smoke 검증 계획을 분리해서 써야 함
6. `browser_session_registry.json`이 사실상 단일 세션 기준선 역할을 하므로 누락/드리프트를 먼저 막지 않으면 24시간 운영에서 세션 소유권이 흔들릴 수 있음
7. Chrome 136+ 계열은 default data directory에 대한 remote debugging 정책이 강화되어, custom `--user-data-dir`를 강제하지 않으면 디버그 연결이 무시될 수 있음
8. 수동 종료/비정상 종료 뒤 `.runtime_v2.profile.lock`이 남으면 다음 프로세스가 새 PID로 진입하지 못해, supervisor가 재기동을 시도해도 계속 launch 실패 루프에 빠질 수 있음

## Stability Design Direction

- 권장안(계획 기본안)
  - 브라우저별 canonical profile을 1개만 둡니다.
  - manager만 canonical profile을 직접 엽니다.
- worker/direct adapter는 canonical profile을 직접 열지 않고 manager가 띄운 디버그 포트만 사용합니다.
  - `session_ready.json`는 live CDP 기반으로만 갱신합니다.
  - profile 복사본이 필요할 때만 `chrome_session_backup.py`와 같은 잠금 기반 snapshot/copy 경로를 사용합니다.
  - default 브라우저 데이터 디렉터리가 아니라 서비스별 전용 `--user-data-dir`만 사용합니다.
  - registry에 기록된 세션만 supervisor가 복구 대상으로 인정하고, 수동 로그인 필요 상태는 재기동 루프로 숨기지 않습니다.
- 대안 1: 모든 브라우저를 프로젝트 하위 `runtime_v2/sessions/`로 통합
  - 장점: 운영 경로 단순화
- 단점: 외부 참고 경로와 충돌 가능, GeminiGen UC 세션 이행 작업 필요
- 대안 2: 외부 canonical profile 경로를 유지하고 `runtime_v2`는 포트/health/controller만 담당
  - 장점: 가장 짧은 안정화 경로
  - 단점: 경로가 분산되고 관리 문서화가 더 중요
- 추천: 대안 2부터 적용 후, 24h 안정화가 확인되면 대안 1로 통합 여부를 재평가합니다.

## Core Feature Decision

- `supervisor가 브라우저 상태를 확인하고, 오류면 복구한 뒤, 가능한 경우 다음 작업을 계속 진행하는 로직`은 이 프로그램의 핵심 기능으로 취급합니다.
- 이유:
- 외부 참고 구현도 CDP 기반 로그인/세션 확인 후 실패를 감지하고 중단 또는 재사용 결정을 했습니다. (참고 구현의 `_check_login_via_cdp`)
  - 현행 `runtime_v2`도 이미 browser manager/supervisor/control gate 구조를 따로 둔 만큼, 브라우저 확인/복구는 부가 기능이 아니라 control plane의 핵심 책임입니다.
  - 수동 종료, 로그인 만료, stale lock, 포트 down 같은 브라우저 축 오류를 복구하지 못하면 Stage 5 단건 smoke도, 24h 운영도 신뢰할 수 없습니다.

## Minimum Required Capabilities For Browser Recovery

- supervisor/browser plane은 최소 아래 능력을 가져야 합니다.

1. **상태 확인**
   - 포트 open 여부
   - CDP `/json` target 확인
   - login page / consent / captcha / intro page 배제
   - profile lock 상태(`free|busy|stale|unknown`) 판정

2. **원인 분류**
   - `running`: 정상 작업 지속 가능
   - `login_required`: 재기동보다 수동 로그인 필요
   - `busy_lock`: 다른 owner가 살아 있으므로 중복 실행 금지
   - `stale_lock`: lock 회수 후 재기동 대상
   - `unknown_lock`: fail-closed, 자동 해제 금지
   - `unhealthy`: 포트/탭/기동 실패로 복구 대상

3. **복구 동작**
   - `stale_lock` 자동 회수
   - `unhealthy` 브라우저 선택 재기동
   - `busy_lock` 재기동 억제 + 에스컬레이션
   - `login_required` 재기동 억제 + 수동 개입 요구

4. **재진행 조건**
   - 복구 후 `running`이 되면 다음 작업을 계속 진행할 수 있어야 합니다.
   - `login_required`, `busy_lock`, `unknown_lock`이면 작업을 계속 진행하지 않고 명시적으로 보류/차단해야 합니다.

5. **운영 증거**
   - 원인 판정과 조치 결과가 `control_plane_events.jsonl` 중심으로 남아야 합니다.

## 24h Supervisor Recovery Requirements

- 필수:
  - 현재 운영이 `control-once`처럼 PID가 바뀌는 구조를 포함하므로, browser profile lock은 `영구 소유권`이 아니라 `launch-attempt lease/TTL` 관점으로 설계해야 합니다.
  - `stale lock` 자동 판별이 있어야 합니다. lock 파일만 보고 막지 말고, `owner pid 살아 있음/죽음`, `debug port 열림/닫힘`, `lock age`를 함께 봐야 합니다.
  - `busy lock`과 `stale lock`을 구분해야 합니다. 살아 있는 다른 owner면 `busy`, owner가 죽었고 포트도 닫혀 있으면 `stale`로 판정합니다.
  - supervisor는 `stale`로 판정된 경우 lock 제거 후 같은 tick 또는 다음 tick에서 재기동할 수 있어야 합니다.
  - supervisor는 `busy`를 `unhealthy`와 다르게 취급해야 합니다. active owner가 있으면 중복 실행을 막고, 불필요한 restart loop를 만들지 않아야 합니다.
  - 복구 시도/성공/실패는 health or event evidence에 남아야 합니다. 24h 운영에서 “왜 안 열렸는지”가 추적 가능해야 합니다.
- 필수 판정표:

| pid_alive | port_open | metadata_valid | lock_age | 판정 | 기본 동작 |
|---|---|---|---|---|---|
| false | false | true | any | `stale` | lock 제거 후 재기동 허용 |
| true | any | true | any | `busy` | 자동 해제 금지, 중복 launch 금지 |
| false | true | true | any | `busy` | 이미 세션이 떠 있으므로 attach 우선 |
| any | any | false | any | `unknown` | fail-closed, 자동 해제 금지, 강한 경고 이벤트 |

- 필수 운영 규칙:
  - `unknown`은 자동 해제 금지입니다. 메타데이터 결손/파손이면 fail-closed로 두고 경고/증거를 남겨야 합니다.
  - `age`는 stale 판정의 보조 안전장치입니다. `pid dead + port closed`면 age를 기다리지 않고 stale로 판정할 수 있어야 합니다.
  - 반대로 `age exceeded`만으로 stale로 해제하면 안 됩니다.
  - `busy`가 장시간 지속되면 무한 대기하지 말고 운영 장애로 승격해야 합니다.
- 강력 권장:
  - lock payload에 `owner_run_id`, `acquired_at`, `pid`, `port`, `profile_dir`를 유지합니다.
  - stale lock 정리에는 `max_lock_age_sec` 같은 상한을 두되, 이 값은 추가 안전장치로만 사용합니다.
  - 동일 서비스가 반복 실패하면 cooldown/backoff를 걸어 restart thrash를 막습니다.
  - supervisor 운영 파라미터(`tick` 주기, `restart_threshold`, `cooldown_sec`)는 `MTTR 120초`를 만족하도록 같이 고정합니다.
- 선택:
  - 운영자용 수동 override CLI (`clear-stale-browser-lock`)는 있으면 좋지만, 24h 무인 운영의 핵심은 아닙니다.

## Lock Recovery Evidence Contract

- primary evidence 위치는 `system/runtime_v2/evidence/control_plane_events.jsonl`로 고정합니다.
- `browser_health.json`에는 latest snapshot 요약만 남기고, 상세 복구 이벤트는 event log를 기준으로 봅니다.
- stale/busy/unknown 관련 최소 필드는 아래를 유지합니다.

```json
{
  "service": "seaart",
  "profile_dir": "C:/chrome_seaart",
  "lock_state": "busy|stale|unknown|free",
  "pid_alive": true,
  "port_open": false,
  "lock_age_sec": 91,
  "metadata_valid": true,
  "action": "none|clear_lock|restart|escalate",
  "action_result": "ok|skipped|failed",
  "error": "",
  "run_id": "...",
  "tick_id": "...",
  "ts": "..."
}
```

## Failure Classes To Cover In Plan And Tests

- `port_down_after_manual_close`
- `login_required_detected`
- `busy_lock_detected`
- `stale_lock_recovered`
- `unknown_lock_fail_closed`
- `browser_launch_failed`
- `cdp_unreachable`
- `ready_false_positive_blocked`

## Test Scope Clarification

- `엑셀 1행 테스트`의 뜻은 `row-index=1`이 아닙니다.
- canonical 의미는 `실제 Excel 입력 1개 행을 끝까지 성공시키는 실서비스 smoke 테스트`입니다.
- 따라서 Stage 5 기본 목표는 `한 개의 준비된 테스트 행을 성공시킨다`이며, 실행 시 row-index는 준비된 테스트 행 위치에 따라 정합니다.
- 24시간 검증은 이 smoke를 통과한 뒤 개발 최종 단계에서만 별도 진행합니다.

---

### Task 1: Browser Inventory and Session Map Freeze

**Files:**
- Modify: `docs/plans/2026-03-08-browser-session-stability-plan.md`
- Modify: `runtime_v2/browser/manager.py`
- Read: separate reference repo `master_manager.py`
- Read: separate reference repo `sub_runners.py`
- Read: separate reference repo `scripts/geminigen_automation.py`
- Read: separate reference repo `scripts/chrome_session_backup.py`

**Step 1: Write the failing test**

```python
def test_browser_inventory_matches_runtime_browser_contracts():
    inventory = build_browser_inventory()
    assert "geminigen" in inventory
    assert inventory["geminigen"]["browser"] == "uc"
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_runtime_v2_browser_inventory -v`
Expected: FAIL with missing inventory helper or missing UC mapping

**Step 3: Write minimal implementation**

```python
def build_browser_inventory() -> dict[str, dict[str, object]]:
    return {
        "chatgpt": {"browser": "chrome", "profile": "runtime_v2/sessions/chatgpt-primary"},
        "genspark": {"browser": "edge", "profile": "C:/edge_debug"},
        "seaart": {"browser": "chrome", "profile": "C:/chrome_seaart"},
"geminigen": {"browser": "uc", "profile": "runtime_v2/sessions/geminigen-primary"},
        "canva": {"browser": "chrome", "profile": "C:/chrome_canva"},
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_runtime_v2_browser_inventory -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_v2_browser_inventory.py runtime_v2/browser/manager.py docs/plans/2026-03-08-browser-session-stability-plan.md
git commit -m "feat: freeze browser inventory and session map"
```

---

### Task 2: Manual Login Launcher and Session Save Flow

**Files:**
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write the failing test**

```python
def test_manual_login_open_marks_session_ready_after_expected_tab_detected():
    result = open_browser_for_login("seaart")
    assert result["service"] == "seaart"
    assert result["profile_dir"]
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: FAIL with missing login-open flow or missing structured result

**Step 3: Write minimal implementation**

```python
def open_browser_for_login(service: str) -> dict[str, object]:
    session = manager.session_for(service)
    _launch_debug_browser(session)
    return {
        "service": service,
        "port": session.port,
        "profile_dir": session.profile_dir,
        "start_url": _start_url_for_service(service),
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/browser/manager.py runtime_v2/cli.py runtime_v2/browser/supervisor.py tests/test_runtime_v2_browser_plane.py
git commit -m "feat: add manual login launcher flow"
```

---

### Task 3: GeminiGen UC Browser Alignment

**Files:**
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/workers` or GeminiGen entry path selected by current architecture
- Read: separate reference repo `scripts/geminigen_automation.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write the failing test**

```python
def test_geminigen_uses_uc_browser_contract():
    session = default_browser_sessions_by_service()["geminigen"]
    assert session.browser_family == "uc"
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: FAIL because geminigen still resolves through Chrome path logic

**Step 3: Write minimal implementation**

```python
def _resolve_browser_executable(service: str) -> Path | None:
    if service == "geminigen":
        return _resolve_uc_executable()
    ...
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/browser/manager.py runtime_v2/config.py tests/test_runtime_v2_browser_plane.py
git commit -m "feat: align geminigen to uc browser contract"
```

---

### Task 4: Profile Collision Prevention Architecture

**Files:**
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Modify: `runtime_v2/cli.py`
- Read: separate reference repo `scripts/chrome_session_backup.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write the failing test**

```python
def test_same_profile_is_not_opened_by_two_browser_processes():
    result = acquire_profile_lock("C:/chrome_seaart")
    assert result["locked"] is True
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: FAIL with missing lock/owner metadata

**Step 3: Write minimal implementation**

```python
def acquire_profile_lock(profile_dir: str) -> dict[str, object]:
    lock_file = Path(profile_dir) / ".runtime_v2.profile.lock"
    ...
```

추가 구현 요구:
- `classify_profile_lock()` 또는 동등 helper를 두어 `free|busy|stale`를 판정합니다.
- `stale`이면 lock metadata와 pid/port 상태를 근거로 안전하게 해제합니다.
- `busy`이면 중복 실행을 막고 supervisor에는 `busy_lock` 성격의 상태로 전달합니다.
- `unknown`이면 자동 해제하지 않고 fail-closed 경고 상태로 전달합니다.
- `acquire_profile_lock()`는 stale 회수 후 1회 재시도 가능해야 하며, 지금처럼 PID 불일치만으로 영구 `locked=False`가 되면 안 됩니다.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/browser/manager.py runtime_v2/browser/supervisor.py runtime_v2/cli.py tests/test_runtime_v2_browser_plane.py
git commit -m "feat: add browser profile collision guards"
```

---

### Task 5: Stable Ready/Health Contract Review

**Files:**
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Modify: `tests/test_runtime_v2_browser_plane.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write the failing test**

```python
def test_login_page_does_not_produce_false_ready():
    healthy = evaluate_browser_health("canva", login_page_url)
    assert healthy is False
```

추가 테스트 항목:

```python
def test_stale_profile_lock_is_recovered_before_restart():
    ...

def test_busy_profile_lock_does_not_trigger_duplicate_launch():
    ...

def test_login_required_blocks_work_continuation():
    ...

def test_unknown_lock_fail_closes_without_auto_clear():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: FAIL if login/consent/captcha pages are treated as ready

**Step 3: Write minimal implementation**

```python
LOGIN_PATTERNS = {
    "canva": ["/login", "accounts.google.com"],
}
```

추가 구현 요구:
- browser health/status는 최소 `running`, `login_required`, `busy_lock`, `stale_lock_recovered`, `unhealthy`를 구분할 수 있어야 합니다.
- supervisor restart 조건은 `unhealthy`와 `stale_lock_recovered`에는 반응하되, `busy_lock`에는 즉시 재기동하지 않도록 분기해야 합니다.
- stale lock recovery 결과는 `browser_health.json` 또는 `control_plane_events.jsonl`에 남겨야 합니다.
- `busy_lock`가 장시간 지속되면 `escalated_busy_lock` 또는 동등 이벤트로 승격돼야 하며, 24h 운영에서 수동 확인 대상으로 surfaced 되어야 합니다.
- `BrowserManager.shutdown()`에만 lock 해제를 의존하지 않도록, one-shot 프로세스 종료 후에도 stale lock이 남지 않는 설계(launch 후 즉시 해제 또는 lease 만료)가 필요합니다.
- browser recovery 결과가 `running`이면 이후 workload gate가 계속 진행되고, `login_required|busy_lock|unknown_lock`이면 continue하지 않는 control-plane 계약이 필요합니다.

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/browser/manager.py runtime_v2/browser/supervisor.py tests/test_runtime_v2_browser_plane.py
git commit -m "fix: harden browser readiness contract"
```

---

### Task 6: Profile Storage Policy and Migration Check

**Files:**
- Modify: `docs/plans/2026-03-08-browser-session-stability-plan.md`
- Modify: `runtime_v2/browser/manager.py`
- Possibly Create: `runtime_v2/browser/profile_map.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write the failing test**

```python
def test_profile_storage_policy_reports_in_project_vs_external_paths():
    policy = build_profile_storage_report()
    assert policy["chatgpt"]["location_type"] == "project_subfolder"
    assert policy["seaart"]["location_type"] == "external"
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: FAIL with missing storage report helper

**Step 3: Write minimal implementation**

```python
def build_profile_storage_report() -> dict[str, dict[str, object]]:
    ...
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_runtime_v2_browser_plane -v`
Expected: PASS

**Step 5: Commit**

```bash
git add runtime_v2/browser/manager.py tests/test_runtime_v2_browser_plane.py docs/plans/2026-03-08-browser-session-stability-plan.md
git commit -m "feat: report browser profile storage policy"
```

---

### Task 7: Stage 5 Real Smoke Re-Verification

**Files:**
- Read: `docs/plans/2026-03-07-runtime-v2-staged-test-plan.md`
- Read/Write Evidence: `system/runtime_v2/health/*.json`, `system/runtime_v2/evidence/*.json`, `system/runtime_v2/logs/*.jsonl`

**Step 1: Write the failing test**

```python
def test_stage5_latest_run_has_interpretable_failure_or_success_evidence():
    metadata = load_latest_result_metadata()
    assert metadata["code"] in {"OK", "GPT_FLOOR_FAIL", "BROWSER_UNHEALTHY"}
```

추가 문서 고정 문구:
- `엑셀 1행`은 `1개의 Excel 행을 성공시키는 smoke`를 의미하고 `row-index=1`을 의미하지 않음
- `24시간 검증`은 Stage 5가 아니라 개발 최종 단계 검증임

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_runtime_v2_phase5_smoke -v`
Expected: FAIL with missing latest-run parser or missing evidence join

**Step 3: Write minimal implementation**

```python
def load_latest_result_metadata() -> dict[str, object]:
    return json.loads(Path("system/runtime_v2/evidence/result.json").read_text())["metadata"]
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_runtime_v2_phase5_smoke -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_v2_phase5_smoke.py system/runtime_v2/evidence/result.json system/runtime_v2/health/gui_status.json
git commit -m "test: capture stage5 latest-run evidence"
```

---

## External Research Guidance To Apply During Implementation

- Chrome/Chromium family persistent profile는 single writer 원칙으로 운영합니다. 같은 `user-data-dir`를 동시에 2개 프로세스가 열지 않습니다.
- Chrome 136+에서는 `--remote-debugging-port`/`--remote-debugging-pipe`가 default data directory에는 적용되지 않으므로, 디버그 포트를 쓰는 세션은 반드시 non-default `--user-data-dir`를 사용합니다. 근거: Chrome for Developers, `Changes to remote debugging switches to improve security` (2025-03-17).
- ChromeDriver 문서 기준 custom profile은 `user-data-dir=/path/to/profile`로 명시적으로 지정하고, 존재하지 않는 경로면 새 profile을 생성합니다. 근거: ChromeDriver `Capabilities and ChromeOptions`.
- Edge는 CDP 사용 시 `msedge.exe --remote-debugging-port=9222`로 띄운 뒤 `/json/list`로 attachable target을 확인할 수 있고, 필요 시 별도 `--user-data-dir=<dir>`로 분리 프로필을 써야 합니다. 근거: Microsoft Learn `Microsoft Edge DevTools Protocol`.
- remote debugging health는 포트 오픈만으로 PASS하지 않고, live tab URL + login-failure URL 배제 + ready marker로 삼중 확인합니다.
- 장시간 운영은 “정상 세션 재기동 금지, unhealthy 세션만 선택 복구” 원칙을 유지합니다.
- session snapshot/restore는 file lock이 있는 경로만 사용합니다.
- UC Browser는 일반 Chrome 설정과 분리해 전용 profile root와 전용 executable 탐색 경로를 둡니다.

## Acceptance Gates For This Plan

1. 사용 브라우저 프로그램 목록이 코드 근거로 정리되어야 함
2. GeminiGen의 UC Browser 요구가 runtime_v2 계획에 명시돼야 함
3. 프로필 저장 위치가 project subfolder인지 외부 경로인지 서비스별로 판정돼야 함
4. 24시간 상시가동에서 profile collision 방지 구조가 설계돼야 함
5. Stage 5 latest-run evidence를 success 또는 structured failure로 해석할 수 있어야 함
6. Stage 5 실서비스 테스트는 `엑셀 1개 행 성공` 기준으로 해석돼야 하며 `row-index=1`로 오해되지 않아야 함
7. 24시간 검증은 개발 최종 단계라는 순서가 문서에 명시돼야 함
8. stale browser profile lock이 남아도 supervisor가 `busy`와 `stale`를 구분해 자동 복구 가능해야 함
9. stale lock 복구 시도와 결과가 health/evidence에 기록돼야 함
10. `unknown` lock 상태는 fail-closed로 처리돼야 하며 자동 해제되지 않아야 함
11. 장기 `busy_lock`은 운영 장애로 승격되고 추적 가능해야 함
12. one-shot runtime 프로세스가 반복돼도 stale lock 자동 복구로 MTTR 120초 목표를 해치지 않아야 함
13. supervisor가 브라우저 오류를 복구한 뒤에만 후속 작업을 계속 진행하는 계약이 핵심 기능으로 문서화돼야 함

## Out of Scope Lock

- 브라우저 외 비브라우저 워커 최적화
- GPT floor 자체 복구 로직 구현
- 24h soak 자동 실행기 전체 구현
- 외부 참고 전면 제거

## Oracle / Vendor Notes

- Oracle 검토 필수 포인트:
  - 세션 단일 소유권 + health/login 판정 일관성 + 24h 운영 증거화 3축으로 구현 순서를 고정할 것
  - `browser_session_registry.json` 드리프트와 profile collision을 계획 1순위 리스크로 다룰 것
  - stale lock recovery가 `control-once`처럼 PID가 바뀌는 운영 방식과 충돌하지 않는지 검토할 것
  - `busy_lock`과 `stale_lock`을 supervisor가 다르게 해석하는지 검토할 것
  - GeminiGen UC Browser 전환이 실제 외부 참고 근거와 맞는지
  - ready marker가 false-positive를 만들지 않는지
  - Stage 5 smoke 해석에서 browser/GPT 축을 분리했는지
- Vendor 확인 게이트:
  - GeminiGen의 UC Browser 요구가 현재도 필수인지
  - UC Browser가 고정 디버그 포트 + 전용 profile root + single-writer 운영을 지원하는지
  - 위 두 항목이 불명확하면 GeminiGen을 당분간 24h 상주 browser SLO 밖에서 별도 취급할지 결정할 것
- kimoring 검증 필수 포인트:
  - `verify-code-quality`
  - `verify-single-change`
  - `verify-debug-convention`
  - `verify-backup-first`

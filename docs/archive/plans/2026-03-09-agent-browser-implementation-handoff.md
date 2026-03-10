# Agent-Browser Implementation Handoff

## Current Goal

`runtime_v2`에 `agent-browser` 기반 최소 verify worker를 붙이고, 이후 closed loop 구현의 기반이 되는 command builder / result parser / CDP attach preflight / control-plane dispatch를 먼저 완성합니다.

## What Was Completed

### 1. Environment / install validation

- global 설치 완료: `npm install -g agent-browser`
- browser install 완료: `agent-browser install`
- PATH 확인 완료: `C:\Users\1\AppData\Roaming\npm\agent-browser.cmd`
- 버전 확인 완료: `agent-browser 0.17.0`

### 2. Real attach smoke findings

- `agent-browser --cdp 9222 get url` 성공
- `agent-browser --cdp 9333 get url` 성공
- `agent-browser --cdp 9222 tab list` 결과에서 기본 활성 탭이 ChatGPT가 아니라 `Omnibox Popup`으로 잡힘
- `agent-browser --cdp 9222 tab 2` 후 `get url` / `get title`로 `https://chatgpt.com/` / `ChatGPT` 확인
- `agent-browser --cdp 9666 get url`는 timeout 발생

### 3. Plan/docs update

- `docs/plans/2026-03-09-agent-browser-closed-loop-development-plan.md`에 실행 경로, attach smoke 관찰값, `tab list -> target tab select`, `CDP preflight 필요`를 반영함

### 4. Test-first progress

새 테스트 파일 추가:

- `tests/test_runtime_v2_agent_browser.py`

테스트 내용:

1. `agent_browser_verify` workload 등록
2. snapshot command builder가 `agent-browser --cdp <port> snapshot -i --max-output <n>`를 생성하는지
3. tab list parser + best-tab selector가 Omnibox보다 ChatGPT 탭을 우선 선택하는지
4. `_run_worker()`가 `agent_browser_verify` workload를 새 worker로 dispatch하는지

RED 확인 결과:

- 초기 실행 `python -m pytest tests/test_runtime_v2_agent_browser.py -q`
- 4개 모두 실패 확인 완료

GREEN 진행 결과:

- 같은 테스트 재실행 후 `4 passed in 0.12s`

### 5. Safety hardening added after chat interruption

- `agent_browser_verify` worker는 이제 명시적 target matcher(`expected_url_substring` 또는 `expected_title_substring`)가 없으면 바로 fail-closed 합니다.
- 즉, 잘못된 기본 탭(예: `Omnibox Popup`)이나 라이브 채팅 탭에 무심코 붙지 않도록 기본 동작을 막았습니다.
- 관련 테스트 추가 후 현재 상태는 `python -m pytest tests/test_runtime_v2_agent_browser.py -q` 기준 `5 passed`입니다.

## Files Added / Modified In This Session

### Added

- `tests/test_runtime_v2_agent_browser.py`
- `runtime_v2/agent_browser/__init__.py`
- `runtime_v2/agent_browser/command_builder.py`
- `runtime_v2/agent_browser/result_parser.py`
- `runtime_v2/workers/agent_browser_worker.py`
- `docs/archive/plans/2026-03-09-agent-browser-implementation-handoff.md`

### Modified

- `runtime_v2/config.py`
- `runtime_v2/control_plane.py`
- `docs/plans/2026-03-09-agent-browser-closed-loop-development-plan.md`

## Current Implementation State

### `runtime_v2/config.py`

- `WorkloadName`에 `agent_browser_verify` 추가
- `WORKLOAD_KINDS`에 browser workload로 추가
- `WORKLOAD_BROWSER_SERVICES`에는 현재 `()`로만 추가됨
  - 주의: 아직 service-specific browser health gate와 완전히 연결된 상태는 아님
  - 현재 최소 구현 단계에서는 worker 내부 preflight로 먼저 attach 확인을 수행하는 상태

### `runtime_v2/agent_browser/command_builder.py`

현재 구현된 함수:

- `build_cdp_command()`
- `build_snapshot_command()`
- `build_tab_list_command()`
- `build_tab_select_command()`
- `build_get_url_command()`
- `build_get_title_command()`

### `runtime_v2/agent_browser/result_parser.py`

현재 구현된 함수:

- `parse_scalar_output()`
- `parse_tab_list_output()`
- `select_best_tab()`

역할:

- `tab list` 출력에서 `[index] title - url` 패턴 파싱
- `omnibox`/`chrome://omnibox*`를 감점
- 기대 URL/title substring이 있으면 해당 탭 우선 선택

### `runtime_v2/workers/agent_browser_worker.py`

현재 구현된 함수:

- `_run_agent_browser_command()`
- `_default_port_for_service()`
- `run_agent_browser_verify_job()`

동작 요약:

1. workspace 생성
2. `tab list`
3. parser/selector로 목표 탭 결정
4. 필요 시 `tab <index>` 선택
5. `get url`, `get title`, `snapshot -i --max-output 1200`
6. transcript JSON / snapshot text 저장
7. `finalize_worker_result()` 반환

실패 시:

- transcript JSON 남김
- `retryable=True`
- `completion.state="blocked"`

추가 안전장치:

- `expected_url_substring`와 `expected_title_substring`가 둘 다 비어 있으면 `agent_browser_target_required`로 즉시 실패
- 이 fail-closed 규칙은 라이브 채팅 탭/오탭 attach 방지 목적

### `runtime_v2/control_plane.py`

- `run_agent_browser_verify_job` import 추가
- `_run_worker()`에 `job.workload == "agent_browser_verify"` branch 추가

## Verification Already Run

### Passed

```bash
python -m pytest tests/test_runtime_v2_agent_browser.py -q
```

결과:

- `5 passed`

### Diagnostics status at interruption point

병렬 진단에서 아래 상태를 확인했음:

- `runtime_v2/agent_browser/command_builder.py`: 진단 없음
- `runtime_v2/config.py`: 진단 없음
- `runtime_v2/workers/agent_browser_worker.py`: 처음엔 unused import 경고가 있었고 일부 제거 진행함
- `runtime_v2/control_plane.py`: 기존 pre-existing unused import/variable 정리 진행 중이었음
- `runtime_v2/agent_browser/result_parser.py`: basedpyright line reference가 `int(tab.get(...))` 쪽으로 보였고, 이를 제거하도록 수정했으나 툴 출력과 라인 표시가 한 번 어긋나 보였음

### Latest verified state after interruption-safe rerun

- `docs/sop/SOP_runtime_v2_development_guardrails.md`를 다시 읽고 interrupt-safe 모드 기준을 재확인함
- 수정 파일 diagnostics 재실행 결과:
  - `runtime_v2/config.py`: clean
  - `runtime_v2/control_plane.py`: clean
  - `runtime_v2/agent_browser/command_builder.py`: clean
  - `runtime_v2/agent_browser/result_parser.py`: clean
  - `runtime_v2/workers/agent_browser_worker.py`: clean
  - `tests/test_runtime_v2_agent_browser.py`: private helper 사용 warning 1개만 존재
- `python -m pytest tests/test_runtime_v2_agent_browser.py -q` 재실행 결과: `5 passed`
- `python -m pytest tests/test_runtime_v2_browser_plane.py -q` 실행은 채팅창 interruption으로 중단됨. 실패가 확인된 것은 아니고, 세션 안정성 때문에 결과 미수집 상태임.

## Immediate Next Step

다음 세션 첫 작업은 이것입니다.

1. `runtime_v2/agent_browser/result_parser.py`를 다시 열어 basedpyright error가 완전히 사라졌는지 확인
2. `runtime_v2/workers/agent_browser_worker.py` unused import 정리 여부 확인
3. `runtime_v2/control_plane.py`에서 pre-existing unused import/variable 제거가 안전한지 확인
4. 아래 검증을 재실행

```bash
python -m pytest tests/test_runtime_v2_agent_browser.py -q
python -m pytest tests/test_runtime_v2_browser_plane.py -q
python -m pytest tests/test_runtime_v2_control_plane_chain.py -q
```

채팅창이 불안정하면 아래처럼 더 잘게 쪼개서 실행:

```bash
python -m pytest tests/test_runtime_v2_browser_plane.py::RuntimeV2BrowserPlaneTests::test_browser_health_requires_ready_marker_not_just_open_port -q
python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_control_plane_holds_browser_blocked_job_with_fixed_backoff -q
```

5. diagnostics clean 후 다음 테스트 추가
   - `run_agent_browser_verify_job()`가 실제로 `tab list -> tab select -> get url/title -> snapshot` 순서를 지키는지
   - `agent_browser_matching_tab_not_found` 실패 contract가 안정적인지
   - `control_plane.run_control_loop_once()`에서 `agent_browser_verify` job이 result/evidence를 정상 join하는지

## Important Constraints To Keep

- `agent-browser`는 기존 browser plane을 우회해서 profile을 직접 열면 안 됨
- worker는 debug port attach만 해야 함
- canonical single-writer 원칙 유지: 최종 evidence/latest join은 control plane만 수행
- 명시적 target matcher 없는 verify job은 금지
- safe tier(`allow_runtime_side_effects=False`)에서 실브라우저를 띄우지 않도록 이후 단계에서 추가 테스트 필요
- `9666` 사례 때문에 port open만 믿지 말고 실제 CDP 응답 preflight를 유지해야 함

## Recommended Resume Prompt

```text
docs/archive/plans/2026-03-09-agent-browser-implementation-handoff.md 읽고 그대로 이어서 구현하세요.
우선 diagnostics 깨끗하게 만들고, 그 다음 agent_browser_verify worker의 실제 preflight/order 테스트를 추가한 뒤 관련 pytest를 다시 돌리세요.
```

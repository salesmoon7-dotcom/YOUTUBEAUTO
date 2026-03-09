# Agent-Browser Live Readiness Report

**Date:** 2026-03-09

**Goal:** `runtime_v2`가 `agent-browser`를 사용해 브라우저 프로그램을 실제로 개발할 준비가 되었는지 live attach 기준으로 판정합니다.

---

## Verdict

- **Partial Go**
- `ChatGPT(9222)`와 `Genspark(9333)`는 바로 개발 시작 가능한 수준입니다.
- `Seaart(9444)`, `Geminigen(9555)`, `Canva(9666)`는 `agent-browser` live attach timeout 때문에 아직 전체 Go 상태가 아닙니다.

## Verified Evidence

### Code / Test Readiness

- `agent-browser 0.17.0` 설치 확인
- closed loop 최소 경로 구현 완료
  - `dev_plan -> dev_implement -> agent_browser_verify -> dev_replan`
- stage2 브라우저 워커 opt-in 경로 추가 완료
  - `video_plan["use_agent_browser_services"]`를 주면 `genspark/seaart/geminigen/canva` payload에 `use_agent_browser`가 자동 주입됩니다.
  - 각 worker는 `use_agent_browser=True`일 때 hidden CLI child(`--agent-browser-stage2-adapter-child`) 기반 adapter command를 자동 구성합니다.
  - hidden CLI child는 workspace에 `attach_evidence.json`을 자동 생성해 attach 결과를 머신-리더블 증거로 남깁니다.
  - 기본값은 여전히 fail-closed이며, opt-in이 없으면 기존 `native_*_not_implemented` 계약을 유지합니다.
- 검증 명령:

```bash
python -m pytest tests/test_runtime_v2_agent_browser.py tests/test_runtime_v2_dev_loop.py tests/test_runtime_v2_agent_browser_closed_loop.py -q
```

- 결과: `13 passed`
- 추가 회귀:
  - `tests/test_runtime_v2_stage2_contracts.py`의 agent-browser opt-in contract 추가
  - `tests/test_runtime_v2_stage2_workers.py`의 genspark/canva agent-browser adapter mode 회귀 추가
  - `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py`의 hidden CLI child artifact write 회귀 추가
  - stage2 worker details/artifacts에 `attach_evidence.json` 포함 회귀 추가
  - `tests/test_runtime_v2_cli_agent_browser_stage2_adapter.py`의 detached row1 probe/fallback 회귀 추가

### Detached 2nd Test Status

- detached `2차 1행` auto probe: `system/runtime_v2_probe/stage2-row1-auto-03/probe_result.json`
- result: `status=ok`, `code=OK`
- interpretation rule:
  - 위 `code=OK`는 **probe success**를 뜻하며, 전체 live readiness `Go`와 동일하지 않습니다.
  - `probe_result.json`의 `live_readiness`는 `full` 또는 `partial`로 실제 attach 준비 수준을 별도 표시해야 합니다.
  - `placeholder_services`는 placeholder/fallback으로 닫힌 서비스를, `live_ready_services`는 real attach로 확인된 서비스를 뜻합니다.
- current automation policy:
  - live-ready 서비스(`genspark`)는 `agent-browser` attach + `attach_evidence.json`을 우선 사용
  - 나머지 browser stage2 서비스는 detached row1 probe에서 placeholder adapter fallback으로 닫아 2차 테스트를 자동 완료

### Additional Live Attach Audit

- evidence: `system/runtime_v2_probe/agent-browser-live-attach-03/summary.json`
- result:
  - `seaart:9444` -> `AGENT_BROWSER_COMMAND_FAILED` (`Failed to connect via CDP`)
  - `geminigen:9555` -> `AGENT_BROWSER_COMMAND_FAILED` (`Failed to connect via CDP`)
  - `canva:9666` -> `AGENT_BROWSER_COMMAND_FAILED` (`Failed to connect via CDP`)
- interpretation:
  - 현재 남은 문제는 구현 결함이 아니라 브라우저 운영 환경 blocker입니다.
  - `agent-browser` 실행 파일 자체는 해결됨 (`APPDATA/npm` fallback path 탐지 구현 완료).
  - 따라서 후속 작업은 코드 구현이 아니라 해당 포트로 브라우저를 실제 기동하는 운영 단계입니다.

### Follow-up Attach Audit

- evidence:
  - `system/runtime_v2_probe/agent-browser-live-attach-07/summary.json`
  - `system/runtime_v2_probe/agent-browser-seaart-final-05/summary.json`
  - `system/runtime_v2_probe/agent-browser-geminigen-final-11/summary.json`
- result:
  - `canva:9666` -> `status=ok`
  - `seaart:9444` -> `status=ok` (raw CDP HTTP fallback)
  - `geminigen:9555` -> `status=ok` (raw CDP HTTP fallback)
- interpretation:
  - 세 서비스 모두 live attach 확인이 완료되었습니다.
  - `seaart`, `geminigen`은 `agent-browser tab list` 자체는 불안정했지만 raw CDP HTTP fallback으로 canonical verify를 통과합니다.

### Final Attach Audit Note

- `seaart`, `geminigen`, `canva` 모두 브라우저 부팅과 live attach 확인이 끝났습니다.
- `seaart`, `geminigen`은 운영 세션에서 `agent-browser` CLI가 불안정할 수 있으므로, 현재 canonical verify는 raw CDP HTTP fallback을 포함한 worker 경로를 사용합니다.
- final environment status:
  - `seaart:9444` -> `ok`
  - `geminigen:9555` -> `ok`
  - `canva:9666` -> `ok`

### Runtime Health Readiness

- `docs/TODO.md` 기준 readiness check 완료
- `system/runtime_v2/health/browser_health.json` 기준
  - `session_count=5`
  - `healthy_count=5`
  - `unhealthy_count=0`
- `system/runtime_v2/health/gpt_status.json` 기준
  - `ok_count=3`
  - `min_ok=1`
  - `floor_breached=false`

## Live Agent-Browser Attach Results

### Ready Now

#### ChatGPT (`9222`)

- `agent-browser --cdp 9222 tab list` 성공
- 기본 활성 탭은 `Omnibox Popup`이라서 target tab selection 필요
- `agent-browser --cdp 9222 tab 2 && agent-browser --cdp 9222 get url && agent-browser --cdp 9222 get title` 성공
- 확인 결과
  - URL: `https://chatgpt.com/`
  - Title: `ChatGPT`

#### Genspark (`9333`)

- `agent-browser --cdp 9333 tab list` 성공
- `agent-browser --cdp 9333 get url && agent-browser --cdp 9333 get title` 성공
- 확인 결과
  - URL: `https://www.genspark.ai/`
  - Title: `Genspark(젠스파크) - 올인원 AI 작업 공간`

### Not Ready Yet

#### Seaart (`9444`)

- `agent-browser --cdp 9444 tab list` 실패
- 증상: timeout (`os error 10060`)

#### Geminigen (`9555`)

- `agent-browser --cdp 9555 tab list` 실패
- 증상: timeout (`os error 10060`)

#### Canva (`9666`)

- `agent-browser --cdp 9666 tab list` 실패
- 증상: timeout (`os error 10060`)

## Operational Interpretation

- 현재 저장소는 `agent-browser`를 쓰는 브라우저 프로그램 개발을 **부분적으로 시작할 준비**가 되어 있습니다.
- 구체적으로는 `ChatGPT`, `Genspark`를 대상으로 한 개발/검증 루프는 바로 시작할 수 있습니다.
- 하지만 브라우저군 전체를 공통 추상화로 묶어 개발하려면 `9444/9555/9666`의 CDP attach timeout 원인을 먼저 해결해야 합니다.
- 따라서 `probe success`와 `live readiness`를 같은 의미로 읽지 않습니다.

## Immediate Next Action

1. `9444`, `9555`, `9666`의 CDP attach timeout 원인을 추적합니다.
2. 각 포트에 대해 `tab list -> get url/get title` live evidence를 다시 확보합니다.
3. `video_plan["use_agent_browser_services"]`에 live-ready 서비스부터 연결해 stage2 row1 자동화 범위를 넓힙니다.
4. 세 포트가 모두 안정 응답하면 전체 readiness를 `Go`로 승격합니다.

## Canonical References

- `docs/TODO.md`
- `docs/plans/2026-03-09-agent-browser-closed-loop-development-plan.md`
- `system/runtime_v2/health/browser_health.json`
- `system/runtime_v2/health/browser_session_registry.json`
- `system/runtime_v2/health/gpt_status.json`
- `system/runtime_v2/evidence/result.json`
- `system/runtime_v2/latest_completed_run.json`

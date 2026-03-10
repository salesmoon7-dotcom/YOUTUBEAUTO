# Browser Instability Debug-Cost Reduction Plan

## Goal

- 브라우저 기반 프로그램(`ChatGPT`, `SeaArt`, `Genspark`, `GeminiGen`, `Canva`)에서 디버깅 비용을 키우는 불안정성 패턴을 고정합니다.
- 구현 논의가 아니라, **원인 분류 규칙과 증거 요구**를 문서화해 같은 디버깅을 반복하지 않도록 합니다.

## Top 3 Instability Multipliers

### 1. Profile/Lock Drift Guardrails

#### Problem

- 같은 증상이라도 실제 원인이 아래로 분산됩니다.
  - profile lock stale/busy/unknown
  - browser plane ownership mismatch
  - `session_ready.json` stale marker
  - dead browser pid / live port mismatch

#### Why it raises debugging cost

- 실패할 때마다 포트, PID, lock metadata, ready marker를 모두 다시 확인해야 합니다.
- 한 번의 포트 실패가 단순 “브라우저 죽음”이 아니라 ownership/lock drift로 퍼집니다.

#### Required observations

- `.runtime_v2.profile.lock`
- `browser_plane.lock`
- `session_ready.json`
- CDP HTTP endpoints (`/json/version`, `/json/list`)
- current pid liveness

#### Classification rule

- `ready marker`만 있고 pid/port가 없으면 stale marker
- pid는 있는데 port가 없으면 broken launch
- port는 있는데 attach가 안 되면 attach heuristic 문제

### 2. Ready/Login Heuristics Reliability

#### Problem

- URL/타이틀/탭 선택 휴리스틱에 과도하게 의존합니다.
- 로그인 페이지, 동의 페이지, redirect, hidden tab이 끼면 같은 서비스도 매번 다른 실패처럼 보입니다.

#### Why it raises debugging cost

- 매번 `tab list`, `current_url`, `current_title`, matcher 규칙을 다시 확인하게 됩니다.

#### Required observations

- selected tab url/title
- matcher input (`expected_url_substring`, `expected_title_substring`)
- login rule match 여부
- `raw_cdp_http` fallback transcript

#### Classification rule

- `tab list` 실패 -> transport/attach 축
- 탭은 보이는데 matcher miss -> heuristic 축
- 로그인 URL 패턴 일치 -> auth/session 축

### 3. DOM/Artifact Capture Heuristics

#### Problem

- selector fallback, stop-button, “첫 이미지” 선택 같은 휴리스틱이 사이트 변화에 취약합니다.

#### Why it raises debugging cost

- 같은 사이트라도 DOM이 바뀌면 입력/전송/응답/산출물 선택이 다시 깨집니다.
- 실제로 `GeminiGen`은 첫 이미지가 로고로 잡히는 문제가 있었습니다.

#### Required observations

- final screenshot
- transcript
- raw capture payload
- selected artifact url/path/hash

#### Classification rule

- 입력/전송 실패 -> selector/input heuristic
- 응답 완료 오판 -> stop-button / completion heuristic
- 잘못된 파일 수집 -> artifact selection heuristic

## Service Notes

### ChatGPT

- 가장 큰 instability cost driver
- submit/read/completion이 모두 휴리스틱에 묶여 있음

### SeaArt / GeminiGen

- `agent-browser tab list` 자체가 흔들릴 수 있음
- raw CDP HTTP fallback이 현재 canonical verify 경로

### Canva / Genspark

- 상대적으로 안정적이지만 title/url/artifact selection drift 가능

## Guardrail Rule

- 불안정성 문제를 해결할 때는 먼저 위 3축 중 어디에 속하는지 분류합니다.
- 분류 전 휴리스틱을 추가하지 않습니다.
- “임시 fallback으로 성공처럼 보이게 만들기”는 금지합니다.

## Immediate Use

- 이후 브라우저 관련 디버깅이 발생하면, 먼저 이 문서의 3축 중 하나로 분류한 뒤 evidence를 수집합니다.
- 수집 없이 임시 수정하지 않습니다.

## Follow-up implementation

- warn-only `single preflight` 1차가 반영되었습니다.
- 위치:
  - `runtime_v2/preflight.py`
  - `runtime_v2/cli.py`
- 역할:
  - effective config snapshot 생성
  - 외부 경로 존재 여부 경고
  - browser service/profile/port drift 경고
  - 결과를 `preflight_report.json`으로 기록
- 주의:
  - 이 preflight는 동작을 바꾸지 않고 검출/보고만 합니다.

# Runtime V2 ChatGPT Browser Environment Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2`의 `chatgpt` stage1 live-capture가 현재 세션/브라우저 실행환경에서 안정적으로 동작하도록, 레거시 `D:\YOUTUBE_AUTO`의 실행환경과 현재 `plain Chrome + raw CDP` 경로의 차이를 정리하고 필요한 최소 remediation 순서를 고정합니다. 동시에 이 문제를 `chatgpt` 단독 이슈가 아니라 5개 브라우저 서비스가 공유하는 실행/프로필/CDP 인프라 리스크 안에서 다룹니다.

**Architecture:** 이 계획은 downstream linkage가 아니라 브라우저 실행환경 remediation입니다. 핵심은 `ready` 판정, 브라우저 launch 환경, longform GPT 탭 유지, 입력 탐지, 전송/완료 대기, 응답 읽기 계층을 분리해서 보고, 증상(`NO_INPUT`, `CHATGPT_RESPONSE_TIMEOUT`, `CHATGPT_BACKEND_UNAVAILABLE`)이 아니라 그 아래 환경 차이를 먼저 해결하는 것입니다. 우선순위는 `ChatGPT longform readiness gate`지만, 진단 범위는 `chatgpt/genspark/seaart/geminigen/canva` 전체를 포함합니다.

**Tech Stack:** Python 3.13, `runtime_v2`, `runtime_v2/browser/manager.py`, `runtime_v2/stage1/chatgpt_backend.py`, `runtime_v2/stage1/chatgpt_interaction.py`, legacy `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py`, Chrome debug port 9222, raw CDP HTTP/WebSocket, `unittest`, `py_compile`

**Status:** TODO

---

## Evidence Summary

### Current runtime_v2 evidence

1. `chatgpt-primary` profile/lock/ready marker can exist while actual tabs are empty or only home tab exists.
2. Browser manager originally treated `https://chatgpt.com/` as ready; this was strengthened to longform GPT URL, but stage1 still fails.
3. Fresh row retries produced multiple failure modes:
   - `NO_INPUT`
   - `CHATGPT_RESPONSE_TIMEOUT`
   - `invalid_voice_groups`
   - `CHATGPT_BACKEND_UNAVAILABLE` with `CDP_METHOD_TIMEOUT`
4. Latest strong evidence shows the current session can have:
   - login/home visible in body text
   - longform GPT tab present
   - `ready=true`, `hasProseMirror=true`
   - yet `submit_ok` still degrades into timeout or missing effective send/read behavior

### Legacy contrast (`D:\YOUTUBE_AUTO`)

1. Legacy ChatGPT execution uses `undetected_chromedriver as uc`, not plain detached Chrome + raw CDP only.
2. Legacy code relies on stronger DOM/input detection and more opinionated completion waiting.
3. Therefore, current failures are likely not just parser issues; they are consistent with a browser-environment mismatch.

### Most plausible environment-level causes

1. **Driver model mismatch**
   - legacy = `uc/selenium`
   - current = `plain Chrome + raw CDP`
2. **Ready signal mismatch**
   - browser manager health != longform GPT workability
3. **Tab stability mismatch**
   - recovery can leave ChatGPT only on home tab or unstable longform tab
4. **Submit/read transport mismatch**
   - raw CDP can attach but still fail to submit/read reliably

### Shared multi-browser infrastructure risk

- `runtime_v2/browser/manager.py`는 5개 서비스를 같은 구조로 운영합니다:
  - `chatgpt(9222)`
  - `genspark(9333)`
  - `seaart(9444)`
  - `geminigen(9555)`
  - `canva(9666)`
- 따라서 이 문제는 `chatgpt` 단독 이슈가 아니라, 공통 `port -> profile -> tabs(/json) -> ready-rule` 인프라의 false-positive / attach instability와 연결될 수 있습니다.
- `genspark/geminigen`은 현재 `READY_URL_RULES`가 느슨하거나 없어서, `chatgpt`와는 다른 형태의 false-healthy가 생길 수 있습니다.

---

## Decision Framework

Before changing more prompt or parser logic, choose one of these paths explicitly.

### Option A: Harden plain Chrome + CDP

**Pros**
- smallest architectural change
- preserves current `runtime_v2` ownership model
- keeps browser manager and stage1 backend in the same family

**Cons**
- may continue to fight longform GPT DOM instability
- may never match legacy reliability if uc-specific behavior is essential

### Option B: Introduce a dedicated legacy-style / environment-parity ChatGPT path (recommended first)

**Pros**
- closest to known working legacy environment
- likely best chance of reproducing yesterday's success consistently

**Cons**
- larger change
- introduces dual-backend maintenance
- must preserve fail-closed contract and current queue ownership

### Recommended path

Start with **Option B** as a strict parity canary for `chatgpt` only. If the legacy-like launch model (`uc/selenium` style profile/port/tab handling) removes `NO_INPUT` / `CDP_METHOD_TIMEOUT`, then environment mismatch is confirmed as the dominant cause and the parity path should become the canonical fix. Only if the parity canary still fails should we return to **Option A** and continue hardening plain Chrome + CDP.

## Canonical parent plan alignment

- This plan is a **sub-plan** under `docs/plans/2026-03-08-browser-session-stability-plan.md`.
- canonical browser/session go/no-go remains owned by that parent plan.
- this document specializes only the `chatgpt` longform capture path and the shared browser-environment diagnosis method.

---

## Task 1: Build a legacy-parity ChatGPT canary path

**Files:**
- Read/compare: `D:\YOUTUBE_AUTO\scripts\chatgpt_automation.py`
- Modify: `runtime_v2/browser/manager.py` or a new ChatGPT-only launch helper
- Modify: relevant docs/tests as needed

**Purpose:** Eliminate the environment-difference variable first by launching ChatGPT in a mode that is maximally close to legacy.

**Step 1: Build a concrete env-diff table**
- driver model (`uc/selenium` vs plain Chrome+CDP)
- fixed port behavior
- profile cleanup/lock/DevToolsActivePort handling
- longform tab navigation method
- background throttling / startup flags

**Step 2: Run one parity canary**
- launch ChatGPT using the legacy-like environment model
- then let `runtime_v2` attach to the already-open debug port rather than owning browser startup from scratch

**Success criteria**
- one fresh row-level GPT run no longer fails with `NO_INPUT` / `CDP_METHOD_TIMEOUT`
- if this succeeds, environment mismatch is confirmed as the primary root cause

---

## Task 2: Split browser health from stage1 GPT readiness

**Files:**
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/stage1/chatgpt_backend.py`
- Modify: `tests/test_runtime_v2_browser_plane.py`

**Purpose:** Browser process health must not be confused with longform GPT workability.

**Step 1: Keep browser manager focused on browser/session liveness**
- port open
- lock ownership sane
- login page not shown
- longform URL ready rules for `chatgpt`

**Step 1A: Raise a shared browser environment checklist to canonical use**

For all 5 browser services, diagnose in this order:
1. port open
2. profile lock state (`free|busy|stale|unknown|owned`)
3. `/json/list` responsiveness
4. tab URL shape
5. service-specific ready rule

**Step 2: Add stage1-specific readiness proof**

Add a separate stage1 preflight artifact or result object that records:
- selected tab URL/title
- input readiness (`hasInteractive`, `hasSsr`, `hasChatInput`, `hasProseMirror`)
- send/stop signal state

**Success criteria**
- browser manager no longer overclaims `chatgpt` readiness
- stage1 has its own explicit readiness evidence before submit

### Task 2A: Add a read-only ChatGPT longform readiness gate

**Files:**
- Modify: `runtime_v2/stage1/chatgpt_backend.py`
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/gpt/floor.py`
- Modify: `runtime_v2/gpt_pool_monitor.py`

**Purpose:** A `chatgpt` session should not count as effectively ready if the longform GPT tab is open but input/send conditions are not truly met.

**Required gate signals:**
- not on login page
- longform GPT URL/tab selected
- input DOM ready (`hasInteractive/hasChatInput/hasProseMirror`)
- send capability present or explicitly classifiable

**Success criteria**
- `chatgpt` can be marked blocked even while browser health is nominal, if longform interaction readiness is false.

---

## Task 3: Mirror legacy input discovery more faithfully

**Files:**
- Modify: `runtime_v2/stage1/chatgpt_backend.py`
- Modify: `tests/test_runtime_v2_stage1_chatgpt_interaction.py`

**Purpose:** Current input detection is still weaker than legacy `find_input_element()`.

**Step 1: Extract exact legacy input rules**
- visible editor fallback order
- hydration wait conditions
- modal/overlay dismissal
- active element / focus handling

**Step 2: Port only the missing pieces**
- do not rewrite the whole backend
- add only the gaps proven by evidence

**Success criteria**
- `NO_INPUT` must disappear on a session that has a visible longform GPT editor

---

## Task 4: Separate submit success from response-start success

**Files:**
- Modify: `runtime_v2/stage1/chatgpt_backend.py`
- Modify: `runtime_v2/stage1/chatgpt_interaction.py`
- Modify: tests under `tests/test_runtime_v2_stage1_chatgpt_interaction.py`

**Purpose:** `submit_ok` is not enough; we need proof that generation actually starts.

**Step 1: Introduce explicit response-start gate**
- stop button appears OR
- assistant block count increases OR
- assistant text begins growing

**Step 2: Keep response completion separate**
- stop disappears
- text/legacy blocks stabilize

**Success criteria**
- retries can distinguish `NO_INPUT`, `SUBMIT_AMBIGUOUS`, `RESPONSE_NOT_STARTED`, `READ_TIMEOUT`

---

## Task 5: Compare yesterday-success environment to current failed environment

**Files:**
- Read/compare evidence only; doc the result in this plan or a linked report

**Purpose:** We already know yesterday worked. We need to compare environment, not only code.

**Compare:**
- profile dir contents
- lock/ready markers
- tab shape
- browser process args
- backend fallback chain in `raw_output.json.gpt_capture`

**Compare across shared environment axes too:**
- browser family / executable resolution
- service-specific ready-rule strictness
- raw CDP `/json/list` responsiveness across the 5 services

**Success criteria**
- one concrete environment difference is isolated and can be tested deliberately

---

## Task 6: Time-box and escalate if parity canary still fails

**Files:**
- Modify: this plan
- Possibly create a follow-up plan for alternate backend

**Purpose:** Avoid infinite retries.

**Rule:**
- If after Tasks 1-5 the parity canary still cannot produce one truthful fresh row-level GPT capture, stop environment tuning and create a dedicated `uc/selenium-backed` ChatGPT capture backend plan.

**Success criteria**
- retries stop being open-ended
- architecture escalation becomes explicit

---

## Verification Gate

The browser-environment remediation is only complete when all of these are true:

1. parity canary for `chatgpt` is executed with a legacy-like launch environment
2. `chatgpt-primary` launches into or can reliably navigate to the longform GPT tab
3. stage1 preflight confirms a visible input-ready state in the current session
4. one fresh row-level GPT run produces a non-fallback `raw_output.json`
5. `parsed_payload.json`, `stage1_handoff.json`, and `video_plan.json` are generated from that same current-session run
6. the result is not blocked by `NO_INPUT`, `RESPONSE_NOT_STARTED`, or `CDP_METHOD_TIMEOUT`
7. the multi-browser environment checklist no longer shows false-healthy on `chatgpt`, and any remaining `genspark/geminigen/canva/seaart` issues can be attributed to service-specific causes rather than shared environment ambiguity

---

## Immediate next action

Do **not** retry blindly.

Next action order:
1. construct a legacy-parity canary for `chatgpt`
2. capture and compare yesterday-success vs current-failure environment evidence
3. only after that, harden the missing environment-level logic inside `runtime_v2`
4. retry one isolated fresh row-level GPT run

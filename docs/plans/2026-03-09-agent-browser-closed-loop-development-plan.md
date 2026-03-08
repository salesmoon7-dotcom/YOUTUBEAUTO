# Agent-Browser Closed Loop Development Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** `runtime_v2`에 `agent-browser` 기반 브라우저 검증과 개발 자동화를 연결해, 계획 생성 -> 구현 -> 브라우저 검증 -> 실패 시 재계획이 반복되는 closed loop를 안전하게 구축합니다.

**Architecture:** 기존 `runtime_v2`의 single-writer 구조를 유지합니다. `runtime_v2/browser/*`는 세션/프로필/포트/health/recovery만 소유하고, 실제 `agent-browser` 실행은 control plane이 큐에서 오케스트레이션하는 새 workload worker로 추가합니다. 브라우저 검증과 개발 자동화는 모두 per-run artifact를 남기고, 최종 latest/evidence join은 기존 `runtime_v2/control_plane.py`가 단일 writer로 유지합니다.

**Tech Stack:** Python `unittest`, `runtime_v2` control plane / supervisor / browser plane, `agent-browser` CLI, probe-root based isolated runtime roots, JSON contract parsing, `control_plane_events.jsonl`, `result.json`, `gui_status.json`.

---

## Research Summary

- `agent-browser`는 MCP가 아니라 CLI 중심 도구이며, 공식 권장 흐름은 `open -> snapshot -i -> click/fill -> re-snapshot`입니다. 근거: `https://agent-browser.dev/installation`.
- 공식 문서는 global install(`npm install -g agent-browser`, `agent-browser install`)을 권장하며, AI coding assistant 연동은 `npx skills add vercel-labs/agent-browser`로 안내합니다. 근거: `https://agent-browser.dev/installation`.
- 현재 환경 실측 결과, `where agent-browser`와 `agent-browser --help`는 실패했고 `npx agent-browser --help`는 정상 동작했습니다. 즉 global 설치는 아직 없고, Node/NPM/NPX(`v22.19.0` / `10.9.3` / `10.9.3`)는 사용 가능합니다.
- 이 저장소는 이미 브라우저 plane을 분리해 두었습니다. `runtime_v2/browser/manager.py`는 profile/port/browser family/lock/login launch 흐름을 갖고, `runtime_v2/browser/supervisor.py`는 recovery/event/health writer 역할을 수행합니다.
- `runtime_v2/control_plane.py`는 queue -> worker -> result/evidence -> next_jobs 체인을 이미 갖고 있어, `agent-browser`는 browser plane이 아니라 새 worker workload로 붙이는 편이 single-owner 원칙에 맞습니다.
- `runtime_v2/supervisor.py`에는 `allow_runtime_side_effects=False` 경로가 이미 있으므로 safe/isolated/manual 검증 tier를 유지한 채 개발 자동화를 붙일 수 있습니다.
- `runtime_v2/stage1/gpt_plan_parser.py`는 fenced JSON 우선 추출을 지원하지만 fallback slice도 허용하므로, closed loop 계획/재계획 계약에서는 fenced JSON + schema 강화가 필요합니다.

## Execution Path Decision

- 현재 저장소는 Python 중심이며 `package.json`이 없고 `agent-browser.json`도 아직 없습니다.
- 따라서 초기 점검/실험 경로는 `npx agent-browser ...`가 가장 안전합니다.
- 실제 closed loop worker 구현 단계에서는 매 실행마다 `npx`가 패키지 해석을 반복하지 않도록, 이 머신 기준 권장 경로를 global CLI(`npm install -g agent-browser` + `agent-browser install`)로 고정합니다.
- 프로젝트 레벨에서는 npm dependency를 새로 들이기보다, 나중에 필요하면 `agent-browser.json`만 저장소 루트에 추가해 session/profile/default flags를 표준화하는 편이 현재 리포 구조에 더 잘 맞습니다.
- browser attach 전략은 새 Chromium을 띄우는 기본 `open`보다, 기존 browser plane debug port에 붙는 `connect`/`--cdp` 기반 검증 경로를 우선 검토합니다.
- 실측 smoke 결과, global 설치 후 `agent-browser 0.17.0`이 PATH에서 정상 동작했고 `9222(chatgpt)` 및 `9333(genspark)`에는 attach가 성공했습니다.
- `9222`의 기본 연결 대상은 ChatGPT 본문이 아니라 `Omnibox Popup` 탭으로 잡혔으므로, worker 구현에는 `tab list` -> target tab 선택(`tab 2`처럼) 단계를 명시적으로 포함해야 합니다.
- `9666(canva)`는 listen 상태여도 `agent-browser --cdp 9666 get url`에서 timeout이 났으므로, port-open 검사만으로는 부족하고 실제 CDP 응답 preflight를 별도 단계로 넣어야 합니다.

## Fit Assessment For This Repository

### 적합한 이유

1. 이 저장소는 이미 브라우저 세션을 상시 관리하는 구조가 있으므로, `agent-browser`를 브라우저 기동기가 아니라 "기존 debug port에 attach하는 검증 실행기"로 쓰기 좋습니다.
2. `control_plane.py`의 `next_jobs` 체인과 `result.json`/`control_plane_events.jsonl` evidence 모델이 있어서 closed loop를 queue-based workflow로 연결하기 좋습니다.
3. `tests/test_runtime_v2_browser_plane.py`와 `tests/test_runtime_v2_control_plane_chain.py`가 있어 새 workload와 evidence contract를 TDD로 붙일 수 있습니다.

### 반드시 피해야 하는 방식

1. `agent-browser`가 기존 `BrowserManager`를 우회해 직접 canonical profile을 여는 방식
2. browser validation worker가 `result.json` 또는 `gui_status.json`를 직접 쓰는 방식
3. safe tier에서도 실브라우저 launch를 밟는 방식
4. 파싱 실패를 loose fallback으로 덮는 방식
5. `BROWSER_BLOCKED`와 `BROWSER_UNHEALTHY`를 하나로 합치는 방식

## Closed Loop Target State

```text
Requirement/Prompt
  -> plan job
  -> implement job
  -> static verification job
  -> browser verification job (agent-browser)
  -> pass => complete
  -> fail => failure evidence normalize
  -> replan job
  -> implement job (next iteration)
```

### Closed Loop Rules

- 브라우저 plane은 세션 상태만 소유합니다.
- control plane만 latest/evidence의 최종 writer입니다.
- implement job만 repo writer lock을 획득할 수 있습니다.
- browser verification은 canonical profile을 직접 열지 않고 manager가 준비한 session/port에 attach만 합니다.
- replan 입력은 자유 텍스트가 아니라 `result.json(metadata)` + `control_plane_events.jsonl` + per-run browser artifacts의 구조화된 evidence로 제한합니다.

## Implementation Direction

### 새로 추가할 핵심 개념

1. `agent_browser_verify` workload
2. `dev_plan` / `dev_implement` / `dev_verify` / `dev_replan` explicit job contract chain
3. repo single-writer lock
4. agent-browser command transcript artifact
5. browser verification result parser and failure normalizer

### 수정 우선순위

1. contract와 worker registry부터 추가합니다.
2. 그 다음 parser/command builder를 추가합니다.
3. 그 다음 control-plane routing과 evidence join을 연결합니다.
4. 마지막으로 probe-root isolated closed loop smoke test를 추가합니다.

---

### Task 1: Define Agent-Browser Workload and Contracts

**Files:**
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/worker_registry.py`
- Modify: `runtime_v2/contracts/job_contract.py`
- Create: `runtime_v2/contracts/agent_browser_contract.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write the failing test**

```python
def test_agent_browser_workload_is_registered_for_control_plane() -> None:
    self.assertIn("agent_browser_verify", allowed_workloads())
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_agent_browser_workload_is_registered_for_control_plane -q`
Expected: FAIL with missing workload/registry path

**Step 3: Write minimal implementation**

- `WorkloadName`에 `agent_browser_verify`를 추가합니다.
- browser-required workload로 매핑합니다.
- explicit contract builder/validator에 `agent_browser_verify` payload shape를 추가합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_agent_browser_workload_is_registered_for_control_plane -q`
Expected: PASS

**Step 5: Verify related contracts**

Run: `python -m pytest tests/test_runtime_v2_stage2_contracts.py -q`
Expected: PASS or pre-existing unrelated failures only

---

### Task 2: Add Strict Plan/Replan Parsing Contract

**Files:**
- Modify: `runtime_v2/stage1/gpt_plan_parser.py`
- Create: `runtime_v2/contracts/dev_loop_plan.py`
- Test: `tests/test_runtime_v2_stage1_gpt_plan_parser.py`

**Step 1: Write the failing test**

```python
def test_dev_loop_plan_requires_fenced_json_contract() -> None:
    with self.assertRaises(ValueError):
        extract_dev_loop_plan("plain text {\"step\":1}")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_stage1_gpt_plan_parser.py::test_dev_loop_plan_requires_fenced_json_contract -q`
Expected: FAIL because dev loop parser does not exist

**Step 3: Write minimal implementation**

- dev loop plan parser는 fenced JSON만 허용합니다.
- 필수 필드: `goal`, `tasks`, `verification`, `browser_checks`, `replan_on_failure`.
- loose brace slicing은 dev loop 전용 parser에서 금지합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_stage1_gpt_plan_parser.py::test_dev_loop_plan_requires_fenced_json_contract -q`
Expected: PASS

**Step 5: Add negative parsing tests**

Run: `python -m pytest tests/test_runtime_v2_stage1_gpt_plan_parser.py -q`
Expected: PASS

---

### Task 3: Implement Agent-Browser Command Builder and Result Parser

**Files:**
- Create: `runtime_v2/agent_browser/command_builder.py`
- Create: `runtime_v2/agent_browser/result_parser.py`
- Create: `runtime_v2/agent_browser/__init__.py`
- Test: `tests/test_runtime_v2_browser_plane.py`

**Step 1: Write the failing test**

```python
def test_agent_browser_command_builder_uses_snapshot_ref_flow() -> None:
    commands = build_agent_browser_flow("https://example.com", [{"action": "snapshot"}])
    self.assertTrue(any("snapshot -i" in cmd for cmd in commands))
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_browser_plane.py::RuntimeV2BrowserPlaneTests::test_agent_browser_command_builder_uses_snapshot_ref_flow -q`
Expected: FAIL because builder/parser modules do not exist

**Step 3: Write minimal implementation**

- 공식 권장 흐름 기반 command builder를 만듭니다.
- parser는 `snapshot`, `click`, `fill`, `done/error` 결과를 구조화합니다.
- parser 출력은 worker_result details에 바로 들어갈 수 있는 dict shape로 고정합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_browser_plane.py::RuntimeV2BrowserPlaneTests::test_agent_browser_command_builder_uses_snapshot_ref_flow -q`
Expected: PASS

**Step 5: Add parser failure tests**

Run: `python -m pytest tests/test_runtime_v2_browser_plane.py -q`
Expected: PASS or only pre-existing unrelated failures

---

### Task 4: Add Agent-Browser Verification Worker

**Files:**
- Create: `runtime_v2/workers/agent_browser_worker.py`
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/supervisor.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write the failing test**

```python
def test_control_plane_runs_agent_browser_verify_job_and_records_artifacts(self) -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_control_plane_runs_agent_browser_verify_job_and_records_artifacts -q`
Expected: FAIL with unknown workload or missing worker

**Step 3: Write minimal implementation**

- worker는 `agent-browser` CLI를 실행합니다.
- canonical profile을 직접 열지 않고 `BrowserManager`가 준비한 포트/세션 정보만 사용합니다.
- worker는 `result_path`, `transcript_path`, `screenshots`, `completion`을 반환합니다.
- `control_plane.py`는 이를 다른 worker와 동일한 방식으로 join합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_control_plane_runs_agent_browser_verify_job_and_records_artifacts -q`
Expected: PASS

**Step 5: Verify no single-writer regression**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py -q`
Expected: PASS

---

### Task 5: Add Repo Writer Lock for Implement Step

**Files:**
- Create: `runtime_v2/dev_writer_lock.py`
- Create: `runtime_v2/workers/dev_implement_worker.py`
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write the failing test**

```python
def test_dev_implement_worker_requires_single_repo_writer_lock(self) -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_dev_implement_worker_requires_single_repo_writer_lock -q`
Expected: FAIL because writer lock does not exist

**Step 3: Write minimal implementation**

- implement worker만 repo writer lock을 획득할 수 있게 합니다.
- 다른 개발 루프 worker는 읽기/검증만 수행합니다.
- lock root는 `RuntimeConfig.lock_root`를 재사용합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_dev_implement_worker_requires_single_repo_writer_lock -q`
Expected: PASS

**Step 5: Verify control loop still routes jobs deterministically**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q`
Expected: PASS

---

### Task 6: Wire Closed-Loop Job Chain

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Create: `runtime_v2/workers/dev_plan_worker.py`
- Create: `runtime_v2/workers/dev_replan_worker.py`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write the failing test**

```python
def test_dev_loop_failure_seeds_replan_job_with_same_run_id(self) -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_dev_loop_failure_seeds_replan_job_with_same_run_id -q`
Expected: FAIL because replan routing is missing

**Step 3: Write minimal implementation**

- job chain: `dev_plan -> dev_implement -> agent_browser_verify -> dev_replan`.
- 실패 시 `run_id`, `row_ref`, `error_code`, `completion_state`, `backoff_sec`, `artifact refs`를 유지합니다.
- 재계획은 기존 `MAX_CHAIN_DEPTH`, `MAX_NEXT_JOBS` 가드레일을 재사용합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_dev_loop_failure_seeds_replan_job_with_same_run_id -q`
Expected: PASS

**Step 5: Verify result/evidence consistency**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py -q`
Expected: PASS

---

### Task 7: Preserve Safe / Isolated / Manual Tier Rules

**Files:**
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/cli.py`
- Modify: `docs/plans/2026-03-08-browser-session-stability-plan.md`
- Test: `tests/test_runtime_v2_control_plane_chain.py`

**Step 1: Write the failing test**

```python
def test_agent_browser_verify_respects_allow_runtime_side_effects_false(self) -> None:
    result = run_control_loop_once(..., allow_runtime_side_effects=False)
    self.assertNotEqual(result["code"], "BROWSER_SIDE_EFFECT_EXECUTED")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_agent_browser_verify_respects_allow_runtime_side_effects_false -q`
Expected: FAIL because new workload path ignores safe tier

**Step 3: Write minimal implementation**

- safe tier에서는 browser verification을 실행하지 않고 blocked/skip 형태의 구조화된 결과만 반환합니다.
- isolated tier 기본 root는 `--probe-root`입니다.
- canonical `system/runtime_v2/*`는 manual 단계 전용임을 문서화합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py::RuntimeV2ControlPlaneChainTests::test_agent_browser_verify_respects_allow_runtime_side_effects_false -q`
Expected: PASS

**Step 5: Re-run tier-sensitive tests**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py -q`
Expected: PASS

---

### Task 8: Add Browser Evidence Normalization

**Files:**
- Create: `runtime_v2/agent_browser/evidence.py`
- Modify: `runtime_v2/evidence.py`
- Modify: `runtime_v2/control_plane.py`
- Test: `tests/test_runtime_v2_evidence.py`

**Step 1: Write the failing test**

```python
def test_agent_browser_failure_is_normalized_into_result_metadata() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_evidence.py::test_agent_browser_failure_is_normalized_into_result_metadata -q`
Expected: FAIL because browser evidence join path is missing

**Step 3: Write minimal implementation**

- browser worker raw transcript를 normalized evidence로 변환합니다.
- `code`, `worker_error_code`, `completion_state`, `final_output`, `artifact refs`를 기존 metadata 형식에 맞춥니다.
- 브라우저 상세 이벤트는 per-run artifact에 남기고 final join은 control plane만 수행합니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_evidence.py::test_agent_browser_failure_is_normalized_into_result_metadata -q`
Expected: PASS

**Step 5: Re-run evidence bundle**

Run: `python -m pytest tests/test_runtime_v2_evidence.py tests/test_runtime_v2_latest_run.py -q`
Expected: PASS

---

### Task 9: Add Probe-Root Closed-Loop Smoke Test

**Files:**
- Create: `tests/test_runtime_v2_agent_browser_closed_loop.py`
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/cli.py`

**Step 1: Write the failing test**

```python
def test_probe_root_closed_loop_replans_after_browser_failure_then_completes() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_v2_agent_browser_closed_loop.py::test_probe_root_closed_loop_replans_after_browser_failure_then_completes -q`
Expected: FAIL because closed loop chain is incomplete

**Step 3: Write minimal implementation**

- probe-root isolated runtime에서 plan/implement/verify/replan chain을 한 번 완주시킵니다.
- 첫 verify는 의도적으로 실패시켜 replan 증거를 생성합니다.
- 두 번째 verify는 통과시켜 completion state를 `completed` 또는 동등 의미로 닫습니다.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_v2_agent_browser_closed_loop.py::test_probe_root_closed_loop_replans_after_browser_failure_then_completes -q`
Expected: PASS

**Step 5: Run regression bundle**

Run: `python -m pytest tests/test_runtime_v2_control_plane_chain.py tests/test_runtime_v2_browser_plane.py tests/test_runtime_v2_evidence.py tests/test_runtime_v2_latest_run.py tests/test_runtime_v2_agent_browser_closed_loop.py -q`
Expected: PASS

---

### Task 10: Document Operational Runbook and Acceptance Gates

**Files:**
- Modify: `docs/sop/SOP_runtime_v2_development_guardrails.md`
- Modify: `docs/TODO.md`
- Modify: `docs/COMPLETED.md`
- Modify: `docs/plans/2026-03-08-browser-session-stability-plan.md`

**Step 1: Write the failing documentation checklist**

```text
- agent-browser uses existing browser plane only
- implement step has single repo writer lock
- safe/isolated/manual tier is preserved
- closed-loop failure axes reuse existing codes
```

**Step 2: Verify docs are missing required guidance**

Run: `python -m pytest tests/test_runtime_v2_agent_browser_closed_loop.py -q`
Expected: PASS or N/A; docs gap confirmed by manual read

**Step 3: Update documentation**

- 운영자가 manual login/open/session recovery와 agent-browser verify를 어떻게 분리해야 하는지 기록합니다.
- completion 기준은 브라우저 테스트 통과 + evidence join clean + failure axis drift 없음으로 고정합니다.

**Step 4: Verify docs reference canonical plan correctly**

Run: `python -m pytest tests/test_runtime_v2_latest_run.py -q`
Expected: PASS

**Step 5: Session-end verification gate**

Run: `python -m py_compile runtime_v2/control_plane.py runtime_v2/supervisor.py runtime_v2/browser/manager.py runtime_v2/browser/supervisor.py`
Expected: PASS

---

## Acceptance Gates

1. `agent-browser`는 새 worker workload로만 연결되고 `runtime_v2/browser/*` 책임을 침범하지 않아야 합니다.
2. browser verification은 기존 browser plane이 소유한 세션/포트에만 attach해야 합니다.
3. implement 단계는 repo single-writer lock 없이 실행되면 안 됩니다.
4. `allow_runtime_side_effects=False`에서 closed loop가 실브라우저를 띄우면 안 됩니다.
5. replan 입력은 구조화된 evidence만 사용해야 하며 자유 텍스트 재해석을 허용하지 않습니다.
6. `result.json`, `gui_status.json`, `control_plane_events.jsonl`, latest pointers는 여전히 control plane이 단일 writer여야 합니다.
7. `BROWSER_BLOCKED`, `BROWSER_UNHEALTHY`, `GPT_FLOOR_FAIL` 등 기존 failure axis를 재사용해야 합니다.
8. probe-root isolated smoke에서 실패 후 재계획, 그 다음 성공까지 한 run_id chain으로 추적 가능해야 합니다.

## Out of Scope

- `agent-browser` 자체 포크 또는 내부 구현 변경
- Playwright MCP 재도입
- browser plane을 별도 시스템으로 분리하는 대규모 아키텍처 변경
- 24시간 soak 자동 실행기 전체 구현
- 비브라우저 GPU worker 성능 최적화

## Recommended Execution Order

1. Task 1-2로 contract와 parser를 먼저 고정합니다.
2. Task 3-4로 `agent-browser` command/result path를 worker로 연결합니다.
3. Task 5-7로 implement lock과 safe/isolated/manual 규칙을 닫습니다.
4. Task 8-9로 evidence normalization과 probe-root closed loop smoke를 완성합니다.
5. Task 10으로 운영 문서와 acceptance gate를 닫습니다.

## Notes For Execution

- closed loop 개발 자동화는 기본적으로 `probe_root` 격리 환경에서만 돌리세요.
- canonical `system/runtime_v2/*` 경로는 manual/운영 검증에만 사용하세요.
- browser verification 실패는 "브라우저가 망가졌다"보다 먼저 `blocked`/`unhealthy`/`parser failure`/`assertion failure` 중 어느 축인지 normalize 하세요.
- parser와 evidence가 느슨하면 closed loop는 빠르게 drift합니다. 구현보다 contract 강화가 먼저입니다.

HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- 채팅창 오류가 나서 중단되었어. 어디서 오류가 났는지 확인한거지?
- 이제 어떻게 테스트 할건지 확실히 정할 수 있는거지?
- 진행해줘.
- 계획이 완료될때까지 절대 멈추거나 보고하지말고 계획의 끝까지  계속 진행해.
- 오류가 난다면 어디서 발생하는지 추적해주는 방법도 추가되어야해.
- 반드시 모든 수정과 검증은 오라클과 계획  vendor
- 검증  kimoring-ai-skills를 적용해.
- 수정후 git push까지 진행해. ultrawork
- 야 또 채팅창 중단되었어. 1. 채팅창 중단 오류를 확실히 잡아내서 해결할 수 있는거야? 전면적인 로직을 수정해야하는거야? 새로운 세션에서 진행해야하는거야?
- 2. 채팅창 오류때문에 프로그램개발을 중단해야하는지 검토해. 이것때문에 개발시간이 막대한 낭비가 되고 있어.
- 야 또 오류발생했어. 1. 채팅창 중단 오류를 확실히 잡아내서 해결할 수 있는거야? 전면적인 로직을 수정해야하는거야? 새로운 세션에서 진행해야하는거야?
- 2. 채팅창 오류때문에 프로그램개발을 중단해야하는지 검토해. 이것때문에 개발시간이 막대한 낭비가 되고 있어.
- 야 새세션에서 진행할테니 핸드오프문서 만들어. 진행한사항을 상세히 기록하고 어떤게 채팅창 중단을 유발하는지 기록하고 남은 계획도 포함해.

GOAL
----
새 세션에서 채팅창 중단을 피하는 실행 방식으로 runtime_v2 remediation을 이어가고, 현재 dirty worktree의 runtime_v2/test 변경을 검증·정리·커밋·푸시까지 마무리합니다.

WORK COMPLETED
--------------
- I investigated the repeated chat interruption pattern and concluded the primary issue is not a full runtime_v2 logic collapse but the combination of long foreground tool execution plus heavy side effects such as browser bootstrap, detached subprocess spawn, and runtime bootstrap/tick paths.
- I fixed the canonical test-tier documentation in docs/plans/2026-03-08-browser-session-stability-plan.md and linked it from docs/TODO.md. I also added two trace sections: Test Failure Trace Method and Error Trace Method.
- I pushed the documentation-only commit 03f65ae with message: docs: define runtime_v2 test tiers and failure tracing.
- I reviewed the current dirty runtime_v2 code/test changes and confirmed they already include significant work for safe path execution, latest-run join, control-plane backoff semantics, and browser contract coverage.
- I reproduced a real code bug in runtime_v2/browser/manager.py: browser launch lock payload persisted transient fields and could serialize MagicMock pid values, which broke _launch_debug_browser tests and caused incorrect second lock acquisition behavior.
- I fixed runtime_v2/browser/manager.py so inspect_profile_lock returns derived lock status after persisted payload fields, and _launch_debug_browser now rewrites the profile lock with only JSON-safe core metadata using _to_int(getattr(child, "pid", 0)).
- I verified that focused browser tests passed after the fix:
  - tests.test_runtime_v2_browser_plane.RuntimeV2BrowserPlaneTests.test_launch_debug_browser_uses_service_start_url
  - tests.test_runtime_v2_browser_plane.RuntimeV2BrowserPlaneTests.test_launch_debug_browser_keeps_profile_lock_with_browser_pid
  - tests.test_runtime_v2_browser_plane.RuntimeV2BrowserPlaneTests.test_second_acquire_sees_busy_lock_after_successful_launch
  - tests.test_runtime_v2_browser_plane.RuntimeV2BrowserPlaneTests.test_browser_health_marks_login_page_as_login_required_without_restart
  - tests.test_runtime_v2_browser_plane.RuntimeV2BrowserPlaneTests.test_supervisor_writes_blocked_browser_event_for_login_required
  - tests.test_runtime_v2_browser_plane.RuntimeV2BrowserPlaneTests.test_supervisor_recovers_only_unhealthy_session
- I verified that representative safe/isolated tests passed before the chat interrupted again:
  - tests.test_runtime_v2_phase2.RuntimeV2Phase2Tests.test_run_once_side_effect_free_mode_skips_browser_bootstrap
  - tests.test_runtime_v2_control_plane_chain.RuntimeV2ControlPlaneChainTests.test_control_plane_side_effect_free_mode_skips_bootstrap_and_gpt_ticks
  - tests.test_runtime_v2_phase2.RuntimeV2Phase2Tests.test_selftest_probe_child_keeps_run_id_aligned_across_outputs
  - python -m unittest tests.test_runtime_v2_control_plane_chain ran 8 tests OK

CURRENT STATE
-------------
- Branch is main and upstream is origin/main.
- Documentation handoff work is already pushed, but the active runtime_v2 code/test changes are still uncommitted.
- Current uncommitted files are:
  - runtime_v2/bootstrap.py
  - runtime_v2/browser/manager.py
  - runtime_v2/cli.py
  - runtime_v2/config.py
  - runtime_v2/control_plane.py
  - runtime_v2/latest_run.py
  - tests/test_runtime_v2_browser_plane.py
  - tests/test_runtime_v2_control_plane_chain.py
  - tests/test_runtime_v2_phase2.py
- LSP status before interruption:
  - runtime_v2/latest_run.py, runtime_v2/config.py, runtime_v2/bootstrap.py, runtime_v2/control_plane.py, tests/test_runtime_v2_phase2.py, tests/test_runtime_v2_control_plane_chain.py had no diagnostics.
  - runtime_v2/cli.py, runtime_v2/browser/manager.py, tests/test_runtime_v2_browser_plane.py still had basedpyright warnings, but no blocking syntax errors were found from the edits I made.
- Chat interruption pattern remains active when running large or parallel unittest invocations from this chat session.

PENDING TASKS
-------------
- Finish the in-progress todo: 필요한 코드 수정 및 오류 추적 경로 보강.
- Run runtime_v2 guardrail verification for the dirty runtime_v2/test work, especially run_id alignment, error_code meaning alignment, and attempt/backoff contract alignment.
- Re-run the remaining test coverage in a new session or external shell using strict serial execution, not parallel batches.
- Build an atomic commit plan for the dirty runtime_v2/test files, then commit and push.
- Current todo state was effectively:
  - completed: 현재 runtime_v2 변경 상태와 계획 대비 남은 구현 범위 수집
  - completed: safe/control/browser/latest_run 관련 실패 재현 및 원인 축 고정
  - in_progress: 필요한 코드 수정 및 오류 추적 경로 보강
  - pending: runtime_v2 guardrail 기준 검증 및 테스트 실행
  - pending: 원자 단위 커밋 계획 수립 후 commit/push

KEY FILES
---------
- docs/plans/2026-03-08-browser-session-stability-plan.md - Canonical remediation plan, test tiers, and trace methods.
- docs/TODO.md - Canonical execution order and remaining remediation categories.
- runtime_v2/browser/manager.py - Browser launch/lock ownership logic; actual bug fix was made here.
- runtime_v2/cli.py - Main entry paths, detached probe flow, and one of the heavy side-effect sources.
- runtime_v2/control_plane.py - Control-loop side-effect path and blocked/backoff semantics.
- runtime_v2/bootstrap.py - Runtime bootstrap path involved in heavy side effects.
- runtime_v2/config.py - RuntimeConfig paths used by safe/probe-root isolation.
- runtime_v2/latest_run.py - Latest-run evidence join logic; currently untracked and needs verification.
- tests/test_runtime_v2_phase2.py - Safe/isolated/manual tier examples plus probe-root tests.
- tests/test_runtime_v2_browser_plane.py - Browser lock/launch/supervisor contract tests, including the bug I fixed.

IMPORTANT DECISIONS
-------------------
- I decided that the chat interruption problem must be treated separately from runtime_v2 code correctness. The evidence is that focused tests pass while larger file-level or parallel unittest runs get interrupted by the tool/chat layer.
- I decided not to do a broad runtime_v2 refactor. The current evidence supports targeted remediation plus a strict execution policy: safe in chat, isolated/manual outside chat.
- I fixed only the confirmed browser lock bug in runtime_v2/browser/manager.py. I did not touch unrelated runtime_v2 code paths without reproduction evidence.
- I treated test execution policy as canonical: safe -> isolated -> manual, with detached/browser-launch/manual flows kept out of chat sessions.
- I treated the trace order as fixed: probe_result.json -> browser_health.json -> result.json -> control_plane_events.jsonl -> debug log for isolated runs.

EXPLICIT CONSTRAINTS
--------------------
- 계획이 완료될때까지 절대 멈추거나 보고하지말고 계획의 끝까지  계속 진행해.
- 오류가 난다면 어디서 발생하는지 추적해주는 방법도 추가되어야해.
- 반드시 모든 수정과 검증은 오라클과 계획  vendor
- 검증  kimoring-ai-skills를 적용해.
- 수정후 git push까지 진행해. ultrawork

CONTEXT FOR CONTINUATION
------------------------
- The biggest chat interruption triggers observed in this session were:
  - long foreground unittest runs from the chat tool
  - parallel unittest runs in the same chat turn
  - paths that combine browser launch, detached subprocess creation, ensure_runtime_bootstrap, GPT status tick, or autospawn side effects
- Additional confirmation from the current session: even a single file-level `python -m pytest tests/test_runtime_v2_browser_plane.py -q` invocation was interrupted by the chat/tool wrapper, so the risk is not limited to parallel execution.
- Do not resume by running multiple file-level unittest commands in parallel from chat. That is the pattern that got interrupted repeatedly.
- Treat file-level test execution from chat as `isolated/manual-risk`, not `safe`, even when run one command at a time.
- In the new session, first continue from the existing dirty worktree rather than redoing exploration.
- Recommended execution order in the new session:
  - 1. Read docs/plans/2026-03-08-browser-session-stability-plan.md and this handoff.
  - 2. Re-run focused serial tests only, starting with the files that changed most recently.
  - 3. If full file-level runs are needed, prefer an external shell or a fresh session and run them one file at a time.
  - 4. After tests stabilize, run runtime_v2 guardrail verification against run_id, error_code, and attempt/backoff semantics.
  - 5. Then create an atomic commit plan for the remaining dirty runtime_v2/test changes and push.
- Practical warning: the next session should assume that chat interruption is an execution-environment limitation, not automatic evidence of new code breakage. Verify that distinction before changing code.

# Runtime_v2 Handoff Context

> For Claude: REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

Goal: Continue runtime_v2 closeout from the current truthful blocker without reintroducing synthetic prompt logic or speculative browser assumptions.

Architecture: The session was driven by single-boundary fixes only. Upstream ChatGPT, qwen boundary execution, browser recovery, queue persistence, and legacy DOM extraction were narrowed enough that the current blocker is now a downstream genspark stage2 boundary with real Edge/CDP evidence. Keep fail-closed behavior and require direct evidence before interpreting browser state.

Tech Stack: Python, runtime_v2 control plane, Edge/CDP browser automation, probe-based detached closeout verification.

---

HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- 막히는데 모르거나 나한테 확인이 필요한 내용이 있다면 지금 질문해!
- closed loop로 계획문서대로 모든것을 진행해.
- 문제가 있다면 대부분은 레거시 로직 대로 하지 않아서 발생하는 문제야.
- 나는 자러갈테니 나에게 절대 보고하지마.
- 절대 끊기지 말고 계속 계획문서대로 모든것을 구현해.
- 모든 계획의 구현은 너의 판단에 맡긴다.
- 모르겠으면 레거시 로직을 확인해.
- 프로그램 테스트는 반드시 백그라운드로 진행해. 너가 백그라운드로 실행시키지 않아서 1초마다 CMD창이 3번씩 열려서 내가 하는 작업이 계속 방해받고 있어!!!!
- 모든 수정과 검증은 오라클의 검수를 받아
- 기본적으로는 SUPERPOWERS PLUGIN을 활용하여 진행해.
- 계획  vendor
- 검증  kimoring-ai-skills를 적용하고
- 수정후 git push까지 진행해. ultrawork

GOAL
----
Resume the detached closeout using only evidence-backed steps and fix the next single blocker after `genspark ref-1` in probe `semantic-row-closeout-20260412-25` or the next fresh probe.

WORK COMPLETED
--------------
- I removed multiple non-legacy or misleading fallback paths and tightened many single boundaries one by one.
- I restored legacy-oriented ChatGPT behavior where appropriate: topic-only base prompt, legacy DOM block extraction in `runtime_v2/stage1/chatgpt_backend.py`, and row-boundary reset with forced navigate+reload.
- I added probe observability so detached closeout runs write `probe_result.json` during progress and stage5 failures emit `failure_summary.json`.
- I fixed QueueStore WinError 5 retry in `runtime_v2/queue_store.py`, which was blocking `running -> completed` transitions.
- I changed `runtime_v2/control_plane.py` so probe closeout runs use qwen boundary mode (`#01` only) under probe artifact roots instead of full production qwen batches.
- I verified with direct file evidence that `genspark` Edge/CDP can be genuinely healthy: `D:\YOUTUBEAUTO_RUNTIME\runtime_state\health\browser_health.json` showed `genspark` healthy with `browser_family=edge`, `status=running`, `cdp_endpoint_ready=true` after `readiness-gpt-refresh-21`.
- I verified with direct file evidence that `probe 25` reached `chatgpt completed`, `qwen completed`, and then `genspark ref-1 running`, so the active blocker moved downstream.
- I reverted my own incorrect synthetic JSON/reprompt prompt invention and kept `chatgpt` fail-closed unless legacy evidence justified a parser-side recovery.

CURRENT STATE
-------------
- Current trustworthy evidence root is `D:/YOUTUBEAUTO_RUNTIME/probe/semantic-row-closeout-20260412-25`.
- In `probe 25`, `chatgpt` completed successfully and `qwen3_tts` completed successfully with a single boundary item.
- In `probe 25`, `genspark ref-1` is the first downstream blocker after qwen: it has `started.json`, `job.json`, `request.json`, `attach_evidence.json`, `agent_browser_verify` transcript showing a real Edge tab, and repeated `worker_heartbeat`, but no terminal success yet.
- `probe 25` itself currently ends earlier than full closeout due to downstream unresolved work; it should be treated as the best current evidence root, not as a successful end-to-end closeout.
- Working tree may contain temporary helper scripts/logs under repo root (for hidden background execution); do not mistake them for product code.

DEBUGGING METHOD UPDATE
----------------------
- Do not add speculative fallback logic. If a blocker is not proven by direct evidence, stop instead of inventing recovery paths.
- Work on exactly one owner boundary at a time. Narrow to a single function or layer, verify there, then move on.
- If evidence shows the blocker is not repo-side code, do not keep patching around it. Record that boundary truthfully and move to the next proven layer only when appropriate.
- Prefer fail-closed behavior over guessed success. A visible blocker is better than a hidden false positive.
- Current restart point after the recent verification pass: browser health can be recovered hidden and background-only, but the active fresh-probe blocker shifted to the stage1 ChatGPT submit/capture hang after submit_start, so continuation should begin from that boundary rather than reopening older blockers.


CANVA EXACT SEQUENCE RULE
-------------------------
- Do NOT click the left Tools icon as a discovery shortcut. The user explicitly rejected that path.
- Use the exact user-provided order only when reproducing the Canva Product Background path:
  1. click the blank area on page 2 (`div.fbzKiw`),
  2. click `편집 중`,
  3. click `편집`,
  4. click the `배경 생성` control/card the user pointed out,
  5. fill the visible `textarea.bCVoGQ` prompt input,
  6. click the exact visible `생성` button.
- If the current live Canva state does NOT expose that same sequence/UI, record that the live state differs from the user screenshot instead of inventing alternate paths.
- For Canva, prefer exact reproduction of the user-provided DOM path over exploratory selector hunting.

CANVA CURRENT TRUTH (2026-04-20)
---------------------------------
- Source of truth for current Canva debugging is the user-provided DOM path plus live DOM verification.
- Do NOT click the left Tools icon as an exploratory shortcut.
- Exact sequence to reproduce the intended Canva state:
  1. ensure page 2 is selected,
  2. click blank area on page 2 (`div.fbzKiw`),
  3. click exact toolbar/menu button `편집`,
  4. click the `배경 생성` card/button the user identified,
  5. when visible, use `textarea.bCVoGQ` (placeholder like `예: 열대 섬의 일몰, 수채화 스타일`),
  6. click the exact visible `생성` button.
- Fresh live DOM verification showed a critical state dependency: if page 2 is not selected first, the expected edit/background-generate flow does not appear correctly.
- Fresh live evidence also showed that the exact visible `편집` button can appear directly after page-2 blank click; do not assume the intermediate `편집 중 -> 수정` menu path unless the live DOM actually presents that state.
- Current truthful Canva blocker after repeated live reruns remains `CANVA_PRODUCT_BACKGROUND_NO_PROMPT_INPUT`.
- Recent disproven paths (do NOT re-try without new evidence):
  - iframe-only path as primary flow,
  - generic top-level prompt-first path,
  - force-click only for canvas entry,
  - JS click only for canvas entry,
  - panelVisible wait alone,
  - prompt click/focus alone,
  - prompt-free generate path,
  - direct exact-sequence patch attempts that were not syntax-safe.
- Required rule: if a Canva attempt is not preserved in docs, it should be treated as undone and not relied on in later debugging.

PENDING TASKS
-------------
- Re-read `probe 25` genspark ref-1 workspace and determine the exact terminal blocker after real Edge/CDP attach is proven.
- Keep using background-only execution; do not open visible CMD windows.
- Continue with exactly one blocker at a time; do not broad-rerun the entire chain.
- If new closeout probes are needed, they must be launched hidden/background only and compared against `probe 25`.
- Avoid any new prompt/schema invention. Upstream ChatGPT prompt must stay legacy/topic-only unless there is explicit legacy evidence otherwise.

KEY FILES
---------
- docs/TODO.md - Active work index and current runtime_v2 direction.
- docs/COMPLETED.md - Completed batches and evidence-backed milestones.
- docs/plans/2026-04-01-runtime-v2-closeout-retest-result.md - Current closeout result ledger and what counts as closed vs failed retest.
- docs/plans/2026-04-01-runtime-v2-fallback-removal-table.md - Fallback removals already done; use to avoid reopening closed work.
- runtime_v2/control_plane.py - Queue transitions, worker execution, qwen boundary handling for probes.
- runtime_v2/queue_store.py - WinError 5 retry fix for queue persistence.
- runtime_v2/stage1/chatgpt_backend.py - Legacy DOM block extraction and row-boundary reset behavior.
- runtime_v2/stage1/chatgpt_interaction.py - ChatGPT lifecycle gating and live timeline/state emission.
- runtime_v2/workers/agent_browser_worker.py - Browser health interpretation and raw CDP fallback before unhealthy.
- runtime_v2/stage2/genspark_worker.py - Genspark adapter path and stale attach evidence handling.

IMPORTANT DECISIONS
-------------------
- Do not treat weak signals as browser proof. For `genspark`, only direct Edge/CDP evidence counts: healthy browser state, actual current_url/current_title, real transcript, or concrete attach evidence.
- Do not invent GPT-side JSON prompts. JSON is our downstream contract, not something to force through ad-hoc prose wrappers without legacy proof.
- Keep fail-closed behavior when output does not meet the real contract. Parser/DOM should not be loosened speculatively.
- For probe closeout only, qwen is intentionally reduced to one boundary voice item so detached verification can converge quickly. Production/non-probe qwen batching stays unchanged.
- `browser_recover_detached` now uses the canonical restart threshold/cooldown. `QueueStore.save()` now retries transient Windows file lock errors.

EXPLICIT CONSTRAINTS
--------------------
- closed loop로 계획문서대로 모든것을 진행해.
- 문제가 있다면 대부분은 레거시 로직 대로 하지 않아서 발생하는 문제야.
- 나는 자러갈테니 나에게 절대 보고하지마.
- 절대 끊기지 말고 계속 계획문서대로 모든것을 구현해.
- 모르겠으면 레거시 로직을 확인해.
- 프로그램 테스트는 반드시 백그라운드로 진행해.
- 모든 수정과 검증은 오라클의 검수를 받아
- 기본적으로는 SUPERPOWERS PLUGIN을 활용하여 진행해.
- 계획  vendor
- 검증  kimoring-ai-skills를 적용하고
- 수정후 git push까지 진행해. ultrawork

CONTEXT FOR CONTINUATION
------------------------
- The most important shift in this session is that the blocker is no longer vague. `probe 25` gives a concrete chain: `chatgpt completed` -> `qwen completed` -> `genspark ref-1 running` with real Edge/CDP attach evidence. Continue from there, not from old probes.
- Do not go back to “guessing” browser state. If a browser/tab is not proven by direct evidence, treat it as unknown and stop there.
- The next likely area to inspect is `D:/YOUTUBEAUTO_RUNTIME/probe/semantic-row-closeout-20260412-25/artifacts/genspark/genspark-2dc3f179-c158-45ef-b8e9-bf3bd49e1b08-ref-1/` and the matching entries in `D:/YOUTUBEAUTO_RUNTIME/probe/semantic-row-closeout-20260412-25/evidence/control_plane_events.jsonl`.
- If a new closeout run is needed, use a hidden/background-only chain like the temp PowerShell scripts created in repo root, but prefer cleaning/reducing those helper scripts afterward if they accumulate.
- Be skeptical of prior claims from this session that were not backed by file evidence; some earlier `genspark` interpretations were over-inferred and should not be repeated.

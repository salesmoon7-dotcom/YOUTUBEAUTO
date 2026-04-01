# Runtime V2 Direction Audit Report

## Purpose

This report evaluates whether the current development direction is technically sound, how it differs from the legacy workflow, whether it respects the plan's core principles, and what correction is required.

## Current Judgment

The current direction is not technically sound enough to continue unchanged.

The main issue is no longer a single service bug. The runtime has accumulated too many shared states and rerun surfaces, so blockers keep moving between `ChatGPT`, `qwen3_tts`, `Genspark`, and `SeaArt` across repeated closeout attempts.

That means the system is currently in what is best described as a **structural-block diagnosis** state, not a normal "fix one bug and continue" state.

This is based on strong operational evidence, not on a fully exhaustive proof of one single root cause. External service instability, environment drift, quota/rate-limit effects, and state leakage may still be contributing factors.

## Main Problems

### 1. Debugging has not become more efficient

- Repeated reruns were used as a discovery tool instead of proving one boundary and moving on.
- The same class of issues resurfaced under different names (`BROWSER_UNHEALTHY`, `CHATGPT_CONTEXT_RESET_FAILED`, `CHATGPT_BACKEND_UNAVAILABLE`, `ADAPTER_TIMEOUT`, `ADAPTER_NONZERO_EXIT`).
- New evidence was produced, but the system was not simplified as evidence accumulated.

### 2. The pipeline has not become simpler

- Shared browser/session state remained active across many runs.
- Long-running workers (`qwen3_tts`) were allowed to stay `running` for long periods before surfacing a clear outcome.
- Closeout runs became a mixed debugging surface for multiple services at once.

### 3. Fresh closeouts stopped being meaningful integration checks

- A true closeout should validate a mostly stable system.
- Here, repeated closeouts continued to surface new blockers in different services.
- That means the closeout loop itself became part of the debugging complexity.

## Legacy vs Current

### Where legacy was better

- Legacy recovery was blunt but simple: restart the browser, select the current page/tab explicitly, and run the minimal action.
- It relied less on shared cross-service state.
- Failure surfaces were smaller and easier to reason about.

### Where current runtime is better

- Current runtime records more evidence: manifests, result files, attach evidence, fail-close codes, queue state, and probe artifacts.
- `stage1`/handoff/video-plan generation is now more explicit and auditable than legacy.
- `qwen` line-by-line execution and fail-close signaling are stronger than the original batch-style path.

### Where current runtime became worse

- Better evidence did not translate into simpler recovery.
- More state surfaces (locks, queues, shared browsers, health files, long-lived workers) created more ways to drift.
- Recovery logic became more layered than legacy without stabilizing the base runtime.

## Plan Compliance Audit

### Principle 1: "Is debugging efficient?"

No.

The runtime repeatedly required long waits and broad reruns to discover what failed next. That is the opposite of efficient debugging.

### Principle 2: "Is the pipeline simple?"

No.

The runtime currently depends on too many moving pieces at once: shared browser state, queue state, worker registry, browser plane lock, multiple long-running services, and repeated reruns.

### Gate compliance summary

- `single-blocker-first`: violated repeatedly
- `broad rerun avoidance`: violated repeatedly
- `fresh service proof before closeout`: only partially respected
- `runtime simplification before more retries`: not respected early enough

## Evidence-Based Direction Assessment

The user's criticism is substantially correct.

For a macro-like browser automation system, this amount of elapsed time should have yielded a small, stable, reproducible workflow. Instead, the project produced an increasingly complex runtime that still cannot guarantee one reliable closeout path.

That does not mean every code change was wrong. Some recent fixes were real progress:

- stage1 can now produce `parsed_payload.json`, `stage1_handoff.json`, and `video_plan.json`
- qwen line-by-line execution is more observable
- service-specific fail-close evidence exists
- Genspark/SeaArt recovery hooks improved some attach cases

But the overall direction still failed the higher bar: **the runtime did not converge toward a stable, simple system**.

## What Must Change

1. Stop using full closeout reruns as a diagnostic surface while blocker identity is unstable.
2. Treat shared browser/session reuse as suspect by default.
3. Require every service proof to succeed or fail-close within a short bounded window.
4. Reduce runtime state before adding more retries/fallbacks.
5. Re-earn the right to run a full row15 closeout only after a stable single-blocker regime is restored.

## Final Assessment

The current development direction should not continue unchanged.

The most technically honest path forward is a **runtime simplification reset** as an engineering/operational decision, not because a single-root-cause proof is already complete, but because the observed blocker churn and shared-state coupling make continued broad closeout reruns low-value and misleading.

- fewer shared states,
- fewer broad reruns,
- smaller isolated proofs,
- deterministic service recovery,
- and only then one fresh row15 closeout.

Until that reset is done, additional closeout reruns are more likely to create new blocker snapshots than to produce a trustworthy completion signal, and any rerun evidence should be treated as provisional rather than conclusive.

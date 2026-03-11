# Runtime V2 Manager GUI Stage5 Console Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `runtime_v2_manager_gui.py`를 Stage 5/5B 수동 운영 절차에 맞는 GUI로 단순화해, 준비된 Excel 행 1개를 seed하고 `control_once`를 한 단계씩 실행하며 최신 증거를 바로 확인할 수 있게 합니다.

**Architecture:** 기존 장시간 loop 중심 GUI를 유지 보조 기능으로 내리고, 전면 UI는 `health -> excel seed -> control once -> evidence review` 순서의 수동 콘솔로 재배치합니다. 실행은 셸 명령이 아니라 이미 존재하는 `seed_excel_row(...)`, `run_control_loop_once(...)`, readiness/evidence 파일 읽기 경로를 직접 호출해 run 의미와 latest evidence 계약을 그대로 유지합니다. 추가로 `RuntimeConfig.from_root(...)`를 통한 `runtime root` 선택을 넣어, GUI가 현재 저장소 기본 경로뿐 아니라 사용자가 지정한 로컬 프로그램 런타임 루트에도 연결되도록 합니다.

**Tech Stack:** Python 3.13, Tkinter, `runtime_v2_manager_gui.py`, `runtime_v2/cli.py`, `runtime_v2/manager.py`, JSON evidence snapshots, `unittest`, `py_compile`

---

### Task 1: Lock the manual Stage 5 operator contract in tests/helpers

**Files:**
- Modify: `runtime_v2_manager_gui.py`
- Modify: `tests/test_runtime_v2_manager_gui.py`

**Step 1: Add pure helper functions for GUI summaries**

Add helper functions that do not require a Tk root and can be tested directly:
- readiness summary from browser/gpt/gui/result snapshots
- seed summary for `excel_path`, `sheet_name`, `row_index`, `row_ref`, `job_id`
- terminal evidence summary for `run_id`, `final_output`, `final_artifact_path`, `failure_summary.json`

**Step 2: Write failing tests for the helper contract**

Add tests that prove:
- browser/GPT stop conditions surface as operator warnings
- final output vs failure summary is summarized without ambiguity
- `run_id` text is preserved in the evidence summary

**Step 3: Run targeted tests**

Run: `python -m unittest tests.test_runtime_v2_manager_gui -v`
Expected: PASS

### Task 2: Rebuild the top GUI flow around manual seed/control execution

**Files:**
- Modify: `runtime_v2_manager_gui.py`

**Step 1: Replace the control section layout**

Promote these fields/buttons to the top of the window:
- Runtime root
- Excel path
- Sheet name
- Row index
- `Health Refresh`
- `Excel Seed 1-Row`
- `Control Once`
- `Open Login Browser`

Keep long-running loop controls as secondary/advanced controls only.

**Step 2: Wire direct internal calls**

Use direct Python calls instead of shell commands:
- Excel seed -> `seed_excel_row(...)`
- Control once -> `run_control_loop_once(...)`
- Login browser -> `open_browser_for_login(...)`

**Step 3: Persist manual-operation settings**

Save and reload `runtime_root`, `excel_path`, `sheet_name`, `row_index`, selected browser service, and existing workload-related fields.

### Task 3: Make health/evidence panels match the operator workflow

**Files:**
- Modify: `runtime_v2_manager_gui.py`

**Step 1: Add a preflight/status panel**

Show at a glance:
- browser health summary for `chatgpt/genspark/seaart/geminigen/canva`
- GPT floor `OK >= 1`
- queue count
- latest `run_id`

**Step 2: Add an operator evidence panel**

Show concise terminal interpretation:
- `final_output=true` and final artifact path when success is closed
- `failure_summary.json` path when failure is closed
- warning when neither exists yet

**Step 3: Keep existing detailed logs/queue/programs below**

Reuse the current detailed panels as secondary diagnostics, not the primary operator flow.

### Task 4: Verification

**Files:**
- Verify: `runtime_v2_manager_gui.py`
- Verify: `tests/test_runtime_v2_manager_gui.py`

**Step 1: Run diagnostics**

Run `lsp_diagnostics` on modified files and require zero errors.

**Step 2: Run targeted tests**

Run: `python -m unittest tests.test_runtime_v2_manager_gui -v`

**Step 3: Run compile verification**

Run: `python -m py_compile runtime_v2_manager_gui.py`

**Step 4: Run project verification skills**

Run verification bundle before completion:
- `verify-backup-first`
- `verify-code-quality`
- `verify-debug-convention`
- `verify-single-change`
- `verify-implementation`

# HANDOFF: runtime_v2 Phase1 -> Phase2

## 1) Session Entry Point

- Workdir: `D:/YOUTUBEAUTO`
- Git baseline commands (must run first):
  - `git branch --show-current`
  - `git rev-parse HEAD`
  - `git status --porcelain=v1`
  - `git log -1 --oneline`
- Start command sequence:
  1. `python -c "from pathlib import Path; import py_compile; [py_compile.compile(str(p), doraise=True) for p in Path('runtime_v2').rglob('*.py')]"`
  2. `python -m runtime_v2.cli --once`
  3. `python -m runtime_v2.cli --selftest`
  4. `python -m runtime_v2.cli --once --callback-url "https://n8n.example/webhook" --callback-mock-out "system/runtime_v2/evidence/callback.json"`

## 2) Current Baseline (Done)

- `--once` / `--selftest` implemented in `runtime_v2/cli.py`
- Deterministic exit code constants in `runtime_v2/exit_codes.py`
- GPU lease contention + release + browser fail + GPT floor fail selftest checks in `runtime_v2/supervisor.py`
- Local GUI payload contract in `runtime_v2/gui_adapter.py`
- Remote n8n callback contract + mock writer in `runtime_v2/n8n_adapter.py`
- JSON event/final report helpers in `runtime_v2/contracts/json_contract.py`

## 3) Commit Baseline

- `1515a2a` docs: pin gui/n8n payload fields and shell-safe compile gate
- `524a766` feat: implement once/selftest flow with deterministic JSON exits
- `bf31264` chore: remove pycache artifacts and add python ignore rules
- `af4315f` feat: add runtime_v2 phase1 supervisor skeleton with gui and n8n adapters
- `43dbab5` docs: bootstrap governance and phase1 execution docs

## 3-1) Current Runtime Split

- Local execution: GUI payload consumer (`execution_env=local_gui`)
- Remote execution: n8n orchestrator callback producer (`execution_env=remote_n8n`)
- Source of truth: runtime final JSON (`run_finished`) + exit code mapping

## 4) Explicit Contracts (Must Preserve)

- GUI is local execution surface: `execution_env=local_gui`
- n8n is remote orchestration surface: `execution_env=remote_n8n`
- GUI payload required keys:
  - `schema_version`, `execution_env`, `runtime`, `run_id`, `mode`, `stage`, `exit_code`, `status`
- n8n callback payload required keys:
  - `schema_version`, `execution_env`, `callback_url`, `ok`, `runtime`, `run_id`, `mode`, `exit_code`, `status`

## 5) Remaining Gaps (Next Session Primary Work)

1. Replace mock callback file write with real HTTP POST path (retry/backoff, timeout, failure mapping to `CALLBACK_FAIL`).
2. Add atomic GUI status file writer (temp file -> rename) for dashboard reader stability.
3. Add persistent lease metadata (`run_id`, `pid`, `started_at`, `host`) and stale lease recovery policy.
4. Add CLI option for forced fault injection flags only in selftest mode.
5. Add tests for exit-code mapping and callback payload schema validation.

## 6) Acceptance Criteria for Phase2 Start

- Real callback mode: timeout/retry behavior deterministic and logged as JSON.
- GUI status file is always valid JSON during updates.
- `--selftest` still validates:
  - lease contention path
  - lease release path
  - browser failure path
  - GPT floor failure path
- No `__pycache__`/`.pyc` tracked by git.

## 6-1) Deterministic Exit Code Gate

- `SUCCESS=0`, `CLI_USAGE=2`, `LEASE_BUSY=10`, `BROWSER_UNHEALTHY=20`, `GPT_FLOOR_FAIL=30`, `SELFTEST_FAIL=40`, `CALLBACK_FAIL=60`
- Final report must include both `status` and `exit_code` keys.

## 7) Risks and Guardrails

- Risk: callback failure conflated with runtime failure.
  - Guardrail: keep `status` and `exit_code` separated in final report.
- Risk: stale lease blocks subsequent run.
  - Guardrail: owner metadata + explicit release on all exits.
- Risk: GUI parser breaks on partial write.
  - Guardrail: atomic write protocol.

## 8) Plan/Vendor References

- Plan file: `docs/plans/2026-03-06-phase1-bootstrap-execution.md`
- Vendor checkpoint mirror: `.sisyphus/plans/2026-03-06-phase1-bootstrap-execution.md`

## 9) NEXT (copy/paste)

```bash
cd /d D:/YOUTUBEAUTO
git branch --show-current
git rev-parse HEAD
python -c "from pathlib import Path; import py_compile; [py_compile.compile(str(p), doraise=True) for p in Path('runtime_v2').rglob('*.py')]"
python -m runtime_v2.cli --selftest
python -m runtime_v2.cli --once --callback-url "https://n8n.example/webhook" --callback-mock-out "system/runtime_v2/evidence/callback.json"
```

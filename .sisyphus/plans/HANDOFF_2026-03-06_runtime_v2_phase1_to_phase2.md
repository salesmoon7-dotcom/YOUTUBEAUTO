# HANDOFF: runtime_v2 Phase1 -> Phase2

- Workdir: `D:/YOUTUBEAUTO`
- Entry: run `py_compile`, `--once`, `--selftest`, callback-mock command in this order.
- Git baseline: `git branch --show-current`, `git rev-parse HEAD`, `git status --porcelain=v1`, `git log -1 --oneline`
- Baseline commits: `1515a2a`, `524a766`, `bf31264`, `af4315f`, `43dbab5`.
- Contracts:
  - local GUI payload includes `schema_version, execution_env, runtime, run_id, mode, stage, exit_code, status`
  - remote n8n callback includes `schema_version, execution_env, callback_url, ok, runtime, run_id, mode, exit_code, status`
- Next priorities:
  1. real HTTP callback implementation with retry/backoff
  2. atomic GUI status file writing
  3. persistent lease metadata and stale recovery
  4. exit-code and payload schema tests
- Deterministic gate: final report must include both `status` and `exit_code`

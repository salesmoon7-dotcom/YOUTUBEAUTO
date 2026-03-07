# COMPLETED

- `docs/plans/2026-03-06-separate-24h-runtime-rebuild-plan.md` - runtime_v2 code and GUI implementation aligned to `system/runtime_v2/` paths
- `runtime_v2/control_plane.py`, `runtime_v2/supervisor.py`, `runtime_v2/cli.py` - isolated explicit mock chain execution and probe seed helper implemented
- `runtime_v2/contracts/job_contract.py` - explicit inbox job contract constants and builder centralized
- `runtime_v2/browser/manager.py` - browser launch now normalizes `--user-data-dir` to an absolute path so runtime_v2 fixed ports open reliably in detached selftest
- `runtime_v2/supervisor.py`, `runtime_v2/gpu/lease.py` - selftest lease flow stabilized by removing immediate post-acquire renew and preventing current-process leases from being treated as stale
- `system/runtime_v2_probe/selftest-run-06/` - detached selftest completed with `code=OK`, `exit_code=0`, and `browser_health.json` healthy_count=4
- `runtime_v2/browser/health.py`, `runtime_v2/browser/registry.py`, `runtime_v2/browser/supervisor.py`, `runtime_v2/control_plane.py`, `runtime_v2/cli.py`, `runtime_v2/gui_adapter.py`, `runtime_v2_manager_gui.py` - detached smoke/latest-run evidence now shares run metadata (`run_id`, `checked_at`, `debug_log`, status/code fields) more consistently across `probe_result.json`, `result.json`, `gui_status.json`, and browser snapshots
- `system/runtime_v2_probe/selftest-run-07/` - detached selftest evidence now aligns `probe_result.json`, `evidence/result.json`, and `health/browser_health.json` on the same UUID run
- `system/runtime_v2_probe/control-idle-run-01/`, `system/runtime_v2_probe/mock-chain-run-05/` - detached control smoke evidence confirms run-id aligned idle/latest-run snapshots and absolute browser profile paths under probe roots
- `docs/sop/SOP_runtime_v2_detached_soak_readiness.md` - detached smoke evidence를 soak/실운영 준비 체크리스트로 분리
- `runtime_v2_manager_gui.py` - Result 패널에서 `유휴`와 `최종완료`를 분리해 latest-run idle 상태와 final artifact 완료 상태를 더 직관적으로 표시

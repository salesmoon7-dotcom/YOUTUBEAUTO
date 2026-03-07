# Docs Index

## Single Classification Rule
- 문서 상태 분류는 `TODO` 또는 `COMPLETE` 두 가지로만 관리합니다.
- 분류 진입점은 아래 두 문서만 사용합니다.
  - `TODO.md`
  - `COMPLETED.md`

## Active Status Docs
- `TODO.md` - 현재 진행 중이거나 운영 검증이 남은 작업 목록
- `COMPLETED.md` - 코드 구현이 끝난 작업 목록

## Reference Directories (Structure Only)
- `plans/`
- `sop/`
- `archive/`

## Operations Priority SOP
- `sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- `sop/SOP_runtime_v2_inbox_contract.md`
- `sop/SOP_runtime_v2_detached_soak_readiness.md`

## Current Runtime_v2 Canonical References
- `plans/2026-03-06-separate-24h-runtime-rebuild-plan.md`
- `sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- `sop/SOP_runtime_v2_inbox_contract.md`
- `sop/SOP_runtime_v2_detached_soak_readiness.md`
- `system/runtime_v2/health/gui_status.json` - control-loop latest-run GUI snapshot
- `system/runtime_v2/evidence/result.json` - latest-run result snapshot
- `system/runtime_v2/evidence/control_plane_events.jsonl` - control-plane transition evidence

위 디렉터리는 저장 위치일 뿐이며, 상태 분류 기준은 `TODO.md` / `COMPLETED.md`의 링크 상태를 따릅니다.

# Runtime V2 Runtime Verification Checklist

> **For Claude:** Use this as an operator checklist, not an implementation plan.

**Goal:** `runtime_v2`의 현재 production 체인을 실제 evidence 파일과 `run_id` 기준으로 검증할 때, 무엇을 어떤 순서로 확인해야 하는지 고정합니다.

**Scope:** `stage1 -> stage2 auto-queue`, `qwen3_tts -> rvc`, `GeminiGen -> render`, `KenBurns resident/inbox`

---

## 1. Run ID Rules

- **체인 키 run_id**: 각 job `payload.run_id`
- **실행 키 run_id**: latest snapshots (`system/runtime_v2/evidence/result.json`, `system/runtime_v2/health/gui_status.json`)의 `run_id`
- 검증 시 두 종류를 섞지 않습니다.

## 2. Evidence File Map

- `system/runtime_v2/evidence/result.json`
- `system/runtime_v2/health/gui_status.json`
- `system/runtime_v2/evidence/control_plane_events.jsonl`
- `system/runtime_v2/state/job_queue.json`
- `system/runtime_v2/state/feeder_state.json`
- `system/runtime_v2/logs/<run_id>.jsonl` (`result.json.metadata.debug_log` 기준)
- resident inbox chain 확인용:
  - `system/runtime_v2/inbox/qwen3_tts/`
  - `system/runtime_v2/inbox/kenburns/`
  - `system/runtime_v2/inbox/rvc/source/`
  - `system/runtime_v2/inbox/rvc/audio/`

## 3. Global PASS Rule

- `result.json.metadata.run_id == gui_status.json.run_id`
- `control_plane_events.jsonl`에 같은 `run_id`의 `job_summary`가 존재
- 세 파일 중 하나라도 latest 의미가 다르면 FAIL

## 4. Chain A: stage1 -> stage2 auto-queue

### PASS evidence
- `job_queue.json`에서 stage1(chatgpt) 완료 후 `genspark`, `seaart`, `geminigen`, `canva`, `render` job이 생성됨
- child jobs가 같은 `payload.run_id`, `payload.row_ref`를 공유함
- `control_plane_events.jsonl`에서 child jobs가 `queued`로 기록됨

### FAIL signs
- stage1 결과는 OK인데 child jobs가 하나도 없음
- `run_id` / `row_ref`가 child jobs에서 끊김

## 5. Chain B: qwen3_tts -> rvc

### PASS evidence
- `qwen3_tts` worker result의 `next_jobs`에 `rvc` 1개 존재
- `control_plane_events.jsonl`에서 `rvc-*` job이 `routed_from=<qwen3 job_id>`로 `queued`
- `job_queue.json`에 `rvc` job payload의 `source_path`, `model_name`, `service_artifact_path`가 존재

### FAIL signs
- `qwen3_tts` 성공인데 `next_jobs=[]`
- `rvc` job이 생겼지만 필수 payload가 없음

## 6. Chain C: GeminiGen -> render

### PASS evidence
- `geminigen` payload/request에 `first_frame_path`가 존재
- `geminigen` job의 `service_artifact_path`가 실제 video artifact로 이어짐
- `render` job은 stage1 성공 시 자동 queue되고, 최종 PASS는 `result.json.metadata.final_output=true` + `final_artifact_path` 존재로만 판정

### FAIL signs
- `GeminiGen` request에 `first_frame_path`가 없음
- `render` latest evidence가 있지만 upstream artifact 경로가 비어 있음

## 7. Chain D: KenBurns resident/inbox

### Expected behavior
- `KenBurns`는 자동 downstream chain이 아닙니다
- `input_root/kenburns`에 이미지가 들어오면 resident/inbox GPU workload로 queue됩니다
- `audio_path`가 필요하면 explicit local-only contract로 같이 줍니다

### PASS evidence
- `job_queue.json` 또는 feeder path에서 `workload=kenburns`가 inbox image 기준으로 생성됨
- `stage1/stage2` auto-queue 결과에는 `kenburns`가 포함되지 않음

### FAIL signs
- stage1 child jobs에 `kenburns`가 자동 생성됨
- inbox image가 있어도 `kenburns` job이 생성되지 않음

## 8. Execution Safety

- GPU workloads는 동시에 여러 개를 쏘지 말고 순차로 확인합니다
- broad search 대신 위 evidence 파일만 직접 읽습니다
- Chat session에서는 file-level foreground pytest 대신 chain별 targeted unittest 또는 detached/manual runtime evidence를 사용합니다

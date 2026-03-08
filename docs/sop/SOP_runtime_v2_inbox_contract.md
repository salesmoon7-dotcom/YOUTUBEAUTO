# SOP: runtime_v2 Inbox Contract

> 버전: 1.0
> 상태: Active
> 적용 범위: `system/runtime_v2/inbox/`

## 1. 목적

- `runtime_v2`의 로컬 입력 계약을 고정합니다.
- feeder가 어떤 파일을 어떤 작업으로 시드하는지 결정 규칙을 명시합니다.
- 모든 입력은 현재 작업 폴더(`D:\YOUTUBEAUTO`) 내부 경로만 허용합니다.

## 2. 루트 경로

- 입력 루트: `system/runtime_v2/inbox/`
- 허용 하위 경로:
  - `system/runtime_v2/inbox/qwen3_tts/`
  - `system/runtime_v2/inbox/kenburns/`
  - `system/runtime_v2/inbox/rvc/source/`
  - `system/runtime_v2/inbox/rvc/audio/`

## 2-1. 명시적 계약 파일

- 명시적 job 계약은 `*.job.json` 파일만 대상으로 합니다.
- 우선순위는 `*.job.json` > 파일명 패턴 feeder 입니다.
- `*.job.json`은 허용 하위 경로 직속(`qwen3_tts/`, `kenburns/`, `rvc/source/`, `rvc/audio/`)에만 허용합니다.
- `*.job.json`은 다음 최상위 키만 사용합니다.
  - `contract`
  - `contract_version`
  - `local_only`
  - `job`
  - 선택: `chain`

### 명시적 계약 최소 규칙
- `contract = runtime_v2_inbox_job`
- `contract_version = 1.0`
- `local_only = true`
- `job.job_id` 필수
- `job.worker` 또는 `job.workload` 필수 (`qwen3_tts`, `rvc`, `kenburns`만 허용)
- 크기 제한: 256KB 이하
- 처리 결과: 수락 파일은 `system/runtime_v2/inbox/accepted/`, 거절 파일은 `system/runtime_v2/inbox/invalid/`로 이동합니다.
- 거절 파일은 같은 이름의 `*.reason.json` sidecar에 `code`/`message`를 기록합니다.
- `gui_status.json.status.invalid_reason` 및 `result.json.metadata.invalid_reason`은 위 `*.reason.json`의 최신 요약값(`code[:message]`)을 사용합니다.
- 충돌 아카이브도 `.job.json` suffix를 유지합니다.

### `job` 블록 규칙
- 허용 키:
  - `job_id`
  - `worker` 또는 `workload`
  - 선택: `checkpoint_key`
  - 선택: `payload`
  - 선택: `args`
  - 선택: `inputs`
- `inputs`는 `{ "name": "source_path", "path": "..." }` 형식 목록만 허용합니다.
- `payload`/`args`/`inputs`는 모두 최종 payload로 병합됩니다.
- `payload.mock_chain=true`는 실제 워커 대신 control plane 내부 mock chain 합성 경로를 사용한다는 뜻입니다.
- `mock_chain` 경로도 같은 local path 규칙과 `runtime_v2_inbox_job` 계약을 그대로 사용합니다.

### `chain` 블록 규칙
- 선택 키:
  - `step`
  - `chain_depth`
  - `parent_job_id`
- feeder는 `step` 또는 `chain_depth`를 `payload.chain_depth`로 반영합니다.
- `parent_job_id`는 `payload.routed_from`으로 반영합니다.

## 3. 작업별 입력 규칙

### 3.1 `qwen3_tts`
- 입력 파일: `*.txt`
- 시드 규칙: 텍스트 파일 1개 = 작업 1개
- payload:
  - `script_text`
  - 선택: 같은 stem의 이미지가 `system/runtime_v2/inbox/kenburns/`에 있으면 `image_path`

### 3.2 `kenburns`
- 입력 파일: `*.png`, `*.jpg`, `*.jpeg`, `*.webp`
- 시드 규칙: 이미지 파일 1개 = 작업 1개
- payload:
  - `source_path`
  - 기본 `duration_sec=8`

### 3.3 `rvc`
- 입력 파일: `system/runtime_v2/inbox/rvc/source/` 아래 `*.wav`, `*.mp3`, `*.flac`, `*.mp4`, `*.mov`, `*.mkv`, `*.avi`
- 선택 입력: 같은 stem의 오디오가 `system/runtime_v2/inbox/rvc/audio/`에 있으면 `audio_path`
- payload:
  - `source_path`
  - 선택: `audio_path`

## 4. 안정화 규칙

- feeder는 수정 시각이 3초 이상 지난 파일만 입력으로 인정합니다.
- `checkpoint_key` 기준으로 이미 시드된 입력은 다시 시드하지 않습니다.
- feeder 상태는 `system/runtime_v2/state/feeder_state.json`에 기록합니다.

## 5. 로컬 전용 규칙

- URL 스킴(`http://`, `https://`, `file://` 등) 금지
- 정규화 후 작업 루트 밖으로 벗어나는 경로 금지
- 외부 참고 폴더/외부 저장소 직접 참조 금지
- `source_path`, `audio_path`, `image_path`는 모두 위 규칙을 통과해야 합니다.

## 6. 체인 계약

- 워커 성공 결과는 워커 결과 계약의 `next_jobs[]`로만 후속 작업을 선언합니다.
- control plane은 인라인 `worker_result.next_jobs[]` 또는 `worker_result.result_path`가 가리키는 워커 결과 JSON을 읽어 후속 작업을 해석합니다.
- 위 `next_jobs[]` 엔트리는 `runtime_v2_inbox_job`와 동일한 최상위 계약 형태를 요구합니다.
- 각 후속 작업 payload는 다음 메타데이터를 가질 수 있습니다.
  - `chain_depth`
  - `routed_from`
- 현재 기본 체인:
  - `qwen3_tts -> rvc`
  - `qwen3_tts(image 포함) -> rvc(image_path 전달) -> kenburns(audio 포함)`
- mock chain 경로에서는 위 기본 체인을 실제 워커 대신 synthetic artifact/next_jobs/result_path로 재현합니다.

## 7. 증거 파일

- `system/runtime_v2/state/job_queue.json`
- `system/runtime_v2/state/feeder_state.json`
- `system/runtime_v2/evidence/control_plane_events.jsonl`
- `system/runtime_v2/health/gui_status.json`
- `system/runtime_v2/evidence/result.json` (`latest-run snapshot`)
- 워커가 내부적으로 참조하는 개별 결과 JSON과 `system/runtime_v2/evidence/result.json`은 같은 이름이지만 용도가 다릅니다.

## 8. Probe Seed Helper

- `python -m runtime_v2.cli --control-once --seed-mock-chain`
- `python -m runtime_v2.cli --control-once-detached --seed-mock-chain --probe-root "system/runtime_v2_probe/<name>"`
- 위 helper는 `inbox/qwen3_tts/mock-chain.job.json`과 `inbox/kenburns/mock-chain.png`를 생성해 explicit mock chain을 바로 시드합니다.

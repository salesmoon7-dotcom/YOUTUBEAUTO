# SOP: 24h Runtime Stability and GPU Gates

> 버전: 1.0
> 상태: Active
> 적용 범위: 신규 분리 런타임(브라우저/GPU/GPT 풀)

## 0. 경로/리소스 분리 원칙

- 신규 런타임은 `runtime_v2/`, `system/runtime_v2/`만 사용합니다.
- 외부 참고 런타임 경로(`runtime/`, `system/runtime/`)에는 쓰기 금지입니다.
- 브라우저 세션/포트/락 파일은 runtime_v2 네임스페이스로 분리합니다.

## 1. 목적

- 브라우저를 24시간 상시 가동 상태로 유지합니다.
- GPU 작업(QWEN3/RVC/KenBurns) 중복 실행을 방지합니다.
- GPT STATUS floor(`OK >= 1`)를 자동복구로 보장합니다.

## 2. 운영 SLO

- Browser Availability: 24h 구간 가용성 99.5% 이상
- Recovery MTTR: 비정상 감지 후 120초 이내 복구
- GPU Duplicate Run: 0건
- GPT Floor Breach: 2분 초과 지속 0건

## 3. 필수 정책

### 3.1 Browser Always-On
- 정상 브라우저는 재기동하지 않습니다.
- 헬스 실패 인스턴스만 선택적으로 교체합니다.
- 세션/포트 매핑은 registry 파일에서 단일 관리합니다.
- browser profile lock은 영구 소유권 파일이 아니라 `launch-attempt lease/TTL`로 취급합니다.
- one-shot/프로세스 교체 운영에서도 lock 해제가 `shutdown()`에만 종속되지 않도록, lease 만료 또는 명시적 회수 경로가 있어야 합니다.
- browser profile lock은 `busy`와 `stale`를 구분해야 합니다.
- stale browser profile lock은 `owner pid 부재 + 포트 닫힘`이면 stale 후보로 보며, age는 추가 안전장치로만 사용합니다. age 초과만으로 자동 해제하면 안 됩니다.
- supervisor는 stale lock 자동 복구를 사용할 수 있어야 하며, busy lock에는 중복 launch를 시도하지 않습니다.
- stale lock 복구 시도/성공/실패는 health/evidence에 남겨야 합니다.
- lock 메타데이터 결손/파손은 `unknown`으로 분류하고 fail-closed 처리합니다.
- `busy lock`가 장시간 지속되면 운영 장애로 에스컬레이션합니다.
- one-shot control 프로세스가 반복되는 운영에서도 stale lock 자동 복구가 가능해야 합니다.

### 3.1.1 Browser Lock Evidence Contract
- primary event log는 `system/runtime_v2/evidence/control_plane_events.jsonl`를 사용합니다.
- 최소 필드: `service`, `profile_dir`, `lock_state`, `pid_alive`, `port_open`, `lock_age_sec`, `metadata_valid`, `action`, `action_result`, `error`, `run_id`, `tick_id`, `ts`
- `browser_health.json`은 latest summary, `control_plane_events.jsonl`은 상세 복구 이벤트 기준으로 해석합니다.

### 3.2 GPU 중복 실행 금지
- 작업군별 락 키를 사용합니다.
  - `lock:qwen3_tts`
  - `lock:rvc`
  - `lock:kenburns`
- 물리 락 파일은 Windows 경로 제약을 피하기 위해 `system/runtime_v2/locks/{workload}.lock`, `system/runtime_v2/locks/{workload}.lease.json`를 사용하고, 논리 락 키는 health payload의 `lock_key`에 기록합니다.
- `system/runtime_v2/health/gpu_scheduler_health.json`은 물리 락 파일 자체가 아니라 최신 GPU gate 이벤트 스냅샷(`event`, `workload`, `lock_key`, `lease`)을 기록합니다.
- 락 미획득 시 작업은 queue 재삽입 후 backoff 합니다.
- stale lock은 TTL 만료 + fencing token 검증 후 해제합니다.

### 3.3 GPT STATUS Floor 자동복구
- 즉시 규칙: `OK < 1` 발생 즉시 경고 이벤트 기록
- 자동기동 규칙: 2분 연속 부족 시 spawn 실행
- 보호장치: 5분 쿨다운, 시간당 최대 6회

## 4. JSON 계약

- 모든 산출물은 JSON에 정의된 폴더에만 저장해야 합니다.
- 저장 후 `system/runtime_v2/evidence/result.json` latest-run snapshot에 경로/해시/시각과 최신 run metadata를 기록해야 합니다.
- 경로 불일치 또는 누락 시 실패 처리합니다.
- 입력 계약은 `docs/sop/SOP_runtime_v2_inbox_contract.md`를 단일 기준으로 사용합니다.
- `gui_status.json`과 `result.json`은 idle/seeded/run/failure 전 구간에서 같은 run 의미로 함께 갱신돼야 합니다.
- `system/runtime_v2/evidence/result.json`은 항상 최신 1개를 덮어쓰는 runtime evidence snapshot이며, 체인 선언 용도가 아닙니다.

## 5. 점검 체크리스트

- detached smoke PASS 확인과 soak/실운영 진입 체크는 `docs/sop/SOP_runtime_v2_detached_soak_readiness.md`를 기준으로 수행합니다.
- 이 문서는 24h 운영 정책(SLO, 게이트, 장애 대응)만 단일 기준으로 유지합니다.

## 6. 장애 대응 순서

1. 경고 수신 후 헬스 스냅샷 파일 3종 수집
2. Browser/GPU/GPT 중 원인 축 분류
3. 자동복구 결과 확인(실패 시 수동 override)
4. 원인/조치/재발방지 항목을 운영 로그에 기록

## 7. 증거 파일

- `system/runtime_v2/health/browser_health.json`
- `system/runtime_v2/health/browser_session_registry.json`
- `system/runtime_v2/health/gpu_scheduler_health.json`
- `system/runtime_v2/health/gpt_status.json`
- `system/runtime_v2/health/gui_status.json`
- `system/runtime_v2/evidence/result.json`
- `system/runtime_v2/evidence/control_plane_events.jsonl`
- `system/runtime_v2/evidence/soak_24h_report.md`

## 8. 구현 상태

- `runtime_v2/` 코드 구현은 완료 상태로 운영합니다.
- 장시간 soak 실행과 운영 지표 수집은 별도 운영 절차로 수행합니다.

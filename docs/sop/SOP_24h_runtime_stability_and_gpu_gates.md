# SOP: 24h Runtime Stability and GPU Gates

> 버전: 1.0
> 상태: Active
> 적용 범위: 신규 분리 런타임(브라우저/GPU/GPT 풀)

## 0. 경로/리소스 분리 원칙

- 신규 런타임은 `runtime_v2/`, `system/runtime_v2/`만 사용합니다.
- 레거시 런타임 경로(`runtime/`, `system/runtime/`)에는 쓰기 금지입니다.
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

### 3.2 GPU 중복 실행 금지
- 작업군별 락 키를 사용합니다.
  - `lock:qwen3_tts`
  - `lock:rvc`
  - `lock:kenburns`
- 락 미획득 시 작업은 queue 재삽입 후 backoff 합니다.
- stale lock은 TTL 만료 + fencing token 검증 후 해제합니다.

### 3.3 GPT STATUS Floor 자동복구
- 즉시 규칙: `OK < 1` 발생 즉시 경고 이벤트 기록
- 자동기동 규칙: 2분 연속 부족 시 spawn 실행
- 보호장치: 5분 쿨다운, 시간당 최대 6회

## 4. JSON 계약

- 모든 산출물은 JSON에 정의된 폴더에만 저장해야 합니다.
- 저장 후 `result.json`에 경로/해시/시각을 기록해야 합니다.
- 경로 불일치 또는 누락 시 실패 처리합니다.

## 5. 점검 체크리스트

1. `browser_health.json`에서 down 인스턴스 수 확인
2. `gpu_scheduler_health.json`에서 lock 충돌/stale lock 확인
3. `gpt_status.json`에서 `ok_count`, `pending_boot` 확인
4. 최근 24h 이벤트에서 floor breach, duplicate run 여부 확인

## 6. 장애 대응 순서

1. 경고 수신 후 헬스 스냅샷 파일 3종 수집
2. Browser/GPU/GPT 중 원인 축 분류
3. 자동복구 결과 확인(실패 시 수동 override)
4. 원인/조치/재발방지 항목을 운영 로그에 기록

## 7. 증거 파일

- `system/runtime/health/browser_health.json`
- `system/runtime/health/gpu_scheduler_health.json`
- `system/runtime/health/gpt_status.json`
- `system/runtime/evidence/soak_24h_report.md`

위 파일은 신규 경로 기준으로 운영합니다:
- `system/runtime_v2/health/browser_health.json`
- `system/runtime_v2/health/gpu_scheduler_health.json`
- `system/runtime_v2/health/gpt_status.json`
- `system/runtime_v2/evidence/soak_24h_report.md`

# Separate 24h Runtime Rebuild Plan (Python Single Stack)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 기존 프로그램과 분리된 신규 런타임을 구축해 24시간 브라우저 상시 가동, GPU 작업 중복 방지, GPT STATUS floor 자동복구를 안정적으로 달성합니다.

**Architecture:** Python 단일 스택을 유지하되 프로세스 책임을 `Control/Browser/GPU/Artifact`로 분리합니다. 메인 파이프라인은 단순 상태머신으로 고정하고, JSON 계약을 단일 입출력 기준으로 사용합니다.

**Tech Stack:** Python 3.13, Playwright/CDP, psutil, file lock/lease, JSONL state log, ffmpeg, 기존 pipeline_common 규약

---

## 0) 확정 의사결정 (Locked Decisions)

1. 런타임 구조: **Python 단일 스택**
2. GPU 단일 실행 범위: **작업군별 단일 실행 락** (`qwen3_tts`, `rvc`, `kenburns`)
3. GPT 자동기동: **하이브리드** (`OK<1 즉시 점검` + `2분 지속 부족 시 spawn` + `5분 쿨다운` + `시간당 최대 6회`)
4. 브라우저 정책: **24시간 상시 가동 + 비정상만 재기동** (정상 세션 강제 재시작 금지)
5. 물리 경로 정책: **신규 폴더에서 시작** (기존 런타임과 파일/포트/세션 완전 분리)

## 0-1) 폴더/리소스 분리 정책 (충돌 방지)

- 신규 런타임 루트: `runtime_v2/`
- 신규 운영 산출 루트: `system/runtime_v2/`
- 신규 락 루트: `system/runtime_v2/locks/`
- 신규 헬스 루트: `system/runtime_v2/health/`
- 신규 증거 루트: `system/runtime_v2/evidence/`

**충돌 방지 규칙:**
- 기존 `runtime/`, `system/runtime/`, 기존 디버그 포트와 공유 금지
- 브라우저 프로필 디렉터리도 `runtime_v2/sessions/*`로 분리
- 신규 프로그램은 외부 참고 파일을 수정하지 않고 read-only 참조만 허용

## 1) 모듈 경계 (New Program Boundaries)

### Task 1: Control Plane 분리

**Files:**
- Create: `runtime_v2/control_plane.py`
- Create: `runtime_v2/state_machine.py`
- Create: `runtime_v2/queue_store.py`
- Create: `runtime_v2/contracts/job_contract.py`

**Acceptance Criteria:**
- 단일 진입 함수 `run_control_loop()`가 상태 전이만 담당
- 상태 전이는 JSONL로 증적 기록 (`queued -> running -> completed|failed|retry`)
- 메인 파이프라인에서 브라우저/GPU 세부 로직 직접 호출 금지

### Task 2: Browser Plane 분리

**Files:**
- Create: `runtime_v2/browser/supervisor.py`
- Create: `runtime_v2/browser/health.py`
- Create: `runtime_v2/browser/registry.py`

**Acceptance Criteria:**
- ChatGPT/Genspark/SeaArt/GeminiGen 세션을 포트/프로필 기준으로 registry 관리
- 24h 유지 중 헬스 실패시에만 교체(재기동) 수행
- health snapshot 파일 생성: `system/runtime_v2/health/browser_health.json`

### Task 3: GPU Worker Gate 분리

**Files:**
- Create: `runtime_v2/gpu_scheduler.py`
- Create: `runtime_v2/gpu/lease.py`
- Create: `runtime_v2/workers/qwen3_worker.py`
- Create: `runtime_v2/workers/rvc_worker.py`
- Create: `runtime_v2/workers/kenburns_worker.py`

**Acceptance Criteria:**
- 동일 작업군 동시 실행 0건(락 충돌 시 대기열 재삽입)
- stale lock TTL 만료 + fencing token으로 오판락 복구
- GPU 스케줄 로그에 `lock_acquire`, `lock_release`, `lock_expired` 이벤트 기록
- Lock 저장소는 `system/runtime_v2/locks/{workload}.lock` + `system/runtime_v2/locks/{workload}.lease.json`로 고정하며, 논리 키는 payload의 `lock_key`로 기록
- Lease TTL=180초, renew interval=30초 고정(renew 실패 시 즉시 실패 후 queue 재삽입)
- fencing token은 acquire 시 단조 증가값 발급, token 불일치 결과는 폐기+실패 처리

### Task 4: Artifact Contract 고정

**Files:**
- Create: `runtime_v2/contracts/artifact_contract.py`
- Create: `runtime_v2/result_router.py`

**Acceptance Criteria:**
- 이미지/동영상/VOICE 산출물은 JSON에 정의된 folder에만 저장
- 저장 후 `system/runtime_v2/evidence/result.json` latest-run snapshot에 절대경로+해시+생성시각과 최신 run metadata를 기록
- 경로 불일치 시 즉시 실패 처리(침묵 보정 금지)

## 2) 신뢰성 규칙 (24h Stability Rules)

### Task 5: GPT STATUS Floor Auto-Recovery

**Files:**
- Create: `runtime_v2/gpt_pool_monitor.py`
- Create: `runtime_v2/gpt_autospawn.py`
- Create: `system/runtime_v2/health/gpt_status.json` (runtime generated)

**Acceptance Criteria:**
- `OK<1`이면 즉시 경고 이벤트 발행
- 부족 상태가 2분 지속되면 자동 spawn
- spawn 폭주 방지: 5분 쿨다운, 시간당 최대 6회
- 지표: `ok_count`, `pending_boot`, `last_spawn_at`, `spawn_fail_count`
- `OK` 정의: `status == "OK"` 이고 `last_seen_at`이 60초 이내인 세션
- Breach 정의: `ok_count < 1` 상태가 샘플 10초 간격으로 연속 120초 유지

### Task 6: Resume/Retry/Circuit 정책

**Files:**
- Create: `runtime_v2/recovery_policy.py`
- Create: `runtime_v2/retry_budget.py`
- Create: `runtime_v2/circuit_breaker.py`

**Acceptance Criteria:**
- 재시도는 지수백오프 + 작업별 예산(최대 3회)
- 동일 원인 5회 연속 실패 시 회로 차단 후 운영 알림
- resume는 체크포인트 기반(진행 중 작업 idempotent 재진입)

## 3) 마이그레이션 전략 (Reference -> New)

### Task 7: 핵심 로직 차용 목록 고정

**Reuse Candidates:**
- `pipeline_common.py`: 상태 전이/표준 결과 처리
- `scripts/supervisor.py`: 장시간 감시/프로세스 정리 패턴
- `json_generator.py`: JSON 산출물 경로 계약

### Task 7-1: 차용 우선 매트릭스 (개발시간 단축용)

| Reference Source | 차용 로직 | New Target | 차용 방식 | 비고 |
|---|---|---|---|---|
| `pipeline_common.py` | 상태 문자열 정규화, 결과 레코드 형식 | `runtime_v2/state_machine.py` | 함수 단위 포팅 | 상태명 호환 테이블 유지 |
| `master_manager.py` | pending row 선별 규칙(`Status` 기반) | `runtime_v2/queue_store.py` | 규칙만 추출, 실행체인 제외 | 오케스트레이션 결합 로직은 제외 |
| `master_manager.py` | 디버그 브라우저 헬스체크/재사용 패턴 | `runtime_v2/browser/health.py` | 헬스 판정식 재사용 | 포트/세션 registry로 일반화 |
| `scripts/supervisor.py` | orphan 브라우저 정리, 메모리 경고, resume 쿨다운 | `runtime_v2/browser/supervisor.py`, `runtime_v2/recovery_policy.py` | 정책 단위 재사용 | PROTECTED_PORTS 정책 유지 |
| `json_generator.py` | 산출물 경로 계산/검증 | `runtime_v2/contracts/artifact_contract.py` | 계약 함수 포팅 | 이미지/동영상/VOICE 공통화 |
| `pipeline.py` | 프로그램 실행 순서 제약(선행조건) | `runtime_v2/control_plane.py` | 순서 제약만 이관 | 직접 호출 코드는 폐기 |

### Task 7-2: 차용 우선 원칙

1. 신규 작성보다 기존 안정 로직 포팅을 우선한다.
2. 포팅 단위는 함수/정책으로 제한하고, 거대 파일 통째 재사용은 금지한다.
3. 포팅 시 원본 동작 동등성 테스트를 먼저 작성한다(회귀 방지).
4. 차용된 로직은 출처 파일/함수명을 주석이 아닌 문서로만 추적한다.

**Rewrite Targets:**
- `master_manager.py`: 과도 결합 영역(오케스트레이션/정책/실행 혼재)
- 프로그램별 직접 호출 체인: 신규 모듈 경계에 맞춰 분리 재작성

### Task 8: 단계별 전환

1. **Phase A (1주):** 차용 매트릭스 상위 3개(`pipeline_common`, `supervisor`, `json_generator`) 우선 포팅 + dry-run
2. **Phase B (1주):** GPU 스케줄러/락 도입, 중복 실행 0건 확인
3. **Phase C (1주):** GPT floor 자동복구 + 24h soak test
4. **Phase D (1주):** 신규 시스템 본전환, 외부 참고는 read-only 모드

**Phase Exit Criteria:**
- Phase A Exit: `control_loop_dryrun_report.md` PASS + 상태 전이 JSONL 회귀 테스트 PASS
- Phase B Exit: `system/runtime_v2/health/gpu_scheduler_health.json` 기준 24h `duplicate_run=0`
- Phase C Exit: `system/runtime_v2/evidence/soak_24h_report.md` 기준 `gpt_floor_breach_over_120s=0` 및 `MTTR p95 <= 120s`
- Phase D Exit: 외부 참고 write 경로 접근 0건(감사 로그 기준) + 운영 체크리스트 PASS

## 4) 검증 게이트 (Must Pass)

### 4-1) Inbox / Chain 계약

- `system/runtime_v2/inbox/` 계약은 `docs/sop/SOP_runtime_v2_inbox_contract.md`를 단일 기준으로 사용합니다.
- feeder는 `checkpoint_key`, 로컬 경로 검증, stable file age 규칙을 통과한 입력만 queue에 넣습니다.
- 후속 체인은 휴리스틱이 아니라 각 워커 결과 계약의 `next_jobs[]` 선언만 사용합니다.
- chain 메타데이터(`chain_depth`, `routed_from`)는 queue, GUI, evidence에서 동일하게 보입니다.
- idle/seeded/run/failure 전 구간에서 `system/runtime_v2/health/gui_status.json`과 `system/runtime_v2/evidence/result.json`은 같은 latest-run 의미로 함께 갱신됩니다.
- `system/runtime_v2/evidence/result.json`은 runtime evidence latest-run snapshot이며, 워커 내부 결과 계약과 같은 이름을 쓰더라도 용도는 분리됩니다.

### 기능 게이트
- 브라우저 24h 연속 유지(세션 살아있음) 성공
- GPU 작업군 동시 실행 위반 0건
- GPT `OK<1` 지속 상황에서 2분 내 자동복구 시작
- 산출물 경로 위반 0건

### 운영 게이트
- Browser Availability (rolling 24h) >= 99.5% (샘플 60초)
- 24h soak test 동안 프로세스 크래시 자동복구율 100%
- 평균 복구 시간(MTTR) 120초 이하
- GPT Floor Breach(`OK<1` 120초 초과) = 0
- 치명 오류 미해결 누적 0건

### 증거 파일
- `system/runtime_v2/health/browser_health.json`
- `system/runtime_v2/health/browser_session_registry.json`
- `system/runtime_v2/health/gpu_scheduler_health.json`
- `system/runtime_v2/health/gpt_status.json`
- `system/runtime_v2/health/gui_status.json`
- `system/runtime_v2/evidence/result.json`
- `system/runtime_v2/evidence/control_plane_events.jsonl`
- `system/runtime_v2/evidence/soak_24h_report.md`

## 5) 리스크와 차단책

1. 브라우저 메모리 누수 -> 메모리 임계치 초과 시 비정상 인스턴스만 교체
2. 락 유실/중복 실행 -> lease TTL + fencing token + stale lock scavenger
3. GPT spawn 연쇄 실패 -> 쿨다운/횟수 제한 + 알림 + 수동 오버라이드
4. JSON 경로 파손 -> 계약 검증 실패 시 즉시 hard fail

## 6) Done Definition

- 위 검증 게이트 전부 PASS
- SOP 업데이트 완료 (`24h SLO`, `GPU 중복실행 금지`, `GPT floor 자동복구`)
- 운영자가 단일 체크리스트로 장애 대응 가능

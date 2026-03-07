# Excel Topic -> GPT -> Stage2 -> Final Video Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `D:\YOUTUBE_AUTO`에서 이미 구현된 `엑셀 Topic 입력 -> GPT 파싱/프롬프트 생성 -> 엑셀 저장 -> JSON 계약 운영 -> stage2 이미지/비디오 -> 최종 동영상` 개념을 `D:\YOUTUBEAUTO`의 `runtime_v2`에 이식하되, 새 프로그램은 디버깅이 쉽고 파이프라인이 단순한 구조를 유지합니다.

**Architecture:** 새 프로그램의 단일 진실은 `runtime_v2/`와 `system/runtime_v2/`의 계약 파일입니다. 레거시의 강점은 `manager-only Excel writer`, `transition gate`, `runner evidence`에서만 추출하고, 거대 오케스트레이션/브라우저 직접 제어/엑셀 직접 수정은 버립니다. 전체 흐름은 `Supervisor -> Manager -> Subprograms -> Evidence/GUI Plane` 계층으로 고정하며, 실제 데이터 체인은 `Excel Bridge -> TopicSpec -> VideoPlan -> RenderSpec -> Final Evidence`의 단일 JSON 체인만 허용합니다. 단, 모든 하부프로그램은 잡이 없어도 프로세스/세션이 살아 있는 `24h resident worker`를 기본 운영 모델로 사용하고, Manager는 해당 resident worker에 JSON job만 공급합니다.

**Tech Stack:** Python 3.13, `openpyxl`, JSON/JSONL contracts, `runtime_v2`, browser session registry/health, ffmpeg, existing `qwen3_tts/rvc/kenburns` workers, `unittest`, `python -m compileall`

---

## 0) 현재 사실 (Plan Truth)

1. 현재 `runtime_v2`는 `txt` 또는 `.job.json` 입력에서 `qwen3_tts -> rvc -> kenburns` 체인만 지원합니다.
2. 현재 `runtime_v2`에는 `4 머니.xlsx` 같은 엑셀 파일을 읽어 `Topic` 기준으로 Stage1 GPT를 시드하는 코드가 없습니다.
3. 현재 `runtime_v2`에는 레거시의 `chatgpt_pending`, `manager-owned-excel`, `merge_chatgpt_json_results`, `save_prompt_json`, `save_geminigen_json`, `Thumb OK/Voice OK/Done` 상태 전이 개념이 없습니다.
4. 따라서 사용자 관점의 실전 테스트(`엑셀 1행 Topic -> 최종 동영상`)는 아직 불가능합니다.

## 1) 최상위 대원칙 (Hard Gates)

1. **디버깅이 쉬울 것**: 각 단계는 입력 계약, 출력 계약, 상태 스냅샷, 실패 이유가 파일 3개 이내로 역추적 가능해야 합니다.
2. **파이프라인이 심플할 것**: control plane은 단계 간 라우팅만 담당하고, 엑셀 파싱/GPT 브라우저 자동화/이미지 생성/렌더 세부는 각 plane에만 둡니다.
3. **manager-only Excel writer**: 엑셀 read는 `Excel Bridge`만, 엑셀 write는 `Excel State Store`만 수행합니다. 워커와 브라우저 스크립트는 엑셀을 직접 열지 않습니다.
4. **하부프로그램 Excel direct I/O 금지**: ChatGPT/Genspark/SeaArt/GeminiGen/Canva/Voice/Render/RVC/KenBurns 하부프로그램은 엑셀 경로를 인자로 받지도, 열지도, 쓰지도 않습니다.
5. **계층 분리 고정**: `Supervisor`는 24시간 자동화/복구/정책의 최종 관리자이고, `Manager`는 엑셀 브리지/상태 전이/파이프라인 orchestration의 단일 주체이며, 하부프로그램은 입력 JSON을 받아 결과 JSON만 돌려줍니다.
6. **Excel은 가장자리에서 한 번만 변환**: 엑셀 row는 Manager가 최초 1회 `TopicSpec` JSON으로 고정하고, 이후 단계는 엑셀을 다시 참조하지 않습니다.
7. **JSON 계약 최소화**: 하부프로그램 간 전달은 문자열 인자 대신 `topic_spec.json`, `video_plan.json`, `render_spec.json`, `runner_result.json`, `result.json`만 사용합니다.
8. **레거시 포팅 단위 제한**: 함수/정책/계약만 차용합니다. `pipeline.py`, `master_manager.py`, `chatgpt_automation.py` 전체 이식은 금지합니다.
9. **stage2 포함**: 이번 계획은 Stage1 GPT까지만이 아니라, Stage2 이미지/비디오/썸네일/최종 렌더 경로까지 포함합니다.
10. **RenderSpec 단일 writer**: `render_spec.json`은 Manager만 생성/병합/갱신합니다. Stage2/Stage3 worker는 `runner_result.json`만 기록합니다.
11. **Manager는 기존 control plane 위에 얇게 올립니다**: 새 `manager.py`는 엑셀 브리지와 상태 전이를 담당하고, 실제 job queue 실행/`next_jobs[]` 해석은 기존 `runtime_v2/control_plane.py`를 재사용합니다.
12. **모든 하부프로그램 24시간 상시 가동**: GPT, `genspark`, `seaart`, `geminigen`, `canva`, `qwen3_tts`, `rvc`, `kenburns`, `render`는 잡 유무와 별개로 resident 상태를 유지하고, Manager는 해당 상주 프로세스에 job contract만 전달합니다.
13. **Resident dispatch는 기존 inbox/job 계약을 재사용**: resident worker job 전달도 `runtime_v2_inbox_job` 계열 계약, `checkpoint_key`, `chain_depth`, `routed_from`, `local_only` 규칙을 그대로 따릅니다.
14. **Debug log 단일 경로 유지**: `cli`, `manager`, `control_plane`, GUI, resident worker는 같은 `debug_log` 경로를 공유하고, 최신 실행 요약은 짧게 남기며 상세 payload는 JSONL debug log로 보냅니다.
15. **No-Work 빠른 분기 유지**: pending row/asset/job이 0건이면 하부프로그램을 띄우지 않고 `status=no_work`, `reason_code=no_work`로 즉시 종료합니다. `no_work`는 실패로 집계하지 않습니다.
16. **필요 서비스만 Preflight/Login Guard 적용**: 실행 전 전체 서비스를 다 검사하지 않고, 실제 pending workload에 필요한 서비스만 preflight/login 검사를 수행합니다. 부족하면 fail-fast로 종료하고 canonical evidence를 남깁니다.

## 1-1) runtime_v2 매핑 결정 (고정)

1. `runtime_v2/control_plane.py`의 `run_control_loop_once(...)`를 계속 단일 queue executor로 사용합니다. 새 Manager loop를 별도로 만들지 않습니다.
2. `runtime_v2/manager.py`는 `seed_excel_row(...)`, `merge_stage1_result(...)`, `merge_stage2_result(...)`, `finalize_excel_row(...)` 같은 bridge/state 전용 함수만 가집니다.
3. `runtime_v2/cli.py`에는 새 진입점 `--excel-once --excel-path ... --sheet-name ... --row-index ...`를 추가하고, 이 모드는 `manager.seed_excel_row(...)` 후 기존 `run_control_loop_once(...)`를 호출합니다.
4. `runtime_v2/supervisor.py`는 이름은 유지하되 역할을 “gate runner”로 제한합니다. 24h Supervisor 개념은 계획상 상위 운영 책임이며, 코드에서는 `cli.py`/운영 프로세스가 이를 감쌉니다.
5. 따라서 코드 매핑은 `CLI/ops wrapper -> manager.py -> control_plane.py -> supervisor.py(run_gated) -> workers` 순서로 고정합니다.
6. `workers`는 one-shot 실행기보다 `resident worker loop`를 우선하며, control plane은 새 프로세스를 매번 띄우지 않고 살아 있는 worker에 계약을 전달하는 방식으로 확장합니다.

## 2) 접근안

### Option A: 레거시 full pipeline 직접 복제
- 장점: 초기 실행 체감은 빠를 수 있습니다.
- 단점: 디버깅 난이도와 복잡도가 그대로 재유입됩니다.
- 판정: **금지**

### Option B: 레거시를 어댑터 프로세스로 감싸 새 프로그램에서 호출
- 장점: 단기 연결은 쉽습니다.
- 단점: 새 프로그램이 블랙박스 의존 구조가 되어 파이프라인 단순성이 깨집니다.
- 판정: **비상 우회용만 허용**

### Option C: Excel/GPT/Stage2/Final 단계별 계약을 새 runtime_v2에 재구성
- 장점: 디버깅과 운영 증거를 새 구조로 잠글 수 있습니다.
- 단점: 상위 plane을 새로 설계해야 합니다.
- 판정: **권장안**

## 3) Legacy Reuse Map (실제 차용 대상)

| Legacy Source | 가져올 개념 | 버릴 개념 | New Target |
|---|---|---|---|
| `data_access.py` | 채널별 엑셀 read 단일 경로, `Topic/Status` 스냅샷 | 전역 캐시 결합 | `runtime_v2/excel/source.py` |
| `master_manager.py::check_pending_work` | `Topic`/`Status` 기반 pending 분류 | 모든 상태를 한 파일에서 직접 관리 | `runtime_v2/excel/selector.py`, `runtime_v2/excel/state_store.py` |
| `sub_runners.py::_build_chatgpt_pending_json` | row selector -> Stage1 입력 계약 개념 | 워커와 manager 혼합 책임 | `runtime_v2/contracts/topic_spec.py` |
| `sub_runners.py::run_chatgpt_via_manager` | Stage1 GPT 진입점, manager-owned canonical evidence | giant automation 직접 결합 | `runtime_v2/stage1/chatgpt_runner.py` |
| `master_manager.py::merge_chatgpt_json_results` | manager-owned merge, terminal status skip | 엑셀 병합 로직 분산 | `runtime_v2/excel/state_store.py` |
| `pipeline.py::run_image_gen` | GPT 결과 -> Stage2 job fan-out -> render 입력 생성 | giant phase loop | `runtime_v2/stage2/router.py`, `runtime_v2/stage2/json_builders.py`, `runtime_v2/contracts/render_spec.py` |
| `json_generator.py` | voice/kenburns/geminigen JSON 계약 | 엑셀/폴더 직접 의존 | `runtime_v2/contracts/stage2_contracts.py` |
| `sub_runners.py::run_genspark_automation`, `run_seaart_automation`, `run_geminigen_for_row`, `run_canva_automation`, `run_render_automation`, `run_voice_generation`, `run_ken_burns_with_audio` | stage2/stage3 runner 경계, result json/evidence 개념 | CLI 인라인 문자열/직접 상태 변경 | `runtime_v2/stage2/*.py`, `runtime_v2/stage3/*.py` |
| `pipeline.py::transition_row` 및 관련 문서 | 상태 전이 gate, reason_code, row binding | 분산된 continue 분기 | `runtime_v2/excel/status_contract.py`, `runtime_v2/control_plane.py` |

## 4) 새 프로그램 목표 흐름 (Oracle 단순화 반영)

1. Supervisor가 Manager를 감시/재기동/정책 통제하고, Manager만 실제 업무 파이프라인을 운영합니다.
2. Manager 내부 Excel Bridge가 `4 머니.xlsx`에서 row 1의 `Topic`과 상태를 읽고, 최초 1회 `topic_spec.json`으로 고정합니다.
3. Stage1 GPT Runner는 `topic_spec.json`만 입력으로 받아 파싱/프롬프트/scene/voice 초안을 생성하고 `video_plan.json`만 반환합니다.
4. Manager의 Excel State Store가 `video_plan.json`의 핵심 필드와 상태만 엑셀에 반영합니다. Stage1 이후 엑셀은 상태판 역할만 합니다.
5. Stage2 Router는 `video_plan.json`을 읽어 `genspark`, `seaart`, `geminigen`, `canva`에 필요한 explicit `.job.json`과 `render_spec.json`을 생성합니다.
6. 하부 worker들은 24시간 resident 상태를 유지하며, 각 계약 파일만 받아 처리하고 결과는 `runner_result.json`의 `next_jobs[]` 또는 `result_path` JSON으로만 넘깁니다.
7. Final Render는 `render_spec.json`만 입력으로 받아 최종 동영상을 만들고, Manager가 최종 상태를 `Done`으로 전이합니다.
8. Supervisor는 24시간 자동화 관점에서 Manager 헬스, latest-run evidence, 복구 상태만 감시합니다.

## 4-1) 책임 계층 고정

| 계층 | 책임 | 금지 사항 |
|---|---|---|
| `Supervisor` | 24h 감시, Manager 재기동, 세션/헬스/복구 정책, 운영 게이트 | 엑셀 파싱, row 선택, prompt 해석, 하부프로그램 세부 실행 |
| `Manager` | Excel Bridge, pending selection, 상태 전이, `TopicSpec/VideoPlan/RenderSpec` 단일 writer, latest-run snapshot | 브라우저 세부 제어 로직 직접 구현, job queue 자체 재구현, 하부프로그램 내부 I/O 중복 |
| `Subprograms` | 24h resident 상태 유지, JSON 입력 수신, 단일 작업 수행, 결과 JSON 반환 | 엑셀 read/write, 전역 상태 직접 수정, Manager/Supervisor 정책 판단 |

## 5) 상태/계약 재정의 (단순화 버전)

### 5-1) Excel Status Contract

| 상태 | 의미 | 다음 허용 상태 |
|---|---|---|
| `""` | Stage1 미실행 | `OK`, `partial`, `failed` |
| `OK` | Stage1 GPT + `video_plan.json` 생성 완료 | `Image OK`, `partial`, `failed` |
| `Image OK` | stage2 이미지/비디오 입력 준비 완료 | `Thumb OK`, `Video OK`, `partial`, `failed` |
| `Thumb OK` | 썸네일/scene 자산 준비 완료 | `Video OK`, `partial`, `failed` |
| `Video OK` | 중간 영상 완료 | `Voice OK`, `Done`, `partial`, `failed` |
| `Voice OK` | 음성/렌더 직전 또는 완료 | `Done`, `partial`, `failed` |
| `Done` | 최종 산출 완료 | - |
| `partial` | 일부 결과/재시도 대기 | `OK`, `Image OK`, `Video OK`, `Voice OK`, `failed` |
| `failed` | hard fail | `partial` 또는 명시적 재시도 |

### 5-2) Minimal JSON Contracts

1. `topic_spec.json` - Excel row를 한 번 고정한 Stage1 입력 계약. 필수 키는 `run_id`, `row_ref`, `topic`, `status_snapshot`, `excel_snapshot_hash`입니다.
2. `video_plan.json` - GPT가 만든 정규화 계획 계약. 필수 키는 `run_id`, `row_ref`, `topic`, `story_outline`, `scene_plan`, `asset_plan`, `voice_plan`, `reason_code`, `evidence`입니다.
3. `render_spec.json` - Stage2 결과를 모아 Final Render로 넘기는 계약. 필수 키는 `run_id`, `row_ref`, `asset_refs`, `timeline`, `audio_refs`, `thumbnail_refs`, `reason_code`입니다.
4. `stage2_*.job.json` - `video_plan.json` 또는 `render_spec.json`에서 파생되는 explicit worker job입니다.
5. `runner_result.json` - 개별 worker 결과와 `next_jobs[]`를 담는 공통 결과 계약입니다.
6. `system/runtime_v2/evidence/result.json` - latest-run snapshot입니다.

### 5-3) Contract Reduction Rules

1. `topic_spec.json`에서 `video_plan.json`으로 갈 때만 GPT/파싱 정보가 확장됩니다.
2. `video_plan.json`에서 Stage2 job들과 `render_spec.json`이 파생됩니다. `prompt_bundle.json` 같은 중간 저장물은 독립 정본으로 두지 않습니다.
3. Stage2 worker 간 데이터 전달은 가능한 한 `runner_result.json -> next_jobs[]`만 사용합니다.
4. 어떤 단계도 `row_index` 외 엑셀 셀 주소나 workbook 경로를 다시 전달하지 않습니다.
5. `render_spec.json` 갱신은 Manager만 수행하며, worker 결과에서 필요한 경로만 읽어 원자적으로 merge합니다.
6. `Supervisor`는 기존 `runtime_v2/supervisor.py`의 게이트/복구 역할을 유지하고, 엑셀/계약 해석은 새 `manager.py`로 내립니다.

### 5-3-1) Voice/Asset Fail-Closed Rules

1. `video_plan.json.voice_plan`은 scene 단위 매핑 정보를 포함하고, 최소 `mapping_source`와 scene-count 정합성 근거를 남깁니다.
2. scene/voice 매핑 수가 맞지 않으면 자동 추정으로 조용히 보정하지 않고 `reason_code=artifact_invalid` 또는 동등한 fail-closed 코드로 중단합니다.
3. Stage2/Stage3 JSON 생성은 필요한 공통 asset/image folder가 없으면 즉시 중단하고 hard fail 또는 `partial` downgrade 근거를 기록합니다.
4. asset gate 실패는 `debug_log`와 `latest-run snapshot`에서 바로 식별 가능해야 합니다.

### 5-4) Workload/Gate Mapping

| workload | gate kind | browser health | GPU lease | notes |
|---|---|---|---|---|
| `qwen3_tts` | `gpu` | required | required | 기존 유지 |
| `rvc` | `gpu` | required | required | 기존 유지 |
| `kenburns` | `gpu` | required | required | 기존 유지 |
| `genspark` | `browser` | required | none | stage2 browser worker |
| `seaart` | `browser` | required | none | stage2 browser worker |
| `geminigen` | `browser` | required | none | stage2 browser worker |
| `canva` | `browser` | required | none | stage2 browser worker |
| `render` | `local` | optional | none | final assembly only |

1. `runtime_v2/config.py`의 하드코딩 `GpuWorkload`는 `WorkloadName` + registry 구조로 확장합니다.
2. `runtime_v2/contracts/job_contract.py`의 `workload_from_value(...)`는 위 workload 전부를 허용하도록 바꿉니다.
3. `runtime_v2/control_plane.py`는 workload registry를 읽어 `gpu`, `browser`, `local` 경로로 분기합니다.
4. `gpu` workload만 기존 `lease_store_for_workload(...)`와 GPU heartbeat를 사용합니다.
5. `browser` workload는 `run_gated(..., require_browser_healthy=True, lease_store=None)`가 아니라 별도 non-gpu gate 경로를 사용해 GPU lease를 건드리지 않습니다.
6. `local` workload는 브라우저/GPU lease 없이 worker만 실행하되, 동일한 `run_id`와 `runner_result.json` 계약은 유지합니다.
7. 위 workload 전부는 resident worker registry에 등록되며, `cold start` 없이 24시간 살아 있는 상태를 기본값으로 합니다.
8. Supervisor는 resident worker가 죽었는지 감시하고, 죽은 인스턴스만 선택적으로 재기동합니다.

### 5-4-1) Resident Worker Rule

1. GPT, `genspark`, `seaart`, `geminigen`, `canva`, `qwen3_tts`, `rvc`, `kenburns`, `render`는 모두 24h resident worker 대상입니다.
2. Manager는 job마다 새 하부프로그램 프로세스를 띄우지 않고, 살아 있는 worker에 `.job.json`만 전달합니다.
3. resident worker의 busy/idle/last_seen/pid/session_id는 별도 health/registry 파일로 추적합니다.
4. worker 재기동은 Supervisor만 수행하고, Manager는 재기동 정책을 갖지 않습니다.
5. resident worker가 죽어도 엑셀 상태는 Manager가 최종 판단하며, worker는 엑셀을 직접 수정하지 않습니다.
6. resident worker dispatch는 `system/runtime_v2/inbox/` 기반 계약을 재사용하며, `checkpoint_key`로 중복 시드를 막고 stable-file-age 규칙을 적용합니다.
7. resident worker 결과도 동일하게 `next_jobs[]`, `result_path`, `chain_depth`, `routed_from` 메타데이터를 사용합니다.
8. stable-file-age는 worker poll 시점에 강제하며, 파일 수정 시각이 3초 이상 지난 계약만 수락합니다. Manager publish 직후 파일은 worker가 즉시 잡지 않습니다.
9. resident worker는 progress heartbeat 또는 마지막 진행 시각을 기록해야 하며, 일정 시간 진전이 없으면 `progress_stall`로 분류합니다.
10. `progress_stall` 판정과 재기동은 Supervisor가 담당하고, Manager는 stall 결과를 상태/증거에만 반영합니다.

### 5-5) Evidence Path Lock

1. 최신 상태 스냅샷 경로는 정확히 `system/runtime_v2/health/gui_status.json`, `system/runtime_v2/evidence/result.json`, `system/runtime_v2/evidence/control_plane_events.jsonl`입니다.
2. `run_id`는 `runtime_v2/cli.py`에서 한 번 생성하고, `manager.py -> control_plane.py -> worker result -> result router` 전체에 그대로 전달합니다.
3. Excel row 기반 실행에서도 latest-run 증거 3종은 같은 `run_id`를 공유해야 합니다.
4. `topic_spec.json`, `video_plan.json`, `render_spec.json`, `runner_result.json`에도 같은 `run_id`를 기록합니다.
5. `system/runtime_v2/evidence/result.json` latest-run snapshot에는 최종 산출물의 절대경로, 해시, 생성시각, `debug_log`, 최신 run metadata를 기록합니다.
6. 경로 불일치 또는 증거 누락은 침묵 보정 없이 즉시 실패 처리합니다.
7. fatal failure 시에는 `원인 1개 + 근거 3개` 구조의 failure summary를 남겨, 운영자가 한 번에 원인 축을 재현할 수 있어야 합니다.
8. canonical failure summary artifact 경로는 `system/runtime_v2/evidence/failure_summary.json`입니다.
9. `failure_summary.json`의 단일 writer는 Manager입니다.
10. 최소 필수 키는 `run_id`, `reason_code`, `summary`, `evidence_refs`, `debug_log`, `ts`입니다. `evidence_refs`는 정확히 3개 포인터를 가집니다.
11. `result.json` latest-run snapshot에는 `failure_summary_path`가 포함되어야 하며, fatal failure 시 위 canonical artifact를 반드시 가리켜야 합니다.

### 5-5-1) Preflight/Login Guard Lock

1. preflight/login guard는 Manager가 pending workload를 계산한 뒤 필요한 서비스에 대해서만 수행합니다.
2. Stage1 GPT 실행 전에는 GPT/ChatGPT service readiness만, Stage2 이미지 실행 전에는 해당 이미지 서비스(`genspark`, `seaart`, `geminigen`, `canva`) readiness만 검사합니다.
3. pending이 없는 서비스에 대한 로그인/세션 검사는 수행하지 않습니다.
4. preflight 실패 시 하부 worker를 띄우지 않고 fail-fast 또는 `no_work`와 구분되는 명시적 `reason_code`로 종료합니다.
5. preflight 판정 결과는 `debug_log`, `gui_status.json`, `result.json`, 필요 시 `failure_summary.json`에 동일 `run_id`로 남깁니다.

### 5-6) Resident Dispatch Contract Lock

1. resident dispatch의 기본 전달 방식은 파일 계약 기반입니다. `*.job.json`은 원자적 write 후 rename으로 publish합니다.
2. worker는 자신에게 할당된 inbox/queue만 poll하거나 registry가 가리키는 계약만 pull합니다. Manager가 worker 내부 API를 직접 호출하지 않습니다.
3. `checkpoint_key`는 Excel row + stage + logical workload 기준으로 결정해 중복 시드를 막습니다.
4. 입력 계약은 모두 `local_only=true`를 유지하고, 작업 루트 밖 경로는 금지합니다.
5. worker ack/result는 `runner_result.json`과 `result_path` 계약으로만 반환하고, 별도 ad-hoc 응답 포맷은 금지합니다.

### 5-7) 24h Soak Readiness Lock

1. 구현 완료 전 최소 게이트는 `selftest detached OK`, `control idle same run_id`, `mock chain final_output=true`입니다.
2. `probe_result.json`, `evidence/result.json`, `health/gui_status.json`, `health/browser_health.json`은 같은 `run_id`로 조인 가능해야 합니다.
3. smoke 증거만으로 Browser/GPU/GPT 원인 축을 다시 분리할 수 있어야 합니다.
4. 장시간 운영 진입 전 `system/runtime_v2/evidence/soak_24h_report.md`를 채울 수 있는 증거 경로가 준비되어야 합니다.

### 5-7-1) Probe Result Contract Lock

1. canonical probe result 경로는 `system/runtime_v2_probe/<probe-name>/probe_result.json`입니다.
2. `probe_result.json`의 단일 writer는 detached probe launcher(`runtime_v2/cli.py`)입니다.
3. 최소 필수 키는 `run_id`, `mode`, `status`, `code`, `exit_code`, `debug_log`, `result_path`, `ts`입니다.
4. detached selftest/control-idle/mock-chain readiness 판정은 위 canonical path의 `probe_result.json`만 기준으로 합니다.
5. 다른 위치의 임시 probe 요약 파일이나 ad-hoc JSON은 readiness gate 근거로 사용하지 않습니다.

## 6) Stage2 포함 실행 계획

### Task 1: Excel Bridge와 TopicSpec 도입

**Files:**
- Create: `runtime_v2/excel/source.py`
- Create: `runtime_v2/excel/selector.py`
- Create: `runtime_v2/excel/state_store.py`
- Create: `runtime_v2/excel/status_contract.py`
- Create: `runtime_v2/contracts/topic_spec.py`
- Create: `runtime_v2/manager.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/control_plane.py`
- Modify: `docs/sop/SOP_runtime_v2_inbox_contract.md`
- Modify: `docs/sop/SOP_runtime_v2_detached_soak_readiness.md`
- Create: `tests/test_runtime_v2_excel_bridge.py`

**Step 1: 실패 테스트 작성**

```python
def test_excel_selector_reads_topic_row_into_topic_spec_contract() -> None:
    ...

def test_excel_state_store_is_single_writer_for_status_updates() -> None:
    ...

def test_subprograms_never_receive_excel_path_directly() -> None:
    ...

def test_excel_once_cli_delegates_to_manager_then_existing_control_loop() -> None:
    ...

def test_excel_pipeline_targets_resident_workers_not_one_shot_processes() -> None:
    ...

def test_excel_seed_uses_checkpoint_key_and_local_only_contract() -> None:
    ...

def test_resident_worker_poll_enforces_stable_file_age_3_seconds() -> None:
    ...

def test_no_work_fast_path_skips_worker_launch_and_is_not_failure() -> None:
    ...

def test_preflight_login_guard_checks_only_required_services() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_excel_bridge -v`
Expected: FAIL with missing Excel selector / state writer behavior

**Step 3: 최소 구현**

```python
workbook = load_workbook(excel_path, read_only=True, data_only=True)
topic = str(row_map["Topic"]).strip()
status = str(row_map.get("Status", "")).strip()
```

Manager는 `excel_path`, `row_index`, `sheet_name`을 내부 컨텍스트로만 유지하고, 하부프로그램에는 `row_ref`와 해시된 스냅샷만 전달합니다.
또한 `Manager.seed_excel_jobs()`는 직접 워커를 실행하지 않고, 기존 `runtime_v2/control_plane.py`의 enqueue/route 경로만 호출합니다.
`runtime_v2/cli.py`는 새 `--excel-once` 모드에서 `run_id`를 만들고, `manager.seed_excel_row(...)` 뒤 곧바로 `run_control_loop_once(...)`를 호출합니다.
단, 실제 하부프로그램 실행 모델은 one-shot spawn이 아니라 resident worker dispatch가 기본입니다.

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_excel_bridge -v`
Expected: PASS

### Task 2: Stage1 GPT 계약과 VideoPlan 이식

**Files:**
- Create: `runtime_v2/stage1/chatgpt_runner.py`
- Create: `runtime_v2/contracts/video_plan.py`
- Create: `runtime_v2/stage1/result_contract.py`
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/contracts/job_contract.py`
- Modify: `runtime_v2/config.py`
- Create: `runtime_v2/worker_registry.py`
- Modify: `runtime_v2/debug_log.py`
- Create: `tests/test_runtime_v2_stage1_chatgpt.py`

**Step 1: 실패 테스트 작성**

```python
def test_stage1_builds_video_plan_from_topic_spec() -> None:
    ...

def test_stage1_chatgpt_runner_accepts_only_topic_spec_contract() -> None:
    ...

def test_video_plan_contains_scene_voice_and_reason_code() -> None:
    ...

def test_stage1_result_records_debug_log_and_run_id() -> None:
    ...

def test_voice_plan_records_mapping_source_and_fails_closed_on_mismatch() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_stage1_chatgpt -v`
Expected: FAIL because TopicSpec -> VideoPlan contract and runner do not exist yet

**Step 3: 최소 구현**

```python
contract = {"row_ref": row_ref, "topic": topic, "status_snapshot": status}
result = {"status": "success", "reason_code": "ok", "video_plan_path": str(plan_path)}
```

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_stage1_chatgpt -v`
Expected: PASS

### Task 3: VideoPlan 병합과 Excel 저장을 새 구조로 고정

**Files:**
- Modify: `runtime_v2/excel/state_store.py`
- Modify: `runtime_v2/result_router.py`
- Modify: `runtime_v2/gui_adapter.py`
- Create: `tests/test_runtime_v2_stage1_excel_merge.py`

**Step 1: 실패 테스트 작성**

```python
def test_video_plan_merge_updates_only_allowed_columns_and_status() -> None:
    ...

def test_terminal_rows_are_not_overwritten_by_stage1_merge() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_stage1_excel_merge -v`
Expected: FAIL because manager-owned merge rules are missing

**Step 3: 최소 구현**

```python
if current_status.lower() in {"voice ok", "done"}:
    return skip_terminal_row
sheet.cell(row=row_no, column=status_col).value = next_status
```

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_stage1_excel_merge -v`
Expected: PASS

### Task 4: VideoPlan -> Stage2/RenderSpec 계약 이식

**Files:**
- Create: `runtime_v2/stage2/router.py`
- Create: `runtime_v2/stage2/json_builders.py`
- Create: `runtime_v2/contracts/render_spec.py`
- Create: `runtime_v2/contracts/stage2_contracts.py`
- Modify: `runtime_v2/config.py`
- Modify: `runtime_v2/contracts/job_contract.py`
- Modify: `docs/sop/SOP_runtime_v2_inbox_contract.md`
- Modify: `runtime_v2/result_router.py`
- Create: `tests/test_runtime_v2_stage2_contracts.py`

**Step 1: 실패 테스트 작성**

```python
def test_video_plan_is_split_into_genspark_and_seaart_jobs() -> None:
    ...

def test_render_spec_and_stage2_contracts_include_row_binding_and_reason_code() -> None:
    ...

def test_browser_stage2_workloads_bypass_gpu_lease_and_use_browser_gate_only() -> None:
    ...

def test_latest_run_snapshot_records_absolute_path_hash_and_debug_log() -> None:
    ...

def test_stage2_contract_builders_fail_closed_when_common_asset_folder_missing() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_stage2_contracts -v`
Expected: FAIL because VideoPlan -> RenderSpec/stage2 contract builders do not exist yet

**Step 3: 최소 구현**

```python
job = build_explicit_job_contract(job_id=..., workload="genspark", payload={...})
render_spec = {"run_id": run_id, "row_ref": row_ref, "asset_refs": asset_refs, "audio_refs": audio_refs}
```

`render_spec.json`은 Manager만 생성/갱신하고, 각 Stage2 worker는 자신의 산출물 경로를 담은 `runner_result.json`만 반환합니다.

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_stage2_contracts -v`
Expected: PASS

### Task 5: Stage2 browser plane (`genspark`, `seaart`, `geminigen`, `canva`)를 새 구조에 연결

**Files:**
- Create: `runtime_v2/stage2/genspark_worker.py`
- Create: `runtime_v2/stage2/seaart_worker.py`
- Create: `runtime_v2/stage2/geminigen_worker.py`
- Create: `runtime_v2/stage2/canva_worker.py`
- Modify: `runtime_v2/browser/manager.py`
- Modify: `runtime_v2/browser/supervisor.py`
- Modify: `runtime_v2/supervisor.py`
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/worker_registry.py`
- Create: `tests/test_runtime_v2_stage2_workers.py`

**Step 1: 실패 테스트 작성**

```python
def test_stage2_worker_uses_json_input_only_and_returns_runner_result() -> None:
    ...

def test_stage2_worker_never_updates_excel_directly() -> None:
    ...

def test_stage2_success_routes_to_next_contract_or_terminal_state() -> None:
    ...

def test_stage2_browser_workload_does_not_allocate_gpu_lease() -> None:
    ...

def test_stage2_jobs_dispatch_to_resident_workers() -> None:
    ...

def test_resident_worker_progress_stall_is_reported_to_supervisor() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_stage2_workers -v`
Expected: FAIL because stage2 workers and router bindings do not exist yet

**Step 3: 최소 구현**

```python
return {"status": "ok", "stage": "genspark", "next_jobs": [...], "completion": {...}}
```

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_stage2_workers -v`
Expected: PASS

### Task 6: Final video plane (`voice`, `kenburns`, `render`)과 Excel 최종 상태 동기화

**Files:**
- Create: `runtime_v2/stage3/render_worker.py`
- Modify: `runtime_v2/workers/qwen3_worker.py`
- Modify: `runtime_v2/workers/rvc_worker.py`
- Modify: `runtime_v2/workers/kenburns_worker.py`
- Modify: `runtime_v2/excel/state_store.py`
- Modify: `runtime_v2/manager.py`
- Modify: `runtime_v2/worker_registry.py`
- Create: `tests/test_runtime_v2_final_video_flow.py`

**Step 1: 실패 테스트 작성**

```python
def test_final_video_success_marks_excel_done_and_updates_latest_run() -> None:
    ...

def test_partial_failure_marks_excel_partial_with_reason() -> None:
    ...

def test_render_spec_is_merged_only_by_manager() -> None:
    ...

def test_final_stage_workers_remain_resident_while_processing_multiple_jobs() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_final_video_flow -v`
Expected: FAIL because final status sync is missing

**Step 3: 최소 구현**

```python
if completion_state == "completed" and final_output:
    update_excel_status(..., to_status="Done")
```

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_final_video_flow -v`
Expected: PASS

### Task 7: 제어면 단순화와 운영 증거 잠금

**Files:**
- Modify: `runtime_v2/control_plane.py`
- Modify: `runtime_v2/manager.py`
- Modify: `runtime_v2/cli.py`
- Modify: `runtime_v2/gui_adapter.py`
- Modify: `docs/sop/SOP_runtime_v2_detached_soak_readiness.md`
- Modify: `docs/sop/SOP_24h_runtime_stability_and_gpu_gates.md`
- Create: `tests/test_runtime_v2_excel_topic_end_to_end.py`

**Step 1: 실패 테스트 작성**

```python
def test_excel_row1_topic_can_seed_stage1_and_finish_final_video_contracts() -> None:
    ...

def test_control_plane_keeps_same_run_id_across_excel_stage1_stage2_final() -> None:
    ...

def test_supervisor_manages_manager_but_never_touches_excel_contracts() -> None:
    ...

def test_detached_selftest_idle_and_mock_chain_evidence_share_run_id_contracts() -> None:
    ...

def test_probe_result_uses_canonical_path_and_required_schema() -> None:
    ...

def test_failure_summary_keeps_one_reason_three_evidence_refs() -> None:
    ...

def test_failure_summary_uses_canonical_path_and_manager_single_writer() -> None:
    ...
```

**Step 2: 실행해 실패 확인**

Run: `python -m unittest tests.test_runtime_v2_excel_topic_end_to_end -v`
Expected: FAIL until Excel bridge and stage2/final routing are complete

**Step 3: 최소 구현**

```python
seeded = seed_excel_stage1_jobs(...)
worker_result = run_worker(job)
seed(worker_result["next_jobs"])
```

**Step 4: 재검증**

Run: `python -m unittest tests.test_runtime_v2_excel_topic_end_to_end -v`
Expected: PASS

## 7) 차단 조건 (원칙 위반 시 계획 실패)

1. 하부 워커(`stage1`, `stage2`, `stage3`)가 엑셀 파일을 직접 읽거나 쓰면 실패입니다.
2. Supervisor가 Excel row 선택/상태 저장/Stage1 prompt 분해까지 관여하면 실패입니다.
3. Manager가 브라우저 세션 생성/셀레니움 단계/ffmpeg 세부 명령까지 직접 품으면 실패입니다.
4. GPT/browser/image/video/voice/render 중 어느 단계든 입력이 `topic_spec.json`, `video_plan.json`, `render_spec.json`, `*.job.json` 계열 JSON 계약이 아니라 인라인 문자열/임시 전역 상태이면 실패입니다.
5. `run_id`, `job_id`, `row_index`, `result_path`, `reason_code` 중 하나라도 증거 파일에서 빠지면 실패입니다.
6. `4 머니.xlsx` row1 같은 단건 테스트를 재현할 때 필요한 증거가 3개 파일을 넘어서 흩어지면 실패입니다.
7. `Manager`가 기존 `runtime_v2/control_plane.py`와 별개로 두 번째 job queue/orchestration loop를 만들면 실패입니다.
8. Stage2/Stage3 worker가 `render_spec.json`을 직접 갱신하면 실패입니다.
9. `genspark/seaart/geminigen/canva` workload가 GPU lease를 잡도록 구현되면 실패입니다.
10. latest-run 증거 경로가 `system/runtime_v2/health/gui_status.json`, `system/runtime_v2/evidence/result.json`, `system/runtime_v2/evidence/control_plane_events.jsonl`와 다르면 실패입니다.
11. 하부프로그램을 job마다 새 프로세스로 반복 spawn하는 one-shot 모델로 구현되면 실패입니다.
12. resident worker dispatch가 `checkpoint_key`, `local_only`, stable-file-age 규칙을 우회하면 실패입니다.
13. latest-run snapshot에 절대경로/해시/생성시각/`debug_log`가 없으면 실패입니다.
14. detached selftest/control-idle/mock-chain 증거가 같은 `run_id`로 조인되지 않으면 실패입니다.
15. pending work가 0건인데도 GPT/worker를 실제 실행하면 실패입니다.
16. scene/voice 매핑 불일치를 자동 추정으로 침묵 보정하면 실패입니다.
17. 공통 asset/image folder gate 실패를 무시하고 Stage2/Stage3 JSON을 생성하면 실패입니다.
18. resident worker progress stall이 증거/재기동 정책 없이 방치되면 실패입니다.
19. pending이 없는 서비스까지 preflight/login 검사를 강제하면 실패입니다.
20. fatal failure가 발생했는데 `system/runtime_v2/evidence/failure_summary.json` canonical artifact와 `result.json.failure_summary_path`가 남지 않으면 실패입니다.

## 8) Verification Gates

### Commands

```bash
python -m unittest tests.test_runtime_v2_excel_bridge -v
python -m unittest tests.test_runtime_v2_stage1_chatgpt -v
python -m unittest tests.test_runtime_v2_stage1_excel_merge -v
python -m unittest tests.test_runtime_v2_stage2_contracts -v
python -m unittest tests.test_runtime_v2_stage2_workers -v
python -m unittest tests.test_runtime_v2_final_video_flow -v
python -m unittest tests.test_runtime_v2_excel_topic_end_to_end -v
python -m unittest tests.test_runtime_v2_phase2 tests.test_runtime_v2_browser_plane tests.test_runtime_v2_external_process tests.test_runtime_v2_gpu_workers tests.test_runtime_v2_control_plane_chain -v
python -m compileall -q runtime_v2 tests
```

### Must Pass

- `4 머니.xlsx` row1을 읽어 `topic_spec.json`을 생성할 수 있음
- Stage1 GPT 결과가 엑셀과 `video_plan.json`에 동시에 반영됨
- pending 0건 실행은 `no_work`로 빠르게 종료되고 실패로 집계되지 않음
- preflight/login guard는 필요한 서비스에만 적용됨
- stage2 worker들은 JSON 입력만 받고 엑셀을 직접 수정하지 않음
- scene/voice 매핑과 공통 asset gate는 fail-closed로 동작함
- Supervisor/Manager/Subprogram 책임이 섞이지 않음
- 최종 video/voice/render 완료 시 Excel 상태가 `Done`으로 전이됨
- latest-run evidence(`gui_status.json`, `result.json`, `control_plane_events.jsonl`)가 같은 `run_id`를 공유함
- fatal failure 시 canonical `failure_summary.json`과 `failure_summary_path`가 남음

## 9) Done Definition

1. 사용자가 `4 머니.xlsx` 1행 Topic을 선택하면, 새 프로그램이 레거시처럼 GPT부터 최종 동영상까지 같은 개념으로 실행됩니다.
2. 그러나 내부 구조는 레거시보다 단순해서, 각 단계의 입력/출력/실패 원인을 계약 파일과 evidence로 바로 찾을 수 있습니다.
3. stage2까지 포함한 전체 흐름이 `Excel Bridge -> TopicSpec -> VideoPlan -> RenderSpec -> Final` 직선 체인으로 설명 가능합니다.
4. Oracle과 Momus 검토에서 “디버깅 어려움” 또는 “파이프라인 복잡도 재유입” 차단 이슈가 남지 않습니다.

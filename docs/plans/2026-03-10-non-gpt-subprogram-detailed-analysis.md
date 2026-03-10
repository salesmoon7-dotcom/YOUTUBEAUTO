# Non-GPT Subprogram Detailed Analysis

## Why This Document Exists

- “비-GPT 범위는 준비가 많이 됐다”는 말만으로는 부족합니다.
- 실제 디버깅 비용을 줄이려면, 각 하부프로그램별로
  - 레거시 동작
  - 현재 `runtime_v2` 동작
  - 숨은 gap
  - 실패모드
  - 장기 안정성 리스크
  를 따로 분리해서 봐야 합니다.

## Review Lens

이 문서는 아래 5개 축으로 평가합니다.

1. **계약 일치성**
2. **실패모드 명시성**
3. **리소스/프로세스 생명주기**
4. **중복 실행/멱등성**
5. **관측가능성/증거 수집성**

## Important Interpretation Rule

- 이 문서는 “코드가 존재하는가”가 아니라 **실제로 기능 동작이 검증되었는가**를 기준으로 평가합니다.
- 따라서 아래 3단계로 상태를 나눕니다.
  - `Implemented`: 코드/계약은 존재하지만 실제 기능 동작 검증은 부족할 수 있음
  - `Contract-verified`: 입력/출력/실패 계약 테스트는 있음
  - `Functionally-verified`: 실제 기능 동작 또는 이에 준하는 강한 evidence가 있음
- **프로그램 하나가 준비됐다고 전체 비-GPT가 완료된 것으로 간주하지 않습니다.**
- exploratory helper/evidence 실험은 가능하지만, **직접 code path에 적용하는 것은 검증 후에만** 허용합니다.

## 1. SeaArt

### Legacy behavior

- GPT 이후 image prompt 컬럼만 있으면 바로 시작
- 브라우저 세션/포트 필요
- 이미지 산출물 suffix: `_SEA_Z`, `_SEA_2`

### Current runtime_v2 status

- stage2 worker 존재
- agent-browser adapter 경로 존재
- live attach evidence 확보
- fail-closed 유지

### Functional validation status

- `Functionally-verified`
- evidence:
  - `system/runtime_v2_probe/seaart-functional-03/exports/seaart.png`
  - `system/runtime_v2_probe/seaart-functional-03/functional_evidence/final_screen.png`
  - `system/runtime_v2_probe/seaart-functional-03/functional_evidence/evidence.json`

### Remaining gaps

- stage1 richer field가 실제 SeaArt 입력 prompt 품질까지 보장하는지 아직 미확인
- 실패모드 분류는 공통 adapter matrix 1차가 반영되었지만, SeaArt 고유 세션 제한/생성 오류/다운로드 실패의 추가 세분화는 남아 있음

### Hidden debugging risk

- 브라우저 세션 불안정과 생성 실패가 같은 에러 코드로 뭉치면 재현 비용 증가

## 2. Genspark

### Legacy behavior

- GPT 이후 image prompt로 바로 시작
- 모델/카테고리별 분기 존재
- 이미지 suffix: `_GENS_N`, `_GEN_2`

### Current runtime_v2 status

- stage2 worker 존재
- live attach evidence 확보
- `agent-browser` opt-in 가능

### Functional validation status

- `Functionally-verified`
- evidence:
  - `system/runtime_v2_probe/genspark-functional-02/exports/genspark.png`
  - `system/runtime_v2_probe/genspark-functional-02/functional_evidence/final_screen.png`
  - `system/runtime_v2_probe/genspark-functional-02/functional_evidence/evidence.json`

### Remaining gaps

- 레거시의 카테고리별 분기(`인물`, `도표`, `슬라이드` 등)는 아직 contract 차원에서 축약 상태
- 생성 실패/세션 제한/다운로드 실패 분리 부족
- exploratory helper 결과를 canonical stage2 adapter path에 올릴지 별도 검증 필요

### Hidden debugging risk

- 같은 prompt라도 모델 분기 누락으로 결과 품질 drift 가능

## 3. TTS (`qwen3_tts`)

### Legacy behavior

- `voice_texts.json` 또는 `voice_texts.txt` 직접 소비
- 결과로 `voice/#NN.flac`, `voice/#NN.txt`, `#00.txt` 생성

### Current runtime_v2 status

- worker 존재
- `voice_texts` direct-consume 추가 완료

### Functional validation status

- `Functionally-verified`
- evidence:
  - `system/runtime_v2_probe/qwen3-functional-01/episode/voice/#01.flac`
  - `system/runtime_v2_probe/qwen3-functional-01/episode/voice/#02.flac`
  - `system/runtime_v2_probe/qwen3-functional-01/episode/voice/#00.txt`
  - `system/runtime_v2_probe/qwen3-functional-01/result.json`
- note:
  - canonical worker path evidence: `system/runtime_v2_probe/qwen3-canonical-03/`
  - handoff-derived downstream real-run evidence: `system/runtime_v2_probe/downstream-real-qwen3-01/`

### Remaining gaps

- 현재 남은 항목은 active blocker가 아니라 follow-up optimization 성격입니다.
- adapter command 기반 success 외에 실제 출력 폴더 규약(`voice/#NN`, `#00.txt`)을 더 강제할지는 후속 판단 범위입니다.
- line 단위 subtitle/txt 산출물 계약과 legacy output 메타(`voice folder` manifest 등)를 canonical completion schema에 더 반영할지는 후속 판단 범위입니다.
- worker-level/1회 downstream closeout은 확보됐고, full orchestration parity만 후속 범위로 남습니다.

### Hidden debugging risk

- downstream(`Kenburn`, `RVC`)가 실제 기대하는 `voice` 폴더 규약과 어긋나면 뒤에서 터질 수 있음

## 4. GeminiGen

### Legacy behavior

- 선행 이미지 필요
- `_GEMI.mp4` 산출

### Current runtime_v2 status

- stage2 worker 존재
- live attach evidence 확보

### Functional validation status

- `Functionally-verified (exploratory evidence)`
- evidence:
  - `system/runtime_v2_probe/geminigen-functional-02/video/#01_GEMI.mp4`
  - `system/runtime_v2_probe/geminigen-functional-03/result.json`

### Current blocker note

- direct helper inspection 기준 현재 페이지에서 첫 번째로 노출되는 이미지가 실제 생성 산출물이 아니라 사이트 로고(`logo-with-text.png`)입니다.
- 따라서 current helper 단독으로는 truthful functional evidence를 만들 수 없습니다.
- exploratory evidence는 legacy batch 경로를 통해 확보했습니다.
- 남은 일은 실제 생성 산출물 선택 규칙을 `runtime_v2` canonical helper에 흡수하는 것입니다.

### Remaining gaps

- 입력 이미지 선택 우선순위는 구현됐지만, 실제 legacy prompt JSON completeness와 1:1인지 미확인
- `_GEMI.mp4` 외 부가 산출물/요약 메타는 축약됨

### Hidden debugging risk

- 이미지 선택 우선순위 drift 시 결과 품질과 후속 RVC 입력이 흔들릴 수 있음

## 5. Canva

### Legacy behavior

- `Title for Thumb` 필수
- `Ref Img 1` 우선
- `THUMB.png` 출력

### Current runtime_v2 status

- worker 존재
- live attach evidence 확보
- `title_for_thumb`, `ref_img_1`, `ref_img_2` direct-consume 추가 완료

### Functional validation status

- `Functionally-verified`
- evidence:
  - `system/runtime_v2_probe/canva-functional-03/exports/THUMB.png`
  - `system/runtime_v2_probe/canva-functional-03/functional_evidence/final_screen.png`
  - `system/runtime_v2_probe/canva-functional-03/functional_evidence/evidence.json`

### Remaining gaps

- legacy의 `parse_thumb_data()`는 `bg_prompt`, `line1`, `line2` 규칙이 더 풍부함
- 현재는 multiline 분리 수준까지만 반영

### Hidden debugging risk

- 썸네일 텍스트 규칙이 풍부해질수록 line split 규칙 drift 가능

## 6. Kenburn

### Legacy behavior

- 이미지 + Voice 둘 다 필요
- suffix 우선순위 이미지 선택
- 최종 mp4 출력

### Current runtime_v2 status

- worker 존재
- ffmpeg silent render + optional mux 구현

### Functional validation status

- `Functionally-verified`
- evidence:
  - `system/runtime_v2_probe/kenburn-functional-03/artifacts/kenburns/kenburn-func-03/kenburns.mp4`
  - `system/runtime_v2_probe/kenburn-functional-03/result.json`
- note:
  - current evidence는 synthetic single-scene input 기준입니다.
  - legacy full `scene_bundle_map` orchestration parity는 여전히 남아 있습니다.

### Remaining gaps

- legacy의 `scene_bundle_map`, 이미지 suffix 우선순위, 음성 길이 합산 전략이 현재 worker 단일 입력(`source_path`, `audio_path`)에 축약됨
- 즉, “한 장면 단위 ffmpeg 래퍼”는 구현됐지만, 레거시 bundle orchestration은 아직 별도 계층 필요

### Hidden debugging risk

- 실제 다중 장면/다중 이미지 세트에서 현재 단순 worker만으로는 legacy 동작과 차이 커질 수 있음

## 7. RVC

### Legacy behavior

- TTS 원본 또는 `_GEMI.mp4` 기반
- `voice`/`video` 폴더 규약 강함
- 변환 후 후처리(`replace_audio_and_trim`) 연동

### Current runtime_v2 status

- worker 존재
- explicit adapter command 경로 검증 완료

### Functional validation status

- `Functionally-verified`
- evidence:
  - `system/runtime_v2_probe/rvc-functional-01/output.flac`
  - `system/runtime_v2_probe/rvc-functional-01/stdout.txt`
  - `system/runtime_v2_probe/rvc-functional-01/stderr.txt`
- note:
  - canonical worker path evidence: `system/runtime_v2_probe/rvc-canonical-04/`

### Remaining gaps

- 현재 worker는 `source_path` + `model_name` 중심으로 축약돼 있고, legacy의 `video_folder` / `voice_folder` 후처리 규약을 전부 품고 있지 않음
- 즉, 단일 변환 contract는 있으나 legacy full pipeline orchestration은 미구현
- `_GEMI.mp4` source mode와 `tts-source` mode를 현재 worker에서 분리해 canonicalize할 필요가 있음
- source mode 분리와 후처리 orchestration은 여전히 남아 있습니다.

### Hidden debugging risk

- 실제 `_GEMI.mp4` 기반 경로와 TTS 기반 경로를 같은 worker 하나로 쓰면 입력 종류 혼합에서 오류 가능

## Cross-Cutting Hidden Risks

### 1. Bridge contract risk

- `stage1_handoff`가 richer해졌지만, 아직 각 downstream worker가 필요한 모든 필드를 동일 수준으로 직접 소비하는 것은 아님

### 2. Failure-mode risk

- 1차 보완 완료:
  - `run_verified_adapter_command()`가 표준 실패 코드를 직접 반환하도록 보강됨
  - 현재 반영 코드:
    - `ADAPTER_TIMEOUT`
    - `ADAPTER_NOT_FOUND`
    - `ADAPTER_NONZERO_EXIT`
    - `OUTPUT_PATH_INVALID`
    - `OUTPUT_OUTSIDE_ROOT`
    - `OUTPUT_NOT_CREATED`
    - `OUTPUT_UNCHANGED_REUSED` (`ok=true` 재사용 분류)
- 남은 일:
  - 더 많은 worker에 서비스별 세분화 코드를 보조 필드로 추가
  - failure matrix 문서와 테스트를 서비스 단위로 더 넓힘

### 3. Long-run stability risk

- browser/service adapter의 장기 재시도/중복 실행/아티팩트 누수는 아직 비-GPT 범위에서도 완전히 닫혔다고 보기 어려움

## Conclusion

- 비-GPT 범위는 “기반 contract/worker 준비”는 많이 끝났습니다.
- 하지만 “실제로 전체가 동작한다”고 하긴 아직 이릅니다.
- 현재 시점에서 더 정확한 표현은 다음과 같습니다.
  - `SeaArt`, `Genspark`, `TTS`, `GeminiGen`, `Canva` -> mostly `Contract-verified`
  - `Kenburn`, `RVC` -> mostly `Implemented`
  - **비-GPT 전체 완료 아님**
- 가장 큰 남은 비-GPT gap은 아래 두 가지입니다.

1. **worker별 richer field direct-consume를 더 확대**
   - 특히 `TTS`, `Canva`, 이후 `Kenburn`, `RVC`

2. **서비스별 failure matrix를 코드/테스트에 반영**
   - adapter/browser/session/input/artifact 오류를 더 세분화
   - 공통 adapter failure matrix 1차는 반영됨

3. **서비스별 functional verification evidence를 따로 확보**
   - 최소 1개 row/asset 기준으로 실제 산출물 evidence 확보
   - 이 evidence가 없으면 `done`으로 올리지 않음

## Immediate Next Non-GPT Steps

1. `Kenburn` 입력을 `scene_bundle_map`/multi-image 기준으로 분해할지 결정
2. `RVC`를 `tts-source` / `gemi-video-source` 두 모드 계약으로 나눌지 결정
3. 서비스별 canonical error code matrix 문서화
4. 프로그램별 `Functionally-verified` evidence 확보 전까지 비-GPT 완료 주장 금지

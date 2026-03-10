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

- `Contract-verified`
- adapter/attach 경로는 확인했지만, 실제 row 기반 end-to-end image generation은 아직 최종 evidence로 닫히지 않음

### Remaining gaps

- 레거시의 카테고리별 분기(`인물`, `도표`, `슬라이드` 등)는 아직 contract 차원에서 축약 상태
- 생성 실패/세션 제한/다운로드 실패 분리 부족

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

- `Contract-verified`
- `voice_texts` direct-consume 테스트는 있음
- 하지만 실제 legacy output 규약(`voice/#NN.flac`, `#NN.txt`, `#00.txt`) 기준 기능 동작 evidence는 아직 없음

### Remaining gaps

- 현재는 adapter command 기반 success 중심 검증이고, 실제 출력 폴더 규약(`voice/#NN`, `#00.txt`) 자체를 강제하지 않음
- line 단위 subtitle/txt 산출물 계약이 아직 worker completion schema에 반영되지 않음

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

- `Contract-verified`
- 실제 row 기반 이미지->video end-to-end evidence는 아직 없음

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

- `Contract-verified`
- thumb_data/ref_img direct-consume 테스트는 있음
- 실제 `THUMB.png` 산출 evidence는 아직 별도 필요

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

- `Implemented`
- 단일 입력 ffmpeg worker는 있으나, legacy `scene_bundle_map`/multi-image orchestration 기준 기능 동작 검증은 부족

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

- `Implemented`
- explicit adapter path는 검증됐지만, legacy full path(`tts-source` / `_GEMI.mp4` source / replace_audio_and_trim`) 기준 기능 동작은 아직 미검증

### Remaining gaps

- 현재 worker는 `source_path` + `model_name` 중심으로 축약돼 있고, legacy의 `video_folder` / `voice_folder` 후처리 규약을 전부 품고 있지 않음
- 즉, 단일 변환 contract는 있으나 legacy full pipeline orchestration은 미구현

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

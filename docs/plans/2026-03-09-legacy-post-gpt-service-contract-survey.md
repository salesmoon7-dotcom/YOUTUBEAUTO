# Legacy Post-GPT Service Contract Survey

## Goal

- 레거시 프로그램 기준으로 `GPT 이후 어떤 상황에 어떤 프로그램이 가동되는지`를 서비스별 계약으로 고정합니다.
- 조사 순서는 사용자 요청대로 `SeaArt -> Genspark -> TTS -> GeminiGen -> Canva -> Kenburn -> RVC`입니다.
- 각 단계마다 `선행 조건`, `입력`, `출력`, `성공/실패 마커`, `다음 단계 handoff`를 정리합니다.

## Scope Note

- 이 문서는 **레거시 계약 조사 문서**입니다. 구현 문서가 아닙니다.
- 나열 순서는 조사 순서이며, 실제 파이프라인에서 반드시 strict serial order를 뜻하지는 않습니다.
- 특히 `SeaArt`와 `Genspark`는 둘 다 GPT 이후 이미지 생성 단계이며, 서로의 산출물을 직접 선행 조건으로 요구하지 않습니다.
- 반대로 `Canva`, `Kenburn`, `RVC`는 명확한 선행 산출물 의존이 있습니다.

## Shared Legacy Premise After GPT

### Canonical state store

- 레거시의 canonical state는 Excel입니다.
- 기준 파일 예시: `4 머니.xlsx`
- ChatGPT 단계가 먼저 Excel row에 다음 필드를 채웁니다.
  - `Title`
  - `Title for Thumb`
  - `Voice`
  - `Description`
  - `Keywords`
  - scene / video prompt 컬럼들

### Episode folder convention

- 이후 단계는 대부분 `download/<채널명>/<에피소드폴더>/...` 구조를 기준으로 파일을 읽고 씁니다.
- 대표 하위 폴더/파일:
  - 이미지: `images/*.png` 또는 episode 루트의 `#NN_*.png`
  - 음성: `voice/#NN.flac`, `voice/#NN.txt`, `voice/#00.txt`
  - 썸네일: `THUMB.png`
  - 비디오: `video/#NN_GEMI.mp4`, `video/#NN.mp4`, `#NN.mp4`

## 1. SeaArt

### Source

- `D:/YOUTUBE_AUTO/scripts/seaart_automation.py`

### Start conditions

- GPT 이후 이미지 프롬프트 컬럼이 준비되어 있어야 합니다.
- 스크립트 주석 기준 입력은 `엑셀 파일의 이미지 프롬프트(#11~마지막 열)`입니다.
- SeaArt 브라우저 세션이 디버그 포트로 살아 있어야 합니다.
  - 설정 포트: `seaart_chrome`
- 서비스 중복 실행 락이 비어 있어야 합니다.
  - `system/state/seaart_run.lock`

### Input contract

- Excel row에서 scene/image prompt를 읽습니다.
- 채널별 Excel 파일을 사용합니다.
  - 예: 채널 4 -> `4 머니.xlsx`
- 모델 URL/모드는 설정된 SeaArt model(`Z`, `FLUX`)에 따라 갈립니다.

### Output contract

- 이미지 출력 파일을 다운로드 폴더/에피소드 폴더에 저장합니다.
- 모델 suffix 계약:
  - `_SEA_Z`
  - `_SEA_2`

### Success markers

- 이미지 다운로드 파일 존재
- 결과 JSON 요약 기록
- 진행 상황 JSON 갱신

### Failure / block markers

- 브라우저 연결 실패
- 세션 락 존재
- DOM/생성 timeout
- 생성 실패 또는 다운로드 실패

### Handoff

- 후속 이미지/비디오 단계는 SeaArt 산출물(`_SEA_Z`, `_SEA_2`)을 참조 이미지 후보로 사용합니다.
- 특히 GeminiGen과 Kenburn은 이미지 우선순위 집합에서 SeaArt 출력을 소비할 수 있습니다.

## 2. Genspark

### Source

- `D:/YOUTUBE_AUTO/scripts/genspark_automation.py`

### Start conditions

- GPT 이후 scene/image prompt가 준비되어 있어야 합니다.
- 주석 기준 입력은 `엑셀 파일의 이미지 프롬프트(#11~마지막 열)`입니다.
- Genspark Edge 디버그 포트 세션이 살아 있어야 합니다.
  - 설정 포트: `genspark_edge`

### Input contract

- Excel 기반 이미지 프롬프트
- 카테고리별 모델 분기
  - `인물`, `글자`, `도표`, `도표-슬라이드` 등
- 일부 단계는 AI Slides URL을 별도 사용합니다.

### Output contract

- episode 폴더에 이미지 파일 저장
- 주요 suffix:
  - `_GENS_N`
  - `_GEN_2`

### Success markers

- 다운로드/저장된 PNG 존재
- 세션 제한 미발생
- 결과 JSON/로그 기록

### Failure / block markers

- 세션 제한 배너 감지
- 생성 오류 키워드 감지
- 브라우저 연결 실패
- 다운로드 실패

### Handoff

- `Canva`의 참조 이미지 탐색은 우선 `Ref Img 1_GENS*.png`를 찾습니다.
- `GeminiGen`, `Kenburn`도 Genspark 출력 이미지를 주요 입력 후보로 사용합니다.

## 3. TTS

### Source

- `D:/YOUTUBE_AUTO/scripts/qwen3_tts_automation.py`

### Start conditions

- GPT 이후 voice/script handoff가 준비되어 있어야 합니다.
- episode 폴더에 아래 중 하나가 있어야 합니다.
  - `voice_texts.json`
  - `voice_texts.txt`

### Input contract

- `voice_texts.json`
  - list 또는 `{ "texts": [...] }`
- fallback: `voice_texts.txt`
  - 줄 단위 텍스트 -> `#01`, `#02` 식으로 매핑
- JSON 기반 실행에서는 `row_data["voice_texts"]`를 직접 사용 가능

### Output contract

- `voice/` 폴더에 오디오 파일 생성
  - `#NN.flac` 또는 `#NN.wav`
- 같은 텍스트의 subtitle txt 생성
  - `#NN.txt`
- 전체 대본 파일 생성
  - `#00.txt`

### Success markers

- `voice` 폴더 생성
- 각 line별 오디오 파일 생성
- `#00.txt` 생성

### Failure / block markers

- `voice_texts` 없음
- JSON row 미존재
- 모델 로드 실패
- 생성 예외

### Handoff

- `Kenburn`은 음성 길이를 맞추기 위해 `voice/#NN.*`를 읽습니다.
- `timeline_generator.py`와 subtitle/sync 계열도 `voice` 폴더를 읽습니다.
- `RVC`는 원본 TTS 결과(`voice/#NN.flac`)를 후속 입력으로 사용합니다.

## 4. GeminiGen

### Source

- `D:/YOUTUBE_AUTO/scripts/geminigen_automation.py`

### Start conditions

- 선행 이미지가 준비되어 있어야 합니다.
- 명시적 JSON prompt 파일 실행 계약이 우선입니다.
  - 예: `--json prompts/ch4_row0_geminigen.json`
- 주석 기준으로 `이미지 -> 동영상` 생성이며 `first_frame = last_frame`를 전제합니다.

### Input contract

- prompt JSON
- 이미지 입력 후보는 suffix 우선순위로 찾습니다.
  - `_GEN_2`
  - `_SEA_2`
  - `_GENS_N`
  - `_SEA_Z`
  - `""`

### Output contract

- `video/{output_file}`
- 대표 suffix: `_GEMI.mp4`

### Success markers

- `_GEMI.mp4` 생성
- 결과 JSON summary 기록

### Failure / block markers

- 계정/세션 문제
- high traffic / cooldown
- 이미지 입력 누락
- generation timeout

### Handoff

- `RVC`는 `_GEMI.mp4`를 직접 찾습니다.
- render/후처리 계층도 `_GEMI.mp4`를 최종 비디오 소스로 사용합니다.

## 5. Canva

### Source

- `D:/YOUTUBE_AUTO/scripts/canva_automation.py`

### Start conditions

- GPT 이후 `Title for Thumb`가 준비되어 있어야 합니다.
- 가능하면 선행 참조 이미지가 있어야 합니다.
  - `Ref Img 1`
  - 실제 파일 탐색은 `Ref Img 1_GENS*.png` 우선
- Canva 브라우저 세션이 살아 있어야 합니다.

### Input contract

- 필수: `Title for Thumb`
  - `parse_thumb_data()`가 아래를 분해합니다.
    - `bg_prompt`
    - `line1`
    - `line2`
- 선택: `Ref Img 1`
  - `find_ref_image(channel, row)`로 찾음
- 실행 인자:
  - `--channel`
  - `--row` (0-based)
  - `--thumb-data` or `--thumb-data-file`
  - `--ref-img`

### Output contract

- episode 폴더의 `THUMB.png`

### Success markers

- `THUMB.png` 다운로드 및 이동 성공
- 결과 JSON에 `thumbnail_path` 기록

### Failure / block markers

- `Title for Thumb` 없음 / 파싱 실패
- 브라우저 연결 실패
- 디자인 페이지 이동 실패
- 다운로드 실패

### Handoff

- review/manifests, 업로드, 최종 패키징 단계가 `THUMB.png`를 소비합니다.

## 6. Kenburn

### Source

- `D:/YOUTUBE_AUTO/scripts/ken_burns_effect.py`

### Nature of component

- 독립 브라우저 자동화 프로그램이 아니라 FFmpeg 래퍼 모듈입니다.

### Start conditions

- **이미지 선행 조건 필수**
  - 이미지 폴더 존재
  - scene key 기준 이미지 파일 존재 (`#NN_*.png` 등)
- **Voice 선행 조건 필수**
  - `voice/` 폴더 존재 또는 명시적 audio folder 존재
  - scene key 기준 audio 파일 존재 (`#NN.wav`, `#NN.flac` 등)
- `scene_bundle_map`이 있어야 합니다.
  - 누락 시 즉시 중단

### Input contract

- `batch_process_with_audio(image_folder, audio_folder, output_folder, scene_bundle_map, ...)`
- 이미지 key와 오디오 key를 맞춰 길이를 합산한 뒤 영상 길이를 결정합니다.
- 이미지 suffix 우선순위:
  - `_GEN_2`
  - `_SEA_2`
  - `_GENS_N`
  - `_SEA_Z`

### Output contract

- key별 `#NN.mp4`

### Success markers

- 출력 mp4 생성
- 기존 mp4가 있으면 스킵 처리도 성공으로 간주

### Failure / block markers

- 이미지 폴더 없음
- 오디오 폴더 없음
- `scene_bundle_map` 누락
- FFmpeg/FFprobe 실패

### Handoff

- Kenburn 결과 mp4는 최종 render/합성 계층으로 전달됩니다.
- 일부 후속 오디오 치환 단계에서 `replace_audio_and_trim`류 함수를 사용합니다.

## 7. RVC

### Source

- `D:/YOUTUBE_AUTO/scripts/rvc_voice_convert.py`

### Start conditions

- **선행 비디오 또는 선행 TTS가 필요합니다.**
- 두 경로가 존재합니다.

#### 7-A. Gemini video 기반 경로

- 입력: `video/` 폴더 내 `_GEMI.mp4`
- 함수: `convert_gemini_voices(video_folder, ...)`
- 이 경로는 `_GEMI.mp4`에서 오디오를 추출해 voice 폴더로 보냅니다.

#### 7-B. TTS 원본 기반 경로

- 입력: `voice/` 폴더 내 원본 TTS `#NN.flac`
- 함수: `find_tts_files(voice_folder, video_folder, ...)`
- 이미 `_RVC.mp4`, `_GEMI.mp4`, `#NN_GEMINI.flac`가 있으면 스킵합니다.

### Input contract

- Applio 설정/모델 파일 존재
- ffmpeg 존재
- RVC model(`pth`, optional `index`) 존재
- Gemini 기반 경로는 `video/_GEMI.mp4`
- TTS 기반 경로는 `voice/#NN.flac`

### Output contract

- Gemini 기반:
  - sibling `voice/` 폴더에 `#NN_GEMI.<fmt>` 계열 산출물
- TTS 기반:
  - `#NN_GEMINI.flac` 같은 변환 파일
- 추가 후처리:
  - `replace_audio_and_trim`
  - `replace_gemini_audio_and_trim`

### Success markers

- 출력 WAV/FLAC 존재
- 변환 마커 생성 가능

### Failure / block markers

- Applio config/model 없음
- ffmpeg 없음
- `_GEMI/_GEMINI` 계약 위반 혼재
- 오디오 추출 실패 / 변환 실패

### Handoff

- RVC 결과는 최종 음성 치환/트림 후 render 또는 배포 단계로 이어집니다.

## Cross-Service Dependency Summary

### GPT 이후 바로 가능한 단계

- `SeaArt`
- `Genspark`
- `TTS`

이 세 단계는 GPT가 채운 Excel/JSON 필드를 직접 입력으로 받습니다.

### 선행 이미지가 있어야 가능한 단계

- `GeminiGen`
- `Canva`
- `Kenburn`

설명:
- `GeminiGen`은 이미지 -> 동영상 단계입니다.
- `Canva`는 `Title for Thumb` + `Ref Img 1` 참조 이미지가 있으면 가장 좋습니다.
- `Kenburn`은 이미지 없이는 시작 자체가 불가능합니다.

### 선행 Voice 또는 Video가 있어야 가능한 단계

- `Kenburn` (voice 길이 필요)
- `RVC` (원본 TTS 또는 `_GEMI.mp4` 필요)

## Practical Contract Interpretation For Runtime_v2

레거시 기준으로 보면, GPT 이후 후속 단계는 다음처럼 해석하는 것이 가장 정확합니다.

1. GPT는 단순 topic planner가 아니라 downstream 필드를 채우는 canonical producer입니다.
2. 이미지 단계(`SeaArt`, `Genspark`)와 음성 단계(`TTS`)는 GPT 직후 독립적으로 시작 가능합니다.
3. `Canva`, `GeminiGen`, `Kenburn`, `RVC`는 모두 선행 산출물 의존이 있으므로 “나중 단계”입니다.
4. 따라서 `runtime_v2` 테스트 준비도는 stage1 parsed handoff가 이 downstream 필드를 얼마나 제대로 채우는지에 달려 있습니다.

## Immediate Follow-up Recommendation

- `runtime_v2`에서 다음으로 필요한 것은 레거시 조사 문서 기준 downstream field matrix를 만드는 것입니다.
- 특히 아래 필드를 canonical handoff에 포함시키는 것이 중요합니다.
  - `title`
  - `title_for_thumb`
  - `description`
  - `keywords`
  - `voice_groups` / `voice_texts`
  - scene prompt fields (`#01`, `#02`, ...)
  - reference image fields (`Ref Img 1`, `Ref Img 2`)
  - optional `bgm`

# SOP: Chat Interruption Repo Triage

## Purpose

- 이 문서는 `D:\YOUTUBEAUTO`에서 채팅/UI interruption이 반복될 때, repo 구조 문제를 빠르게 점검하는 triage 순서를 고정합니다.
- 기본 원칙은 `source-only 검색`, `generated runtime tree 분리`, `interrupt-safe 모드 우선`입니다.

## Triage Order

1. **workspace size 확인**
   - 대형 디렉터리(`runtime_v2/`, `system/`, `tmp_*/`) 크기를 먼저 확인합니다.
2. **repo-root runtime data 확인**
   - `runtime_v2/sessions/`, `system/runtime_v2_probe/`, `system/runtime_v2/logs/` 아래에 generated data가 다시 쌓였는지 봅니다.
3. **dirty/clutter 확인**
   - `git status --short`로 active source 변경 외에 root-level `tmp_*`, patch, log clutter가 남았는지 확인합니다.
4. **broad search suppression 적용**
   - 기본 검색에서 아래 경로를 제외합니다:
     - `runtime_v2/sessions/`
     - `system/runtime_v2_probe/`
     - `system/runtime_v2/logs/`
     - `tmp_*/`
   - `system/runtime_v2/`는 broad search가 아니라 운영 스냅샷 확인 대상으로 두고, 필요한 파일만 직접 읽습니다.
5. **interrupt-safe 모드 전환**
   - 병렬 도구 호출 중단
   - 도구 1개씩 실행
   - pytest는 케이스 단위만 실행
   - 파일 단위/대묶음 foreground pytest는 중단
   - stdout/stderr/result 파일을 남기는 detached log-producing execution으로 전환
   - 실브라우저 relaunch/recovery는 detached 또는 수동 경로로만 수행

## Notes

- probe/evidence 조사가 목적일 때만 generated tree를 명시적으로 다시 포함합니다.
- 과거 probe evidence의 기본 legacy 위치는 `D:/YOUTUBEAUTO_RUNTIME/probe/legacy_runtime_v2_probe/`입니다.
- `runtime_v2` 채팅 세션에서 long/file-level foreground pytest는 triage 완료 전 기본 금지입니다.
- repo-root dependency triage는 최소 4개 표면을 구분해 봅니다: browser session root, runtime state files, worker artifact/output paths, test temp roots.
- browser session root가 외부화되었다고 해서 runtime state/artifact 기본값까지 외부화되었다고 가정하지 않습니다.

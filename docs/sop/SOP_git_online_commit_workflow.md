# SOP: Git Online Commit Workflow

## Purpose

- 이 문서는 `D:\YOUTUBEAUTO`에서 이미 한 번 성공한 온라인 Git 연결/커밋 방식을 표준 절차로 고정합니다.
- 목표는 두 가지입니다.
  - Git 연결/커밋 때문에 개발 시간을 빼앗기지 않기
  - 다음 세션에서도 같은 성공 경로를 반복 사용하기

## Canonical Successful Baseline

- 현재 성공 상태의 기준은 아래와 같습니다.
  - local repo: `D:\YOUTUBEAUTO`
  - remote: `https://github.com/salesmoon7-dotcom/YOUTUBEAUTO.git`
  - default branch: `main`
  - upstream tracking: `main -> origin/main`
- 로컬 근거:
  - `D:\YOUTUBEAUTO\.git\config`
  - `D:\YOUTUBEAUTO\.git\HEAD`
- 레거시 참고 패턴:
  - `D:\YOUTUBE_AUTO\.git\config`

## First Successful Method From This Conversation

- 이 섹션은 `최초 연결 성공` 또는 `원격/브랜치가 꼬였을 때의 복구 절차`를 기록한 것입니다.
- 즉, 매번 반복하는 운영 절차가 아니라 초기 셋업/복구용 기준입니다.
- 실제 최초 성공 순서는 아래였습니다.
  1. 레거시 저장소 `D:\YOUTUBE_AUTO\.git\config`에서 기존 remote 패턴을 먼저 확인
  2. 현재 저장소는 레거시와 같은 원격을 공유하지 않고 `분리`하기로 결정
  3. 새 원격 저장소 URL을 `https://github.com/salesmoon7-dotcom/YOUTUBEAUTO.git`로 고정
  4. `D:\YOUTUBEAUTO`의 `origin`을 위 URL로 연결
  5. 로컬 기본 브랜치 기준을 `main`으로 정렬하고, `HEAD`를 `refs/heads/main`으로 맞춤
  6. `[branch "main"]`의 upstream을 `origin/main` 기준으로 맞춤
  7. 원격 GitHub repo 생성 후 first push 성공
- 일상적인 Git 작업은 아래 `Daily Online Commit Path`를 따릅니다.

## Source Evidence

- `D:\YOUTUBEAUTO\.git\config`
  - `[remote "origin"]`
  - `url = https://github.com/salesmoon7-dotcom/YOUTUBEAUTO.git`
  - `[branch "main"]`
  - `remote = origin`
  - `merge = refs/heads/main`
- `D:\YOUTUBEAUTO\.git\HEAD`
  - `ref: refs/heads/main`
- 세션 근거:
  - 이전 작업 기록에 `main -> origin/main` push 성공과 first push 성공이 남아 있음

## Official Basis

- GitHub Docs: remote repository 관리
  - `git remote add origin https://github.com/OWNER/REPOSITORY.git`
  - `git remote set-url origin https://github.com/OWNER/REPOSITORY.git`
- GitHub Docs: HTTPS credential caching
  - GitHub는 HTTPS 사용 시 GitHub CLI 또는 Git Credential Manager 사용을 권장
- Git Credential Manager README
  - Windows에서 HTTPS remote를 사용할 때 Git이 GCM을 암묵 호출하고, 이후 인증을 재사용함

## Standard Workflow

### 1. Repo Identity Check

- 먼저 아래 3가지만 확인합니다.
  - 현재 작업 폴더가 `D:\YOUTUBEAUTO`인지
  - `.git\config`의 `origin`이 `https://github.com/salesmoon7-dotcom/YOUTUBEAUTO.git`인지
  - `.git\HEAD`가 `refs/heads/main`인지
- 이 3개가 맞으면, 새로운 Git 초기화나 별도 원격 재설정부터 시작하지 않습니다.
- 즉, 이 상태면 이미 초기 셋업은 끝난 상태로 보고 바로 일상 커밋 경로로 갑니다.

### 1-1. Remote Decision Rule

- 이 규칙은 `최초 셋업` 또는 `복구`에만 적용합니다.
- 이 저장소에서 remote 관련 작업을 새로 잡아야 할 때는 먼저 레거시 저장소 설정을 참고만 합니다.
  - 참고 경로: `D:\YOUTUBE_AUTO\.git\config`
- 하지만 결론은 항상 분리 원격 기준입니다.
- 즉, 레거시 remote를 그대로 공유하지 않고 현재 저장소 전용 remote를 사용합니다.

### 2. Remote/Branch Standard

- 이 저장소의 표준은 항상 아래입니다.
  - remote name: `origin`
  - remote URL: `https://github.com/salesmoon7-dotcom/YOUTUBEAUTO.git`
  - branch: `main`
  - tracking: `origin/main`
- 레거시 저장소와 같은 원격을 공유하지 않습니다.
- 이 저장소는 레거시와 분리된 별도 GitHub repo를 기준으로 운영합니다.

### 2-1. First Setup Replay Rule

- remote/upstream이 비어 있거나 꼬였을 때만, 일반 Git 실험을 하지 말고 최초 성공 순서를 그대로 재연합니다.
  1. 레거시 remote 패턴 확인
  2. 분리 원격 유지 결정 확인
  3. `origin = https://github.com/salesmoon7-dotcom/YOUTUBEAUTO.git` 적용
  4. `HEAD -> main` 정렬 확인
  5. `branch.main -> origin/main` 추적 확인
  6. 필요한 경우에만 first push 경로로 복구
- 이 재연 절차는 `기본 운영 경로`가 아니라 `초기 셋업/복구 경로`입니다.

### 3. Daily Online Commit Path

- 초기 셋업이 이미 끝난 상태에서는 아래만 따르면 됩니다.
  1. `origin` 확인
  2. `main` 확인
  3. `origin/main` 추적 확인
  4. 변경 상태 확인
  5. staging
  6. commit
  7. push
- 즉, 일상 작업은 말씀하신 대로 `연결부터 push까지`의 짧은 경로가 표준입니다.

### 3-1. Windows Plain Git Wrapper

- `bash` 실행기에서 Unix형 `export ...` 프리픽스가 섞이는 세션에서는 루트의 `git_plain.bat`를 우선 사용합니다.
- 이 래퍼는 내부적으로 `scripts/git_plain.py`를 호출하고, Python `subprocess.run(["git", ...], shell=False)`로 셸 문법 없이 Git만 직접 실행합니다.
- 예시:
  - `git_plain.bat status --short`
  - `git_plain.bat add AGENTS.md docs/INDEX.md`
  - `git_plain.bat commit -m "docs: add windows plain git wrapper"`
- 즉, Windows에서 plain Git 실행 경로를 강제로 고정해야 할 때의 기본 우회 경로입니다.

### 4. Authentication Standard

- 온라인 커밋/푸시는 Windows HTTPS + Git Credential Manager 기준으로 처리합니다.
- 원칙:
  - HTTPS remote를 유지합니다.
  - 인증 helper는 GCM 재사용을 전제로 합니다.
  - 인증이 이미 성공한 환경이면 매 세션마다 자격 증명 설정 작업을 반복하지 않습니다.
- 실패 시에도 먼저 remote/branch mismatch를 확인하고, 인증 재설정은 마지막 단계에서만 봅니다.

### 5. Online Commit Flow

- 온라인 커밋 전에 먼저 아래만 확인합니다.
  - `origin` URL이 맞는지
  - 현재 branch가 `main`인지
  - 추적 브랜치가 `origin/main`인지
- 위 3개 중 하나라도 틀리면, 바로 commit/push로 가지 말고 `First Successful Method From This Conversation`의 `초기 셋업/복구 절차`를 먼저 재적용합니다.
- 그다음 순서는 아래로 고정합니다.
  1. 변경 상태 확인
  2. 원자 단위로 staging
  3. semantic English commit message로 commit
  4. 필요 시 push
- 이 저장소의 commit style 기본값은 영어 semantic style입니다.
  - 예: `docs: add runtime_v2 plans and operating docs`
  - 예: `feat: import runtime_v2 control plane and tests`
  - 예: `chore: tighten repo ignore rules for local runtime state`

### 6. Time-Saving Rule

- Git 때문에 시간을 낭비하지 않으려면, 세션마다 아래를 새로 고민하지 않습니다.
  - 어떤 remote를 쓸지
  - 어떤 branch를 기준으로 할지
  - HTTPS를 쓸지 SSH를 쓸지
  - 레거시 repo와 합칠지 분리할지
- 그리고 실패 시에도 새 방법을 즉흥적으로 시도하지 않습니다. 먼저 이 채팅에서 성공한 `초기 셋업/복구 순서`를 재연합니다.
- 이 항목들은 이미 결정되었고, 기본값은 아래로 고정입니다.
  - `origin`
  - `https://github.com/salesmoon7-dotcom/YOUTUBEAUTO.git`
  - `main`
  - Windows HTTPS + GCM

## Do Not Re-Decide

- 아래는 매 세션 다시 의사결정하지 않습니다.
  - remote URL
  - branch name
  - tracking branch
  - online auth 방식
- 바꾸는 경우는 아래뿐입니다.
  - 사용자가 명시적으로 다른 remote를 요구한 경우
  - GitHub repo 자체가 변경된 경우
  - 보안/권한 이슈로 HTTPS 경로를 유지할 수 없는 경우

## Fast Failure Checks

- 온라인 커밋/푸시가 막히면 아래 순서로만 봅니다.
  1. `origin` URL mismatch
  2. `HEAD` not `main`
  3. `branch.main` upstream missing
  4. credential prompt / token expiry
- 위 1~3이 맞으면, 그다음에만 인증 문제를 봅니다.
- 즉, 실패 시 첫 조치는 새 git 방법 검색이 아니라 `최초 성공 순서 재연`입니다.

## Tooling Failure Gate (Windows Native)

- win32 네이티브 환경에서 Git 명령이 아래 오류로 즉시 죽으면, 이것은 Git 실패가 아니라 실행 도구 계층 실패로 분류합니다.

```text
'export' is not recognized as an internal or external command,
operable program or batch file.
```

- 이 오류가 보이면 현재 실행 컨텍스트는 `cmd.exe` 계열인데, 호출 앞에 Unix형 `export ...` 프리픽스가 붙어 있는 상태입니다.
- 이 상태에서는 `git status`, `git add`, `git commit`, `git push`를 계속 재시도해도 성공하지 않습니다.
- 즉시 따라야 할 규칙은 아래입니다.
  1. Git 설정 문제로 오진하지 않습니다.
  2. remote/branch/auth를 다시 뒤섞어 고치지 않습니다.
  3. 먼저 `순수 git ...`만 실행되는 컨텍스트를 복구합니다.
  4. 그 뒤에만 `Daily Online Commit Path`로 돌아갑니다.

## Known Root Cause In This Conversation

- 이 채팅에서 earlier 구간의 실제 성공은 `순수 git 실행` 컨텍스트에서 일어났습니다.
- later 구간의 반복 실패는 모든 호출이 사실상 `export ...; git ...` 형태로 들어가 win32 셸에서 선행 `export`에서 즉시 죽은 것입니다.
- 따라서 현재 대화 기준 근본원인은 `Git 저장소/remote/branch`가 아니라 `실행 컨텍스트 드리프트`입니다.

## Recovery Rule For This Specific Failure

- `'export' is not recognized`가 보이면, 새 Git 방법을 계속 시도하지 않습니다.
- 성공 조건은 하나입니다.
  - `export` 프리픽스가 사라진 `순수 git 실행 컨텍스트`를 복구하는 것
- 이 조건이 복구되면, 이후 절차는 다시 아래 짧은 경로로 충분합니다.
  1. `origin` 확인
  2. `main` 확인
  3. `origin/main` 추적 확인
  4. staging
  5. commit
  6. push
- OpenCode/Windows 세션에서 plain `git ...` 직접 호출이 계속 불안정하면, 대체 경로로 `git_plain.bat ...`를 사용합니다.
- 이 경로는 셸 프리픽스를 우회하기 위한 저장소 로컬 래퍼이며, Git 설정 자체를 바꾸지 않습니다.

## Current Session Verification Note

- 이 문서 업데이트 시점의 fresh evidence 기준으로, `bash` 직접 경로는 여전히 `export ...` 프리픽스 때문에 신뢰할 수 없었습니다.
- 하지만 저장소 로컬 래퍼 `git_plain.bat` 경로로는 same-session 검증이 실제로 성공했습니다.
- 확인 증거:
  - `python "D:\YOUTUBEAUTO\scripts\git_plain.py" status --short` 성공
  - `D:\YOUTUBEAUTO\git_plain.bat status --short` 성공
  - `python -m py_compile "D:\YOUTUBEAUTO\scripts\git_plain.py"` 성공
  - 아래 3개 commit이 같은 세션에서 실제 생성됨
    1. `15f3c0b` `docs: wire runtime guardrails into verify entrypoint`
    2. `911181d` `docs: route runtime sessions through guardrails`
    3. `a3b03ef` `docs: define runtime readiness and guardrails`
- 따라서 이 세션에서 확인된 사실은 아래와 같습니다.
  - Git 저장소/remote/branch 자체가 아니라 `bash -> win32 cmd.exe` 실행 경로가 문제임
  - Windows에서는 `git_plain.bat ...` 또는 `scripts/git_plain.py ...`가 재현 가능한 성공 경로임

## Confirmed Successful Recovery Path

- `bash` 직접 호출이 `export` 프리픽스로 오염된 세션에서는 아래 순서로 복구합니다.
  1. `git_plain.bat status --short`
  2. `git_plain.bat branch --show-current`
  3. `git_plain.bat rev-parse --abbrev-ref @{upstream}`
  4. `git_plain.bat add ...`
  5. `git_plain.bat commit -m "..."`
  6. `git_plain.bat status --short`
- 즉, 이 대화 기준으로 이미 검증된 Windows 성공 경로는 `bash` 직접 Git가 아니라 저장소 로컬 plain Git 래퍼입니다.

## Anti-Mistype Rule For Wrapper Commits

- 아래 복구 구간에서는 명령 앞뒤에 어떤 프리픽스도 추가하지 않습니다.
  - 금지 예: `export ...`, `set ... &&`, `$env:...;`, `cmd /c ...`, `bash -lc ...`
- 즉, `git_plain.bat ...` 자체를 명령의 시작으로 두고 그대로 복붙합니다.
- 특히 OpenCode 세션에서는 환경변수 보정용 프리픽스를 수동으로 붙이지 않습니다.

## Exact Copy-Paste Block For The Remaining Wrapper Commit

- 마지막 래퍼 묶음 commit은 아래 블록만 그대로 사용합니다.

```bat
cd /d D:\YOUTUBEAUTO
git_plain.bat add docs/sop/SOP_git_online_commit_workflow.md git_plain.bat scripts/git_plain.py
git_plain.bat commit -m "docs: add windows plain git wrapper workflow" -m "Provide a repo-local wrapper that runs git without shell prefixes so Windows sessions can recover from export-prefixed command failures." -m "Ultraworked with [Sisyphus](https://github.com/code-yeongyu/oh-my-opencode)" -m "Co-authored-by: Sisyphus <clio-agent@sisyphuslabs.ai>"
git_plain.bat status --short
git_plain.bat log -4 --oneline
```

- 위 블록은 수정하지 않고 그대로 실행하는 것을 기본값으로 삼습니다.

## Non-Goals

- 이 문서는 SSH 전환 절차를 기본 경로로 채택하지 않습니다.
- 이 문서는 레거시 repo와의 통합 운영을 표준으로 삼지 않습니다.
- 이 문서는 force push, history rewrite, global git config 변경을 기본 절차에 넣지 않습니다.

## Related Files

| File | Purpose |
|------|---------|
| `D:\YOUTUBEAUTO\.git\config` | 현재 성공한 remote/upstream 기준 |
| `D:\YOUTUBEAUTO\.git\HEAD` | 현재 기본 branch 기준 |
| `git_plain.bat` | Windows에서 plain Git 실행을 고정하는 로컬 래퍼 |
| `scripts/git_plain.py` | shell=False로 Git를 직접 호출하는 Python 진입점 |
| `D:\YOUTUBE_AUTO\.git\config` | 레거시 repo 비교 기준 |
| `AGENTS.md` | 세션 라우팅 진입점 |
| `docs/INDEX.md` | canonical docs 진입점 |

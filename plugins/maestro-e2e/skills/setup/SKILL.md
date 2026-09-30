---
name: setup
description: >-
  Android(Compose)·iOS(SwiftUI) 앱에 Maestro E2E 테스트를 새로 도입할 때 사용합니다. "마에스트로 도입해줘",
  "E2E 테스트 붙여줘", "Maestro 세팅해줘", "UI 자동화 테스트 CI에 넣어줘" 같은 요청이 해당됩니다.
  Setting up Maestro end-to-end tests in an Android or iOS app — shared test ids, a test-mode
  launch flag, smoke/release flows, an emulator CI job, and gating releases on it.
metadata:
  category: testing
  status: draft
---

# Maestro E2E 도입

한 번에 다 하지 않습니다. **4단계로 나누고 단계마다 PR 하나**를 냅니다. 앞 단계가 머지돼야
다음 단계가 의미를 가집니다.

## 시작 전에 확인할 것

코드를 읽고 아래를 먼저 정리해 사용자에게 보여 줍니다. 추측으로 채우지 말고 모르면 묻습니다.

- **플랫폼과 UI**: Android(Compose)만인지, iOS(SwiftUI)도 있는지. 둘 다면 같은 id로 Flow 하나를 공유한다.
  Android는 composition 루트가 몇 개인지 본다. `setContent`와 레이아웃에 끼운 `ComposeView`마다 루트가
  따로라 id 노출 설정도 그만큼 필요하다(`references/test-ids.md`).
- **테스트를 막는 것**: 광고 동의(UMP) 창, 전면·보상형 광고, 온보딩, 권한 요청, 강제 업데이트,
  로그인·본인인증. 이것들을 끄는 테스트 모드가 1단계의 핵심이다(`references/test-mode.md`).
- **광고**: 자동화가 실제 광고를 노출하거나 누르면 무효 트래픽이다. debug 빌드가 테스트 광고 단위만
  쓰는지 확인한다. 광고 SDK·오퍼월 SDK마다 테스트 모드가 따로 있으니 SDK별로 본다.
- **네트워크 의존**: 서버 없이 뜨는 화면과, 서버 응답이 있어야 뜨는 화면을 나눈다. 앞은 `smoke`,
  뒤는 `release` 태그가 된다.
- **CI**: GitHub Actions인지 GitLab CI인지, 러너가 KVM을 쓸 수 있는지. 에뮬레이터를 못 띄우면
  3단계 방식이 달라진다.
- **기기**: 연결된 실기기가 있는지(Android `adb devices`, iOS `xcrun devicectl list devices`). 실기기에
  스토어판이 깔려 있으면 개발 빌드와 서명이 달라 덮어쓸 수 없고, 지우면 사용자 데이터가 사라진다.
  **지우기 전에 반드시 묻는다.** iOS는 시뮬레이터에서 돌리는 경우가 많다(`references/ios.md`).

## 1단계 — 앱을 테스트 가능하게

- 첫 화면 기준점, 하단 탭, 핵심 버튼에 **id**를 붙인다. 규칙은 `references/test-ids.md`.
  두 플랫폼이 다 있으면 양쪽에 같은 이름을 붙인다.
- **테스트 모드 실행 인자**(예: `UI_TESTING`)를 받아 막는 것들을 끈다. Android는 **디버그 빌드에서만** 받는다
  (`references/test-mode.md`).
- 계산 결과처럼 손으로 옮긴 id 매핑이 있으면 유닛 테스트로 값을 고정한다.
- 완료 기준: 각 플랫폼 기기에서 `maestro hierarchy --compact`로 id가 보이고, 인자를 넘겨 실행하면
  막던 화면이 뜨지 않는다. 인자 없이 실행하면 원래대로 뜬다.

## 2단계 — Flow와 MCP

- `templates/maestro/`를 저장소 루트의 `.maestro/`로 복사한다. `launch_clean.yaml`의 기준점 id를 바꾼다.
- `smoke` 2~3개(앱 실행, 서버 없이 되는 핵심 동작, 탭 이동)와 `release` 1~2개로 시작한다.
- `templates/mcp.json`을 `.mcp.json`으로 둔다. Flow는 MCP로 기기를 조작하며 만들고 CLI로 확정한다.
- 이 저장소의 `.claude/skills/`에 **그 프로젝트의 id 표**를 남긴다. 이 플러그인에는 넣지 않는다.
- 두 플랫폼이 다 있으면 **양쪽에서 모두** 통과해야 2단계가 끝난다. iOS 빌드·실행은 `references/ios.md`.
- 작성·실행 규칙은 같은 플러그인의 `flows` 스킬을 따른다.

## 3단계 — CI에 smoke

- GitHub Actions: `references/ci-github-actions.md`와 `templates/github/`, `templates/scripts/`.
- GitLab CI: `references/ci-gitlab.md`. KVM 러너가 없으면 인프라 결정이 먼저라 사용자에게 넘긴다.
- PR마다 `smoke`만 돌린다. 앱과 무관한 경로만 바꾼 PR은 건너뛴다.
- 템플릿은 Android 에뮬레이터 기준이다. iOS CI는 검증된 구성이 없다(`references/ios.md`의 "iOS CI").
- 완료 기준: CI에서 **두 번 이상** 통과. 첫 실행은 에뮬레이터 캐시가 없어 느리다.

## 4단계 — 릴리스 관문

- 릴리스 빌드·스토어 업로드·QA 배포 job이 `smoke` job을 기다리게 한다.
- `release` Flow는 CI에서 돌리지 않는다. 릴리스 전 **태그 커밋의 debug 빌드로 실기기에서** 돌리는
  절차를 저장소 문서에 적는다.
- **릴리스 빌드에는 Maestro를 돌리지 않는다.** 테스트 모드를 디버그에서만 받으므로 실제 광고가 뜬다.

## 하지 않는 것

- 좌표(`point:`)로 누르는 Flow, 화면 문구(현지화된 글자)로 찾는 Flow를 만들지 않는다.
- 로그인·결제·본인인증처럼 되돌릴 수 없거나 운영 데이터를 바꾸는 흐름을 `smoke`에 넣지 않는다.
- 스토어판 앱을 묻지 않고 지우지 않는다. 잠긴 기기를 대신 풀지 않는다.

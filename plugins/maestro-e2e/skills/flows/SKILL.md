---
name: flows
description: >-
  Android·iOS 앱의 Maestro Flow(.maestro/)를 만들거나 수정·실행·리뷰하거나 실패 원인을 찾을 때 사용합니다.
  "smoke 테스트 만들어줘", "마에스트로 돌려줘", "이 화면 플로우 추가해줘", "마에스트로 플로우 리뷰해줘",
  "Maestro 테스트 왜 실패해" 같은 요청이 해당됩니다.
  Creating, running, reviewing, or debugging Maestro flows for an Android or iOS app — project analysis
  (app id, existing ids), smoke flow creation, selector rules, and triaging failures as flow, app, or environment.
metadata:
  category: testing
  status: draft
---

# Maestro Flow 작성·실행

저장소에 `.maestro/`가 아직 없으면 같은 플러그인의 `setup` 스킬부터 따른다.
그 프로젝트의 id 표와 태그 기준은 저장소의 `.claude/skills/`나 문서에 있다. 그것이 우선이다.

이 플러그인은 화면 작업 뒤에 Maestro를 저절로 돌리지 않는다. PR마다 도는 CI `smoke`가 팀 공통 관문이다.
CI에서 smoke를 못 돌리는 저장소는 그 저장소 문서의 릴리스 전 수동 실행 절차가 대신한다(`setup` 3단계).
로컬 기기에서는 사용자가 요청했거나 사용자의 지침이 그렇게 하라고 할 때 돌린다. 프로젝트 CLAUDE.md에
그런 규칙을 넣자고 제안하지 않는다.

## 먼저 프로젝트를 본다

Flow를 새로 만들기 전에 확인한다. 방법은 `references/project-analysis.md`.

- 플랫폼과 UI(Compose·SwiftUI)
- 플랫폼별 `APP_ID`: Android는 debug 빌드의 applicationId(`namespace` 아님), iOS는 Debug 빌드의 bundle id
- 기존 `.maestro/`의 구성: 테스트로 잡히는 위치, 공통 subflow, 태그, 변수. 있으면 그 구성을 따른다.
- 기존 id: **있는 id를 먼저 쓴다.** 없으면 붙일 위치와 이름을 제안하고 동의를 받은 뒤 붙인다.

## smoke 만들기

1. 위의 프로젝트 분석을 하고 결과를 짧게 보여 준다.
2. 서버 없이 되는 **핵심 사용자 흐름**을 고른다. 앱 실행과 첫 화면, 탭 이동, 그 앱의 핵심 동작 한두 개다.
   smoke는 PR마다 돌고 릴리스를 막는다. 3~5개로 시작하고, 더 늘릴 때는 개수가 아니라 CI 시간과 흔들림을 본다.
   새 smoke Flow는 CI에서 여러 번 통과한 것만 넣는다. 서버나 깊은 확인이 필요하면 `release`로 보낸다.
   처음 도입할 때는 2~3개로 시작한다(`setup` 2단계).
   로그인·결제·광고·되돌릴 수 없는 동작은 넣지 않는다. 고른 목록을 보여 준다.
3. 흐름마다 필요한 id를 확인한다. 없는 id는 제안부터 한다.
4. 공통 시작 subflow로 시작하고 `appId: ${APP_ID}`, `tags: [smoke]`를 단다. 이름과 위치는 기존 구성을 따른다.
   아래 작성 규칙을 지킨다.
5. 기기에서 CLI로 **처음부터 두 번 연속** 통과하는지 본다. 두 플랫폼이 다 있으면 양쪽에서 본다.
6. 실패하면 아래 "실패했을 때"로 원인을 판정한다. Flow 문제면 고치고, 앱 문제면 Flow로 가리지 말고 보고한다.

## 기기 고르기

- 바꾼 플랫폼에서 돌린다. 두 플랫폼 공통 Flow를 고쳤으면 양쪽 다 돌린다.
- **실기기가 연결돼 있으면 실기기로, 없으면 에뮬레이터·시뮬레이터로** 돌린다.
  - Android: `adb devices`에서 serial이 `emulator-`로 시작하지 않으면 실기기다.
  - iOS: `xcrun devicectl list devices`로 실기기를 본다. 설치된 Maestro 2.1.0 CLI는 iOS 대상을 시뮬레이터로만
    안내하므로, 실기기에서 안 되면 시뮬레이터로 돌리고 그렇게 했다고 보고한다.
- 에뮬레이터·시뮬레이터는 RAM·CPU를 많이 쓰니 다 쓰면 끈다(`adb emu kill`, `xcrun simctl shutdown all`).
- 실기기에 스토어판이 깔려 있으면 개발 빌드와 서명이 달라 덮어쓸 수 없다. **지우기 전에 묻는다.**
  지우면 그 기기의 앱 데이터가 사라진다.
- 잠금 화면이면 테스트가 실패한다. 잠금은 풀지 말고 사용자에게 요청한다.
- 기기가 없으면 건너뛰고, 건너뛰었다고 보고한다.

## 실행

```bash
maestro --device <serial 또는 udid> test .maestro -e APP_ID=<applicationId 또는 bundle id>
```

- `APP_ID`는 플랫폼마다 다르다. 대소문자까지 확인한다.
- iOS는 먼저 시뮬레이터용으로 빌드해 설치한다. 명령은 `setup` 스킬의 `references/ios.md`.
- 태그로 거른다: `--include-tags=smoke`. 실패 스크린샷을 남기려면 `--test-output-dir=<dir>`.
- 화면 계층: `maestro --device <serial> hierarchy --compact`. id가 실제로 어떻게 보이는지 여기서 확인한다.

## MCP로 Flow 만들기

Maestro MCP가 등록돼 있으면(`claude mcp list`에 `maestro`가 보이면. 저장소 `.mcp.json`이거나 local 등록이다):

1. `inspect_view_hierarchy`로 화면의 id를 확인한다.
2. `tap_on`·`run_flow`로 한 단계씩 조작해 본다.
3. 성공한 단계를 YAML로 옮기고 `check_flow_syntax`로 검사한다.
4. **CLI로 처음부터 다시** 돌려 통과를 확인한다. MCP로 한 번 된 것과 매번 되는 것은 다르다.

`query_docs`와 `cheat_sheet`는 Maestro Cloud API 키가 있어야 동작한다.

## 작성 규칙

- 모든 Flow는 `runFlow: ../subflows/launch_clean.yaml`로 시작한다. 중간에 앱을 지우고 다시 띄우지 않는다.
- **id로 찾는다.** 현지화된 화면 문구로 찾지 않는다. 언어와 무관한 글자(통화 코드, 숫자)는 괜찮다.
- `id:`와 글자 단언은 **전체 일치 정규식**이다. 기호가 든 id는 쓰지 않고, 글자 단언의 `.`은 `\\.`로 쓴다.
- 좌표(`point:`)로 누르지 않는다. 기다릴 때는 요소 기준(`extendedWaitUntil`)으로 기다린다.
- 매일 바뀌는 값(환율, 날짜, 잔액)은 값이 아니라 형식을 정규식으로 본다.
- 결과 숫자를 단언할 때 화면의 다른 글자(키패드 숫자, 탭 이름)와 겹치지 않는 값을 고른다.
- 태그는 `smoke`(서버 없이 통과, CI에서 실행)와 `release`(서버 필요, 릴리스 전 실기기) 둘만 쓴다.
- **광고를 누르거나 실제 광고를 노출하는 Flow를 만들지 않는다.** 릴리스 빌드에는 Maestro를 돌리지 않는다.
- 플랫폼마다 조작이 다르면 `runFlow: { when: { platform: Android|iOS }, commands: [...] }`로 나눈다.
  `back`은 Android 전용이다. iOS 시트는 닫기 버튼 id로 닫는다.

## 기존 Flow 리뷰

`references/review-checklist.md`의 항목으로 본다. 보고까지만 하고, 고치는 건 요청이 있을 때 한다.

## 실패했을 때

1. 실패 스크린샷을 먼저 본다. 기대한 화면이 떴는지, 팝업이 덮었는지.
2. 그 시점의 `hierarchy`에서 찾던 id가 있는지 본다. 없으면 id 누락이거나 별도 창(Dialog)이다.
3. 로그에서 앱 프로세스가 죽었는지, 테스트 모드 인자가 들어왔는지 본다. Android는 logcat(CI면 artifact의
   `logcat.txt`), iOS 시뮬레이터는 `xcrun simctl spawn <udid> log show`.
4. 증상이 `references/gotchas.md`에 있으면 그 대응을 따른다. 대기 시간을 늘리는 건 원인을 확인한 뒤에만.
5. 원인을 셋 중 하나로 판정한다. 헷갈리면 MCP나 손으로 같은 단계를 밟아 앱이 어떻게 움직이는지 본다.

| 판정 | 이럴 때 | 조치 |
| --- | --- | --- |
| **Flow** | 앱은 기대대로 움직이는데 Flow가 틀렸다. 잘못된 id·정규식, 기다림 부족, 플랫폼 차이 미처리, 앱이 일부러 거르는 조건에 걸림 | Flow를 고친다 |
| **앱** | 앱이 기대와 다르게 움직인다. 크래시, 잘못된 결과, 화면이 안 뜸, 코드에 id가 없거나 노출 설정이 빠짐 | 앱 코드를 고치거나 버그로 보고한다. 단언을 느슨하게 하거나 `optional`로 넘겨 가리지 않는다 |
| **환경** | 코드와 무관하다. 기기 잠김, 에뮬레이터 부하, 다른 빌드(스토어판)가 깔림, `APP_ID` 틀림, 서버·네트워크 장애(`release`) | 환경을 정리하고 다시 돌린다. 코드는 고치지 않는다 |

보고에는 판정, 근거(스크린샷·계층·로그에서 본 것 한 줄), 한 조치를 적는다.

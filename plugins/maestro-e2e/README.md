# maestro-e2e

Android·iOS 앱에 Maestro E2E 테스트를 도입하고 운영하는 절차. 두 플랫폼이 Flow 하나를 같이 씁니다.

```bash
claude plugin install maestro-e2e@ahn-cc-kit --scope project
```

## 언제 불리나

| 스킬 | 요청 예 | 직접 부르기 |
| --- | --- | --- |
| `setup` | "마에스트로 도입해줘", "E2E 테스트 CI에 넣어줘" | `/maestro-e2e:setup` |
| `flows` | "smoke 테스트 만들어줘", "마에스트로 돌려줘", "마에스트로 플로우 리뷰해줘", "Maestro 테스트 왜 실패해" | `/maestro-e2e:flows` |

## 무엇을 하나

- **도입을 4단계로 나눠 단계마다 PR을 냅니다**: 테스트 id와 테스트 모드 → Flow와 MCP → CI smoke → 릴리스 관문.
- 시작 전에 플랫폼(Android·iOS), 테스트를 막는 것(광고 동의, 광고, 온보딩), CI 환경, 연결된 기기를
  확인하고 사용자에게 보여 줍니다.
- 두 플랫폼에 같은 id를 붙여 Flow 하나로 양쪽을 돌립니다.
- Flow를 만들기 전에 프로젝트를 봅니다. 플랫폼별 `APP_ID`, 기존 `.maestro/` 구성, 이미 붙은 id를 찾고,
  있는 것을 먼저 씁니다. 없는 id는 위치와 이름을 제안한 뒤 붙입니다.
- 기존 Flow를 체크리스트로 리뷰하고, 실패는 **Flow·앱·환경** 중 무엇 때문인지 판정해 보고합니다.
  앱 버그를 Flow를 느슨하게 고쳐 가리지 않습니다.
- 실기기가 있으면 실기기로 돌립니다. 스토어판 앱을 지워야 하면 먼저 묻습니다.
- **화면 작업을 마칠 때 훅이 알립니다.** 이번 작업에서 화면 코드가 바뀌었으면 Claude가 마치려 할 때 Stop 훅이
  "smoke와 release를 돌리고 보고하라"고 한 번 알립니다. 새 화면 파일이 생겼으면 Flow를 만들지 판단해 묻게 합니다.
  실행은 Claude가 `flows` 스킬대로 하고, 기기나 넘길 변수가 없으면 건너뛰고 알립니다. 아래 "훅"을 보세요.
- 팀 공통 관문은 PR마다 CI에서 도는 `smoke`입니다.
- CI에서 smoke를 못 돌리면(KVM이 없는 GitLab 러너 등) 관문이 없다고 알리고, 러너를 둘지 릴리스 전 수동 실행으로
  갈지 사용자가 정하게 합니다.
- 실제로 CI를 멈추게 했던 원인(정규식 id, 권한 설정 때문의 APK 전송 멈춤, 데이터 삭제 직후 재실행 레이스,
  부팅 직후 에뮬레이터 부하)을 피하는 템플릿을 씁니다.

## 전제

- **Android는 Compose, iOS는 SwiftUI** 화면을 다룹니다. XML 레이아웃에 `ComposeView`로 끼운 Compose 화면도
  포함합니다.
- iOS는 **시뮬레이터 기준**입니다. 설치된 Maestro 2.1.0 CLI는 iOS 대상을 시뮬레이터로만 안내합니다.
- Maestro CLI 2.1.0에서 확인한 동작을 기준으로 합니다(`maestro --version`). 다른 버전이면 id 매칭과
  `launchApp` 기본값부터 다시 확인하세요.
- CI 템플릿은 **GitHub Actions의 Android 에뮬레이터**용입니다. GitLab CI와 iOS CI는 문서만 있고 **실제
  파이프라인에서 검증하지 않았습니다**. GitLab 러너에서 에뮬레이터를 띄우려면 KVM이 필요해 인프라 결정이 먼저입니다.
- 이 플러그인은 절차와 규칙만 담습니다. **프로젝트의 id 표와 Flow는 그 저장소에 둡니다.**

## 훅

| 훅 | 언제 | 하는 일 | opt-out |
| --- | --- | --- | --- |
| `flow-reminder` | UserPromptSubmit | 지금 화면 파일 상태를 턴 시작 기록으로 남깁니다. 아무것도 출력하지 않습니다 | `MAESTRO_E2E_DISABLE_FLOW_REMINDER` |
| `flow-reminder` | Stop | 이번 턴에 바뀐 화면 파일이 있으면 마치지 말고 Maestro를 돌리라고 알립니다(exit 2) | 위와 같음 |

- **화면 파일**: 저장소 루트에 `.maestro/`가 있을 때, 커밋하지 않은 `.kt` 중 `@Composable`이 든 것, `.swift` 중
  SwiftUI `View`가 든 것. 테스트·`build/` 경로는 뺍니다. `.maestro/`가 없는 저장소에서는 아무것도 하지 않습니다.
- **이번 턴에 바뀐 것만** 봅니다. 미리 고쳐 둔 화면 파일이 있는 저장소에서 질문만 했는데 기기 테스트가 시작되지
  않게 하려는 것입니다. 세션 중간에 켜서 턴 시작 기록이 없으면 커밋하지 않은 화면 변경 전체를 봅니다.
- 한 번 알리면 같은 턴에는 다시 알리지 않습니다. 알림 때문에 이어서 일하는 중(`stop_hook_active`)에도 알리지 않습니다.
- Maestro를 훅이 직접 돌리지 않습니다. 기기 선택, 스토어판 확인, 변수가 없는 Flow 건너뛰기는 스킬의 절차입니다.
- 필요: `bash`, `git`. `jq`는 쓰지 않습니다. 턴 시작 기록은 `.git/maestro-e2e-turn-start`에 둡니다.

```bash
MAESTRO_E2E_DISABLE_FLOW_REMINDER=1 claude
```

```bash
python3 plugins/maestro-e2e/hooks/test_hooks.py
```

## 상태

`draft`입니다. Android·iOS 앱 저장소 하나(GitHub Actions)에서 4단계를 모두 거쳐 CI 관문까지 운영한 구성을 일반화했고,
다른 저장소에 이 플러그인만으로 적용해 본 적은 아직 없습니다.

## 구성

```text
hooks/
├── hooks.json                       UserPromptSubmit(턴 시작 기록), Stop(알림)
├── flow-reminder.sh
└── test_hooks.py                    임시 git 저장소로 상태별 판정을 고정
skills/setup/
├── SKILL.md                         도입 4단계, 시작 전 확인 사항
├── references/
│   ├── test-ids.md                  id 규칙(Compose·SwiftUI), Maestro의 id 매칭 방식
│   ├── test-mode.md                 테스트 모드 실행 인자(Android extra, iOS 실행 인자)
│   ├── ios.md                       시뮬레이터 빌드·실행, 플랫폼별 조작, iOS CI (미검증)
│   ├── ci-github-actions.md         CI job 구성과 안정화 장치의 이유
│   └── ci-gitlab.md                 GitLab 선택지와 함정 (미검증)
└── templates/
    ├── maestro/                     config.yaml, subflows/launch_clean.yaml, flows/ 예시
    ├── github/e2e-jobs.yml          기존 워크플로에 붙일 job 두 개
    ├── scripts/                     emulator-settle.sh, maestro-smoke.sh
    └── mcp.json                     Maestro MCP 팀 파일(.mcp.json)용. local 등록이면 쓰지 않음
skills/flows/
├── SKILL.md                         프로젝트 분석, smoke 만들기, 기기 선택, 실행, 작성 규칙, 실패 판정
└── references/
    ├── project-analysis.md          APP_ID 찾기, 기존 .maestro·id 확인, 없는 id 제안
    ├── review-checklist.md          기존 Flow 리뷰 항목과 보고 형식
    ├── when-to-add-flow.md          새 화면에 Flow를 만들지, 기존 Flow에 단계만 넣을지, 만들지 않을지
    └── gotchas.md                   증상 → 원인 → 대응
```

## 필요한 것

- [Maestro CLI](https://maestro.dev) (`maestro`), Java 17
- Android: Android SDK의 `adb`
- iOS: Xcode(`xcodebuild`, `xcrun simctl`)
- MCP로 Flow를 만들려면 `maestro mcp` 등록. 기본은 local 등록(`claude mcp add maestro -- maestro mcp`)이고,
  팀원 모두가 Maestro를 쓸 때만 `.mcp.json`으로 커밋합니다(`templates/mcp.json`)

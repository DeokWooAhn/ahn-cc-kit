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
- 팀에 거는 규칙은 **CI에서 도는 `smoke`** 하나입니다. 화면을 고칠 때마다 기기에서 Maestro를 돌리라는 규칙을
  프로젝트 CLAUDE.md에 넣지 않습니다. 기기 실행은 요청할 때만 하고, 매번 돌리고 싶은 사람은 개인 지침
  (`~/.claude/CLAUDE.md`)에 둡니다.
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

## 상태

`draft`입니다. Android·iOS 앱 저장소 하나(GitHub Actions)에서 4단계를 모두 거쳐 CI 관문까지 운영한 구성을 일반화했고,
다른 저장소에 이 플러그인만으로 적용해 본 적은 아직 없습니다.

## 구성

```text
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
    └── gotchas.md                   증상 → 원인 → 대응
```

## 필요한 것

- [Maestro CLI](https://maestro.dev) (`maestro`), Java 17
- Android: Android SDK의 `adb`
- iOS: Xcode(`xcodebuild`, `xcrun simctl`)
- MCP로 Flow를 만들려면 `maestro mcp` 등록. 기본은 local 등록(`claude mcp add maestro -- maestro mcp`)이고,
  팀원 모두가 Maestro를 쓸 때만 `.mcp.json`으로 커밋합니다(`templates/mcp.json`)

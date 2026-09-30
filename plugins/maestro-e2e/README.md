# maestro-e2e

Android·iOS 앱에 Maestro E2E 테스트를 도입하고 운영하는 절차. 두 플랫폼이 Flow 하나를 같이 씁니다.

```bash
claude plugin install maestro-e2e@ahn-cc-kit --scope project
```

## 언제 불리나

| 스킬 | 요청 예 | 직접 부르기 |
| --- | --- | --- |
| `setup` | "마에스트로 도입해줘", "E2E 테스트 CI에 넣어줘" | `/maestro-e2e:setup` |
| `flows` | "마에스트로 돌려줘", "이 화면 플로우 만들어줘", "Maestro 테스트 왜 실패해" | `/maestro-e2e:flows` |

## 무엇을 하나

- **도입을 4단계로 나눠 단계마다 PR을 냅니다**: 테스트 id와 테스트 모드 → Flow와 MCP → CI smoke → 릴리스 관문.
- 시작 전에 플랫폼(Android·iOS), 테스트를 막는 것(광고 동의, 광고, 온보딩), CI 환경, 연결된 기기를
  확인하고 사용자에게 보여 줍니다.
- 두 플랫폼에 같은 id를 붙여 Flow 하나로 양쪽을 돌립니다.
- 실기기가 있으면 실기기로 돌립니다. 스토어판 앱을 지워야 하면 먼저 묻습니다.
- 도입할 때 프로젝트 CLAUDE.md에 **"화면 코드를 바꾼 작업은 마치기 전에 Maestro를 돌린다"** 규칙을 넣습니다.
  스킬 설명만으로는 에이전트가 E2E를 떠올리지 않으면 돌지 않아서, 매 세션 읽히는 CLAUDE.md에 둡니다.
  기기가 없으면 건너뛰고 건너뛰었다고 알립니다.
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
    ├── claude-md-rule.md            프로젝트 CLAUDE.md에 넣을 "화면 작업 뒤 Maestro 실행" 규칙
    └── mcp.json                     Maestro MCP 등록
skills/flows/
├── SKILL.md                         기기 선택, 실행, MCP 작성 절차, 작성 규칙, 실패 조사 순서
└── references/gotchas.md            증상 → 원인 → 대응
```

## 필요한 것

- [Maestro CLI](https://maestro.dev) (`maestro`), Java 17
- Android: Android SDK의 `adb`
- iOS: Xcode(`xcodebuild`, `xcrun simctl`)
- MCP로 Flow를 만들려면 저장소의 `.mcp.json`에 `maestro mcp` 등록(`templates/mcp.json`)

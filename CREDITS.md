# Credits

이 저장소에 들어온 외부 유래 구성 요소의 출처를 기록합니다.

## android-review

`android` CLI 사용법은 설치된 CLI의 `android skills --help`, `android skills add --help`,
`android skills list` 출력을 직접 확인해 적었습니다. Gradle 데몬 관련 내용은
[Gradle 공식 문서](https://docs.gradle.org/current/userguide/gradle_daemon.html)가 출처입니다.

## android-guard · git-guard

훅 계약 — `${CLAUDE_PLUGIN_ROOT}` 경로, exit 2 차단, stdin을 먼저 비운 뒤 opt-out 확인,
훅별 `*_DISABLE_*` 환경 변수, 경고는 `hookSpecificOutput.additionalContext` JSON —
은 [cc-agents-kit](https://github.com/AndrewDongminYoo/cc-agents-kit)의 `guard-hooks`
플러그인(Apache-2.0)에서 확립된 방식을 따른 것입니다.

같은 규약을 쓰는 이유는 함께 설치해도 충돌하지 않게 하기 위해서입니다.
셸 스크립트와 테스트 하네스는 직접 작성했습니다. 코드를 파생시키면 Apache-2.0 고지를
여기에 추가합니다.

`gradle-cache-guard`가 안내하는 데몬 확인 순서도 위 Gradle 공식 문서가 출처입니다.

## 구조 참고

- [AndrewDongminYoo/cc-agents-kit](https://github.com/AndrewDongminYoo/cc-agents-kit) — Apache-2.0.
  "플러그인 하나는 문제 하나" 원칙, `CREDITS.md`를 두는 관례, 훅마다 테스트를 두는 관례
- [taehwandev/tao-agent-os](https://github.com/taehwandev/tao-agent-os) —
  스킬 프론트매터에 `status`를 두어 성숙도를 표시하는 관례

## maestro-e2e

동작 설명은 설치된 [Maestro CLI](https://github.com/mobile-dev-inc/maestro)(Apache-2.0) 2.1.0의 `--help` 출력과,
Android 에뮬레이터·실기기와 iOS 26 시뮬레이터에서 직접 돌려 본 결과로 적었습니다. `id:` 전체 일치 매칭,
`launchApp` 권한 기본값이 APK 전송을 일으키는 것, iOS 실행 인자 전달과 `tabItem` id 전달이 여기에 해당합니다. Maestro 코드는 가져오지 않았습니다.

CI 템플릿은 [android-emulator-runner](https://github.com/ReactiveCircus/android-emulator-runner)(Apache-2.0)를
Action으로 **사용**할 뿐 코드를 포함하지 않습니다. 템플릿 스크립트와 Flow는 작성자의 다른 저장소에서 쓰던 것을
일반화했습니다.

## explain-diff

[Geoffrey Litt의 explain-diff gist](https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524)에서
페이지 구성(배경·직관·코드·퀴즈 5문항), 날짜로 시작하는 파일명을 저장소 밖에 두는 방식, 그림 원칙(그림 종류를 몇 가지로
정해 되풀이, ASCII 그림 금지, 코드 블록 줄바꿈 확인)을 가져왔습니다. gist에 라이선스 표기가 없어 원문은 옮기지 않고
한국어로 새로 썼습니다. Notion 버전은 가져오지 않았습니다. 퀴즈 골격 코드와 점검 목록은 직접 작성했습니다.
퀴즈 정답이 보기의 위치나 길이로 드러나지 않게 하는 규칙은 같은 gist 댓글(Butanium, fm1randa)의 지적을 반영했습니다.

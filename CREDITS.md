# Credits

이 저장소에 들어온 외부 유래 구성 요소의 출처를 기록한다.

## android-review

리뷰 기준과 체크리스트는 저자가 사내 Android 프로젝트에서 쓰던 프로젝트 스킬을 일반화한 것이다.
프로젝트 고유의 클래스명·모듈명·문서 참조를 걷어내고, XML/ViewBinding 항목을 제거한 뒤
Compose 기준으로 다시 썼다.

`android` CLI 사용법은 설치된 CLI의 `android skills --help`, `android skills add --help`,
`android skills list` 출력을 직접 확인해 적었다. Gradle 데몬 관련 내용은
[Gradle 공식 문서](https://docs.gradle.org/current/userguide/gradle_daemon.html)가 출처다.

## android-guard · git-guard

훅 계약 — `${CLAUDE_PLUGIN_ROOT}` 경로, exit 2 차단, stdin을 먼저 비운 뒤 opt-out 확인,
훅별 `*_DISABLE_*` 환경 변수, 경고는 `hookSpecificOutput.additionalContext` JSON —
은 [cc-agents-kit](https://github.com/AndrewDongminYoo/cc-agents-kit)의 `guard-hooks`
플러그인(Apache-2.0)에서 확립된 방식을 따른 것이다.

같은 규약을 쓰는 이유는 함께 설치해도 충돌하지 않게 하기 위해서다.
셸 스크립트와 테스트 하네스는 직접 작성했다. 코드를 파생시키면 Apache-2.0 고지를 여기에 추가한다.

`gradle-cache-guard`가 안내하는 데몬 확인 순서도 위 Gradle 공식 문서가 출처다.

## 구조 참고

- [AndrewDongminYoo/cc-agents-kit](https://github.com/AndrewDongminYoo/cc-agents-kit) — Apache-2.0.
  "플러그인 하나는 문제 하나" 원칙, `CREDITS.md`를 두는 관례, 훅마다 테스트를 두는 관례
- [taehwandev/tao-agent-os](https://github.com/taehwandev/tao-agent-os) —
  스킬 프론트매터에 `status`를 두어 성숙도를 표시하는 관례

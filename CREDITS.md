# Credits

이 저장소에 들어온 외부 유래 구성 요소의 출처를 기록한다.

## android-review

리뷰 기준과 체크리스트는 저자가 사내 Android 프로젝트에서 쓰던 프로젝트 스킬을 일반화한 것이다.
프로젝트 고유의 클래스명·모듈명·문서 참조를 걷어내고, XML/ViewBinding 항목을 제거한 뒤
Compose 기준으로 다시 썼다.

### using-android-skills (AndrewDongminYoo)

`SKILL.md`의 다음 두 절은 [AndrewDongminYoo](https://github.com/AndrewDongminYoo)가 작성한
`using-android-skills` 스킬 문서에서 얻은 내용을 바탕으로 한다.

- "Gradle·R8·플랫폼 정책 변경은 Google 스킬을 먼저 본다" — `android skills add`가 positional
  인자를 받고 문서의 `--skill` 플래그는 실재하지 않는다는 점, per-project 설치 원칙
- "Gradle 캐시 관련 오류를 만나면" — 캐시 오류가 대개 stale 데몬이라는 점,
  `~/.gradle/caches`를 지우지 말 것, `GRADLE_USER_HOME`을 먼저 확인할 것

표현은 새로 썼고 개인 환경에 종속된 경로·프로젝트명·날짜는 옮기지 않았다.

**이 문서는 [cc-agents-kit](https://github.com/AndrewDongminYoo/cc-agents-kit)의 공개
저장소에는 포함돼 있지 않다.** 즉 그 저장소의 Apache-2.0이 이 문서에 그대로 적용된다고
가정할 수 없다. **공개 배포 전에 원저자에게 사용 허락과 표기 방식을 확인한다.**

## android-guard · git-guard

훅 계약 — `${CLAUDE_PLUGIN_ROOT}` 경로, exit 2 차단, stdin을 먼저 비운 뒤 opt-out 확인,
훅별 `*_DISABLE_*` 환경 변수, 경고는 `hookSpecificOutput.additionalContext` JSON —
은 [cc-agents-kit](https://github.com/AndrewDongminYoo/cc-agents-kit)의 `guard-hooks`
플러그인(Apache-2.0)에서 확립된 방식을 따른 것이다.

같은 규약을 쓰는 이유는 함께 설치해도 충돌하지 않게 하기 위해서다.
셸 스크립트와 테스트 하네스는 직접 작성했다. 코드를 파생시키면 Apache-2.0 고지를 여기에 추가한다.

`gradle-cache-guard`가 안내하는 내용(캐시 오류는 대개 stale 데몬, `~/.gradle/caches`를 지우지
말 것, `GRADLE_USER_HOME` 확인)은 위 `using-android-skills` 항목과 같은 출처다.

## 구조 참고

- [AndrewDongminYoo/cc-agents-kit](https://github.com/AndrewDongminYoo/cc-agents-kit) — Apache-2.0.
  "플러그인 하나는 문제 하나" 원칙, `CREDITS.md`를 두는 관례, 훅마다 테스트를 두는 관례
- [taehwandev/tao-agent-os](https://github.com/taehwandev/tao-agent-os) —
  스킬 프론트매터에 `status`를 두어 성숙도를 표시하는 관례

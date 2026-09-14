---
name: review
description: >-
  Android/Kotlin(Compose) 코드를 리뷰할 때 사용한다. "코드리뷰 해줘", "브랜치 변경분 리뷰해줘",
  "MR/PR 검토해줘", diff나 완료된 구현을 검토해 달라는 요청이 해당된다.
  Reviewing Kotlin, Jetpack Compose, coroutine, Hilt, Gradle, or AndroidManifest changes —
  correctness, regression risk, and resource lifetime over style.
metadata:
  category: code-quality
  status: stable
---

# Android Code Review

요청한 동작과 기존 아키텍처를 기준으로 변경분을 본다.

이 스킬은 **Compose 기준**이다. View 시스템(XML 레이아웃, ViewBinding, Fragment 렌더링)을
전제한 항목은 담지 않는다.

## 우선순위

1. 정확성 — 실제로 깨지는 시나리오가 있는가
2. 회귀 위험 — 기존 흐름을 건드렸는가
3. 범위 이탈 — 요청과 무관한 변경이 섞였는가
4. 보안 — secret, 토큰, 권한, exported 컴포넌트
5. 테스트 누락 — 바뀐 동작을 고정하는 테스트가 있는가, 그 테스트가 실제로 검증력이 있는가

주변 코드와 이미 일치하는 스타일에는 리뷰 노력을 쓰지 않는다.
프로젝트에 코딩 컨벤션 문서가 있으면 그것이 기준이다. 이 스킬은 그 위에서 실제로 문제가 되는 것만 본다.

## 대상 범위

우선 검토한다.

- Kotlin: `**/*.kt`, `**/*.kts`
- Gradle: `*.gradle`, `*.gradle.kts`, `libs.versions.toml`, `gradle.properties`
- `AndroidManifest.xml`, `proguard-rules.pro`
- 테스트: `src/test`, `src/androidTest`

제외한다.

- `build`, `.gradle`, `out`, `generated`
- `ksp`, `kapt`
- `R.java`, `BuildConfig.java`, `*.pb.kt`
- `gradle-wrapper.properties`

## 상태 관리 트랙을 먼저 확인한다

Compose 화면의 상태·일회성 이벤트 처리 방식은 프로젝트마다 다르다. **추측하지 않는다.**

| | StateFlow 직접 | Orbit MVI |
| --- | --- | --- |
| 상태 | `MutableStateFlow` + `asStateFlow()` | `ContainerHost` + `container()` |
| 상태 변경 | ViewModel 함수에서 `update { }` | `intent { reduce { } }` |
| 일회성 이벤트 | `Channel<UiEffect>` + `receiveAsFlow()` | Orbit `SideEffect` |
| 화면 수집 | `collectAsStateWithLifecycle()` | `collectAsState()` |

주변 화면이 쓰는 트랙을 따랐는지 보고, **두 트랙을 한 화면에서 섞었으면 지적한다.**
Orbit을 쓰면서 `Channel<UiEffect>`를 따로 만드는 코드가 대표적이다.

## 일회성 이벤트 수집

일회성 이벤트(토스트, 내비게이션, 다이얼로그)는 **`collectLatest` 계열로 수집하지 않는다.**
새 값이 오면 이전 블록이 취소되므로, suspend 지점이 있는 이벤트가 조용히 유실된다.
상태(state) 수집은 어느 쪽이든 괜찮다.

## 응답 형식

1. 발견한 문제를 심각도 순으로 먼저 제시한다.
2. 파일과 라인을 함께 적는다.
3. 동작 리스크, 테스트 누락, 유지보수 비용을 중심으로 설명한다.
4. 문제가 없으면 "큰 이슈 없음"이라고 명확히 말하고 남은 리스크만 짧게 적는다.
5. 단순 취향이나 불필요한 리팩터링을 필수 수정처럼 말하지 않는다. 심각도를 붙여 구분한다.

리뷰는 설명이 결과물이다. **사용자가 고쳐 달라고 하기 전에는 코드를 수정하지 않는다.**

## 상세 체크리스트

영역별로 깊게 볼 필요가 있을 때만 [references/review-rubric.md](references/review-rubric.md)를 읽는다.
전부 훑지 말고 변경분에 해당하는 절만 본다.

Kotlin, Coroutine, ViewModel, Compose, Compose 성능, 자원 수명, Hilt, Network/Data,
Gradle, Manifest 항목이 있다.

## Gradle·R8·플랫폼 정책 변경은 Google 스킬을 먼저 본다

diff가 AGP 업그레이드, R8/keep rule, targetSdk 상향과 edge-to-edge, intent/exported 보안,
Play 정책·빌링에 걸리면 **직접 조사하기 전에** Google이 배포하는 공식 스킬이 있는지 확인한다.
`android` CLI가 설치돼 있어야 한다.

```bash
android skills list
```

해당하는 스킬이 있으면 대상 저장소에 설치하고 그 `SKILL.md`를 읽은 뒤 리뷰를 이어간다.

```bash
android skills add <skill-name> --project <repo-root>
```

- 인자는 **positional**이다. 문서에 나오는 `--skill` 플래그는 CLI에 없다.
- `.claude/` 디렉터리가 있으면 `.claude/skills/`에 설치되고 Claude Code가 프로젝트 스킬로 바로 읽는다.
  다른 하네스용 사본이 함께 생길 수 있으니, 쓰지 않으면 지운다.
- **필요한 1~3개만, 프로젝트 범위로만 설치한다.** `--all`이나 user scope는 쓰지 않는다.
- 설치는 저장소에 추적 파일을 추가한다. 리뷰 보고에 그 사실을 적는다.
- 애매하게 걸치는 정도면 설치하지 말고 그냥 진행한다.

## Gradle 캐시 관련 오류를 만나면

리뷰 중 빌드를 돌리다 캐시 오류(`Could not read workspace metadata from …/metadata.bin`,
플러그인 해석 중 null `FileLock`, 빌드마다 다른 캐시가 사라짐)를 만나면 캐시 손상이 아니라
**캐시 변경 전에 뜬 오래된 데몬**이 원인인 경우가 대부분이다.

`./gradlew --stop`으로 먼저 정리한다. 이 명령은 wrapper가 쓰는 버전의 데몬만 멈추므로,
남는 게 있으면 `pkill -f GradleDaemon`을 쓴다. **`~/.gradle/caches`를 지우지 않는다.**
IDE는 별도의 Gradle 데몬을 자기 버전으로 띄우고 `--stop`이 닿지 않으니, 원인 후보에서 빼지 않는다.

Gradle 캐시 경로를 뒤질 일이 있으면 `echo $GRADLE_USER_HOME`을 먼저 확인한다.
`~/.gradle`이 아닐 수 있고, 빈 검색 결과를 "의존성이 해석된 적 없음"으로 읽으면 틀린다.

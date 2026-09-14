---
name: review
description: >-
  Android/Kotlin(Compose) 코드를 리뷰할 때 사용합니다. "코드리뷰 해줘", "브랜치 변경분 리뷰해줘",
  "MR/PR 검토해줘", diff나 완료된 구현을 검토해 달라는 요청이 해당됩니다.
  Reviewing Kotlin, Jetpack Compose, coroutine, Hilt, Gradle, or AndroidManifest changes —
  correctness, regression risk, and resource lifetime over style.
metadata:
  category: code-quality
  status: stable
---

# Android Code Review

요청한 동작과 기존 아키텍처를 기준으로 변경분을 봅니다.

이 스킬은 **Compose 기준**입니다. View 시스템(XML 레이아웃, ViewBinding, Fragment 렌더링)을
전제한 항목은 담지 않습니다.

## 우선순위

1. 정확성 — 실제로 깨지는 시나리오가 있는가
2. 회귀 위험 — 기존 흐름을 건드렸는가
3. 범위 이탈 — 요청과 무관한 변경이 섞였는가
4. 보안 — secret, 토큰, 권한, exported 컴포넌트
5. 테스트 누락 — 바뀐 동작을 고정하는 테스트가 있는가, 그 테스트가 실제로 검증력이 있는가

주변 코드와 이미 일치하는 스타일에는 리뷰 노력을 쓰지 않습니다.
프로젝트에 코딩 컨벤션 문서가 있으면 그것이 기준입니다. 이 스킬은 그 위에서 실제로 문제가 되는 것만 봅니다.

## 대상 범위

우선 검토합니다.

- Kotlin: `**/*.kt`, `**/*.kts`
- Gradle: `*.gradle`, `*.gradle.kts`, `libs.versions.toml`, `gradle.properties`
- `AndroidManifest.xml`, `proguard-rules.pro`
- 테스트: `src/test`, `src/androidTest`

제외합니다.

- `build`, `.gradle`, `out`, `generated`
- `ksp`, `kapt`
- `R.java`, `BuildConfig.java`, `*.pb.kt`
- `gradle-wrapper.properties`

## 상태 관리 트랙 확인

Compose 화면의 상태·일회성 이벤트 처리 방식은 프로젝트마다 다릅니다. **추측하지 않습니다.**

| | StateFlow 직접 | Orbit MVI |
| --- | --- | --- |
| 상태 | `MutableStateFlow` + `asStateFlow()` | `ContainerHost` + `container()` |
| 상태 변경 | ViewModel 함수에서 `update { }` | `intent { reduce { } }` |
| 일회성 이벤트 | `Channel<UiEffect>` + `receiveAsFlow()` | Orbit `SideEffect` |
| 화면 수집 | `collectAsStateWithLifecycle()` | `collectAsState()` |

주변 화면이 쓰는 트랙을 따랐는지 보고, **두 트랙을 한 화면에서 섞었으면 지적합니다.**
Orbit을 쓰면서 `Channel<UiEffect>`를 따로 만드는 코드가 대표적입니다.

## 일회성 이벤트 수집

일회성 이벤트(토스트, 내비게이션, 다이얼로그)는 **`collectLatest` 계열로 수집하지 않습니다.**
새 값이 오면 이전 블록이 취소되므로, suspend 지점이 있는 이벤트가 조용히 유실됩니다.
상태(state) 수집은 어느 쪽이든 괜찮습니다.

## 응답 형식

1. 발견한 문제를 심각도 순으로 먼저 제시합니다.
2. 파일과 라인을 함께 적습니다.
3. 동작 리스크, 테스트 누락, 유지보수 비용을 중심으로 설명합니다.
4. 문제가 없으면 "큰 이슈 없음"이라고 명확히 말하고 남은 리스크만 짧게 적습니다.
5. 단순 취향이나 불필요한 리팩터링을 필수 수정처럼 말하지 않습니다. 심각도를 붙여 구분합니다.

리뷰는 설명이 결과물입니다. **사용자가 고쳐 달라고 하기 전에는 코드를 수정하지 않습니다.**

## 상세 체크리스트

영역별로 깊게 볼 필요가 있을 때만 [references/review-rubric.md](references/review-rubric.md)를 읽습니다.
전부 훑지 말고 변경분에 해당하는 절만 봅니다.

Kotlin, Coroutine, ViewModel, Compose, Compose 성능, 자원 수명, Hilt, Network/Data,
Gradle, Manifest 항목이 있습니다.

## Gradle·R8·플랫폼 정책 변경: Google 공식 스킬 먼저

diff가 AGP 업그레이드, R8/keep rule, targetSdk 상향과 edge-to-edge, intent/exported 보안,
Play 정책·빌링에 걸리면 **직접 조사하기 전에** Google이 배포하는 스킬이 있는지 확인합니다.
`android` CLI가 설치돼 있어야 합니다.

```bash
android skills list
```

키워드로 찾을 수도 있습니다.

```bash
android skills find <keyword>
```

해당하는 스킬이 있으면 대상 저장소에 설치하고, 설치된 `SKILL.md`를 읽은 뒤 리뷰를 이어갑니다.

```bash
android skills add <skill> --project=<repo-root>
```

- `<skill>`은 **positional 인자**입니다. `android skills add --help`로 확인할 수 있습니다.
- `--project=<path>`로 저장소 범위를 지정합니다. 생략하면 감지된 에이전트 환경 전체에 설치됩니다.
- `--agent=<list>`로 대상 에이전트를 좁힐 수 있습니다.
- **필요한 1~3개만 설치합니다.** `--all`은 쓰지 않습니다 — 스킬 description은 매 세션 컨텍스트에
  올라가므로, 안 쓰는 스킬까지 깔면 그만큼 다른 것을 밀어냅니다.
- 설치는 저장소에 파일을 추가합니다. 리뷰 보고에 그 사실을 적습니다.
- 애매하게 걸치는 정도면 설치하지 말고 그냥 진행합니다.

리뷰에서 자주 걸리는 것들: `agp-9-upgrade`, `r8-analyzer`, `edge-to-edge`,
`android-intent-security`, `play-policy-insights`, `play-billing-library-version-upgrade`,
`camerax`, `android-profiler`, `testing-setup`.

## 빌드 환경이 이상할 때: 캐시보다 데몬 먼저

리뷰 중 빌드를 돌리다 환경이 이상하게 굴면, 캐시를 지우기 전에 데몬을 확인합니다.
Gradle 공식 문서 기준입니다.

- `./gradlew --stop`은 **같은 Gradle 버전의 데몬만** 멈춥니다. 다른 버전으로 뜬 데몬은 남습니다.
- `./gradlew --status`도 현재 버전만 보여줍니다. 전부 보려면 `jps`를 씁니다.
- IDE는 자기 Gradle 버전으로 별도 데몬을 띄우므로 wrapper의 `--stop`이 닿지 않습니다.
- `JAVA_HOME`, toolchain 설정, IDE의 JDK가 서로 어긋나면 기존 데몬과 호환되지 않아
  새 데몬이 계속 뜹니다.

`~/.gradle/caches`를 지우는 것은 마지막 수단입니다. 재다운로드 비용이 크고, 원인이 데몬이면
아무것도 해결되지 않습니다.

Gradle 캐시 경로를 뒤질 일이 있으면 `echo $GRADLE_USER_HOME`을 먼저 확인합니다.
기본값은 `~/.gradle`이지만 옮겨져 있을 수 있고, 빈 검색 결과를 "의존성이 해석된 적 없음"으로
읽으면 틀립니다.

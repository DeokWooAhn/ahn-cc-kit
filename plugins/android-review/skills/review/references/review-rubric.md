# Review Rubric

`android-review` 스킬에서 영역별로 깊게 볼 때 참고합니다. 전부 훑지 말고 변경분에 해당하는 절만 봅니다.
프로젝트에 코딩 컨벤션 문서가 있으면 그것이 기준이고, 여기서는 리뷰에서 실제로 문제가 되는 것만 다룹니다.

UI는 **Compose 기준**입니다. XML 레이아웃·ViewBinding 전제 항목은 담지 않습니다.

## Kotlin

- nullable을 명확히 다루고 불필요한 `!!`를 피합니다.
- 실패 가능한 작업은 `Result`, `sealed interface` 같은 타입으로 표현합니다. 성공/실패를 nullable로 뭉개지 않습니다.
- 예외를 조용히 삼키지 않습니다. 무시가 의도라면 그 이유가 코드 구조에서 드러나야 합니다.
- 하드코딩된 secret, credential, API key가 없어야 합니다.

## Coroutine

- ViewModel은 `viewModelScope`, UI 계층은 lifecycle에 묶인 scope를 씁니다.
- `GlobalScope`와 UI layer의 `runBlocking`을 쓰지 않습니다.
- `CancellationException`을 삼키지 않습니다. 취소 전파를 막으면 상위 취소가 무의미해집니다.
  `runCatching`과 광범위한 `catch (e: Exception)`이 취소를 함께 잡고 있지 않은지 봅니다.
- blocking I/O에 dispatcher 전환이 필요한지 봅니다.
- 진행 중 작업을 `Job`으로 취소·교체하는 코드는, 늦게 도착한 응답이 최신 상태를 덮어쓸 수 있는지 확인합니다.
- `Flow` 수집은 lifecycle을 인지해야 합니다. 화면이 백그라운드일 때도 도는 수집이 의도인지 봅니다.

## ViewModel

- `@HiltViewModel` + `@Inject constructor`를 씁니다.
- `Context`, `Activity`, `Fragment`, `View`를 필드로 보관하지 않습니다.
- `MutableStateFlow`는 private, 외부에는 `StateFlow`를 노출합니다.
- 일회성 이벤트는 `Channel` + `receiveAsFlow()` 또는 MVI 라이브러리의 side effect로 처리합니다.
  `SharedFlow`를 쓴다면 replay·buffer 설정이 유실·중복을 만들지 않는지 봅니다.
- UI 문자열은 `UiText` 같은 래퍼로 다뤄 ViewModel이 `Context`에 의존하지 않게 합니다.
- 사용자 입력은 명확한 단일 진입점으로 받습니다.
- 중복 요청을 막아야 하는 작업은 `isLoading`, `isSubmitting` 같은 상태로 보호합니다.
  같은 화면 안에서 어떤 요청은 in-flight 가드, 어떤 요청은 취소 후 재요청이라면 그 차이가 의도인지 확인합니다.
- 회전·process death 복원이 필요한 인자는 `SavedStateHandle`을 검토합니다.

## Compose

- state hoisting을 적용하고 비즈니스 상태를 Composable 내부에 두지 않습니다.
- 구성 변경에서 유지할 UI-local 상태는 `remember`가 아니라 `rememberSaveable`을 씁니다.
- `LaunchedEffect`, `DisposableEffect`의 key가 의도와 맞는지 봅니다.
  `key1 = Unit`인데 실제로는 값이 바뀔 때 다시 돌아야 하는 경우, 반대로 매 recomposition마다
  재시작되는 경우 둘 다 흔한 버그입니다.
- 상태 수집은 `collectAsStateWithLifecycle()`을 우선합니다. `collectAsState()`는 백그라운드에서도 수집합니다.
- 일회성 이벤트를 상태에 담아 처리하면 구성 변경 후 재실행됩니다. 소비 후 상태를 비우는 코드가 있는지 봅니다.
- `Modifier` 파라미터는 default `Modifier`로 첫 옵셔널 위치에 둡니다. 내부에서 받은 `Modifier`를
  루트에 적용하지 않고 버리는 코드를 잡습니다.
- 의미 있는 `contentDescription`과 최소 48dp 터치 영역을 확보합니다. 장식용 이미지는 `null`이 맞습니다.
- 하드코딩된 문자열·dp·색상이 리소스/테마 대신 들어가 있지 않은지 봅니다.

## Compose 성능

동작이 맞아도 recomposition이 새면 체감 성능이 무너집니다. **측정 없이 단정하지 않는다** —
의심 지점을 지적하되, 확정하려면 Layout Inspector나 recomposition count가 필요하다고 적습니다.

- `LazyColumn`/`LazyRow` item에 안정적인 `key`가 있는지 봅니다. 없으면 삽입·삭제 시 전체가 다시 그려집니다.
- 불안정(unstable) 타입이 Composable 파라미터로 들어가는지 봅니다. `List<T>`보다 `ImmutableList`,
  또는 `@Immutable`/`@Stable` 표기를 검토합니다.
- 파생 값을 매 recomposition마다 계산하면 `derivedStateOf`를 검토합니다.
  반대로 단순 계산에 `derivedStateOf`를 남발하는 것도 비용입니다.
- 자주 바뀌는 상태를 상위에서 읽어 하위 전체를 recompose시키지 않는지 봅니다.
  값 대신 람다(`() -> State`)를 넘겨 읽는 지점을 낮추는 패턴을 검토합니다.
- 스크롤·애니메이션 값처럼 프레임마다 바뀌는 값은 `Modifier.graphicsLayer`나
  draw 단계에서 읽어 recomposition을 피합니다.

## 자원 수명

수명이 있는 자원은 **소유자와 해제 지점을 짝지어** 봅니다. 할당·등록만 있고 해제가 없는 diff를 우선 잡습니다.

| 자원 | 소유자 | 해제 지점 |
| --- | --- | --- |
| `AndroidView`로 붙인 View | composition | `AndroidView`의 `onRelease` |
| MediaPlayer, ExoPlayer, Surface | 재생 주체 | `DisposableEffect`의 `onDispose` |
| 리스너·콜백·리시버 등록 | 등록한 쪽 | `DisposableEffect`의 `onDispose` |
| 코루틴 | `viewModelScope` / `rememberCoroutineScope` | scope 종료 |
| Dialog, PopupWindow (interop) | 띄운 화면 | 화면 이탈 전 dismiss + 리스너 해제 |

### AndroidView interop

- Compose는 View를 계층에서 **떼어낼 뿐 `destroy()`를 부르지 않습니다.**
  `factory`만 있고 `onRelease`가 없는 `AndroidView`에서 정리가 필요한 View를 쓰면 잡습니다.
- 바깥에서 참조를 잡고 해제를 책임지는 구조라면 예외입니다. 다만 그 소유 관계가 코드에서 드러나야 합니다.
- Lazy 리스트 안의 `AndroidView`는 스크롤로 벗어날 때 `onRelease`가 불립니다.
  재사용을 전제로 상태를 남기는 구현이라면 그게 의도인지 확인합니다.

### WebView

- WebView는 `onRelease`에서 `stopLoading()` → `loadUrl("about:blank")` → `destroy()` 순으로 정리합니다.
  화면에서 참조를 놓기만 하면 renderer 프로세스가 남습니다.
- `addJavascriptInterface`를 쓰면 노출 대상과 해제 시점을 함께 봅니다.
  Manifest의 exported 기준과 같은 눈으로 봅니다. 정리할 때는 `destroy()` 전에
  `removeJavascriptInterface(name)`으로 브리지부터 끊습니다.
- WebView 설정을 공통 함수로 묶었다면, JavaScript를 켜지 않아도 되는 화면까지 함께 묶이지 않았는지 봅니다.
  `@SuppressLint("SetJavaScriptEnabled")`는 실제로 켜는 지점에만 붙입니다.
- 로드할 URL·HTML의 출처를 봅니다. 외부에서 들어온 값을 그대로 로드하면 권한 있는 브리지가 함께 노출됩니다.

### 미디어

- MediaPlayer와 Surface는 `onDispose`에서 **둘 다** release합니다. 하나만 놓치면 화면을 나가도 렌더러가 남습니다.
- 앱 전역 플레이어는 싱글턴으로 두되 resume·pause·release·reset의 경계를 명시합니다.
  "화면이 보이는가"와 "재생 설정이 켜져 있는가"를 한 메서드에서 같이 판단하지 않습니다.
- `MediaPlayer.create()`는 prepare까지 끝내므로 그 뒤의 `setAudioAttributes`가 무시됩니다.
  속성이 필요하면 생성자 + `setDataSource` + `prepare`를 씁니다.
- release는 이미 해제된 상태에서 예외를 던질 수 있습니다. `runCatching`으로 감싼 뒤 참조를 null로 둡니다.

### 참조 보관

- ViewModel, Repository, 싱글턴에 Activity, Context, View, Composition 참조를 보관하지 않습니다.
- 리스너·옵저버·리시버는 등록한 쪽에서 해제합니다. 등록 지점과 해제 지점이 다른 클래스면 그 이유를 봅니다.

### 확인

- diff에서 할당·등록마다 해제 짝이 보이는지 봅니다.
- 화면 진입·이탈, 회전, 백그라운드 전환, 리스트 스크롤 이탈, 로그아웃에서 각각 정리되는지 봅니다.
- 정리 코드가 정상 경로뿐 아니라 취소·에러 경로에서도 도는지 봅니다.

## Hilt / DI

- `@Module`에 `@InstallIn`을 함께 명시합니다.
- interface binding은 `@Binds`를 우선합니다.
- 같은 타입이 여러 개면 `@Qualifier`로 구분합니다.
- Application Context는 `@ApplicationContext`를 씁니다.
- `@Singleton`으로 잡은 것이 정말 앱 수명인지 봅니다. 화면 수명 객체를 싱글턴에 두면 누수가 됩니다.
- 모듈이 커지면 `NetworkModule`, `RepositoryModule`처럼 책임별로 나눕니다.

## Network / Data

- Retrofit API는 `suspend` 함수를 기본으로 합니다.
- DTO는 `data` 계층 밖으로 노출하지 않고 domain model로 변환합니다.
- 서버가 안 내려줄 수 있는 필드는 DTO에서도 nullable로 둡니다.
  쓰지도 않는 필드를 필수로 두면 스키마가 바뀔 때 파싱 실패로 기능이 조용히 죽습니다.
- 서버 에러는 공통 매퍼에서 하나의 타입으로 변환합니다. 화면마다 상태 코드를 다시 해석하지 않습니다.
- 401/403 같은 공통 인증 에러 흐름이 이미 있으면 개별 화면에서 중복 처리하지 않습니다.
- token, refresh token, 기기 식별자 등은 보안 정책에 맞는 저장소를 씁니다.
- DataStore·DB 접근은 `IOException`을 잡되 `CancellationException`은 전파해야 합니다.
- 캐시·fallback이 있으면 어떤 조건에서 stale 값이 나가는지 봅니다.

## Gradle

- 버전은 `libs.versions.toml` version catalog를 씁니다.
- `jcenter()`를 쓰지 않습니다.
- debug 전용과 release 의존성을 분리합니다.
- signing config에 평문 password·secret을 넣지 않습니다.
- 빌드 타입을 새로 추가했다면, 모든 Android 라이브러리 모듈에도 같은 타입이 정의됐는지 봅니다.
  `matchingFallbacks`로 release에 떨어뜨리면 그 빌드 타입이 release 설정을 그대로 쓰게 됩니다.
- signing config를 조건부로 만드는 코드는, 값이 없을 때 **조용히 서명 없이 통과**하지 않는지 봅니다.
- compileSdk, targetSdk, Kotlin JVM target의 일관성을 봅니다.
- AGP 업그레이드나 R8/keep rule 변경이면 `android skills list`로 Google 공식 스킬을 먼저 확인합니다.

## AndroidManifest

- 위험 권한을 추가하면 런타임 권한 요청 흐름도 함께 확인합니다.
- `intent-filter`가 있는 컴포넌트는 `android:exported`와 노출 사유가 명확해야 합니다.
- deeplink scheme/host가 과도하게 넓지 않은지 봅니다.
- Activity의 `launchMode`와 진입 인텐트 플래그가 맞물리는지 봅니다.
  `standard` + `FLAG_ACTIVITY_CLEAR_TOP` 조합은 기존 인스턴스를 finish 후 재생성해서
  `onNewIntent`가 호출되지 않습니다.
- `debuggable`, `usesCleartextTraffic`, `allowBackup`이 빌드 타입·보안 요구사항에 맞는지 봅니다.
- 백업 정책에서 token, 사용자 식별자가 제외되는지 봅니다.

## 테스트

- 바뀐 동작을 고정하는 테스트가 있는지 봅니다. 없으면 왜 없는지 묻습니다.
- **초기값과 기대값이 같은 단언을 조심합니다.** "실패 시 기존 값 유지"를 검증하면서
  기본값이 이미 `false`인 상태에서 `false`를 단언하면, 반대로 구현해도 통과하는 무의미한 테스트가 됩니다.
  먼저 값을 바꿔 놓고 그 값이 유지되는지 확인합니다.
- 외부 의존성만 mock으로 대체합니다. 순수 로직은 실제 객체로 검증합니다.
- Coroutine 테스트는 `runTest`와 test dispatcher로 시간을 제어합니다. 실제 지연에 기대지 않습니다.
- Repository·Mapper 테스트는 응답 파싱, 에러 매핑, 캐시·fallback·예외 전파 분기를 중심으로 봅니다.

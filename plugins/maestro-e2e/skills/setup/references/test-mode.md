# 테스트 모드 실행 인자

Flow가 매번 같은 화면에서 시작하려면, 테스트를 막는 것들을 끄는 스위치가 앱에 있어야 한다.
Maestro는 `launchApp`의 `arguments`를 **Android에서는 intent extra로, iOS에서는 실행 인자로** 넘긴다.

```yaml
- launchApp:
    arguments:
      UI_TESTING: true
```

## 무엇을 끄나

| 대상 | 이유 |
| --- | --- |
| 광고 동의(UMP) 창 | 지역 판정에 따라 뜨기도 안 뜨기도 해서 Flow가 불안정해진다. 막히면 통째로 멈춘다 |
| 광고 로드 | 자동화가 만든 노출·클릭은 무효 트래픽이다. 동의 흐름을 건너뛰면 보통 광고 초기화도 같이 빠진다 |
| 온보딩·튜토리얼·이벤트 팝업 | 첫 실행마다 뜨면 매 Flow가 닫는 단계부터 시작해야 한다 |
| 강제 업데이트·점검 안내 | 서버 설정에 따라 테스트 결과가 달라진다 |

로그인은 끄지 않는다. 로그인이 필요한 화면은 테스트 계정이나 mock 환경이 준비된 뒤 `release`로 다룬다.

## Android: 디버그 빌드에서만 받는다

런처 Activity는 exported라 **다른 앱도 extra를 붙여 실행할 수 있다.** 릴리스 빌드에서 이 값을 받아 주면
광고 동의를 외부에서 끌 수 있게 된다. `BuildConfig.DEBUG`가 없는 모듈(라이브러리 모듈)에서는
`FLAG_DEBUGGABLE`로 판단한다.

```kotlin
private fun isUiTesting(): Boolean {
    val isDebuggable = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
    return isDebuggable && intent.getBooleanExtra(UI_TESTING_EXTRA, false)
}
```

```kotlin
if (isUiTesting()) {
    Log.i(TAG, "UI testing detected; skipping ad consent flow")
} else {
    requestAdConsent()
}
```

## iOS: 실행 인자에 키가 있는지 본다

```swift
static let uiTestingLaunchArgument = "UI_TESTING"

private static var isUITesting: Bool {
    ProcessInfo.processInfo.arguments.contains(uiTestingLaunchArgument)
}
```

- Maestro의 `arguments: { UI_TESTING: true }`로 실행하면 위 조건이 참이 된다(iOS 26 시뮬레이터에서 확인).
- **키 앞에 하이픈을 붙이지 않는다.** `-UI_TESTING`처럼 하이픈으로 시작하면 UserDefaults가 키-값 쌍으로 해석해
  뒤에 오는 인자를 값으로 삼킨다. XCUITest의 `launchArguments`에서도 같은 이름을 쓰면 두 도구가 한 스위치를 공유한다.
- iOS에서는 다른 앱이 실행 인자를 넣을 수 없어 Android만큼 위험하지 않다. 그래도 릴리스에서 켤 이유가
  없으면 `#if DEBUG`로 감싸도 된다.

## 확인

- 인자를 넘겨 실행하면 막던 화면이 뜨지 않고, 로그(Android logcat, iOS `log show`)에 위 로그가 찍힌다.
- 인자 없이 실행하면 동의 흐름이 원래대로 돈다.
- Android 릴리스 빌드에 인자를 넘겨도 무시된다.

iOS 시뮬레이터 로그 확인 예:

```bash
xcrun simctl spawn <udid> log show --last 5m --info --predicate 'subsystem == "<로그 subsystem>"'
```

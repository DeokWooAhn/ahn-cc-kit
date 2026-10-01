# 프로젝트 분석

Flow를 새로 만들기 전에 저장소에서 아래를 확인한다. 추측으로 채우지 말고, 코드에서 못 찾으면 사용자에게 묻는다.
찾은 결과는 짧은 표로 사용자에게 보여 준다(플랫폼, APP_ID, 기존 `.maestro/`, 쓸 수 있는 id, 없는 id).

## 플랫폼과 UI

- Android: `settings.gradle(.kts)`와 `com.android.application` 플러그인을 쓰는 모듈. Compose는 `buildFeatures { compose = true }`나
  Compose 컴파일러 플러그인으로 확인한다.
- iOS: `*.xcodeproj`·`*.xcworkspace`, 화면 코드의 `import SwiftUI`.
- Flutter·React Native·XML 전용 화면이면 이 플러그인의 전제(Compose·SwiftUI) 밖이다. id 붙이는 방법이 다르니
  그렇다고 알리고 진행할지 묻는다.

## APP_ID

Flow에는 `appId: ${APP_ID}`만 쓰고 값은 실행 때 넘긴다. 값은 플랫폼마다 다르고, 대소문자까지 다를 수 있다.

**Android**: debug 빌드의 applicationId다.

- 앱 모듈의 `defaultConfig { applicationId }`에 `buildTypes.debug`와 flavor의 `applicationIdSuffix`를 붙인 값이다.
- `namespace`는 applicationId가 아니다. 둘이 다른 프로젝트가 많다.
- 빌드 결과가 있으면 그 값을 믿는다. `app/build/outputs/apk/debug/output-metadata.json`의 `applicationId`에 있다.
  설치된 기기에서는 `adb shell pm list packages | grep <이름 일부>`로도 확인할 수 있다.

**iOS**: 시뮬레이터용 Debug 빌드의 bundle id다.

- `xcodebuild -showBuildSettings -scheme <scheme> -configuration Debug | grep PRODUCT_BUNDLE_IDENTIFIER`
- 빌드한 `.app`이 있으면 `/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' <앱>.app/Info.plist`.
- 소스의 `Info.plist`는 보통 `$(PRODUCT_BUNDLE_IDENTIFIER)` 변수라 값이 아니다.

## 기존 `.maestro/`

있으면 그 구성이 이 플러그인의 템플릿보다 우선한다. 나란히 새 구조를 만들지 않는다.

- `config.yaml`의 `flows:`가 어느 파일을 테스트로 잡는지. 새 Flow가 거기에 잡히는 위치와 이름을 쓴다.
- 공통 subflow(`launch_clean.yaml` 같은 것). 있으면 그걸로 시작하고 같은 역할의 subflow를 새로 만들지 않는다.
- 쓰고 있는 태그와 그 기준. 저장소의 `.claude/skills/`나 문서에 적혀 있으면 그것을 따른다.
- `${...}`로 받는 변수. 실행 때 모두 넘겨야 한다.
- CI가 어떻게 돌리는지. 워크플로에서 `maestro`를 찾아 태그와 `APP_ID`를 확인한다.

## 기존 id

**있는 id를 먼저 쓴다.** 이름이 이 플러그인의 이름 규칙(`setup` 스킬의 `references/test-ids.md`)과
달라도 바꾸지 않는다. 바꾸면 기존 Flow와 유닛 테스트가 깨진다. 예외는 정규식 특수문자가 든 id다(`+ * ? ( ) [ ] | ^ $ \`).
엉뚱한 요소가 잡히므로 이름을 바꾸자고 제안한다.

- Android: `testTag(`, 그리고 composition 루트의 `testTagsAsResourceId`.
- iOS: `accessibilityIdentifier(`.
- id를 상수로 모아 둔 파일(`TestTags`, `AccessibilityID` 같은 것)이 있으면 그 목록이 기준이다.
- 저장소의 `.claude/skills/`나 문서에 id 표가 있으면 그것이 우선이다.
- 코드에 있어도 기기에서 안 보일 수 있다(Android `testTagsAsResourceId` 누락, Dialog 같은 별도 창). 쓰기 전에
  `maestro --device <serial> hierarchy --compact`로 실제로 보이는지 확인한다.

**없는 id는 붙이기 전에 제안한다.** 앱 코드를 고치는 일이라 먼저 목록을 보여 주고 동의를 받는다.
목록에는 붙일 위치(파일:줄), 제안하는 id, 그 id가 필요한 Flow 단계를 적는다. 두 플랫폼이 다 있으면 양쪽에 같은 이름을 제안한다.

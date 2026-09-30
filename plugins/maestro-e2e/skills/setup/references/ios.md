# iOS에서 돌리기

Flow는 Android와 같은 파일을 쓴다. 다른 것은 빌드·설치 방법, 앱 id, 기기, 몇몇 조작이다.
아래는 Maestro 2.1.0, Xcode 26, iOS 26 시뮬레이터에서 확인한 것이다.

## 빌드·설치·실행

```bash
xcodebuild build -workspace <App>.xcworkspace -scheme <Scheme> -configuration Debug -destination 'platform=iOS Simulator,id=<udid>' -derivedDataPath build/ios
```

```bash
xcrun simctl install <udid> build/ios/Build/Products/Debug-iphonesimulator/<App>.app
```

```bash
maestro --device <udid> test .maestro -e APP_ID=<bundle id>
```

- 워크스페이스가 없으면 `-project <App>.xcodeproj`. SPM 로컬 패키지가 있으면 워크스페이스로 빌드해야 한다.
- **`APP_ID`는 Android applicationId와 대소문자까지 다를 수 있다**(`com.example.app` / `com.example.App`).
  bundle id는 `.app/Info.plist`의 `CFBundleIdentifier`로 확인한다.
- 켜진 시뮬레이터: `xcrun simctl list devices booted`. 다 쓰면 `xcrun simctl shutdown all`.

## 실기기

- 연결된 iPhone은 `xcrun devicectl list devices`로 본다.
- **설치된 Maestro 2.1.0 CLI 도움말은 iOS 대상을 시뮬레이터로만 안내하고, 실기기용 서명 옵션이 없다.**
  실기기가 연결돼 있으면 먼저 시도해 보고, 안 되면 시뮬레이터로 돌린 뒤 그렇게 했다고 보고한다.
- 실기기에 App Store판이 깔려 있으면 개발 빌드로 바꾸기 전에 사용자에게 묻는다.

## 시뮬레이터에서 안 되는 것

- **App Attest·DeviceCheck 같은 기기 증명은 시뮬레이터에서 동작하지 않는다.** Firebase App Check처럼 이걸 쓰는
  서버 호출은 debug provider로 바꾸고, 그 토큰을 서버 쪽에 등록해야 `release` Flow가 통과한다.
- 푸시 알림, 카메라 같은 하드웨어 기능은 Flow에 넣지 않는다.

## 플랫폼마다 다른 조작

같은 Flow 안에서 `runFlow`의 `when: platform`으로 나눈다.

```yaml
# 시트·대화상자 닫기: Android는 뒤로가기, iOS는 닫기 버튼
- runFlow:
    when:
      platform: Android
    commands:
      - back
- runFlow:
    when:
      platform: iOS
    commands:
      - tapOn:
          id: "picker.close"
```

- `back`은 Android 전용이다. iOS 시트에는 닫기 버튼 id를 따로 붙인다.
- 템플릿 `launch_clean.yaml`의 `stopApp` + 2초 대기는 Android 레이스 대응이라 `platform: Android`로 묶여 있다.

## iOS CI

**이 플러그인은 iOS CI에서 Maestro를 돌린 구성을 검증하지 않았다.** 붙인다면:

- macOS 러너가 필요하다. 프로젝트가 요구하는 Xcode 버전이 있는 이미지로 **고정**한다(`macos-latest`는 바뀐다).
- 순서: 시뮬레이터 부팅 → 위 `xcodebuild build` → `simctl install` → `maestro test --include-tags=smoke`.
- macOS 러너는 비싸고 느리다. Android smoke가 CI에 있으면 iOS는 로컬·릴리스 전 확인으로 두는 것도 방법이다.

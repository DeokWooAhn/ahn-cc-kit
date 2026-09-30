# 실제로 겪은 함정

Maestro 2.1.0, GitHub Actions `ubuntu-latest` 에뮬레이터(API 34 `google_apis`)와 Galaxy 실기기에서 겪은 것이다.
대기 시간을 늘려 증상만 가리지 말고, 원인이 같은지 먼저 확인한다.

## 엉뚱한 요소를 누른다

- **증상**: `tapOn: { id: "keypad.+" }`이 더하기가 아니라 다른 키를 누른다.
- **원인**: `id:`는 전체 일치 정규식이다. `+`가 "앞 글자 한 개 이상"이 되어 `keypad.history` 전체와 일치했다.
- **대응**: id에서 기호를 빼고 영어 이름으로 짓는다(`keypad.plus`). 유닛 테스트로 형식을 고정한다.

## `launchApp`에서 수 분씩 멈춘다

- **증상**: CI에서 특정 Flow의 앱 실행 단계만 5분 넘게 걸리고, 다른 Flow에서는 1~3초다.
- **원인**: `launchApp`에 `permissions`를 안 적으면 기본값이 `all: allow`다. Android에서 권한 목록을 읽으려고
  APK 전체(debug 약 89MB)를 매번 adb로 받는데, 에뮬레이터에서 이 전송이 가끔 멈췄다. 스레드 덤프가
  `dadb.AdbSyncStream.recv ← AndroidAppFiles.getApkFile ← setAllPermissions`에 있었다.
- **대응**: `permissions: {}`. 런타임 권한이 필요하면 그 권한만 적는다.
- 참고: 처음에는 설치 직후 dexopt 대기로 추정했는데 틀렸다. 추정만으로 우회를 넣지 않은 게 맞았다.

## 앱을 지우고 다시 띄우면 빈 화면

- **증상**: 느린 에뮬레이터에서 두 번째 이후 Flow가 첫 화면을 못 찾고 실패한다. 실기기에서는 재현되지 않는다.
- **원인**: 살아 있는 앱을 `clearState`(`pm clear`)로 지우면 시스템이 약 1초 뒤 옛 태스크의 프로세스를 한 번 더
  죽인다. Maestro가 그 사이(0.9초 뒤)에 띄운 새 프로세스가 옛 태스크에 붙었다가 함께 죽었다. logcat에
  "remove task"가 찍힌다.
- **대응**: 먼저 `stopApp`, 2초 기다린 뒤 `clearState`로 띄운다. 템플릿 `launch_clean.yaml`이 이렇게 한다.

## 에뮬레이터가 부팅 직후 느리다

- **증상**: 첫 Flow의 첫 화면 대기가 15초를 넘기거나, `pm clear`가 막힌다.
- **원인**: `sys.boot_completed=1`은 한가하다는 뜻이 아니다. GMS 초기화와 dexopt가 CPU와 패키지 매니저를
  붙잡고 있다. 부팅 직후 스냅샷을 찍으면 매 실행마다 같은 작업을 되풀이한다.
- **대응**: 스냅샷은 부하가 내려간 뒤 저장한다. 테스트 전에도 `bg-dexopt-job`을 돌리고 부하가 내려가길
  기다린다(`emulator-settle.sh`). 에뮬레이터는 4코어·4GB. 설치 뒤 앱을 한 번 띄워 첫 실행 비용을 미리 치른다.

## Compose Dialog 안의 요소를 못 찾는다

- **증상**: 화면의 id는 다 보이는데 Dialog나 BottomSheet를 열면 그 안의 id만 안 보인다.
- **원인**: Dialog는 별도 창이라 루트에 켠 `testTagsAsResourceId`가 닿지 않는다.
- **대응**: Dialog 콘텐츠 루트에도 `Modifier.semantics { testTagsAsResourceId = true }`를 켠다.

## 스크롤해도 못 찾는다

- **증상**: `scrollUntilVisible`이 목록 뒤쪽 항목에서 "No visible element found"로 끝난다. 스크린샷에는
  항목이 화면 끝에 걸려 있다.
- **원인**: 기본 제한 시간이 20초다. 긴 목록의 뒤쪽까지 가기 전에 끝난다.
- **대응**: 목록 앞쪽 항목을 쓰거나 `timeout`을 늘린다. Flow가 목록 길이에 기대지 않게 하는 쪽이 낫다.

## 기기 테스트가 화면을 못 찾는다

- **증상**: `No compose hierarchies found`, 또는 Maestro가 아무 요소도 못 찾는다.
- **원인**: 실기기 화면이 꺼져 있거나 잠금 화면이다.
- **대응**: 사용자에게 잠금 해제를 요청한다. 대신 풀지 않는다.

## 기능이 아니라 앱의 규칙 때문에 실패한다

- **증상**: 즐겨찾기처럼 "추가하면 목록에 생긴다"는 Flow가 실패하는데 기능은 정상이다.
- **원인**: 앱이 일부러 걸러내는 조건(예: 기준 대상과 같은 항목은 목록에서 뺀다)에 Flow가 걸렸다.
- **대응**: 먼저 앱 코드에서 그 조건을 확인한다. Flow가 조건을 피하게 고치고, 조건이 사용자에게 이상하게
  보이면(오류 문구가 뜨는 등) 앱 버그로 따로 보고한다.

# android-guard

Android/Gradle 작업에서 에이전트가 **실수로** 저지르면 되돌리기 비싼 것들을 막는 훅 묶음.

```bash
claude plugin install android-guard@ahn-cc-kit
```

필요: `bash`, `jq`.

**`jq`가 없으면 이 훅들은 아무것도 막지 못합니다.** 입력 파싱이 전부 빈 값이 되어,
입력이 깨졌을 때 통과시키는 경로를 그대로 탑니다. 세션 시작 때 `deps-check.sh`가
한 번 확인하고 없으면 알려 줍니다(`*_DISABLE_DEPS_CHECK=1`로 끌 수 있습니다).

설치 범위는 [최상위 README](../../README.md#원하는-프로젝트에서만-켜기)를 참고하세요.
기본값인 user 범위로 넣으면 모든 프로젝트에 붙습니다.

## 훅

### 차단 (PreToolUse, exit 2)

| 훅 | 막는 것 | opt-out |
| --- | --- | --- |
| `signing-secrets-guard` | `local.properties`·키스토어·Play 서비스 계정 접근 | `ANDROID_GUARD_DISABLE_SIGNING_SECRETS` |
| `gradle-wrapper-guard` | `gradle-wrapper.jar`·`gradlew` 편집, `distributionUrl` 변조 | `ANDROID_GUARD_DISABLE_GRADLE_WRAPPER` |
| `gradle-cache-guard` | `~/.gradle/caches` 삭제 | `ANDROID_GUARD_DISABLE_GRADLE_CACHE` |
| `signing-literal-guard` | Gradle·properties에 서명 password 평문 | `ANDROID_GUARD_DISABLE_SIGNING_LITERAL` |

### 경고 (PostToolUse, 막지 않음)

| 훅 | 알리는 것 | opt-out |
| --- | --- | --- |
| `unsigned-release-check` | release 빌드에 서명 설정이 없음 | `ANDROID_GUARD_DISABLE_UNSIGNED_RELEASE` |
| `manifest-risk-check` | Manifest에 `exported="true"` 등이 **새로** 추가됨 | `ANDROID_GUARD_DISABLE_MANIFEST_RISK` |

개별로 끕니다.

```bash
ANDROID_GUARD_DISABLE_GRADLE_CACHE=1 claude
```

## 판정 기준

### signing-secrets-guard

| 대상 | 차단 도구 |
| --- | --- |
| `local.properties`, `keystore.properties`, `signing.properties` | Read, Edit, Write, Grep, Bash |
| `*.jks`, `*.keystore`, `*.p12`, `*.pepk` | Read, Edit, Write, Bash |
| `*service-account*.json`, `*play-publisher*.json` | Read, Edit, Write, Grep, Bash |

**Glob은 어떤 경우에도 막지 않습니다.** 파일이 어디 있는지 찾는 것은 정당하고, 위험한 건 내용입니다.
바이너리 키스토어는 Grep해도 얻을 게 없으므로 Grep도 열어 둡니다. 평문인 `local.properties`는 막습니다.

`local.properties.example`, `local.defaults.properties`, `*.jks.sample`은 통과합니다 —
경로 성분 끝에서만 매치하므로 접미사가 붙으면 자연히 빠집니다.

### unsigned-release-check

**이게 이 묶음의 핵심입니다.** 서명 키를 조건부로 구성하는 흔한 Gradle 패턴은 키가 하나라도
없으면 `signingConfig`를 그냥 건너뜁니다. 강제 검증이 없으면 `assembleRelease`는 **성공합니다.**
빌드가 초록불이라 서명됐다고 착각하기 쉬운데, APK·AAB에는 서명 블록이 없습니다.

키 **이름**은 프로젝트마다 다릅니다. 접두사는 `RELEASE_` / `SIGNING_` / `ANDROID_` / 없음으로
제각각이지만 접미사는 일정해서, 정확한 이름 목록 대신 패턴으로 봅니다. 그래서 묻는 질문이
"정해진 네 개가 다 있나"가 아니라 **"서명 설정이 있기는 한가"** 입니다.

기본 패턴은 언더스코어를 선택적으로 둬서 두 표기를 함께 덮습니다.

```text
STORE_?FILE  STORE_?PASSWORD  KEY_?ALIAS  KEY_?PASSWORD
KEYSTORE_?FILE  KEYSTORE_?PATH  KEYSTORE_?PASSWORD
```

| 관례 | 예 | 판정 |
| --- | --- | --- |
| `RELEASE_` 접두사 | `RELEASE_STORE_PASSWORD` | 조용 |
| `SIGNING_` 접두사 | `SIGNING_STORE_PASSWORD` | 조용 |
| `ANDROID_` 접두사 | `ANDROID_KEYSTORE_PASSWORD` | 조용 |
| 접두사 없음 | `KEY_ALIAS` | 조용 |
| camelCase | `storePassword` (keystore.properties 표준) | 조용 |
| 아무것도 없음 | — | **경고** |

찾는 곳은 환경 변수와 `local.properties`, `keystore.properties`, `signing.properties`
(저장소 루트와 `app/`)입니다. **존재만 확인하고 값은 읽지도 출력하지도 않습니다.**

다른 이름을 쓴다면 정규식으로 지정합니다.

```bash
ANDROID_GUARD_SIGNING_KEYS="MY_SIGN_KEY|MY_SIGN_PASS"
```

빌드 출력에 `BUILD FAILED`가 있으면 조용히 넘어갑니다.

### signing-literal-guard

`storePassword`/`keyPassword` 뒤에 **바로 따옴표**가 오면 리터럴로 봅니다.
`System.getenv(...)`, `providers.environmentVariable(...)`, `findProperty(...)` 같은 간접
참조는 따옴표가 그 위치에 오지 않으므로 판정식에서 자연히 빠집니다. `$` 보간 문자열도 통과시킵니다.

cc-agents-kit의 `staged-secret-guard`는 커밋 시점을 잡고, 이 훅은 쓰는 순간을 잡습니다.
층이 달라 겹치지 않습니다.

## 넣지 않기로 한 것

오탐 비용이 이득보다 큽니다.

- `adb shell pm clear`, `adb uninstall` — 테스트 중 의도적으로 자주 씁니다
- `./gradlew clean`, `build/` 삭제 — 복구가 쌉니다
- `intent-filter`에 `exported` 누락 — targetSdk 31+에서 AGP가 빌드를 실패시킵니다. 중복입니다
- `google-services.json` — 보통 저장소에 커밋되는 파일입니다. 막으면 정상 작업이 깨집니다
- `--refresh-dependencies` — 느릴 뿐 위험하지 않습니다

## 한계

- **문자열 매칭입니다.** 심볼릭 링크, glob 확장, 부모 파일 참조 같은 여러 단계 우회는 막지 못합니다.
  OS 계층 강제가 아니라 **사고 방지용**입니다
- `unsigned-release-check`는 설정의 존재를 볼 뿐 산출물을 검증하지 않습니다.
  확실히 하려면 `apksigner verify <apk>` / `jarsigner -verify <aab>`가 필요합니다

## 훅 계약

cc-agents-kit `guard-hooks`가 확립한 규약을 따릅니다. 같이 설치해도 충돌하지 않습니다.

- **stdin을 먼저 다 읽은 뒤** opt-out을 확인합니다. 읽기 전에 exit하면 하네스가 닫힌 파이프에
  쓰게 되어, *비활성화한* 훅이 오히려 도구 호출을 실패시킵니다
- 입력이 비었거나 깨졌으면 fail open(exit 0)
- 차단은 exit 2 + stderr에 사유와 **대안**
- 경고는 exit 0 + stdout에 `hookSpecificOutput.additionalContext` JSON

## 테스트

```bash
python3 plugins/android-guard/hooks/test_hooks.py
```

훅마다 판정 케이스 + opt-out 무음 + 200KB 파이프 소진을 겁니다.
마지막 항목이 위의 stdin 계약을 고정합니다 — opt-out 확인을 위로 옮기면 `writer=141`(SIGPIPE)로
실패합니다. 파이썬 `subprocess`는 `BrokenPipeError`를 삼키므로 writer가 진짜 셸이어야 잡힙니다.

## 여기 없는 것: git-guard

`main`/`release/*` 직접 push 차단, force push 차단, `reset --hard` 차단은 Android와 무관해서
넣지 않았습니다. Node 저장소에서 브랜치 보호만 원하는 사람이 Android 플러그인을 설치해야 하는 건
이상합니다. 별도 `git-guard`로 만듭니다.

`protected-branch-guard`의 어려운 부분은 인자 없는 `git push`입니다. 명령만 봐서는 대상 브랜치를
알 수 없으므로 `git rev-parse --abbrev-ref HEAD`와 upstream 설정을 함께 봐야 합니다.
저장소 밖에서 실행됐을 때는 fail open.

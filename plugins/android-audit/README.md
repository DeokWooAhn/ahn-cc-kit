# android-audit

이미 저장소에 들어와 있는 것을 훑습니다. `android-guard` 훅이 앞으로의 유입을 막고,
이 플러그인이 **이미 들어온 것**을 찾습니다.

```bash
claude plugin install android-audit@ahn-cc-kit
```

필요: `bash`, `git`.

## 왜 따로 필요한가

훅은 **에이전트의 행동만** 봅니다. 이런 건 전부 통과합니다.

- 훅을 설치하기 **전에** 들어간 키스토어
- 사람이 직접 넣은 평문 password
- `git add .`로 딸려 들어간 시크릿
- `.gitignore`에 서명 파일 규칙이 빠진 상태

예방과 탐지는 다른 일입니다.

## 실행

```bash
android-audit
```

```bash
android-audit ~/work/my-app --history
```

출력 언어는 로케일을 따릅니다(`LANG`, macOS는 시스템 로케일). 한국어와 영어를 지원합니다.

```bash
android-audit --lang en
ANDROID_AUDIT_LANG=en android-audit
```

| 종료 코드 | 뜻 |
| --- | --- |
| 0 | 발견 없음 |
| 1 | 발견 있음 |
| 2 | 경로가 없거나 git 저장소가 아님 |

CI에 그대로 걸 수 있습니다.

## 검사 항목

| 항목 | 등급 |
| --- | --- |
| 추적 중인 `local.properties`·`*.jks`·Play 서비스 계정 JSON | 높음 |
| Gradle·properties의 평문 `storePassword`·`keyPassword` | 높음 |
| 히스토리에 추가된 적 있는 서명 파일 (`--history`) | 높음 |
| `.gitignore`에 서명 파일 규칙 누락 | 중간 |
| gradle.org가 아닌 곳에서 받는 Gradle 배포본 | 중간 |
| Manifest의 `debuggable`·`usesCleartextTraffic`·`allowBackup` | 중간 |

Gradle 프로젝트가 아니면 추적 파일 검사만 하고 나머지는 건너뜁니다.
Node 저장소에 대고 돌려도 안드로이드 항목으로 시끄럽게 굴지 않습니다.

## 두 가지 원칙

**값을 출력하지 않습니다.** 파일과 줄 번호만 보고합니다. 감사 결과가 새 유출 경로가
되면 안 됩니다. 테스트가 이 성질을 고정합니다.

```text
[높음] 서명 password가 문자열 리터럴로 들어 있습니다.
       · app/build.gradle.kts:4,5
       · gradle.properties:1
```

**고치지 않습니다.** `--fix`가 없습니다. 커밋된 시크릿은 파일을 지워도 히스토리에 남으므로
"정리했다"는 결과가 가장 위험합니다. 노출된 키는 회전이 답이고, 히스토리 정리는
협업자 전원이 다시 클론해야 하는 일이라 사용자가 결정할 문제입니다.

## 테스트

```bash
python3 plugins/android-audit/tests/test_audit.py
```

`/bin/bash`(3.2)로 돌립니다. 케이스 중 하나는 **파일 3000개짜리 저장소**를 만듭니다.
`git ls-files | grep -q` 형태는 일찍 매치되면 `grep`이 먼저 끝나면서 `git`이
SIGPIPE로 죽고, `pipefail`이 그걸 실패로 봅니다. 작은 저장소는 목록이 파이프 버퍼에
다 들어가서 이 버그가 숨습니다. 실제로 이 버그가 있었고, 진짜 안드로이드 저장소에
돌려 보고 나서야 드러났습니다.

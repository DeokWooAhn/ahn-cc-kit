---
name: audit
description: >-
  이미 저장소에 들어와 있는 Android 서명·보안 문제를 훑을 때 사용합니다.
  "시크릿 검사해줘", "커밋된 키스토어 있는지 봐줘", "보안 감사해줘",
  "gitignore 제대로 돼 있나 확인해줘" 같은 요청이 해당됩니다.
  Auditing an existing Android repository for committed keystores, plaintext signing
  passwords, gitignore gaps, wrapper tampering, and risky Manifest flags.
metadata:
  category: security
  status: stable
---

# Android 저장소 감사

`android-guard` 훅은 **에이전트의 행동만** 봅니다. 훅을 설치하기 전에 들어간 것,
사람이 직접 넣은 것, `git add .`로 딸려 들어간 것은 아무도 보지 않습니다.
이 스킬은 그 빈틈을 메웁니다.

## 실행

```bash
android-audit
```

경로를 주면 그 저장소를 봅니다. 히스토리까지 보려면 `--history`를 붙입니다(느립니다).

```bash
android-audit ~/work/my-app --history
```

출력 언어는 로케일을 따릅니다(`LANG`, macOS는 시스템 로케일). 필요하면 지정합니다.

```bash
android-audit --lang en
```

`ANDROID_AUDIT_LANG=en`으로도 됩니다. **사용자가 쓰는 언어로 보고합니다** —
영어로 대화 중이면 `--lang en`을 붙입니다.

`android-audit: command not found`가 나오면 플러그인이 활성화되지 않은 것입니다.
직접 검사하지 말고 그 사실을 사용자에게 알립니다.

## 종료 코드

| 코드 | 뜻 |
| --- | --- |
| 0 | 발견 없음 |
| 1 | 발견 있음 |
| 2 | 경로가 없거나 git 저장소가 아님 |

CI에 걸 수 있습니다. 발견이 있으면 실패합니다.

## 결과를 읽을 때

**높음**은 시크릿이 이미 저장소에 있다는 뜻입니다. 나머지와 같은 무게로 보고하지 않습니다.

이 도구는 **값을 출력하지 않습니다.** 파일과 줄 번호만 나옵니다.
보고할 때도 같은 규칙을 지킵니다 — 확인하겠다고 파일을 열어 값을 채팅에 옮기지 않습니다.
위치만 전하고, 사용자가 직접 보게 합니다.

## 고치지 않습니다

**커밋된 시크릿은 파일을 지워도 히스토리에 남습니다.** 그래서 이 도구에는 `--fix`가 없습니다.
"정리했다"고 말하는 것이 가장 위험한 결과이기 때문입니다.

높음 발견이 나오면 순서는 이렇습니다.

1. **키를 회전합니다.** 노출된 키스토어·password는 이미 유출된 것으로 간주합니다.
   저장소가 public이었거나 외부에 공유된 적이 있으면 특히 그렇습니다.
2. 새 값을 CI 변수에 넣습니다. 파일로 되돌리지 않습니다.
3. 추적에서 제외하고 `.gitignore`에 넣습니다.
4. 히스토리 정리(`git filter-repo` 등)는 **사용자가 결정합니다.** 협업자가 있으면
   모두가 다시 클론해야 하므로, 에이전트가 판단해서 실행할 일이 아닙니다.

수정은 사용자가 요청했을 때만 합니다. 감사 결과를 보고하는 것과 고치는 것은 다릅니다.

## 검사 항목

| 항목 | 등급 |
| --- | --- |
| 추적 중인 `local.properties`·키스토어·Play 서비스 계정 JSON | 높음 |
| Gradle·properties의 평문 서명 password | 높음 |
| 히스토리에 추가된 적 있는 서명 파일 (`--history`) | 높음 |
| `.gitignore`에 서명 파일 규칙 누락 | 중간 |
| gradle.org가 아닌 곳에서 받는 Gradle 배포본 | 중간 |
| Manifest의 `debuggable`·`usesCleartextTraffic`·`allowBackup` | 중간 |

Gradle 프로젝트가 아니면 추적 파일 검사만 하고 나머지는 건너뜁니다.

`android-guard` 훅이 앞으로의 유입을 막고, 이 스킬이 이미 들어온 것을 찾습니다.
둘은 겹치지 않습니다.

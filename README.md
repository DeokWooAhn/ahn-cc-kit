# ahn-cc-kit

**모바일 앱 프로젝트를 위한** Claude Code 플러그인 마켓플레이스. 플러그인 하나는 문제 하나만 다룹니다.

다섯 중 셋은 Android·Gradle을 전제하고, `maestro-e2e`는 Android와 iOS를 함께 다룹니다. `git-guard`만
플랫폼과 무관합니다 — Android와 상관없는 규칙을 Android 플러그인에 넣지 않으려고 일부러 떼어 놓았습니다.

| 플러그인 | 전제 | 이런 저장소에서 |
| --- | --- | --- |
| `android-review` | Android · **Compose** | View 시스템(XML·ViewBinding) 항목은 없습니다 |
| `android-guard` | Android · Gradle | Gradle 프로젝트가 아니면 걸릴 일이 거의 없습니다 |
| `android-audit` | Android · Gradle | Gradle이 아니면 추적 파일만 보고 나머지는 건너뜁니다 |
| `git-guard` | **없음** | 어느 언어·플랫폼이든 동작합니다 |
| `maestro-e2e` | Android · iOS · Maestro CLI | Android는 Compose, iOS는 SwiftUI(시뮬레이터) 기준입니다. CI 템플릿은 GitHub Actions의 Android용입니다 |

iOS 프로젝트에서 `android-guard`를 켜 두면 조용히 있을 뿐 `.p12`나 provisioning profile을
지켜주지는 않습니다.

**<https://deokwooahn.github.io/ahn-cc-kit/>** — 어떤 명령이 막히고 통과하는지 136건을
표로 볼 수 있습니다. 그 표는 훅 테스트에서 생성되므로 실제 동작과 어긋나지 않습니다.

## 설치

```bash
claude plugin marketplace add DeokWooAhn/ahn-cc-kit
```

```bash
claude plugin install android-review@ahn-cc-kit
```

```bash
claude plugin install android-guard@ahn-cc-kit
```

```bash
claude plugin install git-guard@ahn-cc-kit
```

```bash
claude plugin install android-audit@ahn-cc-kit
```

```bash
claude plugin install maestro-e2e@ahn-cc-kit
```

## 플러그인

| 플러그인 | 내용 | 상태 |
| --- | --- | --- |
| `android-review` | Compose 기반 Android/Kotlin 코드 리뷰 기준 | stable |
| `android-guard` | Gradle·서명·Manifest 사고 방지 훅 (차단 4 + 경고 2) | stable |
| `git-guard` | 보호 브랜치·force push·파괴적 git 차단 (차단 3) | stable |
| `android-audit` | 이미 들어와 있는 시크릿·설정 문제 감사 | stable |
| `maestro-e2e` | Maestro E2E 도입 절차와 Flow 작성·실행 규칙 | draft |

### android-review

diff·MR·완료된 구현을 리뷰할 때 자동으로 불립니다. 정확성 → 회귀 위험 → 범위 이탈 → 보안 →
테스트 누락 순으로 보고, 스타일 지적에는 노력을 쓰지 않습니다.

`skills/review/references/review-rubric.md`에 영역별 체크리스트가 있습니다.
Kotlin, Coroutine, ViewModel, Compose, Compose 성능, 자원 수명, Hilt, Network/Data,
Gradle, Manifest, 테스트.

**UI는 Compose 기준입니다.** XML 레이아웃·ViewBinding을 전제한 항목은 담지 않았습니다.

### android-guard

Android/Gradle 훅 6개. 서명 자격 증명 접근·wrapper 변조·Gradle 캐시 삭제를 막고,
서명 없는 release 빌드와 Manifest 노출 변경을 알립니다. 훅마다 `ANDROID_GUARD_DISABLE_*`로
개별로 끌 수 있습니다. 판정 기준과 한계는
[plugins/android-guard/README.md](plugins/android-guard/README.md)에 있습니다.

`bash`와 `jq`가 필요합니다.

```bash
python3 plugins/android-guard/hooks/test_hooks.py
```

### git-guard

보호 브랜치로 직접 push, `--force` push(`--force-with-lease`는 통과), `reset --hard`·
`clean -fd`·`branch -D` 같은 되돌리기 어려운 git 명령을 막습니다. 좁은 범위 작업
(`git restore <파일>`, `git clean -nd`)은 통과시킵니다. 판정 기준과 파싱 한계는
[plugins/git-guard/README.md](plugins/git-guard/README.md)에 있습니다.

```bash
python3 plugins/git-guard/hooks/test_hooks.py
```

### maestro-e2e

Android·iOS 앱에 Maestro E2E를 도입할 때("마에스트로 도입해줘")와 Flow를 쓰고 돌릴 때("마에스트로 돌려줘")
불립니다. 두 플랫폼에 같은 id를 붙여 Flow 하나로 양쪽을 돌립니다. 도입은 4단계로 나눠 단계마다 PR을 냅니다. 테스트 id와 테스트 모드 → Flow와 MCP →
CI smoke → 릴리스 관문 순서입니다.
도입할 때 프로젝트 CLAUDE.md에 "화면 코드를 바꾼 작업은 마치기 전에 Maestro를 돌린다" 규칙을 넣어, 요청하지 않아도
화면 작업 마무리 때 E2E가 돌게 합니다.

실제로 CI를 멈추게 했던 원인을 피하는 템플릿(공통 실행 subflow, 에뮬레이터 안정화 스크립트, CI job)이
들어 있습니다. 정규식 id, 권한 기본값 때문의 APK 전송 멈춤, 데이터 삭제 직후 재실행 레이스 같은 것들입니다.
GitLab CI와 iOS CI는 문서만 있고 검증하지 않았습니다. 자세한 내용은
[plugins/maestro-e2e/README.md](plugins/maestro-e2e/README.md)에 있습니다.

## 원하는 프로젝트에서만 켜기

설치할 때 **범위를 고르면 됩니다.** 기본값인 user 범위로 넣으면 그 머신의 모든 프로젝트에
훅이 붙습니다. 안드로이드가 아닌 저장소에서도 매 도구 호출마다 돌게 됩니다.

| 범위 | 적용 | 기록되는 곳 |
| --- | --- | --- |
| user | 모든 프로젝트 | `~/.claude/` |
| project | 이 저장소 + 협업자 전체 | 저장소의 `.claude/settings.json` |
| local | 이 저장소, 나만 | 저장소의 `.claude/settings.local.json` |

`/plugin install`은 설치할 때 이 셋 중 하나를 묻습니다. 셸에서 바로 지정할 수도 있습니다.

```bash
claude plugin install android-guard@ahn-cc-kit --scope project
```

혼자 쓸 저장소라면 `--scope local`을 씁니다. 이미 user 범위로 깔았다면 특정 저장소에서
끄는 대신, 지우고 원하는 범위로 다시 설치하는 편이 깔끔합니다.

```bash
claude plugin uninstall android-guard@ahn-cc-kit
```

### 팀에 자동으로 붙이기

저장소의 `.claude/settings.json`에 마켓플레이스를 적어 두면, 팀원이 그 폴더를 신뢰한 뒤부터는
마켓플레이스가 프롬프트 없이 등록됩니다.

```json
{
  "extraKnownMarketplaces": {
    "ahn-cc-kit": {
      "source": { "source": "github", "repo": "DeokWooAhn/ahn-cc-kit" }
    }
  },
  "enabledPlugins": {
    "android-guard@ahn-cc-kit": true,
    "git-guard@ahn-cc-kit": true
  }
}
```

다만 **등록과 설치는 다릅니다.** GitHub처럼 외부 소스에서 오는 플러그인은 팀원이
`claude plugin install`을 한 번 실행해야 실제로 로드됩니다. 그전까지 Claude Code는
설치되지 않았다고 표시하고 실행할 명령을 알려 줍니다.

## 필요한 것

훅 플러그인(`android-guard`, `git-guard`)은 `bash`와 `jq`가 필요합니다. `git-guard`는 `git`도 씁니다.
`maestro-e2e`는 [Maestro CLI](https://maestro.dev)를 씁니다. iOS까지 돌리려면 Xcode가 필요합니다.

**`jq`가 없으면 훅이 아무것도 막지 못합니다.** 입력 파싱이 전부 빈 값이 되어, 입력이 깨졌을 때
통과시키는 경로를 그대로 타기 때문입니다. 그래서 두 플러그인 모두 세션 시작 때 한 번 확인하고
없으면 알려 줍니다. 이 확인은 `*_DISABLE_DEPS_CHECK=1`로 끌 수 있습니다.

### android-audit

훅은 에이전트의 행동만 봅니다. 훅을 설치하기 전에 들어간 것, 사람이 직접 넣은 것,
`git add .`로 딸려 들어간 것은 아무도 보지 않습니다. 이 플러그인이 그 빈틈을 메웁니다.

```bash
android-audit            # 발견 없으면 0, 있으면 1 — CI 에 그대로 걸 수 있습니다
```

**값을 출력하지 않고 위치만 보고하며, 고치지 않습니다.** 커밋된 시크릿은 파일을 지워도
히스토리에 남으므로 "정리했다"는 결과가 가장 위험합니다. 자세한 내용은
[plugins/android-audit/README.md](plugins/android-audit/README.md)에 있습니다.

```bash
python3 plugins/android-audit/tests/test_audit.py
```

## 훅 플러그인을 고칠 때

훅 테스트는 **`/bin/bash`로 돌립니다.** macOS 기본 셸은 아직 bash 3.2이고, 3.2는 `set -u`
아래에서 빈 배열의 `"${a[@]}"`를 unbound variable로 봅니다. PATH의 최신 bash로만 돌리면
이 계열 버그가 통과해 버립니다. 빈 배열을 펼 때는 `${a[@]+"${a[@]}"}` 가드를 쓰거나,
`${#a[@]}`로 세고 인덱스로 접근합니다.

**긴 입력에서 `${var//패턴/}`을 쓰지 않습니다.** bash 3.2는 이 치환이 입력 길이에 대해 제곱 이상으로 느려서,
`${NEW//[[:space:]]/}`로 빈 내용을 확인하던 훅이 4000줄짜리 파일 하나에 몇 분씩 걸렸습니다. 훅 제한 시간을 넘기면
판정이 조용히 빠집니다. 빈 내용 확인은 `[[ "$NEW" == *[![:space:]]* ]]`처럼 glob으로 합니다. 줄마다
`$(...)` 서브셸을 띄우는 것도 피합니다. 테스트 하네스가 판정을 켠 채로 큰 입력을 넣어 3초 안에 끝나는지 봅니다.

## 로컬 개발

설치하지 않고 바로 로드합니다.

```bash
claude --plugin-dir ./plugins
```

수정 후에는 재시작 없이 반영합니다.

```
/reload-plugins
```

문서 사이트는 `docs/`에 있습니다. GitHub Pages가 `main`의 `/docs`를 그대로 서빙하므로
빌드 과정이 없습니다. 훅의 판정을 바꿨으면 표를 다시 생성합니다.

```bash
python3 scripts/gen-cases.py
```

로컬에서 보려면 정적 서버를 띄웁니다. `cases.json`을 `fetch`로 읽기 때문에 파일을 직접 열면
안 됩니다.

```bash
python3 -m http.server 4173 --directory docs
```

배포 전 검증합니다. 커뮤니티 마켓플레이스 심사와 같은 검사입니다.

```bash
claude plugin validate ./plugins/android-review
```

매니페스트와 문서 숫자가 서로 맞는지 봅니다. 마켓플레이스 목록과 `plugins/` 폴더, 두 곳에 적는 버전,
README의 사례 수를 확인합니다.

```bash
python3 scripts/check-manifests.py
```

### CI

`.github/workflows/ci.yml`이 PR과 `main` 푸시마다 돌립니다.

- **테스트 3종**을 Ubuntu와 macOS에서 돌립니다. macOS의 `/bin/bash` 3.2에서만 드러나는 버그가 있어 둘 다 봅니다.
- **매니페스트 검사**(`scripts/check-manifests.py`).
- **사례 표를 다시 만들고 차이가 없는지** 봅니다. 훅을 고치고 `gen-cases.py`를 돌리지 않으면 여기서 걸립니다.
  감사 샘플은 `--lang ko`로 고정해서 러너의 로케일과 상관없이 같은 결과가 나옵니다.
- **`claude plugin validate`**를 마켓플레이스와 플러그인마다 돌립니다. 로그인 없이 동작하고, CLI 버전은
  워크플로의 `CLAUDE_CODE_VERSION`으로 고정합니다.

## 라이선스

MIT. 파생 구성 요소의 출처는 [CREDITS.md](CREDITS.md)에 기록합니다.

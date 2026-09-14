# ahn-cc-kit

Claude Code 플러그인 마켓플레이스. 플러그인 하나는 문제 하나만 다룹니다.

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

## 플러그인

| 플러그인 | 내용 | 상태 |
| --- | --- | --- |
| `android-review` | Compose 기반 Android/Kotlin 코드 리뷰 기준 | stable |
| `android-guard` | Gradle·서명·Manifest 사고 방지 훅 (차단 4 + 경고 2) | stable |
| `git-guard` | 보호 브랜치·force push·파괴적 git 차단 (차단 3) | stable |

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

## 훅 플러그인을 고칠 때

훅 테스트는 **`/bin/bash`로 돌립니다.** macOS 기본 셸은 아직 bash 3.2이고, 3.2는 `set -u`
아래에서 빈 배열의 `"${a[@]}"`를 unbound variable로 봅니다. PATH의 최신 bash로만 돌리면
이 계열 버그가 통과해 버립니다. 빈 배열을 펼 때는 `${a[@]+"${a[@]}"}` 가드를 쓰거나,
`${#a[@]}`로 세고 인덱스로 접근합니다.

## 로컬 개발

설치하지 않고 바로 로드합니다.

```bash
claude --plugin-dir ./plugins
```

수정 후에는 재시작 없이 반영합니다.

```
/reload-plugins
```

배포 전 검증합니다. 커뮤니티 마켓플레이스 심사와 같은 검사입니다.

```bash
claude plugin validate ./plugins/android-review
```

## 라이선스

MIT. 파생 구성 요소의 출처는 [CREDITS.md](CREDITS.md)에 기록합니다.

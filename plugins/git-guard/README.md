# git-guard

되돌리기 어려운 git 작업을 막는 훅 묶음. Android와 무관한 것만 모았다.

```bash
claude plugin install git-guard@ahn-cc-kit
```

필요: `bash`, `jq`, `git`.

## 훅

| 훅 | 막는 것 | opt-out |
| --- | --- | --- |
| `protected-branch-guard` | 보호 브랜치로 직접 push | `GIT_GUARD_DISABLE_PROTECTED_BRANCH` |
| `force-push-guard` | `--force` push (`--force-with-lease`는 통과) | `GIT_GUARD_DISABLE_FORCE_PUSH` |
| `destructive-git-guard` | `reset --hard`, `clean -fd`, `branch -D` 등 | `GIT_GUARD_DISABLE_DESTRUCTIVE` |

## protected-branch-guard

기본 보호 목록은 `main,master,release/*`다. glob이 먹는다.

```bash
GIT_GUARD_PROTECTED_BRANCHES="main,release/*,hotfix/*"
```

잡는 형태.

| 명령 | 판정 근거 |
| --- | --- |
| `git push origin main` | refspec |
| `git push origin HEAD:main` | refspec의 목적지 |
| `git push origin refs/heads/main` | `refs/heads/` 제거 후 |
| `git push origin +main` | `+` 제거 후 |
| `git push origin :main` | 원격 브랜치 삭제 |
| `git push --delete origin main` | 원격 브랜치 삭제 |
| `git push --all` / `--mirror` | 보호 브랜치까지 함께 나간다 |
| `git push` | **현재 브랜치를 읽어서 판정** |
| `git add . && git push origin main` | 명령 구분자를 넘어서 찾는다 |
| `git -C <path> push origin main` | 전역 옵션을 건너뛴다 |

**인자 없는 `git push`가 가장 까다롭다.** 명령만 봐서는 대상을 알 수 없으므로
`git rev-parse --abbrev-ref HEAD`로 현재 브랜치를 읽는다. 저장소 밖이거나 detached HEAD면
판정할 수 없으므로 통과시킨다.

`-o ci.skip` 같이 값을 먹는 옵션의 값은 refspec으로 세지 않는다.

## force-push-guard

**브랜치를 가리지 않는다.** 자기 feature 브랜치라도 `--force`는 무조건 덮어쓰므로, 마지막
fetch 이후 누군가 올린 커밋이 말없이 사라진다. `--force-with-lease`는 그 경우 거절하고 멈춘다.
한 단어 차이라 대안 비용이 없어서 전면 차단이 성립한다.

refspec 앞의 `+`(`git push origin +main`)도 같은 force로 본다.

## destructive-git-guard

기준은 **reflog로 복구되는가**다.

| 명령 | 잃는 것 |
| --- | --- |
| `git reset --hard` | 워킹트리·인덱스 변경 (커밋은 reflog에 남음) |
| `git clean -fd` | 추적되지 않는 파일. **git 안에 없으므로 복구 불가** |
| `git checkout -f`, `git checkout -- .`, `git restore .` | 커밋되지 않은 변경 전부 |
| `git branch -D` | 병합되지 않은 브랜치의 커밋 |
| `git stash drop` / `clear` | 치워 둔 작업 |
| `git reflog expire`, `git gc --prune` | **복구망 자체** |

좁은 범위 작업은 막지 않는다.

- `git restore src/Foo.kt`, `git checkout -- src/Foo.kt` — 파일 지정은 통과
- `git restore --staged .` — 인덱스만 되돌리므로 워킹트리는 안전하다
- `git clean -nd` — dry run은 통과
- `git branch -d` — 병합 안 됐으면 git이 알아서 거절한다
- `git reset --soft`, `git reset` — 워킹트리를 건드리지 않는다
- `git gc` — 인자 없는 기본값은 안전한 쪽이다

## 파싱 한계

셸 문법을 온전히 파싱하지 않는다. **따옴표로 감싼 내용은 먼저 지운다.**

```bash
git commit -m "git push origin main 은 금지"   # 막지 않는다
git push origin "main"                        # 놓칠 수 있다
```

오탐보다 누락을 택했다. 오탐은 사람이 훅을 꺼 버리게 만들고, 그러면 아무것도 막지 못한다.
변수 확장(`git push $REMOTE $BRANCH`)과 명령 치환도 놓친다. 사고 방지용 가드이지 샌드박스가 아니다.

## 테스트

```bash
python3 plugins/git-guard/hooks/test_hooks.py
```

훅을 **`/bin/bash`로 돌린다.** macOS 기본 셸은 아직 bash 3.2이고, 3.2는 `set -u` 아래에서
빈 배열의 `"${a[@]}"`를 unbound variable로 본다. 최신 bash로만 돌리면 이 계열 버그가
통과해 버린다. 실제로 이 플러그인을 만들면서 세 군데에서 잡혔다.

현재 브랜치를 읽어야 하는 케이스를 위해 임시 저장소 두 개(`main`, `feature/x`)를 만든다.

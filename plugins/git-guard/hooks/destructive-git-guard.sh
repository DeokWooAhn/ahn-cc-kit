#!/usr/bin/env bash
# PreToolUse (matcher: Bash): 되돌리기 어려운 git 명령을 막는다.
#
# 기준은 "reflog로 복구되는가"다.
#   reset --hard  : 커밋은 reflog에 남지만 워킹트리 변경은 사라진다
#   clean -fd     : 추적되지 않는 파일이라 git 안에 애초에 없다. 복구 불가
#   stash drop    : dangling commit으로 남지만 찾기 어렵다
#   gc --prune=now: 복구망 자체를 걷어낸다
#
# 좁은 범위 작업은 막지 않는다. git restore src/Foo.kt 는 통과하고,
# 트리 전체(.)를 되돌리는 것만 막는다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: GIT_GUARD_DISABLE_DESTRUCTIVE=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${GIT_GUARD_DISABLE_DESTRUCTIVE:-}" ]] && exit 0

COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -n "$COMMAND" ]] || exit 0

# shellcheck source=_git_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_git_lib.sh"

# 아래 세 헬퍼는 GIT_ARGS를 전역으로 읽는다. 인자로 넘기지 않는 이유는
# bash 3.2(stock macOS)가 set -u 아래에서 빈 배열의 "${a[@]}" 를 unbound로 보기 때문이다.
# ${#a[@]} 와 인덱스 접근은 3.2에서도 안전하다.

# 묶음 단축 옵션(-fd, -xdf)도 잡는다. 대소문자를 구분한다.
has_short() {
  local letter="$1" a i
  for ((i = 0; i < ${#GIT_ARGS[@]}; i++)); do
    a="${GIT_ARGS[i]}"
    [[ "$a" == --* ]] && continue
    [[ "$a" == -* ]] || continue
    [[ "$a" == *"$letter"* ]] && return 0
  done
  return 1
}
has_arg() {
  local want="$1" i
  for ((i = 0; i < ${#GIT_ARGS[@]}; i++)); do
    [[ "${GIT_ARGS[i]}" == "$want" ]] && return 0
  done
  return 1
}
has_prefix() {
  local want="$1" i
  for ((i = 0; i < ${#GIT_ARGS[@]}; i++)); do
    [[ "${GIT_ARGS[i]}" == "$want"* ]] && return 0
  done
  return 1
}

block() {
  cat >&2 <<MSG
$1

$2

사용자가 명시적으로 요청한 작업이면 사용자가 직접 실행하거나, 이 훅을 끈다.
  GIT_GUARD_DISABLE_DESTRUCTIVE=1
MSG
  exit 2
}

if git_find_sub "$COMMAND" reset && has_arg --hard; then
  block "git reset --hard 는 워킹트리와 인덱스의 변경을 지운다. 커밋되지 않은 작업은 복구할 수 없다." \
"먼저 무엇을 잃는지 본다.
  git status
  git stash push -m \"작업 중\"     (버리지 않고 치워 둔다)
커밋 이력만 되돌리려면 워킹트리를 건드리지 않는 방법을 쓴다.
  git reset --soft <ref>          (변경을 인덱스에 남긴다)
  git revert <ref>                (이력을 지우지 않고 되돌린다)"
fi

if git_find_sub "$COMMAND" clean; then
  if { has_short f || has_arg --force; } &&
    ! has_short n && ! has_arg --dry-run; then
    block "git clean 은 추적되지 않는 파일을 지운다. git 안에 없던 파일이므로 reflog로도 복구되지 않는다." \
"무엇이 지워지는지 먼저 확인한다.
  git clean -nd                   (실제로 지우지 않고 목록만)
-x 를 붙이면 .gitignore된 것까지 지운다. local.properties, 빌드 산출물, IDE 설정이 함께 날아간다."
  fi
fi

if git_find_sub "$COMMAND" checkout; then
  if has_short f || has_arg --force; then
    block "git checkout --force 는 워킹트리의 변경을 말없이 버린다." \
"먼저 확인하고, 버리지 않으려면 치워 둔다.
  git status
  git stash push -m \"작업 중\""
  fi
  if has_arg . || has_arg :/; then
    block "git checkout 으로 트리 전체를 되돌리면 커밋되지 않은 변경이 전부 사라진다." \
"파일을 특정해서 되돌린다.
  git checkout -- <path>
전부 되돌려야 한다면 먼저 치워 둔다.
  git stash push -m \"작업 중\""
  fi
fi

if git_find_sub "$COMMAND" restore; then
  # --staged 만 쓰면 인덱스만 되돌리므로 워킹트리는 안전하다.
  staged_only=0
  if { has_arg --staged || has_short S; } &&
    ! has_arg --worktree && ! has_short W; then
    staged_only=1
  fi
  if ((staged_only == 0)) && { has_arg . || has_arg :/; }; then
    block "git restore 로 트리 전체를 되돌리면 커밋되지 않은 변경이 전부 사라진다." \
"파일을 특정해서 되돌린다.
  git restore <path>
인덱스만 되돌리는 것이라면 워킹트리는 건드리지 않는다.
  git restore --staged ."
  fi
fi

if git_find_sub "$COMMAND" branch; then
  if has_short D ||
    { has_arg --delete && { has_arg --force || has_short f; }; }; then
    block "git branch -D 는 병합되지 않은 브랜치도 지운다. 그 브랜치에만 있던 커밋은 reflog가 만료되면 사라진다." \
"먼저 안전한 삭제를 시도한다. 병합되지 않았으면 git이 거절한다.
  git branch -d <branch>
정말 지워야 한다면 어디에도 없는 커밋이 있는지 확인한다.
  git log --oneline <branch> --not --remotes"
  fi
fi

if git_find_sub "$COMMAND" stash && ((${#GIT_ARGS[@]} > 0)); then
  case "${GIT_ARGS[0]}" in
    drop | clear)
      block "git stash ${GIT_ARGS[0]} 는 치워 둔 작업을 버린다. dangling commit으로 잠시 남지만 찾기 어렵다." \
"무엇이 들어 있는지 먼저 본다.
  git stash list
  git stash show -p stash@{0}
필요 없는 것이 확실하면 사용자가 직접 지운다."
      ;;
  esac
fi

if git_find_sub "$COMMAND" reflog && has_arg expire; then
  block "git reflog expire 는 복구망 자체를 걷어낸다. 이걸 돌린 뒤에는 reset --hard 로 잃은 커밋도 되찾을 수 없다." \
"저장소 용량이 목적이라면 기본 만료 정책(reflog 90일)에 맡긴다. 수동 만료가 필요한 상황은 드물다."
fi

if git_find_sub "$COMMAND" gc && has_prefix --prune; then
  block "git gc --prune 은 도달 불가능한 객체를 즉시 지운다. reflog에서 복구할 여지가 사라진다." \
"용량 회수가 목적이면 인자 없이 돌린다. 기본값이 안전한 쪽이다.
  git gc"
fi

exit 0

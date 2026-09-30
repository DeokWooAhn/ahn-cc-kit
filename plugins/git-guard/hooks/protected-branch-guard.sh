#!/usr/bin/env bash
# PreToolUse (matcher: Bash): 보호 브랜치로 직접 push 하는 것을 막는다.
#
# 보호 브랜치는 MR/PR을 거친다. 직접 push는 리뷰와 CI를 건너뛰고, 서버가 보호 설정으로
# 거절하면 그나마 낫지만 거절하지 않으면 조용히 들어간다.
#
# 인자 없는 git push가 가장 까다롭다. 명령만 봐서는 대상을 알 수 없으므로 현재 브랜치와,
# git이 계산한 실제 목적지(@{push})를 함께 읽는다. push.default=upstream이면 feature 브랜치에서도
# main으로 나갈 수 있다. 저장소 밖이거나 detached HEAD면 판정할 수 없으니 통과시킨다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: GIT_GUARD_DISABLE_PROTECTED_BRANCH=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${GIT_GUARD_DISABLE_PROTECTED_BRANCH:-}" ]] && exit 0

COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -n "$COMMAND" ]] || exit 0

# shellcheck source=_git_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_git_lib.sh"

PATTERNS="${GIT_GUARD_PROTECTED_BRANCHES:-main,master,release/*}"

block() {
  cat >&2 <<MSG
$1

보호 브랜치: $PATTERNS
브랜치를 따서 MR/PR을 만듭니다.

  git switch -c <type>/<subject>
  git push -u origin <type>/<subject>

의도한 것이라면 사용자가 직접 실행합니다.

훅을 끄려면 GIT_GUARD_DISABLE_PROTECTED_BRANCH=1 을 Claude Code 프로세스의 환경에 둡니다.
보호 목록만 바꾸려면 같은 자리에 GIT_GUARD_PROTECTED_BRANCHES 를 쉼표로 구분해 설정합니다.
훅은 자기 환경변수만 읽으므로 명령 앞에 붙이는 것(GIT_GUARD_...=1 git ...)으로는 적용되지 않습니다.
  .claude/settings.json 의 env 에 넣거나, claude 를 띄우기 전에 export 합니다.
MSG
  exit 2
}

# 명령마다 따로 본다. 한 줄에 합쳐 보면 줄바꿈 뒤의 push를 놓치고, 앞 명령의 인자가 refspec처럼 섞인다.
check_push() {
  git_parse_push

  if ((PUSH_ALL)); then
    block "git push --all / --mirror 은 보호 브랜치까지 함께 밀어 올립니다."
  fi

  if ((${#PUSH_REFS[@]} == 0)); then
    # refspec이 없다. 현재 브랜치 이름과 실제 목적지가 다를 수 있으니 둘 다 본다.
    local branch target
    branch=$(git_current_branch)
    if git_is_protected "$branch"; then
      block "현재 브랜치가 보호 대상입니다: '$branch'. 직접 push 하지 않습니다."
    fi
    target=$(git_push_target)
    if git_is_protected "$target"; then
      block "현재 브랜치는 '$branch'이지만 인자 없는 push는 '$target'(으)로 나갑니다. upstream과 push.default 설정 때문입니다. 직접 push 하지 않습니다."
    fi
    return 0
  fi

  local ref dst
  for ref in ${PUSH_REFS[@]+"${PUSH_REFS[@]}"}; do
    dst=$(git_refspec_dst "$ref")
    [[ "$dst" == "HEAD" ]] && dst=$(git_current_branch)
    git_is_protected "$dst" || continue

    if ((PUSH_DELETE)) || [[ "$ref" == :* ]]; then
      block "원격에서 보호 브랜치를 삭제하려 합니다: '$dst'. 복구가 어렵고 다른 사람의 작업 기준이 사라집니다."
    fi
    block "보호 브랜치입니다: '$dst'. 직접 push 하지 않습니다."
  done
  return 0
}

git_split_commands "$COMMAND"
for ((s = 0; s < ${#GIT_SEGMENTS[@]}; s++)); do
  git_find_sub "${GIT_SEGMENTS[s]}" push || continue
  check_push
done

exit 0

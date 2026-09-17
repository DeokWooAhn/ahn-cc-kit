#!/usr/bin/env bash
# PreToolUse (matcher: Bash): 보호 브랜치로 직접 push 하는 것을 막는다.
#
# 보호 브랜치는 MR/PR을 거친다. 직접 push는 리뷰와 CI를 건너뛰고, 서버가 보호 설정으로
# 거절하면 그나마 낫지만 거절하지 않으면 조용히 들어간다.
#
# 인자 없는 git push가 가장 까다롭다. 명령만 봐서는 대상을 알 수 없으므로 현재 브랜치를 읽는다.
# 저장소 밖이거나 detached HEAD면 판정할 수 없으니 통과시킨다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: GIT_GUARD_DISABLE_PROTECTED_BRANCH=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${GIT_GUARD_DISABLE_PROTECTED_BRANCH:-}" ]] && exit 0

COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -n "$COMMAND" ]] || exit 0

# shellcheck source=_git_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_git_lib.sh"

git_find_sub "$COMMAND" push || exit 0
git_parse_push

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

if ((PUSH_ALL)); then
  block "git push --all / --mirror 은 보호 브랜치까지 함께 밀어 올립니다."
fi

if ((${#PUSH_REFS[@]} == 0)); then
  # refspec이 없다 — 현재 브랜치로 나간다.
  branch=$(git_current_branch)
  if git_is_protected "$branch"; then
    block "현재 브랜치가 보호 대상입니다: '$branch'. 직접 push 하지 않습니다."
  fi
  exit 0
fi

for ref in ${PUSH_REFS[@]+"${PUSH_REFS[@]}"}; do
  dst=$(git_refspec_dst "$ref")
  [[ "$dst" == "HEAD" ]] && dst=$(git_current_branch)
  git_is_protected "$dst" || continue

  if ((PUSH_DELETE)) || [[ "$ref" == :* ]]; then
    block "원격에서 보호 브랜치를 삭제하려 합니다: '$dst'. 복구가 어렵고 다른 사람의 작업 기준이 사라집니다."
  fi
  block "보호 브랜치입니다: '$dst'. 직접 push 하지 않습니다."
done

exit 0

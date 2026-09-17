#!/usr/bin/env bash
# PreToolUse (matcher: Bash): --force push를 막는다. --force-with-lease 는 통과시킨다.
#
# 브랜치를 가리지 않는다. 자기 feature 브랜치라도 --force 는 무조건 덮어쓰므로,
# 내가 마지막으로 fetch 한 뒤 누군가 올린 커밋이 있으면 말없이 사라진다.
# --force-with-lease 는 그 경우 거절하고 멈춘다. 한 단어 차이라 대안 비용이 없다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: GIT_GUARD_DISABLE_FORCE_PUSH=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${GIT_GUARD_DISABLE_FORCE_PUSH:-}" ]] && exit 0

COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -n "$COMMAND" ]] || exit 0

# shellcheck source=_git_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_git_lib.sh"

git_find_sub "$COMMAND" push || exit 0
git_parse_push

FORCED=0
((PUSH_FORCE)) && FORCED=1
# refspec 앞의 + 도 force다.
# bash 3.2는 set -u 아래에서 빈 배열의 "${a[@]}" 를 unbound로 본다. + 가드를 쓴다.
for ref in ${PUSH_REFS[@]+"${PUSH_REFS[@]}"}; do
  [[ "$ref" == +* ]] && FORCED=1
done
((FORCED)) || exit 0

cat >&2 <<'MSG'
--force push를 쓰지 않습니다. 마지막 fetch 이후 원격에 올라온 커밋이 있으면 말없이 사라집니다.

--force-with-lease 를 씁니다. 원격이 내가 아는 상태와 다르면 거절하고 멈춥니다.

  git push --force-with-lease origin <branch>

refspec 앞의 + (예: origin +main) 도 같은 force다.
정말로 무조건 덮어써야 한다면 사용자가 직접 실행합니다.

훅을 끄려면 GIT_GUARD_DISABLE_FORCE_PUSH=1 을 Claude Code 프로세스의 환경에 둡니다.
훅은 자기 환경변수만 읽으므로 명령 앞에 붙이는 것(GIT_GUARD_...=1 git ...)으로는 꺼지지 않습니다.
  .claude/settings.json 의 env 에 넣거나, claude 를 띄우기 전에 export 합니다.
MSG
exit 2

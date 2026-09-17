#!/usr/bin/env bash
# SessionStart (matcher: startup|resume): 이 플러그인의 훅이 실제로 동작할 수 있는지 확인합니다.
#
# 훅들은 입력이 깨졌을 때 통과시키도록(fail open) 만들어져 있습니다. 무관한 도구 호출을
# 막지 않기 위해서입니다. 그런데 jq가 없으면 파싱 결과가 전부 빈 값이 되므로 같은 경로를
# 타고 "조용히 아무것도 막지 않는" 상태가 됩니다. 보호받고 있다고 믿는 쪽이 더 위험하므로
# 세션 시작 때 한 번 알립니다.
#
# SessionStart에서 exit 2는 세션 시작 자체를 실패시킵니다. 무슨 일이 있어도 0으로 끝냅니다.
# stdout의 평문은 Claude가 보는 컨텍스트로 들어갑니다.

set -uo pipefail

cat >/dev/null 2>&1 || true

PLUGIN="git-guard"
OPTOUT="GIT_GUARD_DISABLE_DEPS_CHECK"
NEEDED="jq git"

[[ -n "${!OPTOUT:-}" ]] && exit 0

MISSING=""
for bin in $NEEDED; do
  command -v "$bin" >/dev/null 2>&1 || MISSING="${MISSING:+$MISSING, }$bin"
done
[[ -n "$MISSING" ]] || exit 0

cat <<MSG
⚠️ $PLUGIN 플러그인이 동작하지 않습니다. 없는 명령: $MISSING

이 플러그인의 훅은 전부 jq로 입력을 읽습니다. jq가 없으면 모든 판정이 빈 값이 되어
아무것도 막지 못한 채 조용히 통과합니다. 설치 전까지는 보호받고 있지 않습니다.

  macOS   brew install jq
  Debian  sudo apt install jq
  Fedora  sudo dnf install jq

설치한 뒤 세션을 다시 시작하면 됩니다.

이 확인이 필요 없으면 $OPTOUT=1 을 Claude Code 프로세스의 환경에 둡니다.
.claude/settings.json 의 env 에 넣거나, claude 를 띄우기 전에 export 합니다.
MSG
exit 0

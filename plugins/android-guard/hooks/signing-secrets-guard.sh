#!/usr/bin/env bash
# PreToolUse (matcher: Read|Edit|Write|MultiEdit|NotebookEdit|Bash|Grep|Glob):
# Android 서명 자격 증명이 에이전트 컨텍스트에 들어오는 것을 막는다.
# 한 번 읽히면 전사본·로그·요약에서 회수할 수 없다.
#
# Glob은 막지 않는다. 파일이 어디 있는지 찾는 것은 정당하고, 위험한 것은 내용이다.
# 평문인 local.properties 계열은 Grep도 막는다. 바이너리 키스토어는 Grep해도
# 얻을 게 없으므로 막지 않는다.
#
# 사고 방지용 가드다. 샌드박스가 아니며 심볼릭 링크나 여러 단계를 거친 우회는 막지 못한다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: ANDROID_GUARD_DISABLE_SIGNING_SECRETS=1. stdin을 다 읽은 뒤에 확인한다.
# 읽기 전에 exit하면 하네스가 닫힌 파이프에 쓰게 되어 비활성화된 훅이 도구 호출을 실패시킨다.
[[ -n "${ANDROID_GUARD_DISABLE_SIGNING_SECRETS:-}" ]] && exit 0

TOOL=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
[[ "$TOOL" == "Glob" ]] && exit 0

FILE_PATH=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
SEARCH_PATH=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null || true)

# 경로 성분의 시작에서만 매치하고, 뒤에 이름 문자가 이어지면 매치하지 않는다.
# 그래서 local.properties.example / foo.jks.sample 은 자연히 빠진다.
LEAD='(^|[/[:space:]"'\''=:;,(])'
TAIL='([^A-Za-z0-9_.-]|$)'
TEXT_RE="${LEAD}(local\.properties|keystore\.properties|signing\.properties)${TAIL}"
SA_RE="${LEAD}([A-Za-z0-9_.-]*(service-account|play-publisher|play-store-key)[A-Za-z0-9_.-]*\.json)${TAIL}"
BIN_RE="${LEAD}([A-Za-z0-9_.-]+\.(jks|keystore|p12|pepk))${TAIL}"

shopt -s nocasematch

block() {
  echo "$1" >&2
  exit 2
}

for s in "$FILE_PATH" "$COMMAND" "$SEARCH_PATH"; do
  [[ -n "$s" ]] || continue

  if [[ "$s" =~ $TEXT_RE ]]; then
    block "local.properties / keystore.properties 계열은 서명 password와 key alias를 평문으로 담습니다. 읽거나 편집하거나 출력하지 않습니다. SDK 경로가 필요하면 sdk.dir 대신 \$ANDROID_HOME을 씁니다. 서명 값이 실제로 필요하면 사용자에게 묻습니다 — 배포 서명 값은 CI 변수에만 둡니다."
  fi

  if [[ "$s" =~ $SA_RE ]]; then
    block "Play 서비스 계정 JSON은 배포 권한이 있는 개인 키를 담습니다. 읽거나 편집하거나 출력하지 않습니다. 업로드 자동화가 필요하면 CI 변수로 주입합니다."
  fi

  if [[ "$TOOL" != "Grep" && "$s" =~ $BIN_RE ]]; then
    block "키스토어 파일(.jks/.keystore/.p12/.pepk)은 서명 개인 킵니다. 읽거나 복사하거나 옮기지 않습니다. 경로가 필요하면 Glob으로 찾습니다 — 그건 막히지 않습니다."
  fi
done

exit 0

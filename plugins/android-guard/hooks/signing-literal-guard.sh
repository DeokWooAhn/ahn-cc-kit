#!/usr/bin/env bash
# PreToolUse (matcher: Edit|MultiEdit|Write): Gradle·properties 파일에 서명 password를
# 문자열 리터럴로 쓰는 것을 막는다.
#
# cc-agents-kit의 staged-secret-guard는 커밋 시점을 잡는다. 이 훅은 쓰는 순간을 잡는다.
# 층이 다르므로 겹치지 않는다.
#
# 간접 참조(System.getenv, providers.environmentVariable, findProperty, 프로퍼티 맵 조회)는
# 키워드 뒤에 따옴표가 오지 않으므로 판정식에서 자연히 빠진다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: ANDROID_GUARD_DISABLE_SIGNING_LITERAL=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${ANDROID_GUARD_DISABLE_SIGNING_LITERAL:-}" ]] && exit 0

FILE_PATH=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
[[ -n "$FILE_PATH" ]] || exit 0

case "$FILE_PATH" in
  *.example | *.sample | *.template | *.dist) exit 0 ;;
esac

KIND=""
case "$FILE_PATH" in
  *.gradle | *.gradle.kts) KIND="gradle" ;;
  *.properties) KIND="properties" ;;
  *) exit 0 ;;
esac

NEW=$(printf '%s' "$HOOK_INPUT" | jq -r '
  [ (.tool_input.new_string // empty),
    (.tool_input.content // empty),
    ((.tool_input.edits // []) | map(.new_string // empty) | join("\n"))
  ] | join("\n")' 2>/dev/null || true)
[[ -n "${NEW//[[:space:]]/}" ]] || exit 0

# Groovy/KTS: 키워드 뒤에 바로 따옴표가 오면 리터럴이다.
GRADLE_RE='(storePassword|keyPassword)[[:space:]]*(=)?[[:space:]]*("|'\'')'
# .properties: 키 이름이 password로 끝나고 값이 비어 있지 않으면 리터럴이다.
PROPS_RE='(^|[[:space:]])[A-Za-z0-9_.]*(storePassword|keyPassword|KEYSTORE_PASSWORD|KEY_PASSWORD)[[:space:]]*=[[:space:]]*[^[:space:]]'

while IFS= read -r line; do
  case "$line" in
    *storePassword* | *keyPassword* | *KEYSTORE_PASSWORD* | *KEY_PASSWORD*) ;;
    *) continue ;;
  esac

  if [[ "$KIND" == "gradle" ]]; then
    [[ "$line" =~ $GRADLE_RE ]] || continue
    # "${System.getenv("X")}" 같은 보간 문자열은 리터럴이 아니다.
    [[ "$line" == *'$'* ]] && continue
  else
    [[ "$line" =~ $PROPS_RE ]] || continue
    [[ "$line" == *'$'* ]] && continue
  fi

  cat >&2 <<'MSG'
서명 password를 파일에 문자열 리터럴로 쓰지 않습니다. 한 번 커밋되면 히스토리에서 지우기 어렵고,
저장소를 읽을 수 있는 모두에게 노출됩니다.

간접 참조를 씁니다.
  Kotlin DSL : storePassword = System.getenv("RELEASE_KEYSTORE_PASSWORD")
  Groovy     : storePassword System.getenv('RELEASE_KEYSTORE_PASSWORD')
  Gradle API : providers.environmentVariable("RELEASE_KEYSTORE_PASSWORD").orNull

실제 값은 CI 변수(GitLab CI/CD Variables, GitHub Actions secrets)에만 둡니다.
로컬에서 서명이 필요한 개발자는 각자 local.properties에 두되 그 파일은 커밋하지 않습니다.
MSG
  exit 2
done <<< "$NEW"

exit 0

#!/usr/bin/env bash
# PostToolUse (matcher: Bash): release 빌드가 서명 없이 만들어졌을 가능성을 알린다. 막지 않는다.
#
# 서명 키를 조건부로 구성하는 흔한 Gradle 패턴은, 키가 하나라도 없으면 signingConfig를
# 그냥 건너뛴다. 강제 검증이 없으면 assembleRelease는 그대로 성공한다. 빌드가 초록불이라
# 서명이 됐다고 착각하기 쉬운데, APK·AAB에는 서명 블록이 없다.
#
# 훅은 키의 "존재"만 확인한다. 값을 읽지도 출력하지도 않는다.
# 설정의 존재를 볼 뿐 산출물을 검증하지는 않는다 — 확실히 하려면 apksigner verify가 필요하다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: ANDROID_GUARD_DISABLE_UNSIGNED_RELEASE=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${ANDROID_GUARD_DISABLE_UNSIGNED_RELEASE:-}" ]] && exit 0

COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -n "$COMMAND" ]] || exit 0

RELEASE_RE='(assemble|bundle|package)Release'
[[ "$COMMAND" =~ $RELEASE_RE ]] || exit 0

# 빌드가 실패했으면 서명 얘기를 꺼낼 이유가 없다.
OUT=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_response | if type=="string" then . else tostring end' 2>/dev/null || true)
[[ "$OUT" == *"BUILD FAILED"* ]] && exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
LOCAL_PROPS="$PROJECT_DIR/local.properties"
KEYS="${ANDROID_GUARD_SIGNING_KEYS:-RELEASE_KEYSTORE_FILE,RELEASE_KEYSTORE_PASSWORD,RELEASE_KEY_ALIAS,RELEASE_KEY_PASSWORD}"

MISSING=""
IFS=',' read -r -a KEY_LIST <<< "$KEYS"
# bash 3.2는 set -u 아래에서 빈 배열의 "${a[@]}" 를 unbound로 본다. + 가드를 쓴다.
for key in ${KEY_LIST[@]+"${KEY_LIST[@]}"}; do
  key="${key//[[:space:]]/}"
  [[ -n "$key" ]] || continue
  # 환경 변수에 있으면 통과.
  [[ -n "${!key:-}" ]] && continue
  # local.properties에 "키 =" 형태가 있으면 통과. 값은 읽지 않는다.
  if [[ -f "$LOCAL_PROPS" ]] && grep -qE "^[[:space:]]*${key}[[:space:]]*=[[:space:]]*[^[:space:]]" "$LOCAL_PROPS" 2>/dev/null; then
    continue
  fi
  MISSING="${MISSING:+$MISSING, }$key"
done

[[ -n "$MISSING" ]] || exit 0

MSG="⚠️ release 빌드를 돌렸는데 서명 설정을 찾지 못했다: $MISSING (환경 변수에도, local.properties에도 없음). 서명 키를 조건부로 구성하는 Gradle 패턴은 키가 없으면 signingConfig를 건너뛰고 빌드는 그대로 성공하므로, 산출물에 서명 블록이 없을 수 있습니다. 배포용이라면 CI에서 빌드하거나, apksigner verify <apk> / jarsigner -verify <aab> 로 확인합니다. 이 프로젝트가 다른 이름의 키를 쓴다면 ANDROID_GUARD_SIGNING_KEYS로 맞춥니다."
jq -n --arg ctx "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'

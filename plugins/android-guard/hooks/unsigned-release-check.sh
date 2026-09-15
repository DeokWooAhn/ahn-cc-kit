#!/usr/bin/env bash
# PostToolUse (matcher: Bash): release 빌드가 서명 없이 만들어졌을 가능성을 알립니다. 막지 않습니다.
#
# 서명 키를 조건부로 구성하는 흔한 Gradle 패턴은, 키가 하나라도 없으면 signingConfig를
# 그냥 건너뜁니다. 강제 검증이 없으면 assembleRelease는 그대로 성공합니다. 빌드가 초록불이라
# 서명이 됐다고 착각하기 쉬운데, APK·AAB에는 서명 블록이 없습니다.
#
# 키 "이름"은 프로젝트마다 다릅니다. 접두사는 RELEASE_ / SIGNING_ / ANDROID_ / 없음으로
# 제각각이지만 접미사는 STORE_PASSWORD, KEY_ALIAS 처럼 일정하므로, 정확한 이름 목록 대신
# 패턴으로 봅니다. 그래서 "네 개가 다 있나"가 아니라 "서명 설정이 있기는 한가"를 묻습니다.
#
# 훅은 존재만 확인합니다. 값을 읽지도 출력하지도 않습니다.
# 설정의 존재를 볼 뿐 산출물을 검증하지는 않습니다 — 확실히 하려면 apksigner verify가 필요합니다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: ANDROID_GUARD_DISABLE_UNSIGNED_RELEASE=1. stdin을 다 읽은 뒤에 확인합니다.
[[ -n "${ANDROID_GUARD_DISABLE_UNSIGNED_RELEASE:-}" ]] && exit 0

COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -n "$COMMAND" ]] || exit 0

RELEASE_RE='(assemble|bundle|package)Release'
[[ "$COMMAND" =~ $RELEASE_RE ]] || exit 0

# 빌드가 실패했으면 서명 얘기를 꺼낼 이유가 없습니다.
OUT=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_response | if type=="string" then . else tostring end' 2>/dev/null || true)
[[ "$OUT" == *"BUILD FAILED"* ]] && exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"

# 대소문자를 가리지 않고 매칭합니다. camelCase(storePassword)와 SNAKE_CASE를 함께 덮습니다.
# 언더스코어를 선택적으로 둬서 SNAKE_CASE(RELEASE_STORE_PASSWORD)와
# camelCase(storePassword, keystore.properties의 표준 형태)를 함께 덮습니다.
KEYS="${ANDROID_GUARD_SIGNING_KEYS:-STORE_?FILE|STORE_?PASSWORD|KEY_?ALIAS|KEY_?PASSWORD|KEYSTORE_?FILE|KEYSTORE_?PATH|KEYSTORE_?PASSWORD}"

# 1) 환경 변수에 서명 관련 키가 값과 함께 있는가. 값은 비교만 하고 출력하지 않습니다.
if env | grep -qiE "^[A-Za-z0-9_]*(${KEYS})[A-Za-z0-9_]*=.+" 2>/dev/null; then
  exit 0
fi

# 2) properties 파일에 서명 관련 키가 값과 함께 있는가.
for f in local.properties keystore.properties signing.properties \
         app/keystore.properties app/signing.properties; do
  p="$PROJECT_DIR/$f"
  [[ -f "$p" ]] || continue
  if grep -qiE "^[[:space:]]*[A-Za-z0-9_.]*(${KEYS})[A-Za-z0-9_.]*[[:space:]]*=[[:space:]]*[^[:space:]]" "$p" 2>/dev/null; then
    exit 0
  fi
done

MSG="⚠️ release 빌드를 돌렸는데 서명 설정을 찾지 못했습니다. 환경 변수와 local.properties·keystore.properties 어디에도 storePassword/keyAlias 계열 키가 없습니다. 서명 키를 조건부로 구성하는 Gradle 패턴은 키가 없으면 signingConfig를 건너뛰고 빌드는 그대로 성공하므로, 산출물에 서명 블록이 없을 수 있습니다. 배포용이라면 CI에서 빌드하거나, apksigner verify <apk> / jarsigner -verify <aab> 로 확인하세요. 키를 다른 이름으로 쓴다면 ANDROID_GUARD_SIGNING_KEYS에 정규식으로 지정합니다."
jq -n --arg ctx "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'

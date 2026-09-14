#!/usr/bin/env bash
# PostToolUse (matcher: Edit|MultiEdit|Write): AndroidManifest 편집이 새로 추가한
# 보안 민감 속성을 알린다. 막지 않는다.
#
# 넷 다 정당한 경우가 있으므로 문구는 단정하지 않는다. 의도된 노출인지 확인만 요청한다.
# LAUNCHER intent-filter를 가진 Activity의 exported="true"는 필수라 제외한다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: ANDROID_GUARD_DISABLE_MANIFEST_RISK=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${ANDROID_GUARD_DISABLE_MANIFEST_RISK:-}" ]] && exit 0

FILE_PATH=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
[[ "$(basename "${FILE_PATH:-}")" == "AndroidManifest.xml" ]] || exit 0

NEW=$(printf '%s' "$HOOK_INPUT" | jq -r '
  [ (.tool_input.new_string // empty),
    (.tool_input.content // empty),
    ((.tool_input.edits // []) | map(.new_string // empty) | join("\n"))
  ] | join("\n")' 2>/dev/null || true)
[[ -n "${NEW//[[:space:]]/}" ]] || exit 0

FOUND=""
add() { FOUND="${FOUND:+$FOUND
}- $1"; }

# 런처 Activity의 exported는 필수다. 추가된 내용에 LAUNCHER가 함께 있으면 넘어간다.
if [[ "$NEW" == *'android:exported="true"'* && "$NEW" != *"android.intent.category.LAUNCHER"* ]]; then
  add 'android:exported="true" — 다른 앱이 이 컴포넌트를 직접 호출할 수 있다. 받는 Intent의 extra를 신뢰하지 않는지, permission으로 좁힐 수 있는지 본다.'
fi
[[ "$NEW" == *'android:debuggable="true"'* ]] && \
  add 'android:debuggable="true" — release에 들어가면 안 된다. 빌드 타입별로 갈리는지 확인한다.'
[[ "$NEW" == *'android:usesCleartextTraffic="true"'* ]] && \
  add 'android:usesCleartextTraffic="true" — 평문 HTTP가 열린다. 특정 도메인만 필요하면 networkSecurityConfig로 좁힌다.'
[[ "$NEW" == *'android:allowBackup="true"'* ]] && \
  add 'android:allowBackup="true" — 토큰·사용자 식별자가 백업에 실릴 수 있다. dataExtractionRules / fullBackupContent에서 제외되는지 본다.'

[[ -n "$FOUND" ]] || exit 0

MSG="AndroidManifest에 보안 민감 속성이 추가됐다. 의도된 것인지 확인한다.
$FOUND"
jq -n --arg ctx "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'

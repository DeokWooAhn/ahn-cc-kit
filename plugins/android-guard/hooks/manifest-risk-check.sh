#!/usr/bin/env bash
# PostToolUse (matcher: Edit|MultiEdit|Write): AndroidManifest 편집이 새로 추가한
# 보안 민감 속성을 알린다. 막지 않는다.
#
# 넷 다 정당한 경우가 있으므로 문구는 단정하지 않는다. 의도된 노출인지 확인만 요청한다.
# LAUNCHER intent-filter를 가진 Activity의 exported="true"는 필수라 그 Activity만 제외한다.

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
# 내용이 공백뿐이면 볼 것이 없다. ${NEW//[[:space:]]/} 로 지워서 확인하면 bash가 내용 길이에 대해
# 제곱 이상으로 느려진다(4000줄에 100초 넘게). glob 매칭은 선형이다.
[[ "$NEW" == *[![:space:]]* ]] || exit 0

FOUND=""
add() { FOUND="${FOUND:+$FOUND
}- $1"; }

# exported="true"인 컴포넌트 중 런처 Activity가 아닌 것이 있는가. 있으면 yes.
#
# 런처 Activity의 exported는 필수라 제외한다. 예외는 LAUNCHER를 가진 그 Activity 요소에만 적용한다.
# 내용 전체에 LAUNCHER가 한 번 있다고 전부 넘기면, 같은 편집에 들어간 exported Service가 경고 없이 지나간다.
# 요소 경계 없이 속성 조각만 편집한 경우(요소 시작 앞부분이나 요소가 아예 없는 조각)는 어느 요소인지 알 수
# 없으므로, 그 조각에 LAUNCHER가 없을 때만 경고한다.
exported_without_launcher() {
  # < 를 레코드 구분자로 써서 태그 단위로 한 번만 훑는다. 남은 문자열을 잘라 가며 찾으면 요소 수의 제곱만큼
  # 복사해서, Ubuntu 기본 awk(mawk)에서 요소 4000개에 1초 넘게 걸렸다.
  printf '%s' "$NEW" | tr '\n' ' ' | awk -v q="'" '
    BEGIN {
      RS = "<"
      exported_re = "android:exported[ \t]*=[ \t]*[\"" q "]true[\"" q "]"
      launcher = "android\\.intent\\.category\\.LAUNCHER"
      found = 0; seen = 0; tag = ""; elem = ""; pre = ""
    }
    function judge() {
      if (elem ~ exported_re && !(tag ~ /^activity/ && elem ~ launcher)) found = 1
      tag = ""; elem = ""
    }
    {
      r = $0
      if (tag != "") {
        elem = elem "<" r
        if (index(r, "/" tag ">") == 1) judge()
        next
      }
      if (match(r, /^(activity-alias|activity|service|receiver|provider)[ \t\/>]/)) {
        seen = 1
        tag = substr(r, 1, RLENGTH - 1)
        elem = "<" r
        gt = index(r, ">")
        if (gt == 0 || substr(r, gt - 1, 1) == "/") judge()
        next
      }
      # 첫 컴포넌트 앞의 조각. 속성 조각만 편집한 경우 어느 요소인지 알 수 없다.
      if (!seen) pre = pre "<" r
    }
    END {
      if (tag != "") judge()
      if (pre ~ exported_re && pre !~ launcher) found = 1
      print (found ? "yes" : "no")
    }' 2>/dev/null || echo no
}

if [[ "$(exported_without_launcher)" == "yes" ]]; then
  add 'android:exported="true" — 다른 앱이 이 컴포넌트를 직접 호출할 수 있습니다. 받는 Intent의 extra를 신뢰하지 않는지, permission으로 좁힐 수 있는지 봅니다.'
fi
[[ "$NEW" == *'android:debuggable="true"'* ]] && \
  add 'android:debuggable="true" — release에 들어가면 안 됩니다. 빌드 타입별로 갈리는지 확인합니다.'
[[ "$NEW" == *'android:usesCleartextTraffic="true"'* ]] && \
  add 'android:usesCleartextTraffic="true" — 평문 HTTP가 열립니다. 특정 도메인만 필요하면 networkSecurityConfig로 좁힙니다.'
[[ "$NEW" == *'android:allowBackup="true"'* ]] && \
  add 'android:allowBackup="true" — 토큰·사용자 식별자가 백업에 실릴 수 있습니다. dataExtractionRules / fullBackupContent에서 제외되는지 봅니다.'

[[ -n "$FOUND" ]] || exit 0

MSG="AndroidManifest에 보안 민감 속성이 추가됐습니다. 의도된 것인지 확인합니다.
$FOUND"
jq -n --arg ctx "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'

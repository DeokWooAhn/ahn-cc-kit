#!/usr/bin/env bash
# PreToolUse (matcher: Edit|MultiEdit|Write): Gradle wrapper 변조를 막는다.
#
# gradle-wrapper.jar는 저장소에 커밋된 실행 바이너리다. 모든 빌드가 이걸 먼저 실행하므로
# 공급망 관점에서 가장 값싼 표적이고, 손으로 편집할 일이 없다.
# distributionUrl을 낯선 호스트로 바꾸는 것도 같은 표면이다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: ANDROID_GUARD_DISABLE_GRADLE_WRAPPER=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${ANDROID_GUARD_DISABLE_GRADLE_WRAPPER:-}" ]] && exit 0

FILE_PATH=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
[[ -n "$FILE_PATH" ]] || exit 0
BASE=$(basename "$FILE_PATH")

case "$BASE" in
  gradle-wrapper.jar)
    echo "gradle-wrapper.jar는 저장소에 커밋된 실행 바이너리다. 직접 편집하거나 덮어쓰지 않는다. 래퍼를 갱신하려면 ./gradlew wrapper --gradle-version=<버전> 을 쓴다 — jar, 스크립트, properties를 Gradle이 함께 맞춰 준다." >&2
    exit 2
    ;;
  gradlew | gradlew.bat)
    echo "$BASE 는 Gradle이 생성하는 래퍼 스크립트다. 직접 편집하지 않는다. ./gradlew wrapper --gradle-version=<버전> 으로 재생성한다. 빌드 인자를 바꾸고 싶으면 gradle.properties의 org.gradle.jvmargs 같은 설정을 쓴다." >&2
    exit 2
    ;;
  gradle-wrapper.properties) ;;
  *) exit 0 ;;
esac

# 여기부터는 gradle-wrapper.properties 편집이다. 새로 들어가는 내용만 본다.
NEW=$(printf '%s' "$HOOK_INPUT" | jq -r '
  [ (.tool_input.new_string // empty),
    (.tool_input.content // empty),
    ((.tool_input.edits // []) | map(.new_string // empty) | join("\n"))
  ] | join("\n")' 2>/dev/null || true)
[[ -n "${NEW//[[:space:]]/}" ]] || exit 0

# Gradle properties는 URL의 콜론을 \: 로 이스케이프한다. 판정 전에 백슬래시를 걷어낸다.
while IFS= read -r line; do
  [[ "$line" == *distributionUrl* ]] || continue
  url="${line#*distributionUrl}"
  url="${url#*=}"
  url="${url//\\/}"
  url="${url#"${url%%[![:space:]]*}"}"
  [[ -n "$url" ]] || continue
  if [[ ! "$url" =~ ^https://(services|downloads)\.gradle\.org/ ]]; then
    echo "distributionUrl이 https://services.gradle.org/ 또는 https://downloads.gradle.org/ 가 아니다: $url — 모든 빌드가 여기서 Gradle 배포본을 받아 실행한다. 사내 미러를 의도한 것이라면 사용자에게 확인받고 이 훅을 끈다(ANDROID_GUARD_DISABLE_GRADLE_WRAPPER=1)." >&2
    exit 2
  fi
done <<< "$NEW"

exit 0

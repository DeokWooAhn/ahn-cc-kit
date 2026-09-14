#!/usr/bin/env bash
# PreToolUse (matcher: Bash): Gradle 캐시 삭제를 막는다.
#
# 캐시 오류(metadata.bin을 읽을 수 없음, 플러그인 해석 중 null FileLock, 빌드마다 다른 캐시가
# 사라짐)는 캐시 손상이 아니라 캐시 변경 전에 뜬 오래된 데몬이 원인인 경우가 대부분이다.
# 캐시를 지우면 원인은 그대로 둔 채 재다운로드 시간만 잃는다.
#
# 프로젝트 로컬 build/ 와 ./gradlew clean 은 막지 않는다. 복구가 싸다.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: ANDROID_GUARD_DISABLE_GRADLE_CACHE=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${ANDROID_GUARD_DISABLE_GRADLE_CACHE:-}" ]] && exit 0

COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -n "$COMMAND" ]] || exit 0

# 정규식은 변수에 담아 쓴다. [[ =~ ]] 에 괄호가 든 리터럴을 직접 적으면 파싱이 깨진다.
RM_RE='(^|[[:space:]]|;|&|\|)(rm|trash|srm)([[:space:]]|$)'
[[ "$COMMAND" =~ $RM_RE ]] || exit 0

# 대상이 Gradle 홈이나 캐시인가. 프로젝트 로컬 .gradle 디렉터리만으로는 걸리지 않는다.
CACHE_RE='(GRADLE_USER_HOME|~/\.gradle|\$HOME/\.gradle|/\.gradle/caches|(^|[[:space:]])\.gradle/caches)'
[[ "$COMMAND" =~ $CACHE_RE ]] || exit 0

cat >&2 <<'MSG'
Gradle 캐시를 지우지 않는다. 캐시 오류는 대개 손상이 아니라 캐시 변경 전에 뜬 오래된 데몬이 원인이다.

순서대로 확인한다.
  1. ./gradlew --stop          (wrapper가 쓰는 버전의 데몬만 멈춘다)
  2. pkill -f GradleDaemon     (남은 다른 버전까지 정리)
  3. IDE가 띄운 데몬은 --stop이 닿지 않는다. 자기 버전으로 따로 돌고 있는지 본다.

경로를 뒤지기 전에 echo $GRADLE_USER_HOME 부터 확인한다. ~/.gradle이 아닐 수 있고,
빈 검색 결과를 "의존성이 해석된 적 없음"으로 읽으면 틀린다.

정말로 지워야 한다면 사용자에게 재다운로드 비용을 알리고 확인받는다.
MSG
exit 2

#!/usr/bin/env bash
# PreToolUse (matcher: Bash): Gradle 캐시 삭제를 막는다.
#
# 캐시를 지우면 재다운로드 비용이 크고, 원인이 데몬 쪽이면 아무것도 해결되지 않는다.
# Gradle 문서 기준으로 --stop 은 같은 버전의 데몬만 멈추고, --status 도 현재 버전만
# 보여주므로 "멈췄는데도 그대로"인 상황이 쉽게 만들어진다.
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
Gradle 캐시를 지우지 않는다. 재다운로드 비용이 크고, 원인이 데몬 쪽이면 지워도 그대로다.

순서대로 확인한다.
  1. ./gradlew --stop    같은 Gradle 버전의 데몬만 멈춘다. 다른 버전은 남는다.
  2. jps                 모든 버전의 데몬을 본다. --status 는 현재 버전만 보여준다.
  3. IDE는 자기 버전으로 별도 데몬을 띄운다. wrapper의 --stop 이 닿지 않는다.
  4. JAVA_HOME, toolchain, IDE의 JDK가 어긋나면 기존 데몬과 호환되지 않아 새로 뜬다.

경로를 뒤지기 전에 echo $GRADLE_USER_HOME 부터 확인한다. 기본값은 ~/.gradle 이지만
옮겨져 있을 수 있고, 빈 검색 결과를 "의존성이 해석된 적 없음"으로 읽으면 틀린다.

정말로 지워야 한다면 사용자에게 재다운로드 비용을 알리고 확인받는다.
MSG
exit 2

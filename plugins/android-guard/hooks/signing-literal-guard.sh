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
# 내용이 공백뿐이면 볼 것이 없다. ${NEW//[[:space:]]/} 로 지워서 확인하면 bash가 내용 길이에 대해
# 제곱 이상으로 느려진다(4000줄에 100초 넘게). glob 매칭은 선형이다.
[[ "$NEW" == *[![:space:]]* ]] || exit 0

# --- 서명 password 리터럴 판정 ---------------------------------------------------------------
# android-audit/bin/android-audit 에 같은 블록이 있다. 두 플러그인은 따로 설치되므로 파일을 같이 쓸 수 없다.
# 한쪽을 고치면 다른 쪽도 똑같이 고친다. android-audit 테스트가 두 블록이 같은지 확인한다.

# 서명 password를 담는 키 이름. store·key·keystore·signing 뒤에 pass(word)가 온다. 대소문자는 가리지 않는다.
# 예: storePassword, keyPassword, KEYSTORE_PASSWORD, RELEASE_STORE_PASSWORD, ANDROID_STORE_PASS, signing.password
SIGNING_KEY_RE='(store|key|keystore|signing)[_.-]?pass(word)?'

# Gradle(Groovy·KTS) 한 줄이 서명 password에 문자열 리터럴을 넣는가.
#   storePassword = "x"   keyPassword 'x'   val releaseStorePassword = "x"
# 키 이름 앞이 따옴표·$·{ 이면 변수가 아니라 문자열 안의 글자다(getenv("RELEASE_STORE_PASSWORD"),
# props["storePassword"], "$storePassword"). 보간은 키 바로 뒤 큰따옴표 값 안의 $만 인정한다.
# 주석에 $가 있어도 상관없다. Groovy 작은따옴표는 보간하지 않으므로 $가 있어도 리터럴이다.
signing_literal_in_gradle() {
  local line="$1" re q lit rc=1 was=0
  re="(^|[^A-Za-z0-9_\"'\$\{])[A-Za-z0-9_.]*${SIGNING_KEY_RE}[[:space:]]*(=[[:space:]]*|[[:space:]]+)([\"'])(.*)"
  # $(shopt -p) 로 저장하면 줄마다 서브셸이 뜬다. 긴 파일에서 눈에 띄게 느려진다.
  shopt -q nocasematch && was=1
  shopt -s nocasematch
  if [[ "$line" =~ $re ]]; then
    q="${BASH_REMATCH[5]}"
    lit="${BASH_REMATCH[6]}"
    lit="${lit%%"$q"*}"
    rc=0
    [[ -z "$lit" ]] && rc=1
    [[ "$q" == '"' && "$lit" == *'$'* ]] && rc=1
  fi
  ((was)) || shopt -u nocasematch
  return "$rc"
}

# .properties 한 줄이 서명 password에 값을 넣는가. 구분자는 = 와 : 둘 다다.
# 주석 줄(# !)과 빈 값, 값 전체가 ${이름} 자리표시자 하나인 줄은 리터럴이 아니다.
# $ 로 시작한다고 자리표시자가 아니다. $123abc, $ENV, ${ENV}abc 는 리터럴이다.
signing_literal_in_properties() {
  local line="$1" re val rc=1 was=0
  local ph='^[$][{][^{}]+[}][[:space:]]*$'
  [[ "$line" =~ ^[[:space:]]*[#!] ]] && return 1
  re="^[[:space:]]*[A-Za-z0-9_.-]*${SIGNING_KEY_RE}[[:space:]]*[=:][[:space:]]*([^[:space:]].*)$"
  # $(shopt -p) 로 저장하면 줄마다 서브셸이 뜬다. 긴 파일에서 눈에 띄게 느려진다.
  shopt -q nocasematch && was=1
  shopt -s nocasematch
  if [[ "$line" =~ $re ]]; then
    val="${BASH_REMATCH[3]}"
    rc=0
    [[ "$val" =~ $ph ]] && rc=1
  fi
  ((was)) || shopt -u nocasematch
  return "$rc"
}
# --- 판정 끝 ---------------------------------------------------------------------------------

while IFS= read -r line; do
  # 키 이름에는 반드시 pass 가 들어간다. 없는 줄은 정규식까지 가지 않는다.
  case "$line" in *[Pp][Aa][Ss][Ss]*) ;; *) continue ;; esac
  if [[ "$KIND" == "gradle" ]]; then
    signing_literal_in_gradle "$line" || continue
  else
    signing_literal_in_properties "$line" || continue
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

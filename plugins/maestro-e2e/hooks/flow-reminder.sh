#!/usr/bin/env bash
# 화면 코드를 바꾼 작업은 Maestro를 돌린 증거가 있어야 마칠 수 있게 한다.
#
#   flow-reminder.sh mark   UserPromptSubmit: 지금 화면 파일 상태를 턴 시작 기록으로 남기고, 막은 횟수를 지운다
#   flow-reminder.sh        Stop: 이번 턴에 바뀐 화면 파일이 있으면 플랫폼마다 증거를 확인한다
#
# "돌렸습니다"라는 말을 믿지 않고 Maestro가 만든 파일로 판정한다. 플랫폼(android·ios)마다 아래 둘 중 하나가
# 그 플랫폼에서 이번 턴에 바뀐 화면 파일보다 새로워야 통과한다. 둘 다 있으면 더 새로운 쪽을 본다.
#   <git dir>/maestro-e2e-<플랫폼>.xml   maestro test --format=JUNIT --output=<이 경로>
#                                       testcase가 하나 이상이고 failure가 없으면 통과
#   <git dir>/maestro-e2e-<플랫폼>.skip  돌릴 수 없는 이유 한 줄(기기 없음, 넘길 변수 없음 등)
#                                       건너뛰어도 되는지는 스킬이 정한다. 훅은 이유를 사용자에게 그대로 보여 준다
#
# 증거가 없거나 실패한 Flow가 있으면 마치지 못하게 막고(exit 2) 무엇을 할지 알린다.
# 같은 턴에 MAX_BLOCKS번 막았는데도 증거가 없으면 통과시키되, 결과 없이 끝났다고 사용자에게 알린다.
# 기기가 끝내 안 잡히는 경우에도 무한 반복하지 않게 하려는 것이다.
# 통과·건너뜀도 사용자에게 한 줄로 알린다(systemMessage). Claude의 보고와 따로 보이게 하려는 것이다.
#
# Maestro를 여기서 직접 돌리지 않는다. 기기 선택, 스토어판 확인, 변수가 없는 Flow 건너뛰기는 모두
# flows 스킬의 절차라서, 훅은 돌릴 때를 알리고 결과를 확인만 한다.
#
# 화면 파일: 저장소 루트에 .maestro/가 있을 때, 커밋하지 않은 변경 중
#   - Android: .kt 파일에 @Composable
#   - iOS:     .swift 파일에 SwiftUI View(": View", "some View")
#   - 테스트·빌드 산출물 경로는 뺀다
#
# "이번 턴에 바뀐" 것만 본다. 사용자가 미리 고쳐 둔 화면 파일이 있는 저장소에서 질문만 했는데
# 기기 테스트가 시작되면 안 된다. 턴 시작 기록이 없으면(세션 중간에 켠 경우) 지금 상태 전체를 본다.
#
# jq 없이 동작한다. 입력은 읽기만 하고 쓰지 않는다. macOS 기본 bash 3.2에서 돌아야 한다.
# UserPromptSubmit의 stdout은 Claude의 컨텍스트로 들어가므로 mark는 아무것도 출력하지 않는다.

set -uo pipefail

cat >/dev/null 2>&1 || true
MODE="${1:-stop}"
MAX_BLOCKS=3

# Opt-out: MAESTRO_E2E_DISABLE_FLOW_REMINDER=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${MAESTRO_E2E_DISABLE_FLOW_REMINDER:-}" ]] && exit 0

DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -d "$ROOT/.maestro" ]] || exit 0
GIT_DIR=$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null) || exit 0
BASE="$GIT_DIR/maestro-e2e-turn-start"
COUNT="$GIT_DIR/maestro-e2e-stop-count"

is_ui() { # $1 저장소 기준 경로
  local f="$ROOT/$1"
  [[ -f "$f" ]] || return 1
  case "$1" in
    */build/* | build/* | */test/* | */androidTest/* | */testDebug/* | */Tests/* | *Tests.swift | *Test.kt) return 1 ;;
    *.kt) grep -q '@Composable' "$f" 2>/dev/null ;;
    *.swift) grep -Eq '(:[[:space:]]*View([[:space:]]|\{|,|$))|some View' "$f" 2>/dev/null ;;
    *) return 1 ;;
  esac
}

# 지금 상태: 화면 파일마다 "상태코드<TAB>내용해시<TAB>경로" 한 줄.
# -z: 공백·한글 경로도 안전하게 나눈다. 이름 바꾸기(R)·복사(C)는 뒤따르는 원래 경로 항목을 건너뛴다.
STATE=""
skip=0
while IFS= read -r -d '' entry; do
  if ((skip)); then skip=0; continue; fi
  code="${entry:0:2}"
  path="${entry:3}"
  case "$code" in R* | C*) skip=1 ;; esac
  case "$code" in *D*) continue ;; esac
  is_ui "$path" || continue
  hash=$(git -C "$ROOT" hash-object -- "$path" 2>/dev/null)
  STATE="${STATE}${code}"$'\t'"${hash}"$'\t'"${path}"$'\n'
done < <(git -C "$ROOT" status --porcelain=v1 -z --untracked-files=all 2>/dev/null)

if [[ "$MODE" == "mark" ]]; then
  printf '%s' "$STATE" > "$BASE" 2>/dev/null || true
  rm -f "$COUNT" 2>/dev/null || true
  exit 0
fi

[[ -n "$STATE" ]] || exit 0

BEFORE=""
[[ -f "$BASE" ]] && BEFORE=$'\n'"$(cat "$BASE" 2>/dev/null)"$'\n'

# 이번 턴에 바뀐 것: 턴 시작 기록에 같은 줄(같은 경로·같은 내용)이 없는 화면 파일.
CHANGED=""; NEW=""; ANDROID_FILES=""; IOS_FILES=""
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  case "$BEFORE" in *$'\n'"$line"$'\n'*) continue ;; esac
  code="${line%%$'\t'*}"
  path="${line#*$'\t'}"; path="${path#*$'\t'}"
  CHANGED="${CHANGED}${path}"$'\n'
  # 새 파일이면서 턴 시작 때는 없던 경로만 "새 화면"으로 본다.
  case "$code" in
    '??' | A*) case "$BEFORE" in *$'\t'"$path"$'\n'*) ;; *) NEW="${NEW}${path}"$'\n' ;; esac ;;
  esac
  case "$path" in
    *.kt) ANDROID_FILES="${ANDROID_FILES}${path}"$'\n' ;;
    *.swift) IOS_FILES="${IOS_FILES}${path}"$'\n' ;;
  esac
done <<< "$STATE"

[[ -n "$CHANGED" ]] || exit 0

list() { # 최대 5개, 나머지는 개수로
  local n=0 extra=0 p
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    n=$((n + 1))
    if ((n <= 5)); then printf '  - %s\n' "$p"; else extra=$((extra + 1)); fi
  done <<< "$1"
  ((extra)) && printf '  - 외 %d개\n' "$extra"
  return 0
}

# $1 증거 파일이 $2 목록의 모든 화면 파일보다 새로운가
fresh() {
  local p
  [[ -f "$1" ]] || return 1
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    [[ "$1" -nt "$ROOT/$p" ]] || return 1
  done <<< "$2"
  return 0
}

# 사용자에게 보이는 한 줄(Stop 훅 stdout의 systemMessage)
notify() {
  local msg
  msg=$(printf '%s' "$1" | tr '\n\t' '  ' | tr -d '\000-\037' | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '{"systemMessage":"%s"}\n' "$msg"
}

OK_NOTE=""   # 통과·건너뜀 요약
TODO=""      # 막을 때 Claude에게 줄 지시
SHORT=""     # 끝내 증거가 없을 때 사용자에게 줄 요약

check_platform() { # $1 android|ios  $2 표시 이름  $3 바뀐 파일 목록
  local key="$1" label="$2" files="$3"
  local xml="$GIT_DIR/maestro-e2e-$key.xml" skipf="$GIT_DIR/maestro-e2e-$key.skip" use=""
  fresh "$xml" "$files" && use=xml
  if fresh "$skipf" "$files"; then
    if [[ -z "$use" || "$skipf" -nt "$xml" ]]; then use=skip; fi
  fi

  if [[ "$use" == xml ]]; then
    # 줄바꿈 여부와 상관없이 요소마다 한 줄이 되게 '<'에서 끊는다.
    local flat cases failed
    flat=$(tr '<' '\n' < "$xml" 2>/dev/null)
    cases=$(printf '%s\n' "$flat" | grep -cE '^testcase[ >/]' || true)
    failed=$(printf '%s\n' "$flat" | awk '
      /^testcase[ >\/]/ { n = "(이름 없음)"; if (match($0, / name="[^"]*"/)) n = substr($0, RSTART + 7, RLENGTH - 8) }
      /^failure[ >\/]/ { print n }')
    if [[ -z "$failed" && "${cases:-0}" -gt 0 ]]; then
      OK_NOTE="${OK_NOTE:+$OK_NOTE / }$label Flow ${cases}개 통과"
      return 0
    fi
    if [[ -n "$failed" ]]; then
      TODO="${TODO}"$'\n'"$label: 리포트에 실패한 Flow가 있습니다."$'\n'"$(list "$failed")"$'\n'
      TODO="${TODO}flows 스킬의 \"실패했을 때\"로 Flow·앱·환경 중 무엇인지 판정합니다. 고친 뒤 같은 명령으로 다시 돌립니다."$'\n'
      TODO="${TODO}앱 문제를 Flow를 느슨하게 고쳐 가리지 않습니다. 환경 문제라 지금 고칠 수 없으면 아래 .skip에 이유를 남깁니다."$'\n'
      SHORT="${SHORT:+$SHORT / }$label 실패 Flow 있음"
    else
      TODO="${TODO}"$'\n'"$label: 리포트에 Flow가 하나도 없습니다. 돌릴 Flow 경로나 태그를 확인하고 다시 돌립니다."$'\n'
      SHORT="${SHORT:+$SHORT / }$label 리포트 비어 있음"
    fi
  elif [[ "$use" == skip ]]; then
    local reason
    reason=$(head -n 1 "$skipf" 2>/dev/null | tr -d '\r' | cut -c1-200)
    reason="${reason#"${reason%%[![:space:]]*}"}"
    if [[ -n "$reason" ]]; then
      OK_NOTE="${OK_NOTE:+$OK_NOTE / }$label 건너뜀: $reason"
      return 0
    fi
    TODO="${TODO}"$'\n'"$label: 건너뛴 이유가 비어 있습니다. .skip 첫 줄에 이유를 적습니다."$'\n'
    SHORT="${SHORT:+$SHORT / }$label 건너뛴 이유 없음"
  else
    TODO="${TODO}"$'\n'"$label: 화면을 바꾼 뒤 돌린 결과가 없습니다."$'\n'
    SHORT="${SHORT:+$SHORT / }$label 결과 없음"
  fi

  TODO="${TODO}  돌릴 때:   maestro --device <serial 또는 udid> test .maestro -e APP_ID=<$label APP_ID> --format=JUNIT --output='$xml'"$'\n'
  TODO="${TODO}  못 돌릴 때: printf '%s\\n' '<이유 한 줄>' > '$skipf'"$'\n'
  return 1
}

[[ -n "$ANDROID_FILES" ]] && check_platform android Android "$ANDROID_FILES"
[[ -n "$IOS_FILES" ]] && check_platform ios iOS "$IOS_FILES"

if [[ -z "$TODO" ]]; then
  notify "maestro-e2e: $OK_NOTE"
  exit 0
fi

n=$(cat "$COUNT" 2>/dev/null || echo 0)
case "$n" in '' | *[!0-9]*) n=0 ;; esac
n=$((n + 1))
printf '%s' "$n" > "$COUNT" 2>/dev/null || true

if ((n > MAX_BLOCKS)); then
  notify "maestro-e2e: 화면 코드가 바뀌었는데 Maestro 결과 없이 끝났습니다 ($SHORT${OK_NOTE:+ / $OK_NOTE}). ${MAX_BLOCKS}번 요청했습니다."
  exit 0
fi

{
  printf '이 저장소에는 .maestro/가 있고, 이번 작업에서 화면 코드가 바뀌었습니다.\n'
  list "$CHANGED"
  printf '\n마치기 전에 maestro-e2e 플러그인 flows 스킬의 절차대로 바꾼 플랫폼에서 smoke와 release Flow를 돌립니다.\n'
  printf '"돌렸다"는 보고가 아니라 Maestro의 JUnit 리포트로 확인합니다. 리포트가 화면을 바꾼 뒤에 만들어져야 합니다.\n'
  printf '기기가 없거나 넘길 변수가 없어 못 돌리면 이유 한 줄을 .skip으로 남깁니다. 이유는 사용자에게 그대로 보입니다.\n'
  printf '%s' "$TODO"
  [[ -n "$OK_NOTE" ]] && printf '\n확인됨: %s\n' "$OK_NOTE"
  if [[ -n "$NEW" ]]; then
    printf '\n새로 생긴 화면 파일이 있습니다.\n'
    list "$NEW"
    printf '새 화면이면 flows 스킬의 "Flow를 만들지 정하기" 기준으로 판단해, 권하는 방법(새 Flow / 기존 Flow에 단계 추가 / 만들지 않음)과 이유를 붙여 사용자에게 묻습니다. 답을 받기 전에는 Flow를 만들지 않습니다.\n'
  fi
  printf '\n(확인 %d/%d. 끄려면 MAESTRO_E2E_DISABLE_FLOW_REMINDER=1)\n' "$n" "$MAX_BLOCKS"
} >&2
exit 2

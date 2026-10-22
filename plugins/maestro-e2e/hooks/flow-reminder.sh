#!/usr/bin/env bash
# 화면 코드를 바꾼 작업을 마치려 할 때 Maestro를 돌리라고 Claude에게 한 번 알린다.
#
#   flow-reminder.sh mark   UserPromptSubmit: 지금 화면 파일 상태를 턴 시작 기록으로 남긴다
#   flow-reminder.sh        Stop: 이번 턴에 바뀐 화면 파일이 있으면 알린다(exit 2)
#
# Maestro를 여기서 직접 돌리지 않는다. 기기 선택, 스토어판 확인, 변수가 없는 Flow 건너뛰기는 모두
# flows 스킬의 절차라서, 훅은 "지금 돌릴 때다"만 확실하게 알리고 실행은 Claude가 스킬대로 한다.
# 스킬 설명만으로는 Claude가 E2E를 떠올리지 않으면 돌지 않는다. 이 훅이 그 빈틈을 메운다.
#
# 화면 파일: 저장소 루트에 .maestro/가 있을 때, 커밋하지 않은 변경 중
#   - Android: .kt 파일에 @Composable
#   - iOS:     .swift 파일에 SwiftUI View(": View", "some View")
#   - 테스트·빌드 산출물 경로는 뺀다
#
# "이번 턴에 바뀐" 것만 본다. 사용자가 미리 고쳐 둔 화면 파일이 있는 저장소에서 질문만 했는데
# 기기 테스트가 시작되면 안 된다. 턴 시작 기록이 없으면(세션 중간에 켠 경우) 지금 상태 전체를 본다.
# 알린 뒤에는 기록을 지금 상태로 바꿔 같은 턴에 다시 알리지 않는다.
# stop_hook_active가 참이면(이 훅 때문에 이어서 일하는 중이면) 알리지 않는다. 무한 반복을 막는다.
#
# jq 없이 동작한다. 입력에서 필요한 건 stop_hook_active 하나뿐이다.
# UserPromptSubmit의 stdout은 Claude의 컨텍스트로 들어가므로 mark는 아무것도 출력하지 않는다.

set -uo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
MODE="${1:-stop}"

# Opt-out: MAESTRO_E2E_DISABLE_FLOW_REMINDER=1. stdin을 다 읽은 뒤에 확인한다.
[[ -n "${MAESTRO_E2E_DISABLE_FLOW_REMINDER:-}" ]] && exit 0

DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -d "$ROOT/.maestro" ]] || exit 0
GIT_DIR=$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null) || exit 0
BASE="$GIT_DIR/maestro-e2e-turn-start"

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

save() { printf '%s' "$STATE" > "$BASE" 2>/dev/null || true; }

if [[ "$MODE" == "mark" ]]; then
  save
  exit 0
fi

case "$HOOK_INPUT" in
  *'"stop_hook_active":true'* | *'"stop_hook_active": true'*) exit 0 ;;
esac

[[ -n "$STATE" ]] || exit 0

BEFORE=""
[[ -f "$BASE" ]] && BEFORE=$'\n'"$(cat "$BASE" 2>/dev/null)"$'\n'

# 이번 턴에 바뀐 것: 턴 시작 기록에 같은 줄(같은 경로·같은 내용)이 없는 화면 파일.
CHANGED=""; NEW=""; ANDROID=0; IOS=0
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
  case "$path" in *.kt) ANDROID=1 ;; *.swift) IOS=1 ;; esac
done <<< "$STATE"

[[ -n "$CHANGED" ]] || exit 0
save

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

PLATFORMS=""
((ANDROID)) && PLATFORMS="Android"
((IOS)) && PLATFORMS="${PLATFORMS:+$PLATFORMS, }iOS"

{
  printf '이 저장소에는 .maestro/가 있고, 이번 작업에서 화면 코드가 바뀌었습니다.\n'
  list "$CHANGED"
  printf '\n마치기 전에 maestro-e2e 플러그인 flows 스킬의 절차대로 %s에서 smoke와 release Flow를 돌리고 결과를 보고합니다.\n' "$PLATFORMS"
  printf '기기가 없거나 넘길 변수가 없는 Flow는 건너뛰고 건너뛰었다고 보고합니다. 실패하면 Flow·앱·환경 중 무엇인지 판정합니다.\n'
  if [[ -n "$NEW" ]]; then
    printf '\n새로 생긴 화면 파일이 있습니다.\n'
    list "$NEW"
    printf '새 화면이면 flows 스킬의 "Flow를 만들지 정하기" 기준으로 판단해, 권하는 방법(새 Flow / 기존 Flow에 단계 추가 / 만들지 않음)과 이유를 붙여 사용자에게 묻습니다. 답을 받기 전에는 Flow를 만들지 않습니다.\n'
  fi
  printf '\n이번 변경으로 이미 돌렸다면 결과만 보고하고 마칩니다.\n'
  printf '(끄려면 MAESTRO_E2E_DISABLE_FLOW_REMINDER=1)\n'
} >&2
exit 2

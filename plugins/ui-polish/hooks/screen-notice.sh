#!/usr/bin/env bash
# 새 화면 파일이 생기면 다듬을지 사용자에게 한 줄로 알린다.
#
#   screen-notice.sh mark   UserPromptSubmit: 턴 시작 시점의 화면 파일 목록을 남긴다
#   screen-notice.sh        Stop: 이번 턴에 새로 생긴 화면 파일이 있으면 알린다
#
# 막지 않는다(exit 0). 고치지도 않는다. 다듬기는 선택이고, 이미 괜찮은 화면을 달라 보이게
# 바꾸는 것은 개선이 아니기 때문이다. 판단과 지시는 사용자가 한다.
#
# 수정이 아니라 "새로 생긴" 화면만 본다. 기존 화면을 한 줄 고칠 때마다 알림이 뜨면
# 금방 무시하게 되고, 그러면 정작 필요할 때도 안 읽힌다.
#
# 같은 경로는 한 번만 알린다. 알린 경로는 <git dir>/ui-polish-notified 에 쌓인다.
#
# 화면 파일: 커밋하지 않은 변경 중
#   - Compose:  .kt  에 @Composable
#   - SwiftUI:  .swift 에 ": View" 또는 "some View"
#   - Flutter:  .dart 에 StatelessWidget·StatefulWidget·build(BuildContext
#   - 테스트·빌드 산출물 경로는 뺀다
#
# jq 없이 동작한다. 입력은 읽기만 한다. macOS 기본 bash 3.2 에서 돌아야 한다.
# UserPromptSubmit 의 stdout 은 Claude 의 컨텍스트로 들어가므로 mark 는 아무것도 출력하지 않는다.

set -uo pipefail

cat >/dev/null 2>&1 || true
MODE="${1:-stop}"

# Opt-out: UI_POLISH_DISABLE_SCREEN_NOTICE=1. stdin 을 다 읽은 뒤에 확인한다.
[[ -n "${UI_POLISH_DISABLE_SCREEN_NOTICE:-}" ]] && exit 0

DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null) || exit 0
GIT_DIR=$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null) || exit 0
BASE="$GIT_DIR/ui-polish-turn-start"
NOTIFIED="$GIT_DIR/ui-polish-notified"

is_screen() { # $1 저장소 기준 경로
  local f="$ROOT/$1"
  [[ -f "$f" ]] || return 1
  case "$1" in
    */build/* | build/* | */test/* | test/* | */tests/* | */androidTest/* | */Tests/* \
      | *Tests.swift | *Test.kt | *_test.dart | *.g.dart | *.freezed.dart) return 1 ;;
    *.kt) grep -q '@Composable' "$f" 2>/dev/null ;;
    *.swift) grep -Eq '(:[[:space:]]*View([[:space:]]|\{|,|$))|some View' "$f" 2>/dev/null ;;
    *.dart) grep -Eq '(StatelessWidget|StatefulWidget|build\([[:space:]]*BuildContext)' "$f" 2>/dev/null ;;
    *) return 1 ;;
  esac
}

# 지금 상태: 화면 파일마다 "상태코드<TAB>경로" 한 줄.
# -z 로 공백·한글 경로를 안전하게 나눈다. 이름 바꾸기(R)·복사(C)는 뒤따르는 원래 경로 항목을 건너뛴다.
STATE=""
skip=0
while IFS= read -r -d '' entry; do
  if ((skip)); then skip=0; continue; fi
  code="${entry:0:2}"
  path="${entry:3}"
  case "$code" in R* | C*) skip=1 ;; esac
  case "$code" in *D*) continue ;; esac
  is_screen "$path" || continue
  STATE="${STATE}${code}"$'\t'"${path}"$'\n'
done < <(git -C "$ROOT" status --porcelain=v1 -z --untracked-files=all 2>/dev/null)

if [[ "$MODE" == "mark" ]]; then
  printf '%s' "$STATE" > "$BASE" 2>/dev/null || true
  exit 0
fi

[[ -n "$STATE" ]] || exit 0

BEFORE=""
[[ -f "$BASE" ]] && BEFORE=$'\n'"$(cat "$BASE" 2>/dev/null)"$'\n'
SEEN=""
[[ -f "$NOTIFIED" ]] && SEEN=$'\n'"$(cat "$NOTIFIED" 2>/dev/null)"$'\n'

# 새로 생긴 화면: 추적되지 않거나 추가된 파일이면서, 턴 시작 기록에도 알림 기록에도 없는 경로.
NEW=""
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  code="${line%%$'\t'*}"
  path="${line#*$'\t'}"
  case "$code" in '??' | A*) ;; *) continue ;; esac
  case "$BEFORE" in *$'\t'"$path"$'\n'*) continue ;; esac
  case "$SEEN" in *$'\n'"$path"$'\n'*) continue ;; esac
  NEW="${NEW}${path}"$'\n'
done <<< "$STATE"

[[ -n "$NEW" ]] || exit 0

printf '%s' "$NEW" >> "$NOTIFIED" 2>/dev/null || true

# 경로 최대 3개까지만 보여 준다. 한 줄 알림이라 길어지면 읽히지 않는다.
n=0
shown=""
while IFS= read -r p; do
  [[ -n "$p" ]] || continue
  n=$((n + 1))
  if ((n <= 3)); then shown="${shown:+$shown, }${p##*/}"; fi
done <<< "$NEW"
((n > 3)) && shown="$shown 외 $((n - 3))개"

MSG="ui-polish: 새 화면 ${n}개가 생겼습니다 ($shown). 다듬으려면 \"디자인 다듬어줘\"라고 하세요."
MSG=$(printf '%s' "$MSG" | tr '\n\t' '  ' | tr -d '\000-\037' | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"systemMessage":"%s"}\n' "$MSG"
exit 0

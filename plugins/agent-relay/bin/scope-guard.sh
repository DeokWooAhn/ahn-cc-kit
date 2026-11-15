#!/bin/bash
# 계획이 허용한 파일만 바뀌었는지 본다.
#
#   scope-guard.sh snapshot [스냅샷파일]
#       구현을 넘기기 직전 상태를 찍는다. 기본값 .claude/relay/snapshot.txt
#
#   scope-guard.sh check [계획파일] [스냅샷파일]
#       계획의 "건드릴 파일" 목록과 실제 변경을 대조한다.
#       기본값 .claude/relay/plan.md, .claude/relay/snapshot.txt
#
# git status 표시만 보면 untracked 파일을 고친 것을 놓치므로 내용 해시로 비교한다.
# 계획 파일은 "## 건드릴 파일" 아래 첫 코드 블록에 경로를 한 줄에 하나씩 적는다.
set -u

if command -v md5 > /dev/null 2>&1; then
  digest() { md5 -q "$1"; }
elif command -v md5sum > /dev/null 2>&1; then
  digest() { md5sum "$1" | cut -d' ' -f1; }
elif command -v shasum > /dev/null 2>&1; then
  digest() { shasum "$1" | cut -d' ' -f1; }
else
  echo "해시 명령을 찾지 못했다 (md5, md5sum, shasum 중 하나가 필요하다)" >&2
  exit 2
fi

hash_of() { [ -f "$1" ] && digest "$1" 2>/dev/null || echo "MISSING"; }

git rev-parse --git-dir > /dev/null 2>&1 || { echo "git 저장소가 아니다" >&2; exit 2; }

snapshot() {
  git status --porcelain | sed 's/^...//' | while IFS= read -r f; do
    printf '%s  %s\n' "$(hash_of "$f")" "$f"
  done
}

case "${1:-check}" in
  snapshot)
    out="${2:-.claude/relay/snapshot.txt}"
    mkdir -p "$(dirname "$out")"
    snapshot > "$out"
    echo "스냅샷 저장: $out ($(wc -l < "$out" | tr -d ' ')개 파일)"
    exit 0
    ;;
  check) ;;
  *)
    echo "사용법: scope-guard.sh {snapshot|check} [...]" >&2
    exit 2
    ;;
esac

plan="${2:-.claude/relay/plan.md}"
snap="${3:-.claude/relay/snapshot.txt}"

[ -f "$plan" ] || { echo "계획 파일 없음: $plan" >&2; exit 2; }
[ -f "$snap" ] || { echo "스냅샷 없음: $snap — 구현을 넘기기 전에 snapshot 을 찍어라" >&2; exit 2; }

allowed=$(awk '
  /^## 건드릴 파일/ { insec = 1; next }
  insec && /^```/   { if (inblk) exit; inblk = 1; next }
  insec && inblk    { print }
' "$plan" | sed 's/[[:space:]]*(.*)$//' | sed 's/[[:space:]]*$//' | grep -v '^$' | sort -u)

[ -n "$allowed" ] || {
  echo "계획에서 허용 파일 목록을 못 읽었다." >&2
  echo "\"## 건드릴 파일\" 제목 아래 코드 블록에 경로를 한 줄에 하나씩 적어라." >&2
  exit 2
}

changed=""
while IFS= read -r line; do
  f="${line#*  }"
  was=$(grep -F "  $f" "$snap" 2>/dev/null | head -1 | cut -d' ' -f1)
  [ "$(hash_of "$f")" != "$was" ] && changed="${changed}${f}"$'\n'
done < <(snapshot)
changed=$(echo "$changed" | grep -v '^$' | sort -u)

echo "── 계획이 허용한 파일 ──"
echo "$allowed"
echo
echo "── 실제로 바뀐 파일 ──"
[ -n "$changed" ] && echo "$changed" || echo "(없음)"
echo

[ -n "$changed" ] || {
  echo "⚠️  바뀐 파일이 없다. 구현이 아무것도 하지 않았는지 확인해라."
  exit 1
}

violations=$(comm -23 <(echo "$changed") <(echo "$allowed"))

if [ -n "$violations" ]; then
  echo "❌ 범위 위반 — 계획에 없는 파일이 바뀌었다"
  echo "$violations" | sed 's/^/   /'
  exit 1
fi

echo "✅ 범위 안에서만 바뀌었다"

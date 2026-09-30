#!/usr/bin/env bash
# git 명령 파싱 공용. 훅에서 source 한다. 단독 실행하지 않는다.
#
# 셸 문법을 온전히 파싱하지는 않는다. 따옴표로 감싼 인자, 변수 확장, 치환은 놓친다.
# 놓치면 통과시킨다(fail open). 사고 방지용 가드이지 샌드박스가 아니다.
#
# 훅은 먼저 git_split_commands 로 명령을 조각낸 뒤 조각마다 git_find_sub 를 부른다.
# 통째로 토큰화하면 앞 명령의 옵션이 뒤 명령에 섞인다. git clean -nd && git clean -fd 에서
# 앞의 -n 이 뒤의 실제 삭제까지 dry run으로 보이게 만든다.

# 명령 문자열을 셸 명령 단위로 나눠 GIT_SEGMENTS 배열에 담는다.
#
# 1. 줄 이어쓰기(\ + 줄바꿈)를 한 줄로 합친다. 안 합치면 뒤 줄의 --force 가 다른 조각으로 떨어진다.
# 2. heredoc 본문을 지운다. 커밋 메시지·PR 본문을 <<'EOF' 로 넘기면 본문의 "git reset --hard" 같은
#    글자가 명령으로 오인된다. 오탐은 훅을 꺼 버리게 만든다.
# 3. 따옴표로 감싼 내용을 지운다. 여러 줄에 걸친 따옴표도 한 덩어리로 본다.
# 4. && || ; | & ( ) ` 와 줄바꿈을 명령 경계로 본다.
git_split_commands() {
  local cmd="$1" nl=$'\n' bsnl=$'\\\n' q="'" line
  GIT_SEGMENTS=()

  cmd="${cmd//"$bsnl"/ }"

  # heredoc: <<DELIM, <<-DELIM, <<'DELIM', <<"DELIM". <<< (here-string)은 heredoc이 아니다.
  # 끝 줄은 앞 공백을 무시하고 비교한다(<<- 는 탭 들여쓰기를 허용한다). 끝 줄이 없으면 끝까지 지운다.
  cmd=$(printf '%s\n' "$cmd" | awk -v q="$q" '
    BEGIN { re = "<<-?[ \t]*[\"" q "]?[A-Za-z_][A-Za-z0-9_]*[\"" q "]?" }
    skip { t = $0; sub(/^[ \t]+/, "", t); if (t == delim) skip = 0; next }
    {
      print
      s = $0; gsub(/<<</, "   ", s)
      if (match(s, re)) {
        delim = substr(s, RSTART, RLENGTH)
        sub(/^<<-?[ \t]*/, "", delim)
        gsub("[\"" q "]", "", delim)
        skip = 1
      }
    }' 2>/dev/null || printf '%s' "$cmd")

  # 따옴표 상태를 줄을 넘어 유지한다. 따옴표 안의 줄바꿈은 명령 경계가 아니므로 출력하지 않는다.
  # 큰따옴표 안의 \" 와, 따옴표 밖의 \' \" 는 따옴표를 열고 닫지 않는다.
  cmd=$(printf '%s\n' "$cmd" | awk -v q="$q" '
    # 따옴표 밖이고 따옴표·백슬래시가 없는 줄은 그대로 둔다. 한 글자씩 이어 붙이면 긴 줄에서 느려진다.
    st == 0 && index($0, q) == 0 && index($0, "\"") == 0 && index($0, "\\") == 0 { print; next }
    {
      out = ""
      n = length($0)
      for (i = 1; i <= n; i++) {
        c = substr($0, i, 1)
        if (st == 1) { if (c == q) { st = 0; out = out " " } continue }
        if (st == 2) {
          if (c == "\\") { i++; continue }
          if (c == "\"") { st = 0; out = out " " }
          continue
        }
        if (c == "\\") { out = out " "; i++; continue }
        if (c == q) { st = 1; continue }
        if (c == "\"") { st = 2; continue }
        out = out c
      }
      printf "%s", out
      if (st == 0) printf "\n"
    }' 2>/dev/null || printf '%s' "$cmd")

  cmd="${cmd//"&&"/$nl}"
  cmd="${cmd//"||"/$nl}"
  cmd="${cmd//";"/$nl}"
  cmd="${cmd//"|"/$nl}"
  cmd="${cmd//"&"/$nl}"
  cmd="${cmd//"("/$nl}"
  cmd="${cmd//")"/$nl}"
  cmd="${cmd//"\`"/$nl}"

  while IFS= read -r line; do
    # ${line//[[:space:]]/} 로 지워 확인하면 긴 줄에서 제곱 이상으로 느려진다. glob 매칭은 선형이다.
    [[ "$line" == *[![:space:]]* ]] && GIT_SEGMENTS+=("$line")
  done <<< "$cmd"
  return 0
}

# 조각 하나에서 하위 명령이 $2인 첫 git 호출을 찾는다. 조각은 git_split_commands 가 만든다.
# 성공하면 GIT_ARGS(하위 명령 뒤 인자)와 GIT_C_DIR(-C 값)을 채우고 0을 반환한다.
git_find_sub() {
  local cmd="$1" want="$2"
  GIT_ARGS=()
  GIT_C_DIR=""

  # 따옴표로 감싼 내용을 먼저 지운다. git commit -m "push to main" 같은 메시지가
  # 명령으로 오인되는 것을 막는다. 대신 git push origin "main" 처럼 인용된 브랜치는
  # 놓치게 된다 — 오탐보다 누락이 낫다. 오탐은 훅을 꺼 버리게 만든다.
  cmd=$(printf '%s' "$cmd" | sed -e "s/'[^']*'/ /g" -e 's/"[^"]*"/ /g' 2>/dev/null || printf '%s' "$cmd")

  # 명령 구분자를 공백으로 바꿔 단순 토큰화한다. && 를 | 보다 먼저 지운다.
  cmd="${cmd//&&/ }"
  cmd="${cmd//||/ }"
  cmd="${cmd//;/ }"
  cmd="${cmd//|/ }"

  local -a toks
  read -ra toks <<< "$cmd"
  local n=${#toks[@]} i j cdir

  for ((i = 0; i < n; i++)); do
    [[ "${toks[i]}" == "git" || "${toks[i]}" == */git ]] || continue
    j=$((i + 1))
    cdir=""
    # git 전역 옵션을 건너뛴다. 값을 먹는 것과 아닌 것을 구분한다.
    while ((j < n)); do
      case "${toks[j]}" in
        -C) cdir="${toks[j + 1]:-}"; j=$((j + 2)) ;;
        -c | --exec-path | --namespace) j=$((j + 2)) ;;
        -*) j=$((j + 1)) ;;
        *) break ;;
      esac
    done
    ((j < n)) || continue
    if [[ "${toks[j]}" == "$want" ]]; then
      GIT_C_DIR="$cdir"
      GIT_ARGS=("${toks[@]:$((j + 1))}")
      return 0
    fi
  done
  return 1
}

# GIT_ARGS가 git push 인자라고 보고 PUSH_* 를 채운다.
git_parse_push() {
  PUSH_REFS=()
  PUSH_DELETE=0
  PUSH_ALL=0
  PUSH_FORCE=0

  local -a positional=()
  local n=${#GIT_ARGS[@]} i a
  for ((i = 0; i < n; i++)); do
    a="${GIT_ARGS[i]}"
    case "$a" in
      --all | --mirror) PUSH_ALL=1 ;;
      -d | --delete) PUSH_DELETE=1 ;;
      -f | --force) PUSH_FORCE=1 ;;
      --force-with-lease* | --force-if-includes) ;;
      # 값을 먹는 옵션. 값이 refspec으로 오해되지 않게 건너뛴다.
      -o | --push-option | --repo | --receive-pack | --exec) i=$((i + 1)) ;;
      -*) ;;
      *) positional+=("$a") ;;
    esac
  done

  # 첫 positional은 remote, 나머지가 refspec이다.
  # 범위를 벗어난 슬라이스는 bash 3.2에서도 안전하다. 빈 배열을 "${a[@]}" 로 펴는 것만 위험하다.
  PUSH_REFS=("${positional[@]:1}")
  return 0
}

# refspec에서 목적지 브랜치 이름만 꺼낸다. +main, src:dst, :dst, refs/heads/x 를 모두 다룬다.
git_refspec_dst() {
  local ref="${1#+}"
  [[ "$ref" == *:* ]] && ref="${ref#*:}"
  ref="${ref#refs/heads/}"
  printf '%s' "$ref"
}

# 현재 브랜치. 저장소가 아니거나 detached HEAD면 빈 문자열(= 판정 불가 → 통과).
git_current_branch() {
  local d="${GIT_C_DIR:-.}" b
  b=$(git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  [[ "$b" == "HEAD" ]] && b=""
  printf '%s' "$b"
}

# 인자 없는 git push가 실제로 향할 원격 브랜치 이름. 판정할 수 없으면 빈 문자열.
#
# 현재 브랜치 이름과 다를 수 있다. push.default=upstream(또는 tracking)이고 feature 브랜치의
# upstream이 origin/main이면 git push 는 main으로 나간다. @{push}는 push.default와
# pushRemote 설정을 반영한 목적지를 돌려준다.
#
# 실패하는 경우는 둘이다. git이 push 자체를 거부하는 경우(simple인데 upstream 이름이 다름,
# upstream 없음)와, 원격에 아직 없는 브랜치를 current로 새로 만드는 경우다. 앞은 막을 필요가 없고
# 뒤는 현재 브랜치 이름이 곧 목적지이므로, 호출하는 쪽이 현재 브랜치로 판정하면 된다.
# 실패할 때도 "@{push}"를 stdout에 찍으므로 종료 코드로 거른다.
git_push_target() {
  local d="${GIT_C_DIR:-.}" t
  t=$(git -C "$d" rev-parse --abbrev-ref --symbolic-full-name '@{push}' 2>/dev/null) || return 0
  # origin/main → main. 원격 이름에 / 가 들어간 경우는 다루지 않는다.
  [[ "$t" == */* ]] || return 0
  printf '%s' "${t#*/}"
}

# 보호 브랜치인가. GIT_GUARD_PROTECTED_BRANCHES는 쉼표로 구분된 glob 목록이다.
git_is_protected() {
  local b="$1" pat
  [[ -n "$b" ]] || return 1
  local -a pats
  IFS=',' read -ra pats <<< "${GIT_GUARD_PROTECTED_BRANCHES:-main,master,release/*}"
  for pat in "${pats[@]}"; do
    pat="${pat//[[:space:]]/}"
    [[ -n "$pat" ]] || continue
    # shellcheck disable=SC2053  # 우변은 glob 패턴이므로 따옴표를 씌우지 않는다.
    [[ "$b" == $pat ]] && return 0
  done
  return 1
}

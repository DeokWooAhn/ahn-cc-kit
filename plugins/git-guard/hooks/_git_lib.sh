#!/usr/bin/env bash
# git 명령 파싱 공용. 훅에서 source 한다. 단독 실행하지 않는다.
#
# 셸 문법을 온전히 파싱하지는 않는다. 따옴표로 감싼 인자, 변수 확장, 치환은 놓친다.
# 놓치면 통과시킨다(fail open). 사고 방지용 가드이지 샌드박스가 아니다.

# 명령 문자열에서 하위 명령이 $2인 첫 git 호출을 찾는다.
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

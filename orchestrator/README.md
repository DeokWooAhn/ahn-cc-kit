# orchestrator

계획·구현·리뷰를 서로 다른 에이전트에 넘기는 왕복을 지휘하는 런타임.
`agent-orchestrator` 플러그인이 문서로 정한 절차를, 사람이 매번 명령을 치지 않아도 돌게 한다.

**1단계만 들어 있다.** 아직 에이전트를 부르지 않는다. 상태·범위·git 검사만 한다.

## 왜 있나

플러그인(0.2.0)은 절차를 문서로 정했지만 실전 적용이 1회에 그쳤다. 그 1회에서 이런 것들이 드러났다.

| 겪은 일 | 이 런타임이 맡는 것 |
| --- | --- |
| `codex exec`가 stdin EOF를 못 받아 40분 멈춤 | timeout, 종료 코드 확인 (2단계) |
| 어디까지 갔는지 사람 머릿속에만 있음 | 상태 머신 + 파일 저장 |
| "커밋하지 마라"를 프롬프트에 적고 확인은 안 함 | 호출 후 git 검사 |

마지막 줄이 중요하다. `git-guard`·`android-guard`는 Claude Code의 PreToolUse 훅이라
**Claude가 돌리는 명령만** 막는다. `codex exec`로 넘긴 뒤 codex가 하는 일은 그 훅을 거치지 않는다.
codex 샌드박스는 파일 쓰기 범위만 제한할 뿐 커밋·브랜치·푸시를 막지 않는다.

## 지금 있는 것

```text
src/orchestrator/
  state.py     RunState, TaskState, StateStore
  scope.py     스냅샷, 계획의 허용 목록 파싱, 범위 대조
  guards.py    커밋·브랜치·스테이징·푸시 감지
  gitio.py     git 호출
  errors.py
```

### state

```python
from orchestrator import RunState, StateStore

store = StateStore(Path(".claude/orchestrate/작업이름/state.json"))
store.create("20261115-작업이름")
store.transition(RunState.PLANNING, note="계획 시작")
store.record_artifact("plan", "01-plan.md")
```

저장은 임시 파일에 쓴 뒤 `os.replace`로 바꾼다. 중간에 죽어도 반쯤 쓰인 상태 파일이 남지 않는다.
전이는 `history`에 쌓이므로 어디서 멈췄는지 나중에 읽을 수 있다.

상태는 `CREATED → PLANNING → PLAN_APPROVAL → IMPLEMENTING → SCOPE_CHECK → REVIEWING →
FIX_PLANNING → FIXING → VERIFYING → WAITING_HUMAN → COMPLETED`.
차단은 `BLOCKED_SCOPE`, `BLOCKED_GIT`, `FAILED_AGENT`, `FAILED_VERIFY`, `MAX_RETRY_EXCEEDED`.

`SCOPE_CHECK`를 별도 상태로 둔 것은 범위 위반이면 **리뷰로 보내지 않기** 위해서다.
절차 문서의 5단계인데, 상태로 두지 않으면 건너뛰기 쉽다.

### scope

```python
from orchestrator import scope

scope.write_snapshot(repo, Path(".claude/orchestrate/작업/snapshot.json"))
# 여기서 구현을 다른 에이전트에 넘긴다
result = scope.check(repo, plan_path, snapshot_path)
result.ok            # 범위 안에서만 바뀌었나
result.violations    # 계획에 없는데 바뀐 파일
result.nothing_changed
```

- `git status` 표시가 아니라 **내용 해시(sha256)**로 비교한다. 이미 untracked이던 파일을 고친 것도 잡힌다
- 스냅샷을 쓰는 디렉터리는 **자기 자신을 ignore에 넣는다.** 산출물·로그가 쌓여도 위반으로 잡히지 않는다
- 경로는 `-z`로 받으므로 공백과 한글이 들어가도 안전하다. rename은 양쪽 경로를 모두 보고한다
- 허용 목록은 계획 파일의 `## 건드릴 파일` 아래 첫 코드 블록이다. 셸 스크립트와 같은 형식이다

### guards

```python
from orchestrator import guards

before = guards.capture(repo)
# 여기서 구현을 다른 에이전트에 넘긴다
violations = guards.check(repo, before)
```

HEAD, 브랜치, 업스트림, 스테이징을 전후로 비교한다. 파일을 고치는 것 자체는 위반이 아니다
(그건 `scope`가 본다). 커밋·브랜치 전환·스테이징·푸시가 생겼는지만 본다.

**되돌리기는 하지 않는다.** 위반을 보고하고 멈출 뿐, `git reset`을 대신 돌리지 않는다.

## 테스트

의존성이 없다. 표준 라이브러리만 쓴다.

```bash
cd orchestrator && PYTHONPATH=src:tests python3 -m unittest discover -s tests -t tests
```

## 아직 없는 것

2단계부터다. `adapters.py`(codex·claude 호출과 timeout), `prompts.py`(역할별 지시문 조립),
`pipeline.py`(상태 전이 규칙), CLI(`orch init|run|step|status|resume`).

`pyproject.toml`의 `orch` 스크립트는 그 CLI가 생긴 뒤에 동작한다.

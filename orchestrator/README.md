# orchestrator

계획·구현·리뷰를 서로 다른 에이전트에 넘기는 왕복을 지휘하는 런타임.
`agent-orchestrator` 플러그인이 문서로 정한 절차를, 사람이 매번 명령을 치지 않아도 돌게 한다.

**1~4단계가 들어 있다.** `orch run`이 멈출 자리까지 알아서 가고,
사람이 봐야 할 곳에서만 선다. 남은 것은 실전 적용과 회고다.

## 왜 있나

플러그인(0.2.0)은 절차를 문서로 정했지만 실전 적용이 1회에 그쳤다. 그 1회에서 이런 것들이 드러났다.

| 겪은 일 | 이 런타임이 맡는 것 |
| --- | --- |
| `codex exec`가 stdin EOF를 못 받아 40분 멈춤 | stdin 차단, 전체 타임아웃, **무활동 감지** |
| 어디까지 갔는지 사람 머릿속에만 있음 | 상태 머신 + 파일 저장 |
| "커밋하지 마라"를 프롬프트에 적고 확인은 안 함 | 호출 후 git 검사 |

마지막 줄이 중요하다. `git-guard`·`android-guard`는 Claude Code의 PreToolUse 훅이라
**Claude가 돌리는 명령만** 막는다. `codex exec`로 넘긴 뒤 codex가 하는 일은 그 훅을 거치지 않는다.
codex 샌드박스는 파일 쓰기 범위만 제한할 뿐 커밋·브랜치·푸시를 막지 않는다.
어느 역할이 어느 도구인지에 따라 덮이는 범위가 달라지므로, 호출 후 git 검사는 배선과 무관하게 돈다.

## 지금 있는 것

```text
src/orchestrator/
  state.py     RunState, TaskState, StateStore
  scope.py     스냅샷, 계획의 허용 목록 파싱, 범위 대조
  guards.py    커밋·브랜치·스테이징·푸시 감지
  policy.py    검증 명령 게이트
  failures.py  실패를 공급자·환경·에이전트로 가른다
  adapters.py  codex·claude 호출, 타임아웃, 무활동 감지
  prompts.py   플러그인 문서를 읽어 역할별 지시문 조립
  pipeline.py  상태 전이 규칙
  __main__.py  CLI
  gitio.py     git 호출
  errors.py
```

## 쓰는 법

```bash
orch init 20261116-작업이름 --plan 계획.md   # 계획을 이미 썼을 때. 바로 승인 자리에 선다
orch init 20261116-작업이름 --task "무엇을 한다"   # 계획부터 세울 때

orch run       # 멈출 자리까지 자동으로
orch step      # 한 걸음만
orch status    # 지금 상태와 다음에 할 일
orch approve   # 계획을 승인해 구현으로 넘긴다
orch fix       # 04-fix-plan.md 를 넘겨 다시 구현시킨다
orch verify    # 계획의 검증 명령을 돌린다
orch resume    # 막힌 자리에서 다시 시작한다
```

작업이 하나뿐이면 이름을 생략할 수 있다. 막힌 상태면 종료 코드가 1이다.

`run`은 **승인을 대신 누르지 않는다.** `PLAN_APPROVAL`과 `WAITING_HUMAN`에서 서고,
막히거나 끝나도 선다. 사람이 `approve`·`fix`·`verify`로 다음 구간을 연다.

```text
orch run       → 계획을 세우고 PLAN_APPROVAL 에서 멈춘다
orch approve
orch run       → 구현·범위 검사·리뷰를 거쳐 WAITING_HUMAN 에서 멈춘다
orch verify    → 검증하고 COMPLETED
```

`approve`만 상태를 바꾸고 선다. `fix`·`verify`·`resume`은 **멈출 자리까지 이어 간다.**
상태만 바꿔 놓고 끝나면 사람이 `run`을 한 번 더 쳐야 하는데, 그 한 번을 잊으면
돌아간 줄 알고 기다리게 된다.

`--max-steps`(기본 12)를 넘기면 멈추고 알린다. 상태가 돌고 있다는 뜻이다.

`--retry-limit` 은 계획의 위험도보다 우선하고, `--stall-seconds 역할=초` 는 그 역할의
무활동 감지 시간을 바꾼다(0 이면 끈다). `--timeout 역할=초` 는 전체 제한 시간이다.
사람이 정한 추가 왕복을 돌릴 때 쓴다.

```bash
orch step --retry-limit 4 --stall-seconds verify=0 --timeout implementer=3600
```

`--no-verify-before-review` 는 리뷰 전 검증을 끈다. 검증이 몇 분씩 걸리는 프로젝트용이다.

역할이 쓸 어댑터는 `--route`로 바꾼다. 기본은 Planner·Reviewer가 codex,
Implementer·Fixer가 claude다. 구현하는 쪽과 리뷰하는 쪽이 서로 다른 도구면 된다.

```bash
orch step --route implementer=codex
```

**Implementer와 Reviewer를 같은 어댑터로 두어도 세션은 갈린다.** 둘 다 호출마다
새 프로세스이고, 리뷰어는 구현 로그를 받지 않는다.

산출물은 `.orchestrate/<작업이름>/`에 쌓이고, `init`이 그 디렉터리를
`.git/info/exclude`에 넣는다. 팀 저장소에서도 추적 파일을 하나도 건드리지 않는다.

### state

```python
from orchestrator import RunState, StateStore

store = StateStore(Path(".orchestrate/작업이름/state.json"))
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

scope.write_snapshot(repo, Path(".orchestrate/작업/snapshot.json"))
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
- **끝이 `/`인 항목은 디렉터리**다. 그 아래를 전부 덮는다. 슬래시가 없으면 파일 하나다.
  에셋 폴더처럼 파일이 여럿 생기는 자리를 한 줄로 적게 하면서도, `presentation` 같은 줄이
  모듈 전체를 조용히 여는 것은 막는다. 막을 때 슬래시만 붙이면 됐을 항목을 함께 알려 준다
- **수정 계획(`04-fix-plan.md`)의 허용 목록은 원 계획과 합집합**이다. 리뷰를 거치며
  범위가 넓어지는 것은 정상 흐름이라, 원 계획을 손으로 고쳐 넓히지 않아도 된다.
  거기 `## 건드릴 파일` 절이 없으면 아무것도 더하지 않는다

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

#### 위험도가 자동 수정 횟수를 정한다

계획의 `## 위험도` 절에 `low` / `medium` / `high` 중 하나를 적는다. 없으면 `medium` 으로 본다.

| 위험도 | 자동 수정 | 언제 |
| --- | --- | --- |
| `low` | 3회 | 한 파일 안에서 끝나고 되돌리기 쉽다 |
| `medium` | 2회 | 여러 파일이나 계층이 함께 바뀐다 |
| `high` | 1회 | 인증·결제·개인정보·배포 설정·DB 마이그레이션에 닿는다 |

결제나 인증에 가까운 작업을 AI 가 세 번, 네 번 연속으로 고치게 하면 사람이 변경 이력을
따라가기 어려워진다. 승인 화면이 위험도와 남은 횟수를 함께 보여 주고, `high` 면 한 줄 더 붙인다.

`Settings.retry_limit` 을 직접 주면 그것이 이긴다. 아무것도 주지 않으면 계획이 정한다.

**원문과 다른 점.** 원문은 위험도로 `human_approval_required` 도 차등하는데, 우리는 위험도와
상관없이 `PLAN_APPROVAL` 과 `WAITING_HUMAN` 에서 **항상** 멈춘다. 그래서 실제로 달라지는 것은
자동 수정 횟수뿐이다.

#### 계획 형식은 승인 전에 본다

세 절이 없으면 런타임이 일을 못 한다. `## 목적`(리뷰 브리프), `## 건드릴 파일`(범위 검사),
`## 검증`(검증 단계)이다. 예전에는 각각 다른 단계에서 터졌다 — 검증 명령이 없는 것을
`VERIFYING` 에 가서야 알았다.

이제 계획이 나온 직후에 한 번에 본다. 필수 절이 없거나 그 아래 코드 블록이 비어 있으면
`BLOCKED_PLAN` 으로 멈춘다. Planner 가 쓴 계획도, 사람이 쓴 계획도 같은 검사를 거친다.

권고 절(`## 할 일`, `## 지킬 것`, `## 이 작업으로 확인할 수 없는 것`, `## 완료 조건`)은
막지 않고 승인 화면에서 알린다. 특히 "확인할 수 없는 것"이 빠지면 결과가 실제보다 넓게 읽힌다.

### policy

계획에 적힌 검증 명령을 **돌리기 전에** 본다. 하나라도 걸리면 아무것도 실행하지 않고
`BLOCKED_POLICY`로 멈춘다.

```python
from orchestrator import check_command

check_command("./gradlew test").allowed       # True
check_command("git push origin main").allowed # False
```

막는 것은 원격 밀기, 되돌리기 계열 git, 재귀 삭제, 내려받아 바로 실행, 환경 변수 덤프,
비밀·서명 파일, 권한 상승, 배포·인프라 도구다.

- **allowlist 가 아니라 denylist 다.** 프로젝트마다 검증 명령이 달라서 "기본 deny"를 두면
  범용 런타임으로 쓸 수 없다. 정말 필요한 명령은 `Settings.allow_commands`에 **줄 전체**를
  그대로 적어 예외로 둔다. 부분 일치는 통하지 않는다
- 계획은 사람이 승인하지만 검증 명령까지 한 줄씩 보지는 않는다. `PLAN_APPROVAL`에서
  막히는 명령이 있으면 **승인 전에 경고**한다
- `env VAR=x 명령`은 통과하고 `env | ...`만 막는다. 앞에 변수를 붙이는 쓰임이 흔하다

**막지 못하는 것이 있다.** 이 게이트는 런타임이 **직접 실행하는** 명령만 본다.
codex 가 자기 안에서 돌리는 명령은 여기를 거치지 않는다. 그쪽은 codex 샌드박스와
호출 후 `guards` 검사가 맡는다. 프롬프트에 적은 금지는 기준을 알려줄 뿐 차단하지 않는다.

### failures

막혔을 때 **무엇 때문인지** 가른다. 로그 끝 4KB 를 보고 분류하고 `failure.json` 에 남긴다.

| 분류 | 뜻 | 다음 |
| --- | --- | --- |
| `provider` | 로그인 만료, 한도, 공급자 오류 | `--route` 로 어댑터를 바꿔 재개 |
| `environment` | 명령·시뮬레이터·SDK 없음, 네트워크, 디스크 | **코드를 고쳐도 안 풀린다.** 환경을 고친 뒤 재개 |
| `agent` | 비정상 종료, 제한 시간, 멈춤 | 로그를 읽고 계획이 과하면 줄인다 |
| `verify` | 검증 명령 실패 | 코드 문제인지 테스트 문제인지 가른다 |

`orch status` 가 그 분류와 다음에 할 일을 보여 주고, `orch resume` 은 **재시도해도 안 되는 실패**
(환경 문제)였으면 "같은 조건이면 또 막힌다"고 경고한다.

```text
[failed_agent] 막혔다

implementer 호출이 failed로 끝났다.
로그인 세션이 만료됐다 (provider)
   근거: Failed to authenticate: OAuth session expired
   다음: 공급자 문제다. 로그인·한도를 확인하거나 `--route <역할>=<다른 어댑터>`로 바꿔 `orch resume`.
```

**검증 실패도 환경 문제일 수 있다.** `JAVA_HOME is not set` 으로 테스트가 깨졌으면 `verify` 가 아니라
`environment` 로 분류한다. 코드를 고치게 두면 쓸데없는 diff 만 늘어난다.

분류는 패턴 대조다. LLM 을 부르지 않는다. 틀릴 수 있으므로 근거로 삼은 로그 한 줄을 함께 적는다.

### adapters

```python
from orchestrator import AgentRequest, CodexAdapter

request = AgentRequest(
    role="implementer",
    prompt_file=Path(".orchestrate/작업/02-implement-prompt.txt"),
    log_file=Path(".orchestrate/작업/02-implement.log"),
    cwd=repo,
)
result = CodexAdapter().run(request)

result.ok          # outcome 이 "ok" 인가
result.outcome     # ok | failed | timeout | stalled | missing_command
result.returncode
result.duration_seconds
result.log_bytes
```

`CodexAdapter`는 `codex exec -s workspace-write <프롬프트>`,
`ClaudeAdapter`는 `claude -p <프롬프트>`를 만든다.
`read_only=True`면 codex는 `-s read-only`, claude는 Read·Glob·Grep 과 `git diff` 계열만 남긴다.
그렇지 않으면 claude 는 Write·Edit·Bash 까지 받는다. **headless claude 는 도구를 명시하지 않으면
승인을 물을 사람이 없어 아무것도 못 한다.**

리뷰어에게 쓰기 도구를 주지 않는 것은 프롬프트가 아니라 이 목록이 막는다.
`REVIEWING` 다음은 `WAITING_HUMAN`이라 범위 검사가 없어서, 리뷰어가 고치면 아무도 잡지 못한다.

그래서 리뷰어에게 빌드·테스트 권한을 주는 대신, **런타임이 리뷰 직전에 계획의 검증 명령을
돌려 그 출력을 브리프에 넣는다.** 출력은 사실이라 "판단의 결과를 주지 않는다"는 브리프 규칙과
부딪히지 않는다. 실패해도 막지 않고 리뷰어에게 함께 준다 — 지적과 실패 원인을 한 왕복에
모으는 편이 낫다. 정책에 막히는 명령이 하나라도 있으면 아무것도 돌리지 않는다.

그래서 **리뷰어는 테스트를 돌리지 못한다.** 읽고 따져서 판단하고, 돌려 보지 못한 것은
그렇다고 밝힌다. 명령을 직접 돌리는 것은 `VERIFYING` 단계의 일이다.
headless claude는 호출마다 새 세션이라 **Implementer와 Reviewer의 세션 분리가 저절로 지켜진다.**

기본 제한 시간은 역할마다 다르다. implementer·fixer 20분, planner 15분, reviewer 10분.
`--timeout 역할=초` 로 바꾼다. 긴 빌드가 끼는 작업에서는 20분이 모자란다.

제한 시간에 끊기면 **그때까지 바뀐 파일을 함께 적는다.** 일을 다 해 놓고 보고만 못
끝낸 경우가 실제로 있었는데, 로그는 0바이트라 사람이 매번 `git status` 로 가려내야 했다.
`orch resume` 은 그 목록을 다음 호출의 프롬프트에 넣어 준다 — 처음부터 다시 하거나
이미 된 것을 되돌리지 않게 하려는 것이다. 어디까지 됐는지는 런타임이 판정하지 않는다.
그 경우 **구현 직전 스냅샷을 다시 찍지 않는다.** 다시 찍으면 쓰다 만 변경이 기준선 안으로
들어가 범위 검사가 못 본다.

- **stdin을 막는다.** 프롬프트를 인자로 주고 stdin은 `DEVNULL`이다.
  `< /dev/null`을 빠뜨려 40분 멈춘 사건이 `gotchas.md`에 있다. 빠뜨릴 수 없게 했다
- **로그는 파일로 직접 받는다.** 파이프를 거치지 않으므로 큰 출력에 막히지 않고 종료 코드도 잃지 않는다
- **프로세스 그룹째 끊는다.** 넘긴 명령이 띄운 하위 프로세스가 고아로 남지 않는다
- 명령이 없으면 예외 대신 `missing_command`로 돌려준다. 환경 문제와 에이전트 실패를 가르기 위해서다

#### 무활동을 따로 본다

40분 멈춤의 본질은 "오래 걸린 것"이 아니라 **첫 줄에서 멈춘 것**이었다.
전체 제한 시간만 두면 구현자 몫인 20분을 그대로 날리고서야 안다.
로그 크기가 `stall_seconds`(기본 180초) 동안 그대로면 그 전에 끊는다.

대신 출력이 드문 명령은 오판할 수 있다. 자식이 파일에 쓸 때는 블록 버퍼링이라 더 뜸해진다.
그런 명령에는 `stall_seconds=0`으로 끄거나 `--stall-seconds 역할=0` 을 준다.

**끝에 한 번에 뱉는 도구에는 아예 걸지 않는다.** 어댑터가 `streams_output` 으로 선언한다.
`claude -p` 가 그렇다 — 도는 동안 로그가 한 글자도 안 자라므로 "자라지 않는다"가 신호가 되지 못한다.
2026-11-17 CalcMoney 작업에서 180초를 넘긴 리뷰가 `stalled` 로 끊겼다. 그쪽은 전체 제한 시간에 맡긴다.

`--output-format stream-json` 으로 흐르게 하는 길도 있었지만 쓰지 않았다.
`03-review.log` 는 사람이 읽는 산출물이고, JSON 줄 더미가 되면 그 값을 잃는다.

#### killpg는 자기 자신을 죽일 수 있다

`start_new_session=True` 없이 띄운 자식은 **오케스트레이터와 같은 프로세스 그룹**에 있다.
그 상태에서 `os.killpg`를 부르면 자기 자신과 자기를 띄운 셸까지 SIGTERM을 받는다.

테스트를 쓰다가 러너가 통째로 죽어서 알았다. 그래서 자식의 그룹이 자기 그룹과 같으면
그룹을 건드리지 않고 그 프로세스에만 신호를 보낸다.

### prompts

플러그인 문서를 읽어 역할별 지시문을 만든다. 문서를 두 벌로 갈라 두지 않기 위해서다.
`ORCH_PLUGIN_DIR`, 설치된 마켓플레이스, 이 저장소 순으로 찾는다.

역할마다 싣는 것이 다르다.

| 역할 | 싣는 것 | 싣지 않는 것 |
| --- | --- | --- |
| Planner | `plan-template.md` 전문 | |
| Implementer | 계획 **파일 경로**와 `gotchas.md` | 계획 본문 |
| Reviewer | 계획의 `## 목적`, 바뀐 파일 목록, 따질 것 | **구현자의 보고와 결론** |
| Fixer | 수정 계획 경로와 `gotchas.md` | 반영하지 않기로 한 지적 |

**리뷰어 브리프에 구현자의 결론이 들어갈 길이 없다.** `review_prompt()`는 구현 로그를
인자로 받지 않는다. 사람이 하면 "구현자가 이렇게 말했는데"를 붙이기 쉬운 자리다.

### pipeline

```python
from orchestrator import Settings, pipeline

settings = Settings(repo=repo, task_id="20261116-작업이름")
pipeline.init(settings)
result = pipeline.step(settings)
result.state      # 지금 상태
result.stopped    # 사람을 기다리며 멈췄나
```

한 걸음은 **지금 상태가 가리키는 일을 하고 다음 상태로 간다.**

```text
CREATED → PLANNING → PLAN_APPROVAL ┄┄ 멈춤 ┄┄ IMPLEMENTING → SCOPE_CHECK
      → REVIEWING → WAITING_HUMAN ┄┄ 멈춤 ┄┄ FIXING → SCOPE_CHECK → ...
                                              또는 VERIFYING → COMPLETED
```

- **스냅샷은 넘기기 직전에 찍는다.** 사람이 순서를 틀릴 자리를 없앴다.
  Planner가 문서를 고친 뒤 스냅샷을 안 찍어 그 변경이 구현자의 위반으로 잡히던 함정이다
- **스냅샷이 둘이다.** `00-baseline.json`은 작업 시작 때 한 번만 찍고 덮어쓰지 않는다.
  `02-snapshot.json`은 넘길 때마다 다시 찍는다. 범위 검사는 뒤엣것(이번 호출이 뭘 했나),
  **리뷰 브리프는 앞엣것**(이 작업이 통틀어 뭘 바꿨나)을 쓴다.
  둘을 가르지 않으면 두 번째 왕복의 리뷰어가 첫 왕복 변경을 못 본다
- **범위 위반이면 리뷰로 보내지 않는다.** `SCOPE_CHECK`가 별도 상태인 이유다
- `PLAN_APPROVAL`과 `WAITING_HUMAN`에서는 반드시 멈춘다. 멈출 때 다음에 뭘 해야 하는지 함께 적는다
- 검증 명령은 계획의 `## 검증` 절 **모든** 코드 블록에서 읽는다. 사람이 승인한 계획에 적힌 것만 돌린다.
  포맷·린트·빌드·테스트를 블록마다 따로 적는 것이 자연스러워서, 첫 블록만 읽으면
  나머지를 돌리지 않고 "검증을 통과했다"가 된다
- **검증 결과에 명령별 소요 시간과 로그 크기를 적는다.** 구현자가 같은 명령을 이미 돌렸으면
  Gradle 같은 빌드 도구가 캐시를 그대로 쓴다. 106개 태스크가 1초에 `UP-TO-DATE`로 끝나면
  다시 돈 것이 아니다. 입력 해시 기반이라 결과는 유효하지만 독립적 재실행은 아니므로,
  시간을 보고 사람이 판단하게 둔다
- 되돌리기는 하지 않는다. 막히면 멈추고 사람이 고친 뒤 `orch resume`
- **한도를 넘겨 막힌 시도는 세지 않는다.** 돌지도 않은 시도가 `retry_count` 를 먹으면
  한도를 올려 재개할 때 그만큼 더 올려야 한다. 그 전이는 `history` 에 남으므로
  `orch resume` 이 `FIXING` 으로 제대로 돌아간다
- `init --task "..."`로 준 작업 설명은 `task.txt`에 남는다. 다음 명령이 그것을 읽는다

**중간에 Ctrl-C로 끊으면 넘긴 명령도 함께 죽는다.** 프로세스 그룹째 보낸다.
자율 모드는 한 번에 20분씩 돌 수 있어서, 끊었을 때 codex 가 계속 파일을 고치고 있으면 곤란하다.

## 테스트

의존성이 없다. 표준 라이브러리만 쓴다.

```bash
cd orchestrator && PYTHONPATH=src:tests python3 -m unittest discover -s tests -t tests
```

멈추는 명령을 실제로 띄워 끊는 테스트와, 진짜 git 저장소에서 파이프라인을 끝까지 돌리는
테스트가 있어서 40초쯤 걸린다. 에이전트 자리에는 셸 스크립트를 끼워 넣으므로 codex·claude를
부르지 않는다. 그래서 범위 위반·커밋 감지까지 실제로 검사한다.

## 아직 없는 것

5단계는 실전 적용과 회고다. 지금까지 돌린 것은 시험용으로 만든 작은 저장소뿐이다.

Model Router, Context Builder, worktree 격리는 1차 범위 밖이다. 왜 뺐는지는 설계안에 있다.

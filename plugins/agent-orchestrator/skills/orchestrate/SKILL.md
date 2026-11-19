---
name: orchestrate
description: >-
  계획·구현·리뷰를 서로 다른 에이전트와 세션에 나눠 맡기는 왕복 개발을 지휘할 때 사용합니다.
  "코덱스에 넘겨줘", "다른 에이전트로 구현해줘", "교차 리뷰해줘", "왕복으로 해보자",
  "오케스트레이션 해줘", "계획만 세워줘" 같은 요청이 해당됩니다. Relaying work between agents — a plan artifact
  another agent implements from, scope verification that only the planned files changed,
  and a cross-review from a separate session that never sees the implementer's conclusion.
metadata:
  category: workflow
  status: review
---

# 에이전트 오케스트레이션

한 에이전트가 계획하고, 다른 에이전트가 구현하고, 또 다른 세션이 리뷰한다.
이 왕복을 지휘하는 것이 이 스킬이 하는 일이다.
나누는 이유는 손이 모자라서가 아니라 **자기가 쓴 것을 자기가 검사하면 통과시키기 때문**이다.

## 언제 쓰나

- 범위를 글로 못 박을 수 있는 작업. 못 박지 못하면 계획부터 다시 쓴다
- 결과를 기계가 판정할 수 있는 작업(테스트·빌드·린트)
- 틀렸을 때 되돌리기 쉬운 작업

**안 쓰는 경우**: 몇 줄 고치면 끝나는 일, 탐색이 대부분이라 범위를 미리 못 적는 일.
왕복은 계획을 쓰고 넘기고 검증하는 비용이 붙는다. 그 비용보다 작은 일에는 손해다.

## 역할과 경계

| 역할 | 하는 일 | 하지 않는 일 |
| --- | --- | --- |
| Planner | 코드를 읽고 계획 산출물을 쓴다 | 구현하지 않는다 |
| Implementer | 계획이 허용한 파일만 고친다 | 계획을 고치지 않는다. 지적되지 않은 것을 겸사겸사 고치지 않는다 |
| Reviewer | 결과물을 독립적으로 판단한다 | 코드를 고치지 않는다. 구현자의 결론을 받지 않는다 |
| Verifier | 명령을 직접 돌려 확인한다 | 보고를 그대로 믿지 않는다 |

Planner와 Verifier는 같은 세션이어도 된다. **Implementer와 Reviewer는 반드시 분리한다.**

## 런타임이 있으면 그것에 맡긴다

이 플러그인의 짝인 파이썬 런타임 `orch`가 설치돼 있으면, 아래 절차를 기계가 돌린다.
상태 저장, 역할별 제한 시간, 멈춤 감지, 범위 검사, 호출 후 git 검사를 맡는다.
**사람이 순서를 틀릴 자리가 없어진다** — 스냅샷을 넘기기 직전에 찍는 것도 런타임이 한다.

```bash
command -v orch
```

있으면 이렇게 돈다.

```bash
orch init 20261116-작업이름 --task "무엇을 한다"
orch run       # 계획을 세우고 승인 자리에서 멈춘다
orch approve   # 사람이 계획을 읽고 승인한다
orch run       # 구현·범위 검사·리뷰를 거쳐 다시 멈춘다
orch verify    # 계획의 검증 명령을 돌린다
```

리뷰 지적 중 반영할 것을 추려 `04-fix-plan.md`에 쓰고 `orch fix`를 치면 다시 돈다.
막히면 `orch status`로 보고, 사람이 고친 뒤 `orch resume`으로 그 자리에서 다시 시작한다.
`fix`·`resume`·`verify`는 상태만 바꾸지 않고 **멈출 자리까지 이어 간다.**

계획을 이미 썼으면 `orch init <이름> --plan <파일>`로 시작한다. 바로 승인 자리에 선다.

**수정 계획의 `## 건드릴 파일`도 범위에 더해진다.** 리뷰를 거치며 범위가 넓어지는 것은 정상 흐름이라
원 계획과 **합집합**으로 본다. 원 계획을 손으로 고쳐 넓히지 않는다.

리뷰 직전에 런타임이 계획의 검증 명령을 돌려 **그 출력을 리뷰 브리프에 넣는다.**
리뷰어는 읽기 전용이라 직접 못 돌린다. 실패해도 막지 않고 리뷰어에게 함께 준다.
오래 걸리는 프로젝트면 `--no-verify-before-review` 로 끈다.

에이전트가 제한 시간에 끊기면 **그때까지 바뀐 파일을 함께 적는다.** 일을 해 놓고
보고만 못 끝냈을 수 있다. `orch resume` 은 그 목록을 다음 호출에 알려 주고,
범위 검사도 그 변경까지 함께 잰다. 제한 시간은 `--timeout 역할=초` 로 바꾼다.

**승인은 대신 누르지 않는다.** 계획과 리뷰는 사람이 읽는다. 자율 모드에서도 그 자리에서 선다.

`orch`가 없으면 아래 절차를 손으로 따른다. 둘은 같은 참조 문서를 읽고 같은 일을 한다.
설치는 `ahn-cc-kit` 저장소의 `orchestrator/README.md`에 있다.

## 절차

1. **계획**을 쓴다 — `references/plan-template.md`
2. **사람에게 승인**받는다. 설계 결정이 남아 있으면 여기서 묻는다
3. 넘기기 직전 **스냅샷**을 찍는다 — `bin/scope-guard.sh snapshot`
4. **구현**을 넘긴다 — 계획 파일 경로를 주고 그것을 읽게 한다
5. **범위를 검증**한다 — `bin/scope-guard.sh check`. 위반이면 리뷰로 보내지 않고 되돌린다
6. **교차 리뷰**를 받는다 — 다른 세션에. `references/review-brief.md`
7. 지적 중 **반영할 것을 추려** 수정 계획을 쓴다. 전부 반영이 기본값이 아니다
8. **수정**을 넘기고 다시 5·6을 돈다
9. **직접 검증**한다 — 테스트·린트를 손으로 돌리고, 지적이 실제로 반영됐는지 파일에서 확인한다

## 산출물 위치

저장소를 더럽히지 않는다. 팀 저장소에서도 파일 하나 고치지 않고 쓸 수 있어야 한다.

```
.orchestrate/          산출물 (계획·프롬프트·로그·리뷰)
```

`.git/info/exclude`에 `.orchestrate/`를 넣는다. 이 파일 자체가 커밋되지 않으므로 팀 설정을 건드리지 않는다.

```bash
grep -q '^\.orchestrate/$' .git/info/exclude || echo '.orchestrate/' >> .git/info/exclude
```

번호를 붙여 순서를 남긴다: `01-plan.md`, `02-prompt.txt`, `02-output.log`, `03-review.md`, `04-fix-plan.md`.

## 넘기는 법

산출물 파일 경로를 주고 **그것을 읽게** 한다. 프롬프트에 계획을 통째로 붙이지 않는다.

```bash
codex exec -s workspace-write "$(cat .orchestrate/02-prompt.txt)" < /dev/null > .orchestrate/02-output.log 2>&1
```

`< /dev/null`을 빠뜨리면 멈춘다. 이유와 나머지 함정은 `references/gotchas.md`에 있다.

## 지킬 것

- **계획에 검증 명령을 쓰기 전에 한 번 돌려 본다.** 안 돌아가는 명령을 적으면 구현자가 거기서 막힌다
- **구현자에게 "통과시켜라"라고 하지 않는다.** 사실을 확인하는 작업이면 "틀렸으면 틀렸다고 드러나게 하라"고 적는다
- **리뷰 브리프에 구현자의 결론을 넣지 않는다.** 이것 하나가 리뷰 품질을 가른다
- **보고를 믿지 않는다.** 범위도 테스트도 지적 반영도 직접 확인한다
- 커밋·브랜치·푸시는 사람이 지시할 때만 한다. 넘기는 프롬프트에도 금지로 적는다

## 참고

- `references/plan-template.md` — 계획 산출물 형식
- `references/review-brief.md` — 교차 리뷰 브리프 규칙
- `references/gotchas.md` — 실제로 겪은 함정
- `ahn-cc-kit` 저장소의 `orchestrator/` — 이 절차를 기계가 돌리는 런타임

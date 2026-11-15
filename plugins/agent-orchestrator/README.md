# agent-orchestrator

계획·구현·리뷰를 서로 다른 에이전트와 세션에 나눠 맡기고, 그 왕복을 지휘하는 절차.

```bash
claude plugin install agent-orchestrator@ahn-cc-kit
```

## 언제 불리나

"코덱스에 넘겨줘", "다른 에이전트로 구현해줘", "교차 리뷰해줘", "왕복으로 해보자", "계획만 세워줘"
같은 요청에서 모델이 자동으로 불러옵니다. 직접 부르려면 `/agent-orchestrator:orchestrate`.

## 왜 나누나

자기가 쓴 것을 자기가 검사하면 통과시킵니다. 테스트가 통과했다는 사실은
"그 테스트가 옳은 것을 검사했다"를 뜻하지 않습니다.

실제로 이 절차를 처음 돌렸을 때, 구현자는 "가설이 확정됐다"고 보고했고 테스트도 통과했지만,
브리프에서 그 결론을 숨긴 채 받은 리뷰어가 라이브러리 소스를 열어
**테스트가 통과하는 진짜 이유**와 **결론을 넓게 읽으면 틀리는 네 지점**을 찾아냈습니다.

## 무엇을 하나

- **계획 산출물 형식**을 정합니다. 구현자는 대화 맥락 없이 그 파일만 읽고 일합니다
- **범위를 검증합니다.** `scope-guard.sh`가 계획이 허용한 파일만 바뀌었는지 보고,
  위반이면 리뷰로 보내지 않습니다. untracked 파일 수정도 잡도록 내용 해시로 비교합니다
- **리뷰 브리프에서 구현자의 결론을 뺍니다.** 이 한 줄이 리뷰 품질을 가릅니다
- **산출물을 저장소 밖으로 뺍니다.** `.claude/orchestrate/`에 두고 `.git/info/exclude`에 넣습니다.
  그 파일 자체가 커밋되지 않으므로 **팀 저장소 파일을 하나도 고치지 않고** 쓸 수 있습니다

## 전제

- 넘길 상대가 필요합니다. `codex` CLI를 전제로 썼지만, 계획 파일을 읽고 범위를 지킬 수 있으면 무엇이든 됩니다
- 결과를 기계가 판정할 수 있어야 합니다(테스트·빌드·린트). 판정이 사람 눈뿐이면 왕복의 값이 줄어듭니다
- 언어·플랫폼은 가리지 않습니다. 검증 명령은 프로젝트에서 읽어 옵니다

## 구성

| 파일 | 내용 |
| --- | --- |
| `skills/orchestrate/SKILL.md` | 절차 전체와 역할 경계 |
| `skills/orchestrate/references/plan-template.md` | 계획 산출물 형식 |
| `skills/orchestrate/references/review-brief.md` | 교차 리뷰 브리프 규칙 |
| `skills/orchestrate/references/gotchas.md` | 실제로 겪은 함정 |
| `bin/scope-guard.sh` | 범위 검증 |

## scope-guard만 따로 쓰기

스킬 없이도 됩니다.

```bash
# 구현을 넘기기 직전
scope-guard.sh snapshot .claude/orchestrate/snapshot.txt

# 구현이 끝난 뒤
scope-guard.sh check .claude/orchestrate/plan.md .claude/orchestrate/snapshot.txt
```

계획 파일의 `## 건드릴 파일` 아래 첫 코드 블록을 읽어 허용 목록으로 씁니다.
범위를 벗어나면 종료 코드 1, 아무것도 안 바뀌어도 1입니다.

## 하지 않는 것

- 커밋·브랜치·푸시를 대신 하지 않습니다. 넘기는 프롬프트에도 금지로 적습니다
- 리뷰어가 코드를 고치지 않습니다. 고치기 시작하면 리뷰가 아니라 두 번째 구현이 됩니다
- 지적을 전부 반영하지 않습니다. 추려서 수정 계획을 쓰고, 빼는 이유를 적습니다

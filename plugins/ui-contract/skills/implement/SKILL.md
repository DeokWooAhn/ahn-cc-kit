---
name: implement
description: >-
  고정된 디자인 계약(layout-contract·design-tokens·component-map)을 기준으로 UI를 구현하거나,
  구현 결과가 그 계약과 맞는지 검증할 때 사용합니다. "계약대로 구현해줘",
  "이 화면 수치 맞는지 확인해줘", "디자인이랑 다른 데 찾아줘",
  "디자인대로 구현됐는지 봐줘" 같은 요청이 해당됩니다.
  Implementing a screen from a fixed layout contract and verifying the result against it —
  Compose, SwiftUI and Flutter mappings for Auto Layout, hug/fill/fixed and dp/sp/pt,
  plus screenshot tolerance. Not a general-purpose code review.
metadata:
  category: workflow
  status: draft
---

# 계약 기준 구현과 검증

목표는 **pixel perfect가 아니라 contract matching이다.**

iOS와 Android는 폰트 렌더링·line-height 처리·anti-aliasing이 달라서 스크린샷이 완전히 같아질 수
없다. 같아지게 만들려고 수치를 비틀면 오히려 계약에서 멀어진다.
지킬 것은 **계약된 수치·토큰·컴포넌트 매핑**이고, 스크린샷은 허용 오차 안에서 통과하면 된다.

## 먼저 무엇을 요청받았는지 가른다

| 요청 | 할 일 |
| --- | --- |
| 구현해 달라 | 아래 전부 |
| 맞는지 봐 달라·리뷰해 달라 | **검증만 한다.** 코드를 고치지 않고 계약 파일도 만들지 않는다 |
| 계약 없이 리뷰해 달라 | 대조할 기준이 없다고 먼저 알린다. 계약을 지어내 리뷰하지 않는다 |

검토 요청을 받아 코드를 고치면 구현자와 리뷰어가 한 사람이 된다.
**이 플러그인이 막으려는 것이 그것이다.** 고칠지는 지적을 읽은 사람이 정한다.

세 번째 경우에는 `extract`를 돌릴지 묻는다. 계약 없이도 할 수 있는 것은
[references/platforms.md](references/platforms.md)의 플랫폼 함정을 보는 것까지다.
그 결과를 "디자인과 맞다/다르다"로 적지 않는다. 대조한 기준이 없기 때문이다.

## 구현하기 전에

`layout-contract.json`·`design-tokens.json`·`component-map.md`를 읽는다.
**없으면 구현하지 않는다.** [extract 스킬](../extract/SKILL.md)로 먼저 만든다.

`ambiguity-report.md`에 답 안 받은 항목이 있으면 그 부분은 구현하지 않는다.
나머지를 구현하고 그 항목을 남겨 둔 채로 보고한다. 가까운 값을 골라 메우지 않는다.

## 구현

1. 계약 파일 넷을 읽는다. 그 다음 코드베이스의 **기존 토큰과 컴포넌트를 확인한다.**
2. `component-map.md`에 적힌 컴포넌트를 쓴다. 매핑된 컴포넌트가 없으면 만들지 말고 멈춘다.
3. 수치의 출처를 가른다. 둘 다 계약이고, **어느 쪽에도 없는 숫자를 쓰면 위반이다.**

   | 종류 | 정본 |
   | --- | --- |
   | 크기·padding·gap·radius·테두리 두께 | `layout-contract.json`의 숫자를 그대로 |
   | 폰트·색·shadow | `design-tokens.json`이 `codeRef`로 가리키는 **코드 토큰** |

   폰트와 색은 숫자를 코드에 박지 않는다. `design-tokens.json`의 `fontSize`·`lineHeight`는
   **토큰이 맞는지 대조하는 값**이지 직접 쓸 값이 아니다.
   플랫폼이 환산을 요구하면(Flutter의 `height`) 그 값으로 계산한다.

   레이아웃 값은 한자리에 모아 둔다 — 나중에 계약과 대조할 수 있어야 한다.
4. 새 색상·새 폰트·새 토큰·새 컴포넌트를 만들지 않는다.
5. Auto Layout을 플랫폼 레이아웃으로 옮긴다. 플랫폼별 매핑과 자주 틀리는 지점은
   [references/platforms.md](references/platforms.md)에 있다.

절대 위치는 디자인에서 명시적으로 절대 위치일 때만 쓴다.
hug content를 고정 height로 바꾸지 않는다. 이 둘이 가장 자주 깨진다.

## 검증

빌드가 통과하는 것은 UI 작업의 완료가 아니다. 수치가 맞아야 완료다.

기준·허용 오차·스크린샷 절차는 [references/validation.md](references/validation.md)에 있다.
같은 문서에 **리뷰 기준과 출력 형식**이 함께 있다.

## 리뷰는 구현한 쪽이 하지 않는다

자기가 쓴 수치를 자기가 대조하면 통과시킨다. 사람이 읽든 다른 세션이 읽든
리뷰어에게는 [references/validation.md](references/validation.md) 경로와 계약 파일, diff,
렌더링 스크린샷만 준다. **구현자의 "다 맞췄다"는 결론을 리뷰 입력에 넣지 않는다.**

세션을 갈라 돌리는 절차는 `agent-orchestrator`에 있다. 여기서 같은 절차를 다시 만들지 않는다.

## 보고

- 바뀐 파일
- 계약에 없어서 새로 넣은 수치 — **있으면 전부**. 없으면 없다고 적는다
- 쓴 토큰과 매핑한 컴포넌트
- 빌드 결과, 스크린샷 검증 결과
- 남은 불일치와 사람이 판단할 항목

스크린샷 없이 "디자인과 일치한다"고 적지 않는다. 확인한 것과 확인 못 한 것을 가른다.

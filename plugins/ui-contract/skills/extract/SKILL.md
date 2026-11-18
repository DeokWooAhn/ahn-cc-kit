---
name: extract
description: >-
  Figma·Zeplin 같은 디자인 소스에서 UI 구현에 필요한 수치를 뽑아 계약 파일로 고정할 때 사용합니다.
  "이 피그마 화면 구현해줘", "피그마 수치 뽑아줘", "디자인대로 만들어줘",
  "디자인 토큰 정리해줘", "제플린 보고 작업해줘" 같은 요청이 해당됩니다.
  이 단계에서는 코드를 쓰지 않습니다. Extracting layout numbers, tokens and component
  mappings from a design source into a contract the implementer must follow —
  spacing, typography, radius, shadow, hug/fill/fixed — with every ambiguity reported
  instead of guessed.
metadata:
  category: workflow
  status: draft
---

# 디자인 수치 추출

AI가 만든 UI가 미묘하게 틀리는 것은 UI를 못 짜서가 아니라 **입력이 이미지뿐이었기 때문**이다.
이미지에서는 padding이 16인지 20인지, line-height가 22인지 24인지 알 수 없다. 추측할 뿐이다.

그래서 구현 전에 수치를 먼저 고정한다. **이 단계에서는 코드를 쓰지 않는다.**
수치가 틀리면 그 위에 올린 구현은 계속 흔들린다.

## 먼저 입력이 무엇인지 가른다

| 가진 것 | 할 일 |
| --- | --- |
| Figma·Zeplin MCP가 붙어 있다 | layout 데이터를 직접 읽는다. 아래 전부 |
| Dev Mode 복사값이나 스펙 문서만 있다 | 있는 값으로 계약을 쓰고 빈칸은 `null`로 둔다 |
| 스크린샷뿐이다 | **계약을 지어내지 않는다.** 읽을 수 있는 값만 적고 나머지는 질문으로 남긴다 |

스크린샷뿐인데 계약 파일을 채우면 추측에 권위를 입히는 꼴이 된다. 그게 가장 나쁘다.
디자인 데이터를 받을 수 있는지 먼저 묻는다.

## 무엇을 뽑는가

frame 크기, Auto Layout 방향·gap·padding, 자식 순서, fixed/hug/fill, 텍스트 스타일,
색상 변수, radius, shadow, asset export 이름, 컴포넌트 variant.

뽑는 방법과 도구별 주의는 [references/sources.md](references/sources.md)에 있다.

**스크린샷은 검증용이지 수치의 출처가 아니다.** layout 데이터가 있으면 그것이 우선한다.
둘이 어긋나면 어긋났다고 적는다. 한쪽을 골라 조용히 넘어가지 않는다.

## 계약으로 고정한다

[templates/](templates/)를 작업 폴더에 복사해 채운다. 두는 자리는 프로젝트 관례를 따르고,
없으면 `.ui-contract/<화면이름>/`을 쓴다.

| 파일 | 담는 것 |
| --- | --- |
| `layout-contract.json` | 크기·padding·gap·radius 등 **숫자 전부**. 구현이 쓸 수 있는 유일한 수치 출처 |
| `design-tokens.json` | 색상·타이포그래피·radius·shadow 토큰. light/dark 양쪽 |
| `component-map.md` | 디자인 컴포넌트 ↔ 코드 컴포넌트. **없으면 만들지 말고 멈춘다**는 규칙 포함 |
| `ambiguity-report.md` | 판단이 필요한 것 전부 |

`layout-contract.json`의 모든 숫자에는 출처가 있어야 한다. 출처 없는 숫자를 적으면
구현자가 그것을 근거로 삼는다. 모르면 `null`로 두고 `unresolved`에 적는다.

## 애매한 것은 보고한다

Figma에 17px인데 토큰에는 16과 18만 있다. shadow가 기존 토큰과 정확히 안 맞는다.
hug height가 데이터 길이에 따라 달라진다 — 이런 것은 **반드시 생긴다.**

AI가 조용히 가까운 값을 고르면 디자이너 리뷰에서 터진다. 판별 기준과 보고 형식은
[references/ambiguity.md](references/ambiguity.md)에 있다.

새 토큰·새 색상·새 폰트는 이 단계에서 만들지 않는다. 필요하면 그 사실을 보고한다.

## 넘긴다

계약 파일 경로와 `ambiguity-report.md`의 판단 항목을 사람에게 알린다.
**애매한 항목이 남아 있으면 구현으로 넘어가기 전에 답을 받는다.**

구현은 [implement 스킬](../implement/SKILL.md)이 맡는다.
다른 에이전트에게 넘기거나 리뷰를 분리하려면 `agent-orchestrator`의 왕복 절차를 쓴다.
이 스킬은 그 왕복에서 오가는 산출물의 **내용**만 정한다.

작업 범위·수정 금지 파일·완료 보고 형식은 `context-pack`이 이미 다룬다.
같이 쓰면 `task.md`에 범위를 적고 계약 파일을 `files.md`에서 가리킨다. 두 벌 만들지 않는다.

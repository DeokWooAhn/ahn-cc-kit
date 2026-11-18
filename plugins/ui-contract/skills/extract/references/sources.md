# 디자인 소스에서 수치 꺼내기

## 무엇을 뽑는가

하나라도 빠지면 구현자가 그 자리를 추측으로 메운다.

| 묶음 | 항목 |
| --- | --- |
| 크기 | frame width·height, fixed / hug / fill |
| 배치 | Auto Layout 방향, gap, padding 네 방향, 정렬, 자식 순서 |
| 텍스트 | fontFamily, size, lineHeight, weight, letterSpacing, 줄 수 제한 |
| 색 | 변수 이름, light/dark 값, opacity가 섞였는지 |
| 장식 | cornerRadius, border 두께·색, shadow의 x·y·blur·spread·opacity |
| 자원 | asset export 이름과 배율, 아이콘 원본 크기 |
| 상태 | 컴포넌트 variant, 상태별 차이(기본·눌림·비활성·오류) |

**`opacity`가 섞인 색은 특히 자주 틀린다.** 디자인에서 검정 12%로 보이는 것이
토큰에서는 별도 회색일 수 있다. 어느 쪽인지 적는다.

## Figma MCP가 붙어 있을 때

도구 이름은 서버 버전에 따라 다를 수 있으니 세션에 올라온 것을 먼저 확인한다.
보통 파일 세션을 연 뒤 아래를 쓴다.

| 도구 | 쓰는 곳 |
| --- | --- |
| `get_metadata` | 노드 트리와 구조. 자식 순서와 중첩을 여기서 본다 |
| `get_design_context` | 레이아웃 값 전체. 주 도구 |
| `get_variable_defs` | 색·타이포그래피 변수. `design-tokens.json`의 재료 |
| `get_screenshot` | **검증용 참조 이미지.** 수치의 출처로 쓰지 않는다 |
| `get_code_connect_map` | 디자인 컴포넌트와 코드 컴포넌트가 이미 연결돼 있는지. `component-map.md`를 지어내기 전에 본다 |

`get_design_context`는 코드를 함께 내놓는다. **그 코드를 그대로 쓰지 않는다.**
공식 문서도 그것을 "프로젝트에 맞게 고칠 참조이지 최종 코드가 아니다"라고 적는다.
이 스킬이 하는 일은 그 참조에서 **수치만 꺼내 계약으로 고정하는 것**이다.
코드를 받아 붙이면 프로젝트의 기존 토큰과 컴포넌트를 건너뛰게 된다.

URL에서 꺼낼 것: `figma.com/design/<fileKey>/...?node-id=<nodeId>`.
`node-id`의 `-`는 `:`로 바꿔 쓴다.

## Zeplin MCP가 붙어 있을 때

`get_screen`으로 화면 레이어와 수치를, `get_design_tokens`로 토큰을,
`get_component`로 컴포넌트 정의를 읽는다. asset은 `download_layer_asset`으로 받는다.

## MCP 없이 Dev Mode만 있을 때

사람이 브라우저에서 보고 복사해 준다. **복사해 온 값은 측정값이므로 계약 파일을 만들어도 된다.**
스크린샷과 다른 점이 이것이다.

### 무엇을 복사해 달라고 하나

**CSS로 복사하는 것이 정보량이 가장 많다.** 크기·여백·간격·radius·폰트·색이 한 번에 온다.
플랫폼 코드(SwiftUI·Compose)로 복사하면 오히려 값이 줄고 해석이 섞인다.

| Dev Mode CSS | 계약의 자리 |
| --- | --- |
| `width` / `height` | `size` — 다만 아래 "가장 큰 함정"을 먼저 읽는다 |
| `padding` | `padding` |
| `gap` | `layout.gap` |
| `display: flex` + `flex-direction` | `layout.direction` |
| `align-items` / `justify-content` | `layout.alignment` |
| `border-radius` | `cornerRadius` |
| `border` | `border` |
| `box-shadow` | `design-tokens.json`의 `shadows` |
| `font-family` · `font-size` · `font-weight` · `line-height` · `letter-spacing` | `design-tokens.json`의 `typography` |
| `color` · `background` | `design-tokens.json`의 `colors` |

### 가장 큰 함정

**CSS의 `width`·`height`는 Figma가 계산해 낸 그 순간의 실제 크기다.**
hug든 fill이든 구체적인 px로 찍힌다. 그래서 CSS만 보면 모든 레이어가 fixed처럼 보인다.

이대로 옮기면 긴 텍스트에서 잘리고, 화면 폭이 다른 기기에서 깨진다.
**fixed/hug/fill은 CSS가 아니라 오른쪽 속성 패널에서 확인한다.** 레이어를 고르면
크기 입력칸 옆에 Fixed·Hug·Fill이 표시된다. 그 값을 따로 받는다.

CSS에서 읽을 수 있는 단서도 있다.

- 주축 fill → 자식에 `flex: 1 0 0`
- 교차축 fill → 자식에 `align-self: stretch`
- hug → 부모에 크기 지정이 없고 자식 크기로 결정됨

단서가 없으면 추측하지 말고 묻는다. 이 한 가지만 틀려도 나머지 수치가 다 맞아도 화면이 깨진다.

### 복사 순서

레이어마다 따로 복사해야 하므로 순서를 정해 두면 왕복이 줄어든다.

1. **루트 프레임** — 전체 크기, padding, 방향, gap, radius, 배경
2. **바로 아래 자식들** — 각각의 크기 동작(fixed/hug/fill)과 간격
3. **텍스트 레이어** — 타이포그래피. 같은 스타일이 반복되면 한 번만
4. **색과 토큰 이름** — 변수가 설정돼 있으면 속성 패널에 변수 이름이 보인다.
   **이름을 받아 적는다.** hex보다 이름이 중요하다 — 코드 토큰과 이어야 하기 때문이다

중첩이 깊으면 전부 받지 말고 **이번에 구현할 범위까지만** 받는다.

### CSS를 그대로 믿으면 안 되는 값

- `line-height: normal` — Figma에서 auto로 둔 것이다. 실제 높이는 폰트가 정하므로
  **계약에 숫자로 적을 수 없다.** `null`로 두고 보고한다
- `rgba(...)` — 색에 opacity가 섞여 있다. 별도 토큰인지 토큰 + 투명도인지 확인해야 한다
- `letter-spacing`이 `em` 같은 상대값 — 폰트 크기에 따라 달라진다. 환산값과 원본을 함께 적는다
- 반올림된 소수 — `11.999px` 같은 값은 12로 보되, 여러 개가 어긋나면 기준 배율을 묻는다

### 코드 패널의 코드

Dev Mode는 SwiftUI·Compose 코드도 만들어 준다. **그 코드를 받아 붙이지 않는다.**
MCP의 `get_design_context`와 같은 이유다 — 프로젝트의 토큰도 컴포넌트도 모르는 코드이고,
절대 위치나 매직 넘버가 섞여 있다. 수치만 꺼내 계약으로 옮긴다.

### 빠진 값

사람이 복사해 준 값은 **보통 일부만 온다.** 온 값만 계약에 넣고 나머지는 `null`로 둔다.
빈칸을 "보통 이 정도" 값으로 채우면 계약 파일 전체의 신뢰가 깨진다.
`unresolved`에 빠진 키를 전부 적고, **받아야 할 값을 한 번에 묻는다.**
한 번에 묻는 것이 중요하다 — 레이어를 다시 찾아 들어가는 것이 사람에게는 가장 번거롭다.

## 스펙 문서나 디자이너가 적어 준 값만 있을 때

같은 규칙을 따른다. 다만 사람이 옮겨 적는 과정에서 값이 바뀌었을 수 있으므로
**어디서 온 값인지** `source.tool`에 적는다. 나중에 화면이 어긋났을 때
구현이 틀린 것인지 받은 값이 틀린 것인지 가르는 근거가 된다.

## 스크린샷뿐일 때

**계약 파일을 만들지 않는다.** 대신 이렇게 한다.

1. 이미지에서 확실한 것만 적는다 — 색 계열, 요소 순서, 대략의 비율, 상태 종류
2. 디자인 파일이나 Dev Mode 접근을 받을 수 있는지 묻는다
3. 끝내 못 받으면 **추측값으로 구현한다는 사실을 먼저 알린다.**
   그때 만든 숫자는 계약이 아니라 임시값이고, 디자이너 리뷰에서 바뀔 것이라고 적는다

이미지에서 뽑은 값에 계약 파일의 형식을 입히면, 나중에 읽는 사람은 그것이
측정값인지 추측인지 구별할 수 없다. 그게 이 절차가 막으려는 것이다.

## 기준 디바이스를 적는다

같은 디자인도 기준 폭이 다르면 수치가 달라진다. `layout-contract.json`의 `reference`에
기준 폭과 단위를 적는다. 디자인이 360dp 기준인데 코드가 412dp에서 돌면
fill 동작이 다르게 보인다 — 그 차이는 버그가 아니라 기준 차이다.

반응형 규칙이 있으면 중단점과 각 구간의 동작을 적는다. 없으면 "기준 폭 외는 미정"이라고 적는다.

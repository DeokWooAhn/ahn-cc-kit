# 플랫폼 매핑과 자주 틀리는 지점

## 단위

| 디자인 | Compose | SwiftUI | Flutter |
| --- | --- | --- | --- |
| 레이아웃 값 | `dp` | `CGFloat`(pt) | `double`(논리 픽셀) |
| 텍스트 크기 | `sp` — 타이포그래피 토큰을 거쳐서 | pt, Dynamic Type 대응 | `fontSize`, `textScaler` 대응 |
| 얇은 선(논리 1) | `1.dp` | `1` | `1.0` |
| 물리 1픽셀 hairline | `Dp.Hairline` | `1 / displayScale` | `width: 0.0` |

디자인의 "1px 선"은 대개 **논리 단위 1**이지 물리 픽셀 1개가 아니다.
Figma의 1px는 1배율 기준 값이라 그대로 dp·pt·논리 픽셀로 옮긴다.
밀도와 무관하게 가장 얇은 선을 원하는 것인지 디자이너에게 확인하고, 그럴 때만 표의 마지막 행을 쓴다.
Flutter의 `width: 0.0`은 **물리 1픽셀** 테두리를 그린다. 다만 경로가 한 픽셀을 두 번 지나면
그 자리가 조금 진하거나 흐려질 수 있어서, 색이 디자인과 미세하게 달라 보일 수 있다.

**Compose에서 레이아웃은 dp, 텍스트는 sp다.** 섞으면 글자 크기 설정을 켠 사용자에게서 깨진다.
반대로 아이콘 크기에 sp를 쓰면 글자 배율을 따라 커진다 — 대개 의도가 아니다.

## Auto Layout 옮기기

| 디자인 | Compose | SwiftUI | Flutter |
| --- | --- | --- | --- |
| vertical | `Column` | `VStack` | `Column` |
| horizontal | `Row` | `HStack` | `Row` |
| gap | `Arrangement.spacedBy(n.dp)` | `spacing: n` | `spacing:` 또는 사이에 `SizedBox` |
| padding | `Modifier.padding(...)` | `.padding(.top, n)` 등 | `Padding` 또는 `Container(padding:)` |
| fixed | `Modifier.size` / `width` / `height` | `.frame(width:height:)` | `SizedBox` |
| hug | 크기 지정 안 함 | 크기 지정 안 함 | `mainAxisSize: MainAxisSize.min` |
| fill | `Modifier.weight(1f)` / `fillMaxWidth()` | `Spacer()` / `.frame(maxWidth: .infinity)` | `Expanded` / `double.infinity` |

**gap과 padding을 겹쳐 넣지 않는다.** `spacedBy`를 쓰고 자식마다 또 padding을 주면
간격이 두 번 들어간다. 계약의 `gap`은 한 군데서만 구현한다.

## Compose에서 자주 틀리는 것

- `Row` 안에서 `weight` 위치를 잘못 잡아 정렬이 어긋난다
- hug content를 고정 height로 바꾼다
- `fillMaxWidth()`를 디자인이 fill이 아닌 자리에도 쓴다
- Material 컴포넌트의 **기본 padding과 최소 터치 크기**가 섞여 디자인 수치와 달라진다.
  `Button`·`IconButton`·`ListItem`이 특히 그렇다. 디자인이 커스텀 padding을 지정하면
  기본값을 끄거나 기본 컴포넌트를 쓰지 않는다
- 값 텍스트에 `textAlign` 없이 `weight`만 줘서 오른쪽 정렬이 안 된다
- `Modifier` 순서를 바꿔 padding과 background·clip의 적용 범위가 달라진다 —
  background 뒤에 padding을 주면 배경 안쪽에 여백이 생기고, 앞에 주면 바깥에 생긴다

## SwiftUI에서 자주 틀리는 것

- stack의 `spacing`과 자식의 `padding`을 혼동한다
- 디자인이 hug인데 `frame(height:)`를 고정한다
- `.lineLimit(1)`을 요구하지 않은 자리에 넣는다
- `Spacer()` 위치가 디자인의 fill 동작과 달라진다
- `cornerRadius`만 주고 `style: .continuous`를 놓쳐 모서리 곡률이 달라 보인다
- shadow를 임의 값으로 만든다
- asset을 원본 크기와 다른 크기로 잡는다
- Dynamic Type에서 레이아웃이 깨지는지 보지 않는다

## Flutter에서 자주 틀리는 것

- `Expanded`와 `Flexible`을 바꿔 쓴다 — 디자인의 fill은 보통 `Expanded`,
  "넘치면 줄어듦"은 `Flexible`이다
- `Column`에 `mainAxisSize`를 안 줘서 hug가 아니라 화면을 다 차지한다
- Material 위젯의 기본 `visualDensity`·`materialTapTargetSize`가 수치를 밀어낸다
- `TextStyle`의 `height`가 **배수**라서 디자인의 lineHeight를 그대로 넣으면 안 된다.
  `height = lineHeight / fontSize`로 환산한다
- `SafeArea`를 이중으로 감싼다

## 공통으로 조심할 것

- **절대 위치**는 디자인에서 명시적으로 절대 위치일 때만 쓴다
- **safe area·status bar**를 어디서 처리하는지 계약에 없으면 보고한다.
  화면 전체가 조금 내려가 보이는 문제는 대개 여기서 온다
- **스크롤 영역과 고정 영역**의 경계를 디자인에서 확인한다. 추측하면 긴 데이터에서 드러난다
- **line-height 처리**가 플랫폼마다 다르다. 같은 숫자를 넣어도 첫 줄 위 여백이 다르게 보인다.
  이건 구현 실수가 아니라 플랫폼 차이이므로 허용 오차에서 다룬다

## 레이아웃 값을 한자리에 모은다

계약의 숫자는 코드 여기저기에 흩어 놓지 않는다. 화면마다 한 곳에 모아 두면
나중에 계약 파일과 **눈으로 대조할 수 있다.** 흩어 놓으면 대조가 불가능해지고,
그 순간 계약은 지켜지는지 알 수 없는 문서가 된다.

프로젝트에 이미 레이아웃 상수를 두는 관례가 있으면 그것을 따른다. 없으면 화면 단위로 묶는다.

# 테스트 id 규칙

Maestro는 화면 문구보다 id로 찾는 게 안정적이다. 앱이 여러 언어를 지원하면 문구로 찾는 Flow는 기기
언어만 바뀌어도 깨진다. Android와 iOS가 **같은 id**를 쓰면 Flow 하나로 두 플랫폼을 돌릴 수 있다.

## Maestro가 id를 찾는 방식 (Maestro 2.1.0에서 확인)

- **`id:`는 정규식이고, id 전체와 일치해야 잡힌다.** `recycler`로는 `recycler_view`가 잡히지 않는다.
- 그래서 **정규식 특수문자가 든 id는 위험하다.** `keypad.+`는 "keypad 뒤에 아무 글자나 한 개 이상"이
  되어 `keypad.history` 전체와 일치해 엉뚱한 키를 누른다. `+ = ( ) * ? [ ] | ^ $ \`를 쓰지 않는다.
- `.`도 정규식에서는 "아무 글자 하나"지만, 구분자로 쓰는 건 괜찮다. 같은 자리에 다른 글자가 오는
  id가 따로 없으면 다른 요소와 섞이지 않는다.
- 글자 단언(`assertVisible: "0.25"`)도 정규식이다. 소수점은 `"0\\.25"`로 이스케이프한다.
- 화면 계층(`maestro hierarchy --compact`)에서는 두 플랫폼 모두 `resource-id=`로 보인다.

## Android (Compose)

- `Modifier.testTag("...")`를 붙이고, **composition 루트마다** `Modifier.semantics { testTagsAsResourceId = true }`를
  켠다. 이게 없으면 외부 도구가 testTag를 못 본다.
- composition 루트는 하나가 아닐 수 있다. **`setContent { }`마다, 레이아웃에 끼운 `ComposeView`마다** 따로
  켠다. Fragment 화면 안에 `ComposeView`를 여러 개 둔 구조라면 그 수만큼 켜야 한다.
- **Dialog, BottomSheet, Popup도 별도 창이라 바깥 설정이 닿지 않는다.** 그 안의 루트에도 따로 켠다.
- 공통 루트 컴포저블(테마 래퍼 등)이 있으면 거기서 한 번 켜면 그 아래 화면이 모두 덮인다.

## iOS (SwiftUI)

- `.accessibilityIdentifier("...")`를 붙인다. 버튼·텍스트뿐 아니라 `tabItem`의 `Label`에 붙여도
  탭 버튼까지 전달된다(iOS 26 시뮬레이터에서 확인).
- **컨테이너(VStack, 화면 루트, 목록 행)에 id를 달 때는 `.accessibilityElement(children: .contain)`를 함께 쓴다.**
  안 그러면 id가 없는 자식 요소가 모두 같은 id를 물려받아 기준점 하나가 여러 요소와 매칭된다.
  자식에 이미 붙은 id는 덮어쓰이지 않는다.
- 공용 컴포넌트가 버튼 글자로 id를 만들고 있으면(`"keypad.\(text)"`) 기호가 그대로 들어간다. 키 정의 쪽에서
  이름을 정해 붙이도록 옮긴다.
- 아이콘만 있는 닫기 버튼처럼 Android에 대응 요소가 없는 것(Android는 `back`으로 닫는 시트 등)도
  iOS에서만 쓰는 id를 붙여 둔다.

## 이름 짓기

- `종류.이름` 또는 `종류.이름.값` 형태로, 각 부분은 영문자와 숫자만 쓴다.
  예: `screen.home`, `tab.settings`, `keypad.plus`, `item.row.USD`, `item.favorite.USD`.
- 기호 키는 이름으로 바꾼다: `+`→`plus`, `=`→`equals`, `( )`→`parenthesis`, `⌫`→`delete`.
- 종류를 앞에 둔다. `item.row.USD`와 `item.favorite.USD`처럼 두면 서로 섞이지 않는다.
- 화면이 떴는지 확인할 **기준점 id**를 화면 루트마다 하나씩 둔다(`screen.<이름>`).
- 여러 곳에 쓰는 컴포넌트(선택 버튼 등)는 컴포넌트 안에서 같은 id를 붙이고, Flow에서 `childOf:`로
  어느 카드 안의 것인지 좁힌다.
- 두 플랫폼이 다 있으면 **양쪽에 같은 이름**을 붙인다. 한쪽에만 있는 요소는 한쪽에만 둔다.

## 고정하기

- 키 → id처럼 코드로 만든 매핑은 유닛 테스트로 목록 전체를 고정한다. 값이 바뀌면 Flow가 조용히 깨진다.
- "모든 id가 `종류\.[a-z0-9]+` 형식인가", "서로 겹치지 않는가"도 테스트로 둔다.
- 두 플랫폼이 다 있으면 양쪽 테스트에 **같은 목록**을 적는다. 한쪽만 바꾸면 테스트가 깨지게 하려는 것이다.

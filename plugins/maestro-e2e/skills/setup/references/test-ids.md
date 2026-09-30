# 테스트 id 규칙

Maestro는 화면 문구보다 id로 찾는 게 안정적이다. 앱이 여러 언어를 지원하면 문구로 찾는 Flow는 기기
언어만 바뀌어도 깨진다.

## Maestro가 id를 찾는 방식 (Maestro 2.1.0에서 확인)

- **`id:`는 정규식이고, id 전체와 일치해야 잡힌다.** `recycler`로는 `recycler_view`가 잡히지 않는다.
- 그래서 **정규식 특수문자가 든 id는 위험하다.** `keypad.+`는 "keypad 뒤에 아무 글자나 한 개 이상"이
  되어 `keypad.history` 전체와 일치해 엉뚱한 키를 누른다. `+ = ( ) * ? [ ] | ^ $ \`를 쓰지 않는다.
- `.`도 정규식에서는 "아무 글자 하나"지만, 구분자로 쓰는 건 괜찮다. 같은 자리에 다른 글자가 오는
  id가 따로 없으면 다른 요소와 섞이지 않는다.
- 글자 단언(`assertVisible: "0.25"`)도 정규식이다. 소수점은 `"0\\.25"`로 이스케이프한다.

## XML View

- `android:id`가 곧 resource-id다. Maestro에는 **`:id/` 뒤의 짧은 이름**(`id: "btn_login"`)으로 쓰면 된다.
  전체 id(`com.example:id/btn_login`)도 된다.
- View id는 보통 영문·숫자·`_`뿐이라 정규식 문제가 거의 없다.
- RecyclerView 행처럼 **같은 id가 여러 개**면 그대로는 첫 번째가 잡힌다. 특정 행을 고르려면 그 행에만
  있는 언어 무관한 글자(코드·숫자)로 찾거나, `index:`로 순서를 지정한다. 순서는 데이터에 따라 바뀌니
  고유한 글자 쪽이 낫다.

## Compose

- `Modifier.testTag("...")`를 붙이고, **루트에 한 번** `Modifier.semantics { testTagsAsResourceId = true }`를
  켠다. 이게 없으면 외부 도구가 testTag를 못 본다.
- **Dialog, BottomSheet, Popup은 별도 창이라 루트 설정이 닿지 않는다.** 그 안의 루트에도 따로 켠다.
- testTag는 자유 문자열이라 정규식 특수문자가 섞이기 쉽다. 아래 이름 규칙을 지킨다.

## 이름 짓기

- `종류.이름` 또는 `종류.이름.값` 형태로, 각 부분은 영문자와 숫자만 쓴다.
  예: `screen.home`, `tab.settings`, `keypad.plus`, `item.row.USD`, `item.favorite.USD`.
- 기호 키는 이름으로 바꾼다: `+`→`plus`, `=`→`equals`, `( )`→`parenthesis`, `⌫`→`delete`.
- 종류를 앞에 둔다. `item.row.USD`와 `item.favorite.USD`처럼 두면 서로 섞이지 않는다.
- 화면이 떴는지 확인할 **기준점 id**를 화면 루트마다 하나씩 둔다(`screen.<이름>`).
- 여러 곳에 쓰는 컴포넌트(통화 선택 버튼 등)는 컴포넌트 안에서 같은 id를 붙이고, Flow에서
  `childOf:`로 어느 카드 안의 것인지 좁힌다.

## 고정하기

- 키 → id처럼 코드로 만든 매핑은 유닛 테스트로 목록 전체를 고정한다. 값이 바뀌면 Flow가 조용히 깨진다.
- "모든 id가 `종류\.[a-z0-9]+` 형식인가", "서로 겹치지 않는가"도 테스트로 둔다.

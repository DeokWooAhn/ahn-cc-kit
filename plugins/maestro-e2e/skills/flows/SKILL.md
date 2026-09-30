---
name: flows
description: >-
  Android 앱의 Maestro Flow(.maestro/)를 작성·수정·실행하거나 실패 원인을 찾을 때, 화면 코드를 바꾼 뒤
  E2E로 확인할 때 사용합니다. "마에스트로 돌려줘", "E2E 플로우 만들어줘", "Maestro 테스트 왜 실패해",
  "이 화면 플로우 추가해줘" 같은 요청이 해당됩니다.
  Writing, running, or debugging Maestro flows for an Android app — device choice, MCP-driven
  authoring, selector rules, and known flakiness causes.
metadata:
  category: testing
  status: draft
---

# Maestro Flow 작성·실행

저장소에 `.maestro/`가 아직 없으면 같은 플러그인의 `setup` 스킬부터 따른다.
그 프로젝트의 id 표와 태그 기준은 저장소의 `.claude/skills/`나 문서에 있다. 그것이 우선이다.

## 기기 고르기

- **실기기가 연결돼 있으면 실기기로, 없으면 에뮬레이터로** 돌린다. `adb devices`에서 serial이
  `emulator-`로 시작하지 않으면 실기기다. 에뮬레이터는 RAM·CPU를 많이 쓰니 다 쓰면 끈다.
- 실기기에 스토어판이 깔려 있으면 debug 빌드와 서명이 달라 덮어쓸 수 없다. **지우기 전에 묻는다.**
  지우면 그 기기의 앱 데이터가 사라진다.
- 잠금 화면이면 테스트가 실패한다. 잠금은 풀지 말고 사용자에게 요청한다.
- 기기가 없으면 건너뛰고, 건너뛰었다고 보고한다.

## 실행

```bash
maestro --device <serial> test .maestro -e APP_ID=<applicationId>
```

- 태그로 거른다: `--include-tags=smoke`. 실패 스크린샷을 남기려면 `--test-output-dir=<dir>`.
- 화면 계층: `maestro --device <serial> hierarchy --compact`. id가 실제로 어떻게 보이는지 여기서 확인한다.

## MCP로 Flow 만들기

`.mcp.json`에 `maestro mcp`가 있으면:

1. `inspect_view_hierarchy`로 화면의 id를 확인한다.
2. `tap_on`·`run_flow`로 한 단계씩 조작해 본다.
3. 성공한 단계를 YAML로 옮기고 `check_flow_syntax`로 검사한다.
4. **CLI로 처음부터 다시** 돌려 통과를 확인한다. MCP로 한 번 된 것과 매번 되는 것은 다르다.

`query_docs`와 `cheat_sheet`는 Maestro Cloud API 키가 있어야 동작한다.

## 작성 규칙

- 모든 Flow는 `runFlow: ../subflows/launch_clean.yaml`로 시작한다. 중간에 앱을 지우고 다시 띄우지 않는다.
- **id로 찾는다.** 현지화된 화면 문구로 찾지 않는다. 언어와 무관한 글자(통화 코드, 숫자)는 괜찮다.
- `id:`와 글자 단언은 **전체 일치 정규식**이다. 기호가 든 id는 쓰지 않고, 글자 단언의 `.`은 `\\.`로 쓴다.
- 좌표(`point:`)로 누르지 않는다. 기다릴 때는 요소 기준(`extendedWaitUntil`)으로 기다린다.
- 매일 바뀌는 값(환율, 날짜, 잔액)은 값이 아니라 형식을 정규식으로 본다.
- 결과 숫자를 단언할 때 화면의 다른 글자(키패드 숫자, 탭 이름)와 겹치지 않는 값을 고른다.
- 태그는 `smoke`(서버 없이 통과, CI에서 실행)와 `release`(서버 필요, 릴리스 전 실기기) 둘만 쓴다.
- **광고를 누르거나 실제 광고를 노출하는 Flow를 만들지 않는다.** 릴리스 빌드에는 Maestro를 돌리지 않는다.
- 플랫폼·조건마다 조작이 다르면 `runFlow: { when: ..., commands: [...] }`로 나눈다.

## 실패했을 때

1. 실패 스크린샷을 먼저 본다. 기대한 화면이 떴는지, 팝업이 덮었는지.
2. 그 시점의 `hierarchy`에서 찾던 id가 있는지 본다. 없으면 id 누락이거나 별도 창(Dialog)이다.
3. CI면 artifact의 `logcat.txt`에서 앱 프로세스가 죽었는지, 테스트 모드 인자가 들어왔는지 본다.
4. 증상이 `references/gotchas.md`에 있으면 그 대응을 따른다. 대기 시간을 늘리는 건 원인을 확인한 뒤에만.

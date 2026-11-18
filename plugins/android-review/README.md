# android-review

Compose 기반 Android/Kotlin 리뷰 기준. 범용 코드 리뷰에 Android 판단을 보탭니다.

```bash
claude plugin install android-review@ahn-cc-kit
```

## 언제 불리나

"Compose 화면 리뷰해줘", "이 ViewModel 괜찮아?", "코틀린 변경분 봐줘" 같은 요청, 또는 검토 중인
변경분에 `.kt`·`.kts`·Gradle·AndroidManifest가 들어 있을 때 불립니다.
직접 부르려면 `/android-review:review`.

**범용 코드 리뷰를 대체하지 않습니다.** Claude Code의 `/code-review`는 리뷰어를 여러 개 띄워
교차 검증하고 지적마다 판정을 붙이지만 Android 맥락을 모릅니다. 이 스킬은 그 위에 상태 관리 트랙,
일회성 이벤트 수집, 이펙트 key, 자원 수명 같은 판단을 보탭니다. Kotlin이 없는 변경분에는 불리지 않습니다.
프로젝트 전용 리뷰 기준이 있으면 그것이 먼저입니다.

## 무엇을 하나

- 정확성 → 회귀 위험 → 범위 이탈 → 보안 → 테스트 누락 순으로 심각도를 매겨 보고합니다
- 파일·라인을 함께 적습니다
- 주변 코드와 일치하는 스타일은 지적하지 않습니다
- **코드도 저장소 파일도 고치지 않습니다.** 리뷰는 설명이 결과물입니다

## 전제

- UI는 **Compose**입니다. XML 레이아웃·ViewBinding 항목은 없습니다
- 상태 관리는 StateFlow 직접 / Orbit MVI 둘 다 인정하고, 한 화면에서 섞였을 때만 지적합니다
- Gradle·R8·targetSdk·intent 보안 변경은 Google이 배포하는 공식 스킬(`android skills list`)을
  먼저 확인하도록 안내합니다. `android` CLI가 없으면 이 단계는 건너뜁니다
- 그 스킬은 **저장소 밖 임시 폴더에 받아 읽기만** 합니다. 리뷰 요청만으로 `.claude/skills/` 같은 저장소 파일이
  생기지 않습니다. 저장소에 설치하는 것은 사용자가 요청할 때뿐입니다

## 구성

```text
skills/review/
├── SKILL.md                        진입점. 우선순위·대상 범위·응답 형식
└── references/review-rubric.md     영역별 상세 체크리스트 (필요할 때만 읽음)
```

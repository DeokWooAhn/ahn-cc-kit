# android-review

Compose 기반 Android/Kotlin 코드 리뷰 기준.

```bash
claude plugin install android-review@ahn-cc-kit
```

## 언제 불리나

"코드리뷰 해줘", "브랜치 변경분 리뷰해줘", "MR/PR 검토해줘" 같은 요청, 또는 diff·완료된 구현을
검토해 달라는 요청에서 모델이 자동으로 불러옵니다. 직접 부르려면 `/android-review:review`.

## 무엇을 하나

- 정확성 → 회귀 위험 → 범위 이탈 → 보안 → 테스트 누락 순으로 심각도를 매겨 보고합니다
- 파일·라인을 함께 적습니다
- 주변 코드와 일치하는 스타일은 지적하지 않습니다
- **코드를 고치지 않습니다.** 리뷰는 설명이 결과물입니다

## 전제

- UI는 **Compose**입니다. XML 레이아웃·ViewBinding 항목은 없습니다
- 상태 관리는 StateFlow 직접 / Orbit MVI 둘 다 인정하고, 한 화면에서 섞였을 때만 지적합니다
- Gradle·R8·targetSdk·intent 보안 변경은 Google이 배포하는 공식 스킬(`android skills list`)을
  먼저 확인하도록 안내합니다. `android` CLI가 없으면 이 단계는 건너뜁니다

## 구성

```text
skills/review/
├── SKILL.md                        진입점. 우선순위·대상 범위·응답 형식
└── references/review-rubric.md     영역별 상세 체크리스트 (필요할 때만 읽음)
```

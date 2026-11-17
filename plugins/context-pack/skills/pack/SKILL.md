---
name: pack
description: >-
  변경 작업에 필요한 Context Pack을 작성·갱신하거나 기존 팩을 기준으로 구현·검증·인계할 때 사용합니다.
  "컨텍스트팩 만들어줘", "이 팩대로 구현해줘", "작업 맥락 정리해줘" 요청이 해당됩니다.
  Prepare or resume task-scoped context: goals, allowed files, applicable rules, tests and completion criteria.
metadata:
  category: workflow
  status: draft
---

# 작업별 Context Pack

프로젝트에 `.context-pack/workflow.md`가 있으면 그 절차와 `project.md`를 읽는다.
없으면 [references/workflow.md](references/workflow.md)를 따른다. 명시적인 팩 작성 요청은
프로젝트 전체 도입 권한이 아니므로 루트 지침이나 전역 설정을 바꾸지 않는다.

1. 요청이 변경·계획·팩 작성인지, 읽기만 하는 질문·리뷰인지 구분한다. 질문만으로 구현용 파일을 만들지 않는다.
2. 현재 사용자 변경과 기존 작업 메모·계획을 확인하고, 이번 작업의 근거가 될 코드·스킬·테스트만 읽는다.
3. `context/<작업명>/`의 다섯 문서를 **내용까지 작성**한다. 생성기는 빈 파일 준비를 돕는다.
   `<plugin>`은 `skills/pack/`에서 두 단계 위다.

   ```bash
   python3 "<plugin>/scripts/context_pack.py" new --project "<project>" --task "<task-name>"
   ```

4. 팩 위치와 수정 계획을 짧게 알린다. 현재 요청의 권한과 프로젝트 승인 규칙을 따라 구현·검증한다.
   팩만 요청받았으면 구현하지 않는다.
5. 실제 diff·실행 결과를 팩 기준으로 대조한다. 검증 미실행·실패·한계를 그대로 보고한다.

기존 계획이 있는 작업, 다른 kit와 함께 쓰는 작업은 [references/integrations.md](references/integrations.md)를 읽는다.
절차 본문과 템플릿은 프로젝트에 복사해도 동작하도록 플러그인 설치 경로를 참조하지 않는다.

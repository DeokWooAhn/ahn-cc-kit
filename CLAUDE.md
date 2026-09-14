# ahn-cc-kit

Claude Code 플러그인 마켓플레이스 저장소입니다. 여기의 산출물은 앱 코드가 아니라 **스킬 문서**입니다.

## 구조

```text
.claude-plugin/marketplace.json     마켓플레이스 매니페스트
plugins/<name>/
├── .claude-plugin/plugin.json      플러그인 매니페스트
├── README.md
└── skills/<skill>/
    ├── SKILL.md
    └── references/                 필요할 때만 읽히는 상세 문서
```

`skills/`, `hooks/`, `agents/`는 **플러그인 루트**에 둡니다. `.claude-plugin/` 안에는
`plugin.json`만 들어갑니다. 공식 문서가 "Common mistake"로 지목하는 지점입니다.

## 스킬을 쓸 때

- `SKILL.md`는 진입점입니다. 짧게 유지하고 상세는 `references/`로 내립니다.
  모델은 `SKILL.md`를 항상 읽고 `references/`는 필요할 때만 읽습니다.
- `description`에 **언제 불려야 하는지**를 씁니다. 무엇을 하는지만 쓰면 트리거가 안 걸립니다.
  한국어 요청 문구와 영어 키워드를 함께 넣습니다.
- 특정 프로젝트의 클래스명·모듈명·사내 문서 경로를 넣지 않습니다.
  프로젝트 고유 지식은 그 저장소의 `.claude/skills/`에 남깁니다.
- 프론트매터 `metadata.status`로 성숙도를 표시한다: `draft` | `review` | `stable`.

## 검증

```bash
claude --plugin-dir ./plugins
```

```bash
claude plugin validate ./plugins/<name>
```

매니페스트를 고쳤으면 JSON 파싱을 먼저 확인합니다.

## 외부 유래 구성 요소

다른 저장소에서 가져온 것은 반드시 `CREDITS.md`에 출처와 라이선스를 적습니다.
Apache-2.0 파생은 출처 표기가 의무입니다.

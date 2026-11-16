from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import PlanFormatError, PluginDocsMissing

PLUGIN_DIR_ENV = "ORCH_PLUGIN_DIR"
REFERENCE_DIR = Path("skills/orchestrate/references")
PLAN_TEMPLATE = "plan-template.md"
GOTCHAS = "gotchas.md"

PURPOSE_SECTION = "목적"
ALLOWED_SECTION = "건드릴 파일"
VERIFY_SECTION = "검증"
LIMITS_SECTION = "이 작업으로 확인할 수 없는 것"
RULES_SECTION = "지킬 것"

HEADING = re.compile(r"^##\s+(.+?)\s*$")
FENCE = re.compile(r"^\s*```")

HANDOFF_RULES = """## 지킬 것

- 계획의 `## 건드릴 파일` 목록 밖의 파일을 바꾸지 않는다
- 계획 파일 자체를 고치지 않는다
- 지적되지 않은 것을 겸사겸사 고치지 않는다
- 커밋하지 않는다. 브랜치를 만들지 않는다. 스테이징하지 않는다. 푸시하지 않는다
- 통과시키는 것이 목표가 아니다. 틀렸으면 틀렸다고 드러나게 한다
- 검증 명령이 막히면 거기서 멈추고 무엇이 막혔는지 적는다. 우회하지 않는다"""

REVIEW_RULES = """## 지킬 것

- 코드를 고치지 않는다. 고치기 시작하면 리뷰가 아니라 두 번째 구현이 된다
- 보고를 믿지 말고 코드로 직접 판단한다
- 심각도를 나눠 보고한다. 문제가 없으면 없다고 해도 된다
- 범위를 넓히는 지적은 그렇다고 밝히고 적는다"""

REVIEW_QUESTIONS = """## 따질 것

1. **이게 정말 그것을 증명하는가. 통과하도록 짜인 것은 아닌가**
2. 바뀐 코드가 주변의 기존 구조·관용구와 어긋나지 않는가
3. 계획이 "확인할 수 없는 것"으로 적어 둔 경계가 실제로 지켜졌는가
4. 빠뜨린 경계 조건이 있는가"""


def find_plugin_dir(explicit: Path | str | None = None) -> Path:
    looked: list[Path] = []
    for candidate in _plugin_candidates(explicit):
        looked.append(candidate)
        if (candidate / REFERENCE_DIR / PLAN_TEMPLATE).is_file():
            return candidate
    raise PluginDocsMissing(looked)


def read_reference(plugin_dir: Path, name: str) -> str:
    path = Path(plugin_dir) / REFERENCE_DIR / name
    if not path.is_file():
        raise PluginDocsMissing([path])
    return path.read_text(encoding="utf-8").strip()


def read_sections(plan: Path) -> dict[str, str]:
    text = Path(plan).read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    title = None
    fenced = False

    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        if not fenced:
            heading = HEADING.match(line)
            if heading:
                title = heading.group(1)
                found.setdefault(title, [])
                continue
        if title is not None:
            found[title].append(line)

    return {name: "\n".join(body).strip() for name, body in found.items()}


def section(plan: Path, name: str, *, required: bool = True) -> str:
    body = read_sections(plan).get(name, "")
    if required and not body:
        raise PlanFormatError(f"계획에 `## {name}` 절이 없거나 비어 있다: {plan}")
    return body


def first_block(body: str) -> list[str]:
    lines: list[str] = []
    inside = False
    for line in body.splitlines():
        if FENCE.match(line):
            if inside:
                break
            inside = True
            continue
        if inside:
            lines.append(line)
    return [line.strip() for line in lines if line.strip()]


def verify_commands(plan: Path) -> list[str]:
    return first_block(section(plan, VERIFY_SECTION))


def plan_prompt(task: str, plan_path: Path, plugin_dir: Path) -> str:
    template = read_reference(plugin_dir, PLAN_TEMPLATE)
    return f"""당신은 Planner다. 코드를 읽고 계획 산출물을 쓴다. 구현하지 않는다.

## 할 일

{task}

계획을 `{plan_path}`에 쓴다. 코드는 한 줄도 고치지 않는다.

## 지킬 것

- 읽어서 안 것만 "조사로 확인한 구조"에 적는다. 추측은 가설로 돌린다
- 검증 명령은 **적기 전에 한 번 돌려 본다.** 안 돌아가는 명령을 적으면 구현자가 거기서 막힌다
- `## 건드릴 파일` 제목과 그 아래 코드 블록 형식을 바꾸지 않는다. 기계가 읽는다
- 커밋하지 않는다. 브랜치를 만들지 않는다. 푸시하지 않는다

## 계획 형식

{template}"""


def implement_prompt(plan_path: Path, plugin_dir: Path) -> str:
    gotchas = read_reference(plugin_dir, GOTCHAS)
    return f"""당신은 구현자다. 계획 파일을 읽고 그대로 따른다.

계획: `{plan_path}`

대화 맥락 없이 그 파일만 보고 일한다. 모르는 것이 있으면 추측하지 말고 적어 둔다.

{HANDOFF_RULES}

## 끝낼 때

무엇을 바꿨는지 파일별로 적는다. 검증 명령을 돌렸으면 결과를 그대로 적는다.
막힌 것이 있으면 숨기지 않는다.

## 먼저 알아 둘 것

{gotchas}"""


def review_prompt(plan_path: Path, changed: list[str], plugin_dir: Path) -> str:
    purpose = section(plan_path, PURPOSE_SECTION)
    limits = section(plan_path, LIMITS_SECTION, required=False)
    rules = section(plan_path, RULES_SECTION, required=False)
    files = "\n".join(f"- `{path}`" for path in sorted(changed)) or "- (없음)"

    parts = [
        "당신은 리뷰어다. 이 변경을 독립적으로 판단한다.",
        "구현자의 보고는 주어지지 않는다. 코드를 직접 읽고 판단한다.",
        "",
        "## 이 변경이 하려는 것",
        "",
        purpose,
        "",
        "## 바뀐 파일",
        "",
        files,
        "",
        "커밋되지 않은 변경이다. `git diff`와 파일을 직접 읽는다.",
        "",
        REVIEW_QUESTIONS,
    ]
    if limits:
        parts += ["", "## 계획이 확인할 수 없다고 적은 것", "", limits]
    if rules:
        parts += ["", "## 이 작업에 걸리는 규칙", "", rules]
    parts += ["", REVIEW_RULES]
    return "\n".join(parts)


def fix_prompt(fix_plan_path: Path, plugin_dir: Path) -> str:
    gotchas = read_reference(plugin_dir, GOTCHAS)
    return f"""당신은 구현자다. 수정 계획을 읽고 그대로 따른다.

수정 계획: `{fix_plan_path}`

**거기 적힌 것만 고친다.** 리뷰가 낸 지적 중 반영하지 않기로 한 것은 그 계획에 빠져 있다.
빠진 지적을 겸사겸사 고치지 않는다.

{HANDOFF_RULES}

## 끝낼 때

지적별로 무엇을 어떻게 고쳤는지 적는다. 고치지 않은 것이 있으면 이유를 적는다.

## 먼저 알아 둘 것

{gotchas}"""


def _plugin_candidates(explicit: Path | str | None):
    if explicit:
        yield Path(explicit).expanduser()
    env = os.environ.get(PLUGIN_DIR_ENV)
    if env:
        yield Path(env).expanduser()
    yield Path.home() / ".claude/plugins/marketplaces/ahn-cc-kit/plugins/agent-orchestrator"
    yield Path(__file__).resolve().parents[3] / "plugins/agent-orchestrator"

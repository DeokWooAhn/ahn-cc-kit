#!/usr/bin/env python3
"""기존 문서를 보존하면서 도입 파일 또는 작업별 다섯 문서의 빈 양식을 준비한다."""

import argparse
import re
import sys
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
RESOURCES = PLUGIN / "skills" / "pack"
NAMES = ("task.md", "files.md", "rules.md", "tests.md", "done.md")
BEGIN = "<!-- context-pack:start -->"
END = "<!-- context-pack:end -->"
AGENTS_BRIDGE = "팀 지침은 `CLAUDE.md`에 있다. 작업 전에 직접 읽는다.\n"
BLOCK = f"""{BEGIN}
## Context Pack

변경 작업 전에 `.context-pack/workflow.md`를 직접 읽고 따른다.
AI가 별도 요청 없이 필요한 작업 팩을 내용까지 작성하고 그 기준으로 구현·검증한다.
질문·읽기 전용 리뷰는 팩을 만들지 않는다. 사소한 변경은 채팅으로 축약한다.
기존 계획·승인·검증 규칙은 유지하고 중복 작성하지 않는다.
{END}
"""


def inside(root, relative):
    """프로젝트 밖으로 향하는 경로·링크와 파일인 부모 디렉터리를 거절한다."""
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"프로젝트 밖 경로는 사용할 수 없습니다: {relative}")
    parent = path.parent
    while parent != root:
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"디렉터리가 필요한 위치입니다: {parent.relative_to(root)}")
        parent = parent.parent
    return path


def read_optional(path):
    if path.exists():
        if not path.is_file():
            raise ValueError(f"일반 파일이 필요한 위치입니다: {path.name}")
        return path.read_bytes().decode("utf-8")
    return ""


def instructions_for(root, selected):
    if selected:
        return selected
    agents = inside(root, "AGENTS.md")
    claude = inside(root, "CLAUDE.md")
    if agents.exists() and claude.exists():
        if read_optional(agents) == AGENTS_BRIDGE:
            return "CLAUDE.md"
        linked = agents.resolve() == claude.resolve() or re.search(
            r"(?m)^@(?:\./)?AGENTS\.md\s*$", read_optional(claude)
        )
        if not linked:
            raise ValueError("두 지침의 정본을 확인한 뒤 --instructions로 지정합니다.")
    return "AGENTS.md" if agents.exists() or not claude.exists() else "CLAUDE.md"


def setup(root, selected=None):
    instruction = instructions_for(root, selected)
    target = inside(root, instruction)
    original = read_optional(target)
    starts, ends = original.count(BEGIN), original.count(END)
    if starts != ends or starts > 1 or (starts and original.index(BEGIN) > original.index(END)):
        raise ValueError("Context Pack 연결 표식이 불완전합니다. 기존 내용을 확인합니다.")

    # 모든 경로·리소스를 먼저 검사한다. 기존 절차·사용자 템플릿은 갱신하지 않는다.
    copies = {
        "workflow.md": (RESOURCES / "references" / "workflow.md").read_bytes(),
        "integrations.md": (RESOURCES / "references" / "integrations.md").read_bytes(),
        "project.md": (RESOURCES / "templates" / "project.md").read_text(encoding="utf-8").replace(
            "{{INSTRUCTIONS}}", instruction
        ).encode(),
    }
    for name in NAMES:
        copies[f"templates/{name}"] = (RESOURCES / "templates" / name).read_bytes()
    pending = {}
    for name, data in copies.items():
        path = inside(root, f".context-pack/{name}")
        read_optional(path)
        if not path.exists():
            pending[path] = data

    # 새 프로젝트·단일 지침 프로젝트에서만 반대 도구의 짧은 진입 파일을 만든다.
    bridge = None
    if instruction == "AGENTS.md":
        bridge = (inside(root, "CLAUDE.md"), b"@AGENTS.md\n")
    elif instruction == "CLAUDE.md":
        bridge = (inside(root, "AGENTS.md"), AGENTS_BRIDGE.encode())
    if bridge:
        read_optional(bridge[0])
        if not bridge[0].exists():
            pending[bridge[0]] = bridge[1]

    for path, data in pending.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(data)
    if not starts:
        # 조사 중 다른 세션이 지침을 바꿨으면 새 내용 위에 덮어쓰지 않는다.
        if read_optional(target) != original:
            raise ValueError("지침이 다른 세션에서 바뀌었습니다. 다시 확인합니다.")
        separator = "" if not original else "\n" if original.endswith("\n") else "\n\n"
        target.write_bytes((original + separator + BLOCK).encode())
    print(f"도입 연결 확인: {instruction}; 기존 파일 유지, 새 파일 {len(pending)}개")
    print("AI가 .context-pack/project.md를 실제 경로로 채우고 기존 메모·진입점 중복을 확인해야 합니다.")


def new_pack(root, task):
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?", task):
        raise ValueError("작업명은 영문 소문자·숫자·하이픈 1~80자이며 글자·숫자로 시작하고 끝나야 합니다.")
    folder = inside(root, f"context/{task}")
    targets = [inside(root, f"context/{task}/{name}") for name in NAMES]
    if folder.exists():
        if not folder.is_dir() or not all(path.is_file() for path in targets):
            raise ValueError("기존 작업 팩이 불완전합니다. 덮어쓰지 않고 내용을 확인합니다.")
        print(f"기존 팩 재사용: context/{task}; 파일을 변경하지 않았습니다.")
        return
    contents = []
    for name in NAMES:
        local = inside(root, f".context-pack/templates/{name}")
        source = local if local.is_file() else RESOURCES / "templates" / name
        contents.append(source.read_bytes())
    folder.mkdir(parents=True)
    for path, data in zip(targets, contents):
        with path.open("xb") as output:
            output.write(data)
    print(f"빈 양식 생성: context/{task}; AI가 관련 근거로 다섯 문서의 내용을 작성해야 합니다.")


def main():
    # 한국어 안내는 로케일과 무관하게 출력한다. UTF-8 모드가 꺼진 환경에서도 실패로 끝나지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("setup", "new"):
        command = commands.add_parser(name)
        command.add_argument("--project", required=True, type=Path)
        if name == "setup":
            command.add_argument("--instructions", choices=("AGENTS.md", "CLAUDE.md", "CLAUDE.local.md"))
        else:
            command.add_argument("--task", required=True)
    args = parser.parse_args()
    try:
        root = args.project.resolve()
        if not root.is_dir():
            raise ValueError("프로젝트 디렉터리가 존재하지 않습니다.")
        if args.command == "setup":
            setup(root, args.instructions)
        else:
            new_pack(root, args.task)
    except (OSError, ValueError) as error:
        print(f"준비 실패: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

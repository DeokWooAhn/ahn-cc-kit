#!/usr/bin/env python3
"""실제 새 Claude 세션 3개로 도입·질문·자동 팩 작성과 구현을 확인한다. 수동 실행 전용이다.

Claude 로그인과 모델 호출을 사용한다. CI에서는 실행하지 않는다.
원본 대화는 지정한 결과 폴더에만 남기고 커밋하지 않는다.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
NAMES = {"task.md", "files.md", "rules.md", "tests.md", "done.md"}
FIXTURE = {
    "AGENTS.md": """# 재고 주문 예제

Python 표준 라이브러리만 사용한다. src는 재고 규칙과 주문 흐름으로 나뉜다.
직접 변경을 요청받으면 관련 근거를 읽고 구현·검증까지 진행한다. 같은 계획의 반복 승인은 필요 없다.
기존 사용자 변경과 관련 없는 파일을 보존한다. 커밋·푸시·네트워크 접근은 이 예제 작업에 포함되지 않는다.
팀 세부 규칙과 검증 명령은 docs/development.md를 읽는다. 답변과 설명은 한국어로 쓴다.
""",
    "CLAUDE.md": "@AGENTS.md\n",
    ".gitignore": "__pycache__/\n*.pyc\n",
    "docs/development.md": """# 개발 안내

src/inventory.py는 수량 검증과 단일 상품 예약 규칙을 맡는다.
src/checkout.py는 여러 항목으로 주문을 만들며 재고 모듈을 사용한다.
주문 반환값은 입력 순서의 (상품, 수량) 목록이다. 이 공개 형태는 유지한다.
가격·상품 표시 원본 src/catalog.py는 이번 재고 작업의 대상이 아니다.
표준 검증은 저장소 루트에서 python3 -m unittest discover -s tests -v로 실행한다.
외부 서버나 새 의존성은 없다. 테스트는 실제 규칙을 사용한다.
""",
    "src/__init__.py": "",
    "src/catalog.py": 'DISPLAY_NAME = {"apple": "사과", "pear": "배"}\n',
    "src/inventory.py": """def reserve(stock, sku, quantity):
    if stock[sku] < quantity:
        raise ValueError("재고 부족")
    stock[sku] -= quantity
""",
    "src/checkout.py": """from src.inventory import reserve


def place_order(stock, lines):
    result = []
    for sku, quantity in lines:
        reserve(stock, sku, quantity)
        result.append((sku, quantity))
    return result
""",
    "tests/test_checkout.py": """import unittest
from src.checkout import place_order
from src.inventory import reserve


class CheckoutTest(unittest.TestCase):
    def test_order_reserves_stock_and_keeps_receipt_order(self):
        stock = {"apple": 5, "pear": 3}
        self.assertEqual(place_order(stock, [("pear", 2), ("apple", 1)]), [("pear", 2), ("apple", 1)])
        self.assertEqual(stock, {"apple": 4, "pear": 1})

    def test_insufficient_single_reservation_is_rejected(self):
        stock = {"apple": 2}
        with self.assertRaises(ValueError):
            reserve(stock, "apple", 3)
        self.assertEqual(stock, {"apple": 2})
""",
    "notes/personal.md": "개인 검토 메모: 다음 주에 문서 용어를 확인한다.\n",
}
ADOPT = "이 프로젝트에 context-pack 방식을 도입해줘. 기존 지침과 개발 문서를 확인해서 통합해줘. 앱 코드·테스트·CI는 바꾸지 말고 커밋·푸시도 하지 마."
QUESTION = "checkout과 inventory가 어떤 역할을 나눠 맡고 있는지 설명만 해줘. 파일은 수정하지 마."
CHANGE = """주문 실패 뒤에도 앞 상품의 재고가 줄어드는 버그를 고쳐줘.
여러 상품 중 뒤 항목이 재고 부족이거나 없는 상품이면 주문 전체가 실패하고 원래 재고를 유지해야 해.
같은 상품이 여러 줄일 때 합계 수량이 재고를 넘는 경우도 포함해줘.
0이나 음수 수량은 재고 예약 단계에서 거절하고 재고를 바꾸면 안 돼.
정상 주문의 반환 형식과 차감 동작은 유지하고 관련 회귀 테스트도 추가해줘.
"""
ORACLE = """from src.checkout import place_order
from src.inventory import reserve

def reject_without_changes(call, stock):
    before = dict(stock)
    try:
        call()
    except (ValueError, KeyError):
        pass
    else:
        raise AssertionError('잘못된 요청을 허용함')
    assert stock == before, (stock, before)

for lines in [[('apple', 2), ('pear', 9)], [('apple', 2), ('missing', 1)],
              [('apple', 3), ('apple', 3)], [('apple', 2), ('pear', 0)],
              [('apple', 2), ('pear', -1)]]:
    stock = {'apple': 5, 'pear': 2}
    reject_without_changes(lambda: place_order(stock, lines), stock)
for quantity in [0, -3, 6]:
    stock = {'apple': 5}
    reject_without_changes(lambda: reserve(stock, 'apple', quantity), stock)
stock = {'apple': 5, 'pear': 2}
receipt = place_order(stock, [('apple', 2), ('apple', 3), ('pear', 2)])
assert receipt == [('apple', 2), ('apple', 3), ('pear', 2)]
assert stock == {'apple': 0, 'pear': 0}
stock = {'apple': 5}
assert place_order(stock, []) == [] and stock == {'apple': 5}
print('독립 검증 10개 시나리오 통과')
"""


def snapshot(project):
    return {str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in project.rglob("*") if path.is_file()
            and not {".git", "__pycache__"}.intersection(path.relative_to(project).parts)
            and path.suffix != ".pyc"}


def run_session(stage, prompt, project, output, with_plugin=False):
    command = ["claude", "-p", "--verbose", "--output-format", "stream-json",
               "--no-session-persistence", "--setting-sources", "project,local",
               "--settings", '{"autoMemoryEnabled":false}',
               "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--permission-mode", "acceptEdits", "--permission-prompts", "none",
               "--max-budget-usd", "4", "--tools", "Read,Write,Edit,Glob,Grep,Bash,Skill",
               "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Skill",
               "Bash(python3 *)", "Bash(git status*)", "Bash(git diff*)",
               "Bash(ls *)", "Bash(find *)", "Bash(cat *)", "Bash(sed *)",
               "Bash(mkdir *)", "Bash(cp *)", "Bash(wc *)", "Bash(rg *)"]
    if with_plugin:
        command.extend(["--plugin-dir", str(PLUGIN), "--add-dir", str(PLUGIN)])
    print(f"시작: {stage}", flush=True)
    (output / f"{stage}.prompt.txt").write_text(prompt, encoding="utf-8")
    with (output / f"{stage}.jsonl").open("w", encoding="utf-8") as log, \
         (output / f"{stage}.stderr.txt").open("w", encoding="utf-8") as errors:
        result = subprocess.run(command, input=prompt, text=True, encoding="utf-8", cwd=project,
                                stdout=log, stderr=errors, timeout=600, check=False)
    events = [json.loads(line) for line in (output / f"{stage}.jsonl").read_text(encoding="utf-8").splitlines()
              if line.startswith("{")]
    final = next((event for event in reversed(events) if event.get("type") == "result"), {})
    initial = next((event for event in events if event.get("type") == "system"
                    and event.get("subtype") == "init"), {})
    calls = [block for event in events if event.get("type") == "assistant"
             for block in event.get("message", {}).get("content", []) if block.get("type") == "tool_use"]
    record = {"stage": stage, "session_id": final.get("session_id"), "exit_code": result.returncode,
              "is_error": final.get("is_error", True), "subtype": final.get("subtype"),
              "permission_denials": final.get("permission_denials", []),
              "model": initial.get("model"),
              "loaded_plugins": [plugin["name"] for plugin in initial.get("plugins", [])],
              "tools": [call["name"] for call in calls], "duration_ms": final.get("duration_ms")}
    (output / f"{stage}.result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"종료: {stage}, exit={result.returncode}, result={record['subtype']}", flush=True)
    if result.returncode or record["is_error"]:
        raise AssertionError(f"새 세션 실행 실패: {stage}; {output / (stage + '.result.json')}")
    return record, calls


def observe(project, stop, timeline):
    previous = snapshot(project)
    while not stop.wait(0.05):
        current = snapshot(project)
        for path, digest in current.items():
            if previous.get(path) != digest:
                timeline.append({"at": (project / path).stat().st_mtime_ns, "path": path, "sha256": digest,
                                 "text": (project / path).read_text(encoding="utf-8")})
        previous = current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="새로 생성할 결과 디렉터리. 기본값은 임시 디렉터리")
    args = parser.parse_args()
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="context-pack-eval-"))
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    project = output / "project"
    project.mkdir()
    for name, content in FIXTURE.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git = ["git", "-C", str(project)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "검증용 기본 프로젝트를 준비한다"], check=True)
    note = project / "notes/personal.md"
    note.write_text(note.read_text(encoding="utf-8") + "사용자가 먼저 수정한 메모: 이번 주문 작업과 별개다.\n", encoding="utf-8")
    initial = snapshot(project)
    baseline = subprocess.run([sys.executable, "-c", ORACLE], cwd=project, capture_output=True, text=True)
    assert baseline.returncode != 0, "재현 코드가 수정 전부터 성공합니다."
    (output / "oracle-before.txt").write_text(baseline.stdout + baseline.stderr, encoding="utf-8")

    records = []
    adopted, _ = run_session("01-adopt", ADOPT, project, output, with_plugin=True)
    records.append(adopted)
    assert "context-pack" in adopted["loaded_plugins"], "도입 세션에서 플러그인이 로드되지 않았습니다."
    after_adopt = snapshot(project)
    changed = {name for name in set(initial) | set(after_adopt) if initial.get(name) != after_adopt.get(name)}
    assert all(name in {"AGENTS.md", "CLAUDE.md"} or name.startswith(".context-pack/")
               for name in changed), changed
    for name in ("workflow.md", "integrations.md", "project.md"):
        assert (project / ".context-pack" / name).is_file(), name
    assert "{{INSTRUCTIONS}}" not in (project / ".context-pack/project.md").read_text(encoding="utf-8")

    question, _ = run_session("02-question", QUESTION, project, output)
    records.append(question)
    assert "context-pack" not in question["loaded_plugins"], "설명 세션에 플러그인이 추가 로드됐습니다."
    assert snapshot(project) == after_adopt, "설명 요청에서 파일이 바뀌었습니다."

    timeline = []
    stop = threading.Event()
    watcher = threading.Thread(target=observe, args=(project, stop, timeline), daemon=True)
    watcher.start()
    try:
        implemented, calls = run_session("03-change", CHANGE, project, output)
    finally:
        stop.set()
        watcher.join()
        (output / "change-timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records.append(implemented)
    assert "context-pack" not in implemented["loaded_plugins"], "수정 세션에 플러그인이 추가 로드됐습니다."
    assert all(record["session_id"] for record in records) and len({record["session_id"] for record in records}) == 3, \
        "서로 다른 새 세션이 아닙니다."
    production = [event for event in timeline if event["path"].startswith(("src/", "tests/"))]
    assert production, "구현 변경이 없습니다."
    first_change = min(event["at"] for event in production)
    prepared = {}
    for event in timeline:
        path = Path(event["path"])
        if path.parts[0] == "context" and path.name in NAMES and event["at"] < first_change:
            template = project / ".context-pack/templates" / path.name
            if not template.exists() or event["text"] != template.read_text(encoding="utf-8"):
                prepared.setdefault(str(path.parent), set()).add(path.name)
    assert any(names == NAMES for names in prepared.values()), "구현 전에 다섯 문서의 내용이 준비되지 않았습니다."
    assert any(call["name"] == "Bash" and "unittest" in call.get("input", {}).get("command", "")
               for call in calls), "모델이 검증 명령을 실행하지 않았습니다."
    final = snapshot(project)
    assert final["notes/personal.md"] == initial["notes/personal.md"], "기존 사용자 메모가 바뀌었습니다."
    assert final["src/catalog.py"] == initial["src/catalog.py"], "관련 없는 상품 파일이 바뀌었습니다."
    changed = {name for name in set(after_adopt) | set(final) if after_adopt.get(name) != final.get(name)}
    assert all(name in {"src/inventory.py", "src/checkout.py"} or name.startswith(("tests/", "context/"))
               for name in changed), changed
    verified = subprocess.run([sys.executable, "-c", ORACLE], cwd=project, capture_output=True, text=True)
    (output / "oracle-after.txt").write_text(verified.stdout + verified.stderr, encoding="utf-8")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    own_tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                               cwd=project, capture_output=True, text=True)
    (output / "tests-after.txt").write_text(own_tests.stdout + own_tests.stderr, encoding="utf-8")
    assert own_tests.returncode == 0, own_tests.stdout + own_tests.stderr
    summary = {"sessions": records, "adoption_only_changed_instructions": True,
               "question_preserved_all_files": True, "prepared_before_implementation": True,
               "pack_paths": sorted(name for name, names in prepared.items() if names == NAMES),
               "changed_files": sorted(changed), "user_change_preserved": True,
               "oracle_failed_before_passed_after": True, "model_ran_tests": True,
               "own_tests_passed": True}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"행동 검증 통과: {output / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()

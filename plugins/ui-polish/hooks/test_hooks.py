#!/usr/bin/env python3
"""ui-polish screen-notice 훅 회귀 테스트.

이 훅은 도구 입력이 아니라 저장소 상태로 판정한다. 그래서 케이스마다 임시 git 저장소를 만들고
파일을 더한 뒤 Stop 입력을 넣는다. 훅은 막지 않으므로 모든 케이스에서 exit 0 이고,
차이는 알림이 나오는지와 그 내용뿐이다.
훅은 /bin/bash(macOS 3.2)로 돌린다. 3.2 에서만 드러나는 버그가 있다.

    python3 test_hooks.py
"""

import json
import pathlib
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
HOOK = HERE / "screen-notice.sh"
BASH = "/bin/bash"
STOP = '{"session_id":"s","hook_event_name":"Stop","stop_hook_active":false}'
PROMPT = '{"session_id":"s","hook_event_name":"UserPromptSubmit","prompt":"질문"}'

COMPOSE = '@Composable\nfun HomeScreen() {\n  Text("hi")\n}\n'
SWIFTUI = 'import SwiftUI\n\nstruct HomeView: View {\n  var body: some View { Text("hi") }\n}\n'
FLUTTER = (
    "import 'package:flutter/material.dart';\n\n"
    "class HomePage extends StatelessWidget {\n"
    "  @override\n"
    "  Widget build(BuildContext context) => const Text('hi');\n}\n"
)
PLAIN_KT = "class Repo {\n  fun load() = 1\n}\n"

fails = 0


def check(ok, name, detail=""):
    global fails
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else f"  ({detail})"))
    if not ok:
        fails += 1


def git(d, *args):
    return subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, text=True).stdout.strip()


def repo(tmp, name, committed=None):
    """빈 git 저장소. committed 는 먼저 커밋해 둘 {경로: 내용}."""
    d = pathlib.Path(tmp) / name
    d.mkdir(parents=True)
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@example.com")
    git(d, "config", "user.name", "t")
    (d / ".gitkeep").write_text("")
    for path, body in (committed or {}).items():
        f = d / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    git(d, "add", "-A")
    git(d, "commit", "-qm", "init")
    return d


def write(d, path, body):
    f = d / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)
    return f


def run(d, mode=None, stdin=STOP, cwd=None, env=None):
    cmd = [BASH, str(HOOK)] + ([mode] if mode else [])
    e = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(d), "CLAUDE_PROJECT_DIR": str(d)}
    e.update(env or {})
    p = subprocess.run(cmd, cwd=str(cwd or d), input=stdin, capture_output=True, text=True, env=e)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def message(out):
    """알림 JSON 에서 systemMessage 를 꺼낸다. 알림이 없으면 None."""
    if not out:
        return None
    return json.loads(out).get("systemMessage")


def main():
    tmp = tempfile.mkdtemp()
    try:
        print("새 화면을 알린다")
        for label, path, body in (
            ("Compose", "app/HomeScreen.kt", COMPOSE),
            ("SwiftUI", "App/HomeView.swift", SWIFTUI),
            ("Flutter", "lib/home_page.dart", FLUTTER),
        ):
            d = repo(tmp, f"new-{label}")
            run(d, "mark", stdin=PROMPT)
            write(d, path, body)
            rc, out, _ = run(d)
            msg = message(out)
            check(rc == 0 and msg and "새 화면 1개" in msg, f"{label} · 알림", f"exit={rc} out={out!r}")

        print("\n알리지 않을 것")
        d = repo(tmp, "plain")
        run(d, "mark", stdin=PROMPT)
        write(d, "data/Repo.kt", PLAIN_KT)
        rc, out, _ = run(d)
        check(rc == 0 and not out, "@Composable 없는 .kt · 조용", f"out={out!r}")

        d = repo(tmp, "edit", {"app/HomeScreen.kt": COMPOSE})
        run(d, "mark", stdin=PROMPT)
        write(d, "app/HomeScreen.kt", COMPOSE + "// edit\n")
        rc, out, _ = run(d)
        check(rc == 0 and not out, "기존 화면 수정만 · 조용", f"out={out!r}")

        d = repo(tmp, "preexisting")
        write(d, "app/HomeScreen.kt", COMPOSE)
        run(d, "mark", stdin=PROMPT)  # 턴 시작 때 이미 있던 새 파일
        rc, out, _ = run(d)
        check(rc == 0 and not out, "턴 시작부터 있던 새 파일 · 조용", f"out={out!r}")

        d = repo(tmp, "twice")
        run(d, "mark", stdin=PROMPT)
        write(d, "app/HomeScreen.kt", COMPOSE)
        rc, out, _ = run(d)
        check(rc == 0 and message(out), "같은 화면 첫 번째 · 알림", f"out={out!r}")
        rc, out, _ = run(d)
        check(rc == 0 and not out, "같은 화면 두 번째 · 조용", f"out={out!r}")

        d = repo(tmp, "tests-excluded")
        run(d, "mark", stdin=PROMPT)
        write(d, "app/src/androidTest/HomeScreenTest.kt", COMPOSE)
        write(d, "test/home_page_test.dart", FLUTTER)
        rc, out, _ = run(d)
        check(rc == 0 and not out, "테스트 경로 · 조용", f"out={out!r}")

        d = repo(tmp, "optout")
        run(d, "mark", stdin=PROMPT)
        write(d, "app/HomeScreen.kt", COMPOSE)
        rc, out, _ = run(d, env={"UI_POLISH_DISABLE_SCREEN_NOTICE": "1"})
        check(rc == 0 and not out, "opt-out · 조용", f"out={out!r}")

        print("\n여러 개와 경계")
        d = repo(tmp, "many")
        run(d, "mark", stdin=PROMPT)
        for i in range(5):
            write(d, f"app/Screen{i}.kt", COMPOSE)
        rc, out, _ = run(d)
        msg = message(out) or ""
        check(rc == 0 and "새 화면 5개" in msg and "외 2개" in msg, "5개 · 3개만 보이고 나머지는 개수", f"msg={msg!r}")

        d = repo(tmp, "spaced")
        run(d, "mark", stdin=PROMPT)
        write(d, "app/홈 화면.kt", COMPOSE)
        rc, out, _ = run(d)
        msg = message(out) or ""
        check(rc == 0 and "홈 화면.kt" in msg, "공백·한글 경로", f"msg={msg!r}")

        rc, out, _ = run(pathlib.Path(tmp) / "not-a-repo-dir", cwd=tmp)
        check(rc == 0 and not out, "git 저장소 밖 · 조용", f"exit={rc}")

        d = repo(tmp, "empty-stdin")
        rc, out, _ = run(d, stdin="")
        check(rc == 0 and not out, "빈 입력 · 조용", f"exit={rc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n실패 없음" if not fails else f"\n실패 {fails}건")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

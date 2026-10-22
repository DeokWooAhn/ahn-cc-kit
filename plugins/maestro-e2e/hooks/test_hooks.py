#!/usr/bin/env python3
"""maestro-e2e flow-reminder 훅 회귀 테스트.

이 훅은 도구 입력이 아니라 저장소 상태로 판정한다. 그래서 케이스마다 임시 git 저장소를 만들고
파일을 바꾼 뒤 Stop 입력을 넣는다. 훅은 /bin/bash(macOS 3.2)로 돌린다. 3.2에서만 드러나는 버그가 있다.

    python3 test_hooks.py
"""

import os
import pathlib
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
HOOK = HERE / "flow-reminder.sh"
BASH = "/bin/bash"
STOP = '{"session_id":"s","hook_event_name":"Stop","stop_hook_active":false}'
PROMPT = '{"session_id":"s","hook_event_name":"UserPromptSubmit","prompt":"질문"}'
STOP_ACTIVE = '{"session_id":"s","hook_event_name":"Stop","stop_hook_active": true}'

SCREEN_KT = "@Composable\nfun HomeScreen() {\n  Text(\"hi\")\n}\n"
SCREEN_SWIFT = "import SwiftUI\n\nstruct HomeView: View {\n  var body: some View { Text(\"hi\") }\n}\n"
PLAIN_KT = "class Repo {\n  fun load() = 1\n}\n"


def git(d, *args):
    subprocess.run(["git", *args], cwd=d, check=True, capture_output=True)


def repo(tmp, name, files, maestro=True):
    d = pathlib.Path(tmp) / name
    d.mkdir(parents=True)
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@example.com")
    git(d, "config", "user.name", "t")
    if maestro:
        (d / ".maestro").mkdir()
        (d / ".maestro/config.yaml").write_text('flows:\n  - "flows/*"\n')
    for rel, body in files.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "init", "--allow-empty")
    return d


def write(d, rel, body):
    f = d / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)


def run(d, stdin=STOP, env_extra=None, cwd=None, mode=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MAESTRO_E2E_")}
    env["CLAUDE_PROJECT_DIR"] = str(d)
    env.update(env_extra or {})
    p = subprocess.run([BASH, str(HOOK), *([mode] if mode else [])], input=stdin, capture_output=True, text=True,
                       env=env, cwd=cwd or d)
    return p.returncode, p.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="maestro-hook-")
    fails = 0

    def check(ok, label, detail=""):
        nonlocal fails
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label}{('  ' + detail) if detail else ''}")

    try:
        print("\n== flow-reminder.sh")

        d = repo(tmp, "android", {"app/src/main/java/a/HomeScreen.kt": SCREEN_KT})
        rc, err = run(d)
        check(rc == 0 and not err, "변경 없음 · 조용", f"exit={rc}")

        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 바꿈\n")
        rc, err = run(d)
        check(rc == 2, "Compose 화면 수정 · 알림", f"exit={rc}")
        check("smoke와 release" in err and "Android" in err, "Android에서 smoke·release를 돌리라고 함")
        check("새로 생긴 화면" not in err, "수정만이면 Flow 판단은 묻지 않음")

        rc, err = run(d)
        check(rc == 0 and not err, "같은 변경 · 다시 알리지 않음", f"exit={rc}")

        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 또 바꿈\n")
        rc, _ = run(d)
        check(rc == 2, "내용이 또 바뀜 · 다시 알림", f"exit={rc}")

        write(d, "app/src/main/java/a/SettingsScreen.kt", SCREEN_KT.replace("Home", "Settings"))
        rc, err = run(d)
        check(rc == 2 and "새로 생긴 화면" in err and "SettingsScreen.kt" in err,
              "새 화면 파일 · Flow 판단도 물음", f"exit={rc}")
        check("답을 받기 전에는 Flow를 만들지 않습니다" in err, "묻기만 하고 만들지 않게 함")

        write(d, "app/src/main/java/a/Other.kt", SCREEN_KT + "// x\n")
        rc, _ = run(d, STOP_ACTIVE)
        check(rc == 0, "stop_hook_active · 알리지 않음 (반복 방지)", f"exit={rc}")

        rc, _ = run(d, env_extra={"MAESTRO_E2E_DISABLE_FLOW_REMINDER": "1"})
        check(rc == 0, "opt-out · 알리지 않음", f"exit={rc}")

        print("\n-- 턴 시작 기록 (UserPromptSubmit)")
        d = repo(tmp, "turn", {"app/a/HomeScreen.kt": SCREEN_KT, "app/a/Repo.kt": PLAIN_KT})
        write(d, "app/a/HomeScreen.kt", SCREEN_KT + "// 사용자가 미리 고쳐 둠\n")
        write(d, "app/a/DraftScreen.kt", SCREEN_KT.replace("Home", "Draft"))
        rc, out = run(d, PROMPT, mode="mark")
        check(rc == 0 and not out, "mark · exit 0, 출력 없음", f"exit={rc}")
        rc, err = run(d)
        check(rc == 0 and not err, "미리 고쳐 둔 화면만 · 질문에 답하고 마칠 때 조용", f"exit={rc}")
        write(d, "app/a/Repo.kt", PLAIN_KT + "// 이번 턴\n")
        rc, _ = run(d)
        check(rc == 0, "이번 턴엔 화면 아닌 파일만 · 조용", f"exit={rc}")
        run(d, PROMPT, mode="mark")
        write(d, "app/a/HomeScreen.kt", SCREEN_KT + "// 이번 턴에 바꿈\n")
        rc, err = run(d)
        check(rc == 2 and "HomeScreen.kt" in err, "이번 턴에 화면 수정 · 알림", f"exit={rc}")
        check("DraftScreen.kt" not in err, "턴 전부터 있던 새 파일은 다시 묻지 않음")
        rc, _ = run(d)
        check(rc == 0, "같은 턴 두 번째 Stop · 조용", f"exit={rc}")
        run(d, PROMPT, mode="mark")
        write(d, "app/a/ProfileScreen.kt", SCREEN_KT.replace("Home", "Profile"))
        rc, err = run(d)
        check(rc == 2 and "ProfileScreen.kt" in err and "새로 생긴 화면" in err, "이번 턴의 새 화면 · Flow 판단 물음", f"exit={rc}")

        d = repo(tmp, "plain", {"app/src/main/java/a/Repo.kt": PLAIN_KT})
        write(d, "app/src/main/java/a/Repo.kt", PLAIN_KT + "// 바꿈\n")
        rc, _ = run(d)
        check(rc == 0, "화면이 아닌 Kotlin · 조용", f"exit={rc}")

        write(d, "app/src/test/java/a/HomeScreenTest.kt", SCREEN_KT)
        write(d, "app/build/generated/a/Gen.kt", SCREEN_KT)
        rc, _ = run(d)
        check(rc == 0, "테스트·build 경로 · 조용", f"exit={rc}")

        d = repo(tmp, "no-maestro", {"app/src/main/java/a/HomeScreen.kt": SCREEN_KT}, maestro=False)
        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 바꿈\n")
        rc, _ = run(d)
        check(rc == 0, ".maestro/ 없는 저장소 · 조용", f"exit={rc}")

        d = repo(tmp, "ios", {"ios/App/Home View.swift": SCREEN_SWIFT})
        write(d, "ios/App/Home View.swift", SCREEN_SWIFT + "// 바꿈\n")
        rc, err = run(d)
        check(rc == 2 and "iOS" in err and "Home View.swift" in err, "SwiftUI 화면(공백 경로) · iOS로 알림", f"exit={rc}")

        d = repo(tmp, "rename", {"app/a/OldScreen.kt": SCREEN_KT})
        git(d, "mv", "app/a/OldScreen.kt", "app/a/NewScreen.kt")
        rc, err = run(d)
        check(rc == 2 and "NewScreen.kt" in err, "이름 바꾼 화면 · 새 경로로 알림", f"exit={rc}")

        d = repo(tmp, "delete", {"app/a/GoneScreen.kt": SCREEN_KT})
        (d / "app/a/GoneScreen.kt").unlink()
        rc, _ = run(d)
        check(rc == 0, "삭제만 · 조용", f"exit={rc}")

        rc, _ = run(pathlib.Path(tmp) / "not-a-repo-dir", cwd=tmp)
        check(rc == 0, "git 저장소 밖 · 조용", f"exit={rc}")

        rc, _ = run(d, stdin="")
        check(rc == 0, "빈 입력 · 조용", f"exit={rc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n실패 없음" if not fails else f"\n실패 {fails}건")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

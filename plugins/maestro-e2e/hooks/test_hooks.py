#!/usr/bin/env python3
"""maestro-e2e flow-reminder 훅 회귀 테스트.

이 훅은 도구 입력이 아니라 저장소 상태와 Maestro 결과 파일로 판정한다. 그래서 케이스마다 임시 git 저장소를
만들고 파일을 바꾼 뒤 Stop 입력을 넣는다. 결과 파일이 화면 파일보다 새로운지는 수정 시각으로 보므로,
화면 파일은 100초 전, 결과 파일은 10초 전으로 시각을 맞춘다.
훅은 /bin/bash(macOS 3.2)로 돌린다. 3.2에서만 드러나는 버그가 있다.

    python3 test_hooks.py
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
HOOK = HERE / "flow-reminder.sh"
BASH = "/bin/bash"
STOP = '{"session_id":"s","hook_event_name":"Stop","stop_hook_active":false}'
PROMPT = '{"session_id":"s","hook_event_name":"UserPromptSubmit","prompt":"질문"}'
STOP_ACTIVE = '{"session_id":"s","hook_event_name":"Stop","stop_hook_active": true}'

SCREEN_KT = "@Composable\nfun HomeScreen() {\n  Text(\"hi\")\n}\n"
SCREEN_SWIFT = "import SwiftUI\n\nstruct HomeView: View {\n  var body: some View { Text(\"hi\") }\n}\n"
PLAIN_KT = "class Repo {\n  fun load() = 1\n}\n"

OLD = 100  # 화면 파일: 100초 전
RUN = 10  # 결과 파일: 10초 전


def git(d, *args):
    return subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, text=True).stdout.strip()


def age(f, seconds):
    t = time.time() - seconds
    os.utime(f, (t, t))


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


def write(d, rel, body, seconds_ago=OLD):
    f = d / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)
    age(f, seconds_ago)


def evidence(d, name):
    return pathlib.Path(git(d, "rev-parse", "--absolute-git-dir")) / name


def report(d, key, cases, one_line=False, seconds_ago=RUN):
    """Maestro 2.1.0 JUnit 리포터와 같은 요소 이름. cases: [(이름, 실패 여부)]"""
    body = []
    for name, failed in cases:
        attrs = f'id="{name}" name="{name}" classname="{name}" time="1.0"'
        if failed:
            body.append(f'<testcase {attrs} status="ERROR"><failure>Element not found: Id {name}_x</failure></testcase>')
        else:
            body.append(f'<testcase {attrs} status="SUCCESS"/>')
    sep = "" if one_line else "\n    "
    fails = sum(1 for _, f in cases if f)
    xml = (f"<?xml version='1.0' encoding='UTF-8'?>{sep[:1]}<testsuites>{sep}"
           f'<testsuite name="Test Suite" device="emulator-5554" tests="{len(cases)}" failures="{fails}" time="5">'
           f"{sep}{sep.join(body)}{sep}</testsuite>{sep[:1]}</testsuites>\n")
    f = evidence(d, f"maestro-e2e-{key}.xml")
    f.write_text(xml)
    age(f, seconds_ago)


def skip(d, key, text, seconds_ago=RUN):
    f = evidence(d, f"maestro-e2e-{key}.skip")
    f.write_text(text)
    age(f, seconds_ago)


def clear(d):
    for key in ("android", "ios"):
        for ext in ("xml", "skip"):
            evidence(d, f"maestro-e2e-{key}.{ext}").unlink(missing_ok=True)
    evidence(d, "maestro-e2e-stop-count").unlink(missing_ok=True)


def run(d, stdin=STOP, env_extra=None, cwd=None, mode=None, keep_count=False):
    """keep_count=False면 막은 횟수를 지우고 돌린다. 횟수 상한을 보는 케이스만 True로 둔다."""
    if not keep_count and mode is None and (d / ".git").exists():
        evidence(d, "maestro-e2e-stop-count").unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("MAESTRO_E2E_")}
    env["CLAUDE_PROJECT_DIR"] = str(d)
    env.update(env_extra or {})
    p = subprocess.run([BASH, str(HOOK), *([mode] if mode else [])], input=stdin, capture_output=True, text=True,
                       env=env, cwd=cwd or d)
    return p.returncode, p.stdout, p.stderr


def message(out):
    """stdout이 비었으면 None, 있으면 systemMessage. JSON이 아니면 예외."""
    return json.loads(out)["systemMessage"] if out.strip() else None


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
        rc, out, err = run(d)
        check(rc == 0 and not out and not err, "변경 없음 · 조용", f"exit={rc}")

        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 바꿈\n")
        rc, out, err = run(d)
        check(rc == 2, "Compose 화면 수정 · 결과 없음 · 막음", f"exit={rc}")
        check("smoke와 release" in err and "Android: 화면을 바꾼 뒤 돌린 결과가 없습니다" in err,
              "Android에서 smoke·release를 돌리라고 함")
        check("--format=JUNIT" in err and "maestro-e2e-android.xml" in err and "maestro-e2e-android.skip" in err,
              "리포트·건너뜀 파일 경로를 알려 줌")
        check("확인 1/3" in err, "몇 번째 확인인지 알려 줌")
        check("새로 생긴 화면" not in err and "iOS" not in err, "수정만이면 Flow 판단을 묻지 않고, iOS는 요구하지 않음")

        report(d, "android", [("smoke_tabs", False), ("smoke_calculator", False)])
        rc, out, err = run(d)
        msg = message(out)
        check(rc == 0 and not err and msg and "Android Flow 2개 통과" in msg, "새 리포트 · 통과 · 사용자에게 한 줄", f"exit={rc} {msg}")

        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 돌린 뒤 또 바꿈\n", seconds_ago=0)
        rc, out, err = run(d)
        check(rc == 2 and "결과가 없습니다" in err, "리포트 뒤에 화면을 또 바꿈 · 다시 막음", f"exit={rc}")

        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 바꿈\n")
        report(d, "android", [("smoke_tabs", False), ("smoke_calculator", True)])
        rc, out, err = run(d)
        check(rc == 2 and "  - smoke_calculator" in err and "  - smoke_tabs" not in err,
              "실패한 Flow · 막고 실패한 이름만 보여 줌", f"exit={rc}")
        check('"실패했을 때"' in err and "가리지 않습니다" in err, "판정 절차와 가리지 말 것을 알려 줌")

        report(d, "android", [("smoke_tabs", False), ("smoke_calculator", False)], one_line=True)
        rc, out, _ = run(d)
        check(rc == 0 and "2개 통과" in (message(out) or ""), "한 줄짜리 리포트 · 통과", f"exit={rc}")
        report(d, "android", [("smoke_tabs", True)], one_line=True)
        rc, _, err = run(d)
        check(rc == 2 and "  - smoke_tabs" in err, "한 줄짜리 리포트 · 실패 이름", f"exit={rc}")

        report(d, "android", [])
        rc, _, err = run(d)
        check(rc == 2 and "Flow가 하나도 없습니다" in err, "Flow가 없는 리포트 · 막음", f"exit={rc}")

        clear(d)
        skip(d, "android", '기기 없음 (adb devices 비어 있음) "따옴표" \\역슬래시\n둘째 줄\n')
        rc, out, err = run(d)
        msg = message(out)
        check(rc == 0 and msg and "Android 건너뜀: 기기 없음" in msg and '"따옴표"' in msg and "\\역슬래시" in msg,
              "건너뛴 이유 · 통과 · 이유를 그대로 보여 줌(JSON 이스케이프)", f"exit={rc} {msg}")
        check("둘째 줄" not in (msg or ""), "이유는 첫 줄만")

        skip(d, "android", "  \n")
        rc, _, err = run(d)
        check(rc == 2 and "이유가 비어 있습니다" in err, "빈 이유 · 막음", f"exit={rc}")

        clear(d)
        report(d, "android", [("smoke_tabs", True)], seconds_ago=20)
        skip(d, "android", "서버 장애로 release를 못 돌림", seconds_ago=5)
        rc, out, _ = run(d)
        check(rc == 0 and "건너뜀" in (message(out) or ""), "실패 리포트보다 새 건너뜀 · 건너뜀으로 판정", f"exit={rc}")
        report(d, "android", [("smoke_tabs", False)], seconds_ago=1)
        rc, out, _ = run(d)
        check(rc == 0 and "1개 통과" in (message(out) or ""), "건너뜀보다 새 리포트 · 리포트로 판정", f"exit={rc}")

        clear(d)
        rc, _, err = run(d, STOP_ACTIVE)
        check(rc == 2 and "확인 1/3" in err, "stop_hook_active여도 결과가 없으면 막음", f"exit={rc}")
        rc, _, err = run(d, keep_count=True)
        check(rc == 2 and "확인 2/3" in err, "두 번째 · 막음", f"exit={rc}")
        run(d, keep_count=True)
        rc, out, err = run(d, keep_count=True)
        msg = message(out)
        check(rc == 0 and not err and msg and "결과 없이 끝났습니다" in msg and "3번" in msg and "Android 결과 없음" in msg,
              "세 번 막은 뒤 · 통과시키고 결과 없이 끝났다고 알림", f"exit={rc} {msg}")
        run(d, PROMPT, mode="mark")
        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 다음 턴\n")
        rc, _, err = run(d, keep_count=True)
        check(rc == 2 and "확인 1/3" in err, "다음 턴(mark) · 횟수를 다시 셈", f"exit={rc}")

        rc, out, err = run(d, env_extra={"MAESTRO_E2E_DISABLE_FLOW_REMINDER": "1"})
        check(rc == 0 and not out and not err, "opt-out · 조용", f"exit={rc}")

        print("\n-- 턴 시작 기록 (UserPromptSubmit)")
        d = repo(tmp, "turn", {"app/a/HomeScreen.kt": SCREEN_KT, "app/a/Repo.kt": PLAIN_KT})
        write(d, "app/a/HomeScreen.kt", SCREEN_KT + "// 사용자가 미리 고쳐 둠\n")
        write(d, "app/a/DraftScreen.kt", SCREEN_KT.replace("Home", "Draft"))
        rc, out, err = run(d, PROMPT, mode="mark")
        check(rc == 0 and not out and not err, "mark · exit 0, 출력 없음", f"exit={rc}")
        rc, out, err = run(d)
        check(rc == 0 and not out and not err, "미리 고쳐 둔 화면만 · 질문에 답하고 마칠 때 조용", f"exit={rc}")
        write(d, "app/a/Repo.kt", PLAIN_KT + "// 이번 턴\n")
        rc, out, _ = run(d)
        check(rc == 0 and not out, "이번 턴엔 화면 아닌 파일만 · 조용", f"exit={rc}")
        run(d, PROMPT, mode="mark")
        write(d, "app/a/HomeScreen.kt", SCREEN_KT + "// 이번 턴에 바꿈\n")
        rc, _, err = run(d)
        check(rc == 2 and "HomeScreen.kt" in err, "이번 턴에 화면 수정 · 막음", f"exit={rc}")
        check("DraftScreen.kt" not in err, "턴 전부터 있던 새 파일은 목록에 넣지 않음")
        report(d, "android", [("smoke_tabs", False)])
        rc, out, _ = run(d)
        check(rc == 0 and "통과" in (message(out) or ""), "리포트를 남김 · 통과", f"exit={rc}")
        run(d, PROMPT, mode="mark")
        write(d, "app/a/ProfileScreen.kt", SCREEN_KT.replace("Home", "Profile"), seconds_ago=0)
        rc, _, err = run(d)
        check(rc == 2 and "ProfileScreen.kt" in err and "새로 생긴 화면" in err, "이번 턴의 새 화면 · Flow 판단 물음", f"exit={rc}")
        check("답을 받기 전에는 Flow를 만들지 않습니다" in err, "묻기만 하고 만들지 않게 함")

        print("\n-- 두 플랫폼")
        d = repo(tmp, "both", {"app/a/HomeScreen.kt": SCREEN_KT, "ios/App/HomeView.swift": SCREEN_SWIFT})
        write(d, "app/a/HomeScreen.kt", SCREEN_KT + "// 바꿈\n")
        write(d, "ios/App/HomeView.swift", SCREEN_SWIFT + "// 바꿈\n")
        report(d, "android", [("smoke_tabs", False)])
        rc, _, err = run(d)
        check(rc == 2 and "iOS: 화면을 바꾼 뒤 돌린 결과가 없습니다" in err and "maestro-e2e-ios.xml" in err,
              "Android만 리포트 · iOS 결과를 요구함", f"exit={rc}")
        check("Android: 화면을 바꾼" not in err and "확인됨: Android Flow 1개 통과" in err, "확인된 Android는 다시 요구하지 않음")
        skip(d, "ios", "시뮬레이터 런타임 없음")
        rc, out, _ = run(d)
        msg = message(out) or ""
        check(rc == 0 and "Android Flow 1개 통과" in msg and "iOS 건너뜀: 시뮬레이터 런타임 없음" in msg,
              "iOS는 건너뜀 · 두 결과를 한 줄로", f"exit={rc} {msg}")

        print("\n-- 화면 파일 판정")
        d = repo(tmp, "plain", {"app/src/main/java/a/Repo.kt": PLAIN_KT})
        write(d, "app/src/main/java/a/Repo.kt", PLAIN_KT + "// 바꿈\n")
        rc, out, _ = run(d)
        check(rc == 0 and not out, "화면이 아닌 Kotlin · 조용", f"exit={rc}")

        write(d, "app/src/test/java/a/HomeScreenTest.kt", SCREEN_KT)
        write(d, "app/build/generated/a/Gen.kt", SCREEN_KT)
        rc, out, _ = run(d)
        check(rc == 0 and not out, "테스트·build 경로 · 조용", f"exit={rc}")

        d = repo(tmp, "no-maestro", {"app/src/main/java/a/HomeScreen.kt": SCREEN_KT}, maestro=False)
        write(d, "app/src/main/java/a/HomeScreen.kt", SCREEN_KT + "// 바꿈\n")
        rc, out, _ = run(d)
        check(rc == 0 and not out, ".maestro/ 없는 저장소 · 조용", f"exit={rc}")

        d = repo(tmp, "ios", {"ios/App/Home View.swift": SCREEN_SWIFT})
        write(d, "ios/App/Home View.swift", SCREEN_SWIFT + "// 바꿈\n")
        rc, _, err = run(d)
        check(rc == 2 and "iOS: 화면을 바꾼" in err and "Home View.swift" in err, "SwiftUI 화면(공백 경로) · iOS 결과 요구", f"exit={rc}")
        report(d, "ios", [("smoke_tabs", False)])
        rc, out, _ = run(d)
        check(rc == 0 and "iOS Flow 1개 통과" in (message(out) or ""), "공백 경로 · 리포트로 통과", f"exit={rc}")

        d = repo(tmp, "rename", {"app/a/OldScreen.kt": SCREEN_KT})
        git(d, "mv", "app/a/OldScreen.kt", "app/a/NewScreen.kt")
        age(d / "app/a/NewScreen.kt", OLD)
        rc, _, err = run(d)
        check(rc == 2 and "NewScreen.kt" in err, "이름 바꾼 화면 · 새 경로로 막음", f"exit={rc}")

        d = repo(tmp, "delete", {"app/a/GoneScreen.kt": SCREEN_KT})
        (d / "app/a/GoneScreen.kt").unlink()
        rc, out, _ = run(d)
        check(rc == 0 and not out, "삭제만 · 조용", f"exit={rc}")

        rc, out, _ = run(pathlib.Path(tmp) / "not-a-repo-dir", cwd=tmp)
        check(rc == 0 and not out, "git 저장소 밖 · 조용", f"exit={rc}")

        rc, out, _ = run(d, stdin="")
        check(rc == 0 and not out, "빈 입력 · 조용", f"exit={rc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n실패 없음" if not fails else f"\n실패 {fails}건")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""git-guard 훅 전체 회귀 테스트.

훅을 /bin/bash 로 돌린다. macOS 기본 셸은 아직 bash 3.2이고, 3.2는 set -u 아래에서
빈 배열의 "${a[@]}" 를 unbound variable로 본다. 최신 bash로만 돌리면 이 계열의
버그가 통과해 버린다.

현재 브랜치를 읽어야 하는 케이스(인자 없는 git push)를 위해 임시 저장소 두 개를 만든다.

    python3 test_hooks.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASH = "/bin/bash"
WRAP = 'cd "$3" && cat "$1" | ' + BASH + ' "$2"; echo "STATUS ${PIPESTATUS[0]} ${PIPESTATUS[1]}"'

BLOCK, PASS = "block", "pass"


def run(hook, payload, env_extra=None, cwd=None):
    env = dict(os.environ)
    for var in [k for k in env if k.startswith("GIT_GUARD_")]:
        del env[var]
    env.update(env_extra or {})
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(payload)
        tmp = fh.name
    try:
        proc = subprocess.run(
            [BASH, "-c", WRAP, "_", tmp, os.path.join(HERE, hook), cwd or HERE],
            capture_output=True, text=True, env=env,
        )
    finally:
        os.unlink(tmp)
    lines = proc.stdout.splitlines()
    writer_rc, hook_rc = (int(x) for x in lines[-1].split()[1:3])
    return writer_rc, hook_rc, "\n".join(lines[:-1]), proc.stderr


def cmd(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def make_repo(parent, branch):
    """branch 위에 커밋 하나가 있는 저장소를 만든다."""
    path = os.path.join(parent, branch.replace("/", "_"))
    os.makedirs(path)
    q = {"cwd": path, "capture_output": True, "check": True}
    subprocess.run(["git", "init", "-q", "-b", branch], **q)
    subprocess.run(["git", "config", "user.email", "t@t"], **q)
    subprocess.run(["git", "config", "user.name", "t"], **q)
    open(os.path.join(path, "f"), "w").write("x")
    subprocess.run(["git", "add", "f"], **q)
    subprocess.run(["git", "commit", "-qm", "init"], **q)
    return path


def build_suites(on_main, on_feature):
    return [
        ("protected-branch-guard.sh", "GIT_GUARD_DISABLE_PROTECTED_BRANCH", [
            ("origin main", BLOCK, cmd("git push origin main"), {}, None),
            ("origin master", BLOCK, cmd("git push origin master"), {}, None),
            ("release/1.2", BLOCK, cmd("git push -u origin release/1.2"), {}, None),
            ("HEAD:main", BLOCK, cmd("git push origin HEAD:main"), {}, None),
            ("refs/heads/main", BLOCK, cmd("git push origin refs/heads/main"), {}, None),
            ("+main (force refspec)", BLOCK, cmd("git push origin +main"), {}, None),
            (":main (원격 삭제)", BLOCK, cmd("git push origin :main"), {}, None),
            ("--delete main", BLOCK, cmd("git push --delete origin main"), {}, None),
            ("--all", BLOCK, cmd("git push --all"), {}, None),
            ("compound && push", BLOCK, cmd("git add . && git push origin main"), {}, None),
            ("git -C 경유", BLOCK, cmd("git -C /tmp/x push origin main"), {}, None),
            ("feature 브랜치", PASS, cmd("git push origin feature/x"), {}, None),
            ("-o 값은 refspec 아님", PASS, cmd("git push -o ci.skip origin feature/x"), {}, None),
            ("인자 없음 · main 위", BLOCK, cmd("git push"), {}, on_main),
            ("인자 없음 · feature 위", PASS, cmd("git push"), {}, on_feature),
            ("보호목록 변경 시 통과", PASS, cmd("git push origin main"), {"GIT_GUARD_PROTECTED_BRANCHES": "develop"}, None),
            ("커밋 메시지 오탐", PASS, cmd('git commit -m "git push origin main 은 금지"'), {}, None),
            ("git 아닌 명령", PASS, cmd("./gradlew assembleDebug"), {}, None),
            ("git pull", PASS, cmd("git pull origin main"), {}, None),
        ]),
        ("force-push-guard.sh", "GIT_GUARD_DISABLE_FORCE_PUSH", [
            ("--force", BLOCK, cmd("git push --force origin main"), {}, None),
            ("-f (feature 라도)", BLOCK, cmd("git push -f origin feature/x"), {}, None),
            ("+refspec", BLOCK, cmd("git push origin +feature/x"), {}, None),
            ("--force-with-lease", PASS, cmd("git push --force-with-lease origin feature/x"), {}, None),
            ("--force-if-includes", PASS, cmd("git push --force-if-includes origin feature/x"), {}, None),
            ("평범한 push", PASS, cmd("git push origin feature/x"), {}, None),
            ("인자 없는 push", PASS, cmd("git push"), {}, on_feature),
        ]),
        ("destructive-git-guard.sh", "GIT_GUARD_DISABLE_DESTRUCTIVE", [
            ("reset --hard", BLOCK, cmd("git reset --hard HEAD~1"), {}, None),
            ("reset --soft", PASS, cmd("git reset --soft HEAD~1"), {}, None),
            ("reset (기본)", PASS, cmd("git reset"), {}, None),
            ("clean -fd", BLOCK, cmd("git clean -fd"), {}, None),
            ("clean -xdf", BLOCK, cmd("git clean -xdf"), {}, None),
            ("clean -nd (dry run)", PASS, cmd("git clean -nd"), {}, None),
            ("checkout -- .", BLOCK, cmd("git checkout -- ."), {}, None),
            ("checkout .", BLOCK, cmd("git checkout ."), {}, None),
            ("checkout -f", BLOCK, cmd("git checkout -f main"), {}, None),
            ("checkout 파일 지정", PASS, cmd("git checkout -- src/Foo.kt"), {}, None),
            ("checkout 브랜치 전환", PASS, cmd("git checkout main"), {}, None),
            ("checkout -b", PASS, cmd("git checkout -b feature/x"), {}, None),
            ("restore .", BLOCK, cmd("git restore ."), {}, None),
            ("restore --staged .", PASS, cmd("git restore --staged ."), {}, None),
            ("restore 파일 지정", PASS, cmd("git restore src/Foo.kt"), {}, None),
            ("branch -D", BLOCK, cmd("git branch -D old"), {}, None),
            ("branch -d -f", BLOCK, cmd("git branch -d -f old"), {}, None),
            ("branch -df", BLOCK, cmd("git branch -df old"), {}, None),
            ("branch --delete --force", BLOCK, cmd("git branch --delete --force old"), {}, None),
            ("branch -d", PASS, cmd("git branch -d old"), {}, None),
            ("branch -f (삭제 아님)", PASS, cmd("git branch -f topic main"), {}, None),
            ("stash drop", BLOCK, cmd("git stash drop"), {}, None),
            ("stash clear", BLOCK, cmd("git stash clear"), {}, None),
            ("stash push", PASS, cmd("git stash push -m wip"), {}, None),
            ("stash list", PASS, cmd("git stash list"), {}, None),
            ("gc --prune=now", BLOCK, cmd("git gc --prune=now"), {}, None),
            ("gc", PASS, cmd("git gc"), {}, None),
            ("reflog expire", BLOCK, cmd("git reflog expire --expire=now --all"), {}, None),
            ("reflog 조회", PASS, cmd("git reflog"), {}, None),
            ("커밋 메시지 오탐", PASS, cmd('git commit -m "reset --hard 주의"'), {}, None),
        ]),
    ]


HUGE = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo " + "x" * 200_000}})



def check_deps_hook(prefix):
    """SessionStart 의존성 확인 훅. jq가 없을 때만 말하고, 절대 exit 2를 내지 않는다.

    SessionStart에서 exit 2는 세션 시작 자체를 실패시키므로 그 경계를 고정한다.
    jq 없는 환경은 필요한 실행 파일만 심볼릭 링크한 임시 PATH로 만든다.
    """
    import shutil as _sh
    failures = 0
    print("\n== deps-check.sh (SessionStart)")

    fake = tempfile.mkdtemp(prefix="no-jq-")
    for b in ("basename", "dirname", "grep", "sed", "cat", "git", "env"):
        src = _sh.which(b)
        if src:
            os.symlink(src, os.path.join(fake, b))
    try:
        for label, env_extra, want_msg in (
            ("jq 있음 · 무음", {}, False),
            ("jq 없음 · 경고", {"PATH": fake}, True),
            ("opt-out · 무음", {"PATH": fake, f"{prefix}_DISABLE_DEPS_CHECK": "1"}, False),
        ):
            _, rc, out, _ = run("deps-check.sh", "{}", env_extra)
            said = "플러그인이 동작하지 않습니다" in out
            ok = rc == 0 and said == want_msg
            failures += not ok
            print(f"  {'ok  ' if ok else 'FAIL'} {label:<24} exit={rc} 경고={said} (want 0/{want_msg})")
    finally:
        _sh.rmtree(fake, ignore_errors=True)
    return failures

def main():
    tmp = tempfile.mkdtemp(prefix="git-guard-test-")
    try:
        on_main = make_repo(tmp, "main")
        on_feature = make_repo(tmp, "feature/x")
        failures = 0
        for hook, optout, cases in build_suites(on_main, on_feature):
            print(f"\n== {hook}")
            for label, want, body, env_extra, cwd in cases:
                _, rc, _, _ = run(hook, body, env_extra, cwd)
                ok = (rc == 2) if want is BLOCK else (rc == 0)
                failures += not ok
                print(f"  {'ok  ' if ok else 'FAIL'} {label:<24} exit={rc} (want {'2' if want is BLOCK else '0'})")

            label, _, body, env_extra, cwd = next(c for c in cases if c[1] is BLOCK)
            _, rc, out, err = run(hook, body, {**env_extra, optout: "1"}, cwd)
            ok = rc == 0 and not out.strip() and not err.strip()
            failures += not ok
            print(f"  {'ok  ' if ok else 'FAIL'} {'opt-out 무음':<24} exit={rc} (want 0, 출력 없음)")

            writer_rc, rc, _, _ = run(hook, HUGE, {optout: "1"})
            ok = writer_rc == 0 and rc == 0
            failures += not ok
            print(f"  {'ok  ' if ok else 'FAIL'} {'200KB 파이프 소진':<24} writer={writer_rc} hook={rc} (want 0/0)")

        failures += check_deps_hook('GIT_GUARD')

        print(f"\n{'실패 없음' if not failures else f'실패 {failures}건'}  (bash: {BASH})")
        return 1 if failures else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

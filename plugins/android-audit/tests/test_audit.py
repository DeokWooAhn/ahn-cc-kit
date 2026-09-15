#!/usr/bin/env python3
"""android-audit 회귀 테스트.

/bin/bash 로 돌립니다. macOS 기본 셸이 아직 bash 3.2 이기 때문입니다.

    python3 tests/test_audit.py
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
AUDIT = HERE.parent / "bin" / "android-audit"
BASH = "/bin/bash"

SECRETS = ["SuperSecret_DoNotLeak_123", "AnotherSecret_456", "PlainTextPassword_789"]


def repo(files, tmp, name):
    """파일 목록으로 저장소를 만들고 전부 커밋합니다."""
    d = pathlib.Path(tmp) / name
    d.mkdir(parents=True)
    q = {"cwd": d, "capture_output": True, "check": True}
    subprocess.run(["git", "init", "-q", "-b", "main"], **q)
    subprocess.run(["git", "config", "user.email", "t@t"], **q)
    subprocess.run(["git", "config", "user.name", "t"], **q)
    for rel, body in files.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    subprocess.run(["git", "add", "-A"], **q)
    subprocess.run(["git", "commit", "-qm", "init"], **q)
    return d


def run(d, *args, env_extra=None):
    env = dict(os.environ)
    for k in ("ANDROID_AUDIT_LANG", "LANG", "LC_ALL", "LC_MESSAGES"):
        env.pop(k, None)
    env.update(env_extra or {})
    p = subprocess.run([BASH, str(AUDIT), str(d), *args],
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


GRADLE_MIN = {
    "settings.gradle.kts": 'rootProject.name = "x"\n',
    "gradlew": "#!/bin/sh\n",
}

DIRTY = {
    **GRADLE_MIN,
    # build.gradle.kts 는 목록 앞쪽에서 매치됩니다. grep -q 를 파이프 뒤에 두면
    # git 이 SIGPIPE 로 죽고 pipefail 때문에 Gradle 감지가 통째로 실패합니다.
    "app/build.gradle.kts": (
        'android {\n  signingConfigs {\n    create("release") {\n'
        f'      storePassword = "{SECRETS[0]}"\n      keyPassword = "{SECRETS[1]}"\n'
        "    }\n  }\n}\n"
    ),
    "gradle.properties": f"RELEASE_KEYSTORE_PASSWORD={SECRETS[2]}\n",
    "app/release.jks": "binary\n",
    "app/src/main/AndroidManifest.xml": '<manifest><application android:allowBackup="true"/></manifest>\n',
}

CLEAN = {
    **GRADLE_MIN,
    "app/build.gradle.kts": 'storePassword = System.getenv("RELEASE_STORE_PASSWORD")\n',
    ".gitignore": "local.properties\n*.jks\n*.keystore\n",
    "app/src/main/AndroidManifest.xml": "<manifest><application/></manifest>\n",
}

NOT_GRADLE = {"README.md": "# just a repo\n", "index.js": "console.log(1)\n"}


def big_repo(tmp):
    """파일 목록이 파이프 버퍼(보통 64KB)를 넘는 저장소.

    이 크기가 있어야 grep -q + pipefail 버그가 드러납니다. 작은 저장소는
    git 이 목록을 다 쓰고 끝나므로 SIGPIPE 가 나지 않아 버그가 숨습니다.
    """
    d = pathlib.Path(tmp) / "big"
    d.mkdir(parents=True)
    q = {"cwd": d, "capture_output": True, "check": True}
    subprocess.run(["git", "init", "-q", "-b", "main"], **q)
    # build.gradle.kts 는 목록 앞쪽에서 매치되어 grep 이 일찍 끝납니다.
    (d / "app").mkdir()
    (d / "app" / "build.gradle.kts").write_text("android { }\n")
    filler = d / "src"
    filler.mkdir()
    for i in range(3000):
        (filler / f"module_with_a_reasonably_long_name_{i:05d}.kt").write_text("//\n")
    subprocess.run(["git", "add", "-A"], **q)
    listing = subprocess.run(["git", "ls-files"], cwd=d, capture_output=True, text=True).stdout
    return d, len(listing)


def main():
    tmp = tempfile.mkdtemp(prefix="audit-test-")
    fails = 0

    def check(ok, label, detail=""):
        nonlocal fails
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label}{('  ' + detail) if detail else ''}")

    try:
        print("\n== 문제 있는 저장소")
        d = repo(DIRTY, tmp, "dirty")
        rc, out, err = run(d)
        check(rc == 1, "발견이 있으면 exit 1", f"exit={rc}")
        check("Gradle 프로젝트가 아니어서" not in out,
              "Gradle 프로젝트로 인식", "← grep -q + pipefail 회귀 지점")
        check("app/release.jks" in out, "추적 중인 키스토어를 찾음")
        check("app/build.gradle.kts:4,5" in out, "리터럴 위치를 줄 번호까지 보고")
        check("gradle.properties:1" in out, "properties 리터럴도 보고")
        check("allowBackup" in out, "Manifest 노출 설정 보고")
        leaked = [s for s in SECRETS if s in out or s in err]
        check(not leaked, "시크릿 값을 출력하지 않음", f"유출={leaked}" if leaked else "")

        print("\n== 깨끗한 저장소")
        d = repo(CLEAN, tmp, "clean")
        rc, out, _ = run(d)
        check(rc == 0, "발견이 없으면 exit 0", f"exit={rc}")
        check("발견 없음" in out, "발견 없음으로 보고")

        print("\n== Gradle 프로젝트가 아닌 저장소")
        d = repo(NOT_GRADLE, tmp, "plain")
        rc, out, _ = run(d)
        check(rc == 0, "안드로이드 전용 검사를 건너뜀", f"exit={rc}")
        check("건너뛰었습니다" in out, "건너뛴 사실을 밝힘")

        print("\n== 파일이 많은 저장소 (파이프 버퍼 초과)")
        d, size = big_repo(tmp)
        rc, out, _ = run(d)
        check(size > 100_000, "목록이 파이프 버퍼를 넘음", f"{size:,} bytes")
        check("Gradle 프로젝트가 아니어서" not in out,
              "Gradle 감지가 SIGPIPE 로 실패하지 않음", "← 실제 회귀 지점")

        print("\n== 언어")
        d = repo(DIRTY, tmp, "lang")
        _, ko, _ = run(d, "--lang", "ko")
        _, en, _ = run(d, "--lang", "en")
        check("[높음]" in ko and "[HIGH]" not in ko, "--lang ko 는 한국어만")
        check("[HIGH]" in en and "[높음]" not in en, "--lang en 은 영어만")
        check("finding(s)" in en, "요약도 영어로")
        _, envout, _ = run(d, env_extra={"ANDROID_AUDIT_LANG": "en"})
        check("[HIGH]" in envout, "ANDROID_AUDIT_LANG 로도 전환")
        _, locout, _ = run(d, env_extra={"LANG": "en_US.UTF-8"})
        check("[HIGH]" in locout, "LANG 로케일을 따름")
        _, koloc, _ = run(d, env_extra={"LANG": "ko_KR.UTF-8"})
        check("[높음]" in koloc, "ko 로케일이면 한국어")
        rc, _, err = run(d, "--lang", "fr")
        check(rc == 2 and "unknown language" in err, "모르는 언어는 exit 2", f"exit={rc}")
        leaked = [s for s in SECRETS if s in ko or s in en]
        check(not leaked, "두 언어 모두 값을 출력하지 않음", f"유출={leaked}" if leaked else "")

        print("\n== 사용법")
        rc, _, _ = run(pathlib.Path(tmp) / "does-not-exist")
        check(rc == 2, "없는 경로는 exit 2", f"exit={rc}")
        p = subprocess.run([BASH, str(AUDIT), tmp], capture_output=True, text=True)
        check(p.returncode == 2, "git 저장소가 아니면 exit 2", f"exit={p.returncode}")

        print(f"\n{'실패 없음' if not fails else f'실패 {fails}건'}  (bash: {BASH})")
        return 1 if fails else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

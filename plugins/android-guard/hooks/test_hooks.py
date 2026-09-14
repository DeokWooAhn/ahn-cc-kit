#!/usr/bin/env python3
"""android-guard 훅 전체 회귀 테스트.

훅마다 케이스 표를 두고, 모든 훅에 공통 계약 두 가지를 함께 건다.

  1. opt-out 환경 변수를 켜면 차단 케이스도 통과한다.
  2. 비활성화된 훅도 stdin을 끝까지 읽는다.

(2)가 이 파일의 존재 이유다. opt-out 확인을 stdin 읽기보다 위에 두면, 비활성화된 훅이
페이로드를 다 읽기 전에 종료하면서 하네스가 닫힌 파이프에 쓰게 된다. 그러면 훅을 껐는데
오히려 도구 호출이 실패한다. 200KB 페이로드로 이 위치를 고정한다.
파이프 반대편이 SIGPIPE로 죽는지 보려면 writer가 진짜 셸이어야 한다 —
파이썬 subprocess는 BrokenPipeError를 삼켜서 이 회귀를 놓친다.

    python3 test_hooks.py
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# /bin/bash 로 고정한다. macOS 기본 셸은 아직 bash 3.2이고, 3.2는 set -u 아래에서
# 빈 배열의 "${a[@]}" 를 unbound로 본다. 최신 bash로만 돌리면 그 계열 버그가 통과한다.
BASH = "/bin/bash"
WRAP = 'cat "$1" | ' + BASH + ' "$2"; echo "STATUS ${PIPESTATUS[0]} ${PIPESTATUS[1]}"'

BLOCK, PASS, WARN = "block", "pass", "warn"


def run(hook, payload, env_extra=None, cwd=None):
    """훅을 진짜 파이프 뒤에서 실행한다. (writer_rc, hook_rc, stdout, stderr)."""
    env = dict(os.environ)
    for var in [k for k in env if k.startswith("ANDROID_GUARD_")]:
        del env[var]
    env.update(env_extra or {})
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(payload)
        tmp = fh.name
    try:
        proc = subprocess.run(
            [BASH, "-c", WRAP, "_", tmp, os.path.join(HERE, hook)],
            capture_output=True, text=True, env=env, cwd=cwd or HERE,
        )
    finally:
        os.unlink(tmp)
    lines = proc.stdout.splitlines()
    writer_rc, hook_rc = (int(x) for x in lines[-1].split()[1:3])
    return writer_rc, hook_rc, "\n".join(lines[:-1]), proc.stderr


def payload(tool, tool_input, tool_response=None):
    doc = {"tool_name": tool, "tool_input": tool_input}
    if tool_response is not None:
        doc["tool_response"] = tool_response
    return json.dumps(doc)


# (훅, opt-out 변수, [(라벨, 기대, 페이로드, 추가 env)])
SUITES = [
    ("signing-secrets-guard.sh", "ANDROID_GUARD_DISABLE_SIGNING_SECRETS", [
        ("local.properties 읽기", BLOCK, payload("Read", {"file_path": "local.properties"}), {}),
        ("local.properties grep", BLOCK, payload("Grep", {"pattern": "x", "path": "local.properties"}), {}),
        ("keystore 읽기", BLOCK, payload("Read", {"file_path": "app/release.jks"}), {}),
        ("keystore glob 은 허용", PASS, payload("Glob", {"pattern": "**/*.jks"}), {}),
        ("keystore grep 은 허용", PASS, payload("Grep", {"pattern": "x", "path": "app/release.jks"}), {}),
        ("bash cat 차단", BLOCK, payload("Bash", {"command": "cat local.properties"}), {}),
        ("서비스 계정 json", BLOCK, payload("Read", {"file_path": "ci/play-service-account.json"}), {}),
        ("example 는 허용", PASS, payload("Read", {"file_path": "local.properties.example"}), {}),
        ("local.defaults 는 허용", PASS, payload("Read", {"file_path": "local.defaults.properties"}), {}),
        ("무관한 파일", PASS, payload("Read", {"file_path": "app/build.gradle.kts"}), {}),
        ("무관한 명령", PASS, payload("Bash", {"command": "./gradlew assembleDebug"}), {}),
    ]),
    ("gradle-wrapper-guard.sh", "ANDROID_GUARD_DISABLE_GRADLE_WRAPPER", [
        ("wrapper jar", BLOCK, payload("Write", {"file_path": "gradle/wrapper/gradle-wrapper.jar", "content": "x"}), {}),
        ("gradlew", BLOCK, payload("Edit", {"file_path": "gradlew", "new_string": "x"}), {}),
        ("낯선 distributionUrl", BLOCK, payload("Write", {
            "file_path": "gradle/wrapper/gradle-wrapper.properties",
            "content": "distributionUrl=https\\://evil.example.com/gradle-8.9-bin.zip"}), {}),
        ("평문 http", BLOCK, payload("Write", {
            "file_path": "gradle/wrapper/gradle-wrapper.properties",
            "content": "distributionUrl=http\\://services.gradle.org/distributions/gradle-8.9-bin.zip"}), {}),
        ("정상 distributionUrl", PASS, payload("Write", {
            "file_path": "gradle/wrapper/gradle-wrapper.properties",
            "content": "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.9-bin.zip"}), {}),
        ("무관한 파일", PASS, payload("Write", {"file_path": "app/build.gradle.kts", "content": "x"}), {}),
    ]),
    ("gradle-cache-guard.sh", "ANDROID_GUARD_DISABLE_GRADLE_CACHE", [
        ("홈 캐시 삭제", BLOCK, payload("Bash", {"command": "rm -rf ~/.gradle/caches"}), {}),
        ("GRADLE_USER_HOME 삭제", BLOCK, payload("Bash", {"command": 'rm -rf "$GRADLE_USER_HOME/caches"'}), {}),
        ("프로젝트 build 삭제", PASS, payload("Bash", {"command": "rm -rf app/build"}), {}),
        ("gradlew clean", PASS, payload("Bash", {"command": "./gradlew clean"}), {}),
        ("데몬 정지", PASS, payload("Bash", {"command": "./gradlew --stop"}), {}),
    ]),
    ("signing-literal-guard.sh", "ANDROID_GUARD_DISABLE_SIGNING_LITERAL", [
        ("kts 리터럴", BLOCK, payload("Write", {"file_path": "app/build.gradle.kts", "content": 'storePassword = "hunter2"'}), {}),
        ("groovy 리터럴", BLOCK, payload("Write", {"file_path": "app/build.gradle", "content": "keyPassword 'hunter2'"}), {}),
        ("properties 리터럴", BLOCK, payload("Write", {"file_path": "gradle.properties", "content": "RELEASE_KEYSTORE_PASSWORD=hunter2"}), {}),
        ("getenv", PASS, payload("Write", {"file_path": "app/build.gradle.kts", "content": 'storePassword = System.getenv("RELEASE_KEYSTORE_PASSWORD")'}), {}),
        ("providers", PASS, payload("Write", {"file_path": "app/build.gradle.kts", "content": 'storePassword = providers.environmentVariable("P").orNull'}), {}),
        ("빈 값", PASS, payload("Write", {"file_path": "gradle.properties", "content": "RELEASE_KEYSTORE_PASSWORD="}), {}),
        ("example 면제", PASS, payload("Write", {"file_path": "signing.properties.example", "content": 'storePassword = "changeme"'}), {}),
        ("무관한 파일", PASS, payload("Write", {"file_path": "README.md", "content": 'storePassword = "x"'}), {}),
    ]),
    ("unsigned-release-check.sh", "ANDROID_GUARD_DISABLE_UNSIGNED_RELEASE", [
        ("키 없는 release 빌드", WARN, payload("Bash", {"command": "./gradlew :app:bundleRelease"}, "BUILD SUCCESSFUL in 2m"), {}),
        ("빌드 실패는 조용히", PASS, payload("Bash", {"command": "./gradlew :app:bundleRelease"}, "BUILD FAILED"), {}),
        ("debug 빌드", PASS, payload("Bash", {"command": "./gradlew :app:assembleDebug"}, "BUILD SUCCESSFUL"), {}),
        ("환경 변수로 채워짐", PASS, payload("Bash", {"command": "./gradlew assembleRelease"}, "BUILD SUCCESSFUL"), {
            "RELEASE_KEYSTORE_FILE": "k.jks", "RELEASE_KEYSTORE_PASSWORD": "x",
            "RELEASE_KEY_ALIAS": "a", "RELEASE_KEY_PASSWORD": "x"}),
    ]),
    ("manifest-risk-check.sh", "ANDROID_GUARD_DISABLE_MANIFEST_RISK", [
        ("exported 추가", WARN, payload("Edit", {
            "file_path": "app/src/main/AndroidManifest.xml",
            "new_string": '<activity android:name=".DeepLink" android:exported="true" />'}), {}),
        ("런처는 제외", PASS, payload("Edit", {
            "file_path": "app/src/main/AndroidManifest.xml",
            "new_string": '<activity android:exported="true"><intent-filter><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity>'}), {}),
        ("cleartext", WARN, payload("Write", {
            "file_path": "app/src/main/AndroidManifest.xml",
            "content": '<application android:usesCleartextTraffic="true" />'}), {}),
        ("무관한 파일", PASS, payload("Write", {"file_path": "app/src/main/res/values/strings.xml", "content": 'android:exported="true"'}), {}),
    ]),
]

HUGE = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.kt", "content": "x" * 200_000}})


def main():
    failures = 0
    for hook, optout, cases in SUITES:
        print(f"\n== {hook}")
        for label, want, body, env_extra in cases:
            _, rc, out, _ = run(hook, body, env_extra)
            if want is BLOCK:
                ok = rc == 2
                detail = f"exit={rc} (want 2)"
            elif want is WARN:
                ok = rc == 0 and "additionalContext" in out
                detail = f"exit={rc} warn={'additionalContext' in out} (want 0/True)"
            else:
                ok = rc == 0 and "additionalContext" not in out
                detail = f"exit={rc} quiet={'additionalContext' not in out} (want 0/True)"
            failures += not ok
            print(f"  {'ok  ' if ok else 'FAIL'} {label:<24} {detail}")

        # 계약 1: opt-out을 켜면 차단 케이스도 통과한다.
        blocked = [c for c in cases if c[1] is BLOCK] or [c for c in cases if c[1] is WARN]
        if blocked:
            label, _, body, env_extra = blocked[0]
            _, rc, out, err = run(hook, body, {**env_extra, optout: "1"})
            ok = rc == 0 and not out.strip() and not err.strip()
            failures += not ok
            print(f"  {'ok  ' if ok else 'FAIL'} {'opt-out 무음':<24} exit={rc} (want 0, 출력 없음)")

        # 계약 2: 비활성화된 훅도 200KB를 끝까지 읽는다.
        writer_rc, rc, _, _ = run(hook, HUGE, {optout: "1"})
        ok = writer_rc == 0 and rc == 0
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {'200KB 파이프 소진':<24} writer={writer_rc} hook={rc} (want 0/0)")

    print(f"\n{'실패 없음' if not failures else f'실패 {failures}건'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

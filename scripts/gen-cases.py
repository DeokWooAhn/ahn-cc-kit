#!/usr/bin/env python3
"""훅 테스트의 케이스 표를 docs/cases.json 으로 뽑습니다.

사이트의 "무엇이 막히나" 표를 손으로 적으면 훅을 고칠 때마다 낡습니다.
테스트가 실제 동작을 고정하고 있으므로 거기서 그대로 가져옵니다.

    python3 scripts/gen-cases.py
"""

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(path):
    spec = importlib.util.spec_from_file_location(f"m{abs(hash(path))}", path)
    m = importlib.util.module_from_spec(spec)
    sys.argv = ["gen"]
    spec.loader.exec_module(m)
    return m


def display(payload):
    """케이스를 언어 중립적으로 보여줄 문자열. 명령이 있으면 명령, 없으면 도구 + 경로 + 내용 일부."""
    d = json.loads(payload)
    ti = d.get("tool_input", {})
    if ti.get("command"):
        return ti["command"]

    target = ti.get("file_path") or ti.get("path") or ti.get("pattern") or ""
    s = f'{d["tool_name"]}  {target}'.rstrip()

    # 같은 파일을 다른 내용으로 쓰는 케이스들이 있어 구분되는 한 줄을 덧붙입니다.
    body = ti.get("content") or ti.get("new_string") or ""
    line = next((l.strip() for l in body.split("\n") if l.strip()), "")
    if line and len(line) > 1:
        if len(line) > 58:
            line = line[:55] + "…"
        s += f"   ⟨{line}⟩"
    return s


def env_note(env):
    """판정을 가르는 것이 환경 변수인 케이스가 있습니다. 이름만 보여 주고 값은 버립니다."""
    keys = [k for k in (env or {}) if k not in ("PATH",)]
    return ", ".join(sorted(keys)) if keys else ""


def collect(suites, plugin):
    out = []
    for hook, optout, cases in suites:
        rows = []
        for case in cases:
            label, want, payload = case[0], case[1], case[2]
            env = case[3] if len(case) > 3 else {}
            # 인자 없는 git push 는 현재 브랜치로 판정이 갈립니다. 그 조건을 보여 줍니다.
            cwd = case[4] if len(case) > 4 else None
            branch = ""
            if cwd:
                branch = "main" if cwd.endswith("main") else "feature/x"
            rows.append({
                "cmd": display(payload),
                "verdict": want,
                "note": label,
                "env": env_note(env),
                "branch": branch,
            })
        out.append({"plugin": plugin, "hook": hook.replace(".sh", ""),
                    "optout": optout, "cases": rows})
    return out


ag = load(ROOT / "plugins/android-guard/hooks/test_hooks.py")
gg = load(ROOT / "plugins/git-guard/hooks/test_hooks.py")

data = collect(ag.SUITES, "android-guard")
data += collect(gg.build_suites("/repo-on-main", "/repo-on-feature"), "git-guard")

total = sum(len(g["cases"]) for g in data)
out = ROOT / "docs/cases.json"
out.write_text(json.dumps({"groups": data, "total": total}, ensure_ascii=False, indent=2) + "\n")
print(f"{out.relative_to(ROOT)} — 훅 {len(data)}개, 케이스 {total}건")

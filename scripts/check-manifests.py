#!/usr/bin/env python3
"""매니페스트와 문서 숫자가 서로 맞는지 봅니다. CI에서 돌고, 로컬에서도 그대로 돌립니다.

    python3 scripts/check-manifests.py

- 모든 JSON(마켓플레이스, plugin.json, hooks.json)이 파싱되는가
- 마켓플레이스 목록과 plugins/ 폴더가 일치하는가
- 마켓플레이스의 name·version이 각 plugin.json과 같은가
- README에 적은 사례 수가 docs/cases.json의 total과 같은가

버전은 사람이 두 곳에 손으로 적습니다. 한쪽만 올리면 설치된 쪽이 업데이트를 받지 못하거나,
마켓플레이스와 실제 플러그인이 다른 버전을 말하게 됩니다.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
errors = []


def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"{path.relative_to(ROOT)}: JSON을 읽지 못했습니다 ({e})")
        return None


market = load(ROOT / ".claude-plugin" / "marketplace.json") or {}
listed = {p["name"]: p for p in market.get("plugins", [])}
on_disk = {p.name for p in (ROOT / "plugins").iterdir() if (p / ".claude-plugin" / "plugin.json").exists()}

for name in sorted(on_disk - listed.keys()):
    errors.append(f"plugins/{name}: 마켓플레이스에 없습니다")
for name in sorted(listed.keys() - on_disk):
    errors.append(f"marketplace.json: '{name}'의 plugins/{name}/.claude-plugin/plugin.json 이 없습니다")

for name in sorted(listed.keys() & on_disk):
    entry = listed[name]
    manifest = load(ROOT / "plugins" / name / ".claude-plugin" / "plugin.json")
    if manifest is None:
        continue
    if manifest.get("name") != name:
        errors.append(f"plugins/{name}/plugin.json: name이 '{manifest.get('name')}'입니다")
    if entry.get("source") != name:
        errors.append(f"marketplace.json: '{name}'의 source가 '{entry.get('source')}'입니다")
    if manifest.get("version") != entry.get("version"):
        errors.append(
            f"{name}: 버전이 다릅니다 — marketplace.json {entry.get('version')}, "
            f"plugin.json {manifest.get('version')}"
        )
    hooks = ROOT / "plugins" / name / "hooks" / "hooks.json"
    if hooks.exists():
        load(hooks)

cases = load(ROOT / "docs" / "cases.json") or {}
readme = (ROOT / "README.md").read_text()
m = re.search(r"통과하는지 (\d+)건을", readme)
if not m:
    errors.append("README.md: 사례 수 문장('…통과하는지 N건을')을 찾지 못했습니다")
elif int(m.group(1)) != cases.get("total"):
    errors.append(f"README.md: 사례 수가 {m.group(1)}건인데 docs/cases.json은 {cases.get('total')}건입니다")

for e in errors:
    print(f"FAIL {e}")
print("매니페스트·문서 일치" if not errors else f"실패 {len(errors)}건")
sys.exit(1 if errors else 0)

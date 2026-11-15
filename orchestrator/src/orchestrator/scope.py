from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PlanFormatError, SnapshotFileError
from .gitio import changed_paths, ensure_repository

SNAPSHOT_VERSION = 1
DIGEST_ALGORITHM = "sha256"
MISSING = "MISSING"

ALLOWED_SECTION = re.compile(r"^##\s+건드릴 파일\s*$")
FENCE = re.compile(r"^\s*```")
TRAILING_NOTE = re.compile(r"\s*\(.*\)\s*$")


def digest_file(path: Path) -> str:
    try:
        with open(path, "rb") as handle:
            return hashlib.file_digest(handle, DIGEST_ALGORITHM).hexdigest()
    except (OSError, IsADirectoryError):
        return MISSING


def normalize_ignore(ignore: Iterable[str]) -> tuple[str, ...]:
    cleaned = {entry.strip().strip("/") for entry in ignore}
    return tuple(sorted(entry for entry in cleaned if entry))


def is_ignored(path: str, ignore: Iterable[str]) -> bool:
    return any(path == entry or path.startswith(entry + "/") for entry in ignore)


@dataclass(frozen=True)
class Snapshot:
    files: dict[str, str] = field(default_factory=dict)
    ignore: tuple[str, ...] = ()


def snapshot(repo: Path, *, ignore: Iterable[str] = ()) -> Snapshot:
    root = ensure_repository(repo)
    ignored = normalize_ignore(ignore)
    paths = sorted({path for path in changed_paths(root) if not is_ignored(path, ignored)})
    return Snapshot(files={path: digest_file(root / path) for path in paths}, ignore=ignored)


def write_snapshot(repo: Path, out: Path, *, ignore: Iterable[str] = ()) -> Snapshot:
    root = ensure_repository(repo)
    out = Path(out)
    entries = list(ignore)
    inside = _relative_to_repository(root, out.parent)
    if inside is not None:
        entries.append(inside)
    taken = snapshot(root, ignore=entries)
    payload = {
        "schema_version": SNAPSHOT_VERSION,
        "algorithm": DIGEST_ALGORITHM,
        "ignore": list(taken.ignore),
        "files": taken.files,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=out.parent,
        prefix=out.name + ".",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle as tmp:
            tmp.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(handle.name, out)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return taken


def read_snapshot(path: Path) -> Snapshot:
    path = Path(path)
    if not path.is_file():
        raise SnapshotFileError(f"스냅샷이 없다: {path} — 구현을 넘기기 전에 찍어야 한다")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SnapshotFileError(f"스냅샷이 깨졌다: {path} ({exc})") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SNAPSHOT_VERSION:
        raise SnapshotFileError(f"스냅샷 스키마 버전이 다르다: {path}")
    if data.get("algorithm") != DIGEST_ALGORITHM:
        raise SnapshotFileError(
            f"스냅샷 해시 알고리즘이 다르다: {data.get('algorithm')!r} (이 런타임은 {DIGEST_ALGORITHM})"
        )
    files = data.get("files")
    if not isinstance(files, dict):
        raise SnapshotFileError(f"스냅샷에 files가 없다: {path}")
    return Snapshot(
        files={str(key): str(value) for key, value in files.items()},
        ignore=normalize_ignore(data.get("ignore", [])),
    )


def parse_allowed(plan: Path) -> frozenset[str]:
    plan = Path(plan)
    if not plan.is_file():
        raise PlanFormatError(f"계획 파일이 없다: {plan}")
    allowed: list[str] = []
    in_section = False
    in_block = False
    closed = False
    for line in plan.read_text(encoding="utf-8").splitlines():
        if ALLOWED_SECTION.match(line):
            in_section = True
            continue
        if not in_section or closed:
            continue
        if FENCE.match(line):
            if in_block:
                closed = True
                continue
            in_block = True
            continue
        if in_block:
            entry = TRAILING_NOTE.sub("", line).strip()
            if entry:
                allowed.append(entry)
    if not allowed:
        raise PlanFormatError(
            f"계획에서 허용 파일 목록을 못 읽었다: {plan}\n"
            '"## 건드릴 파일" 제목 아래 코드 블록에 경로를 한 줄에 하나씩 적어야 한다'
        )
    return frozenset(allowed)


@dataclass(frozen=True)
class ScopeResult:
    allowed: frozenset[str]
    changed: frozenset[str]
    violations: frozenset[str]

    @property
    def nothing_changed(self) -> bool:
        return not self.changed

    @property
    def ok(self) -> bool:
        return not self.violations and not self.nothing_changed


def compare(repo: Path, before: Snapshot) -> frozenset[str]:
    after = snapshot(repo, ignore=before.ignore)
    changed = {path for path, digest in after.files.items() if before.files.get(path) != digest}
    changed |= {
        path
        for path, digest in before.files.items()
        if after.files.get(path, MISSING) != digest
    }
    return frozenset(changed)


def check(repo: Path, plan: Path, snapshot_path: Path) -> ScopeResult:
    allowed = parse_allowed(plan)
    before = read_snapshot(snapshot_path)
    changed = compare(repo, before)
    return ScopeResult(
        allowed=allowed,
        changed=changed,
        violations=frozenset(changed - allowed),
    )


def _relative_to_repository(root: Path, target: Path) -> str | None:
    try:
        relative = target.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    text = str(relative)
    return None if text == "." else text

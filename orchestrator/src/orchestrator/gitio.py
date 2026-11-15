from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import GitCommandFailed, NotAGitRepository

GIT_TIMEOUT_SECONDS = 30


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if check and result.returncode != 0:
        raise GitCommandFailed(args, result.returncode, result.stderr)
    return result


def ensure_repository(repo: Path) -> Path:
    repo = Path(repo)
    if not repo.is_dir():
        raise NotAGitRepository(repo)
    result = run_git(repo, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        raise NotAGitRepository(repo)
    return Path(result.stdout.strip())


def changed_paths(repo: Path) -> list[str]:
    result = run_git(repo, "status", "--porcelain", "-z", "--untracked-files=all")
    return _parse_status_z(result.stdout)


def _parse_status_z(raw: str) -> list[str]:
    entries = raw.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status = entry[:2]
        paths.append(entry[3:])
        if "R" in status or "C" in status:
            if index < len(entries) and entries[index]:
                paths.append(entries[index])
            index += 1
    return paths


def head_commit(repo: Path) -> str:
    result = run_git(repo, "rev-parse", "HEAD", check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def current_branch(repo: Path) -> str | None:
    result = run_git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def upstream_commit(repo: Path) -> str | None:
    result = run_git(repo, "rev-parse", "--verify", "--quiet", "@{upstream}", check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def staged_paths(repo: Path) -> list[str]:
    result = run_git(repo, "diff", "--cached", "--name-only", "-z", check=False)
    if result.returncode != 0:
        return []
    return [path for path in result.stdout.split("\0") if path]

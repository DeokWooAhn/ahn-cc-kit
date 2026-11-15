from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .gitio import current_branch, ensure_repository, head_commit, staged_paths, upstream_commit

COMMIT = "commit"
BRANCH = "branch"
STAGED = "staged"
PUSH = "push"


@dataclass(frozen=True)
class GitSnapshot:
    head: str
    branch: str | None
    upstream: str | None
    staged: tuple[str, ...]

    def to_json_object(self) -> dict:
        return {
            "head": self.head,
            "branch": self.branch,
            "upstream": self.upstream,
            "staged": list(self.staged),
        }

    @classmethod
    def from_json_object(cls, data: dict) -> GitSnapshot:
        return cls(
            head=data.get("head", ""),
            branch=data.get("branch"),
            upstream=data.get("upstream"),
            staged=tuple(data.get("staged", [])),
        )


@dataclass(frozen=True)
class GitViolation:
    kind: str
    detail: str


def capture(repo: Path) -> GitSnapshot:
    root = ensure_repository(repo)
    return GitSnapshot(
        head=head_commit(root),
        branch=current_branch(root),
        upstream=upstream_commit(root),
        staged=tuple(sorted(staged_paths(root))),
    )


def compare(before: GitSnapshot, after: GitSnapshot) -> tuple[GitViolation, ...]:
    violations: list[GitViolation] = []

    if before.head != after.head:
        violations.append(
            GitViolation(COMMIT, f"HEAD가 바뀌었다: {_short(before.head)} → {_short(after.head)}")
        )

    if before.branch != after.branch:
        violations.append(
            GitViolation(BRANCH, f"브랜치가 바뀌었다: {_name(before.branch)} → {_name(after.branch)}")
        )

    new_staged = tuple(path for path in after.staged if path not in set(before.staged))
    if new_staged:
        violations.append(
            GitViolation(STAGED, "스테이징된 파일이 생겼다: " + ", ".join(new_staged))
        )

    if before.upstream != after.upstream:
        violations.append(
            GitViolation(
                PUSH,
                f"업스트림이 바뀌었다: {_short(before.upstream)} → {_short(after.upstream)}",
            )
        )

    return tuple(violations)


def check(repo: Path, before: GitSnapshot) -> tuple[GitViolation, ...]:
    return compare(before, capture(repo))


def _short(commit: str | None) -> str:
    if not commit:
        return "(없음)"
    return commit[:12]


def _name(branch: str | None) -> str:
    if not branch:
        return "(detached)"
    return branch

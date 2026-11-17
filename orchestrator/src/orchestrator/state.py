from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from .errors import InvalidTransition, StateFileError

SCHEMA_VERSION = 1


class RunState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    PLAN_APPROVAL = "plan_approval"
    IMPLEMENTING = "implementing"
    SCOPE_CHECK = "scope_check"
    REVIEWING = "reviewing"
    FIX_PLANNING = "fix_planning"
    FIXING = "fixing"
    VERIFYING = "verifying"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    BLOCKED_SCOPE = "blocked_scope"
    BLOCKED_GIT = "blocked_git"
    BLOCKED_POLICY = "blocked_policy"
    BLOCKED_PLAN = "blocked_plan"
    FAILED_AGENT = "failed_agent"
    FAILED_VERIFY = "failed_verify"
    MAX_RETRY_EXCEEDED = "max_retry_exceeded"


BLOCKED_STATES = frozenset(
    {
        RunState.BLOCKED_SCOPE,
        RunState.BLOCKED_GIT,
        RunState.BLOCKED_POLICY,
        RunState.BLOCKED_PLAN,
        RunState.FAILED_AGENT,
        RunState.FAILED_VERIFY,
        RunState.MAX_RETRY_EXCEEDED,
    }
)

HUMAN_STATES = frozenset({RunState.PLAN_APPROVAL, RunState.WAITING_HUMAN})

TERMINAL_STATES = frozenset({RunState.COMPLETED})


def is_blocked(state: RunState) -> bool:
    return state in BLOCKED_STATES


def needs_human(state: RunState) -> bool:
    return state in HUMAN_STATES


def is_terminal(state: RunState) -> bool:
    return state in TERMINAL_STATES


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TransitionRecord:
    at: str
    previous: str
    current: str
    note: str = ""


@dataclass
class TaskState:
    task_id: str
    state: RunState = RunState.CREATED
    created_at: str = field(default_factory=now_text)
    updated_at: str = field(default_factory=now_text)
    retry_count: int = 0
    artifacts: dict[str, str] = field(default_factory=dict)
    history: list[TransitionRecord] = field(default_factory=list)
    note: str = ""

    def to_json_object(self) -> dict:
        data = asdict(self)
        data["state"] = str(self.state)
        data["schema_version"] = SCHEMA_VERSION
        return data

    @classmethod
    def from_json_object(cls, data: dict) -> TaskState:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise StateFileError(
                f"상태 파일 스키마 버전이 다르다: {version!r} (이 런타임은 {SCHEMA_VERSION})"
            )
        missing = {"task_id", "state"} - data.keys()
        if missing:
            raise StateFileError(f"상태 파일에 빠진 항목: {', '.join(sorted(missing))}")
        try:
            state = RunState(data["state"])
        except ValueError as exc:
            raise StateFileError(f"모르는 상태: {data['state']!r}") from exc
        history = [TransitionRecord(**record) for record in data.get("history", [])]
        return cls(
            task_id=data["task_id"],
            state=state,
            created_at=data.get("created_at", now_text()),
            updated_at=data.get("updated_at", now_text()),
            retry_count=data.get("retry_count", 0),
            artifacts=dict(data.get("artifacts", {})),
            history=history,
            note=data.get("note", ""),
        )


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    def create(self, task_id: str, *, overwrite: bool = False) -> TaskState:
        if self.exists() and not overwrite:
            raise StateFileError(f"상태 파일이 이미 있다: {self.path}")
        state = TaskState(task_id=task_id)
        self.save(state)
        return state

    def load(self) -> TaskState:
        if not self.exists():
            raise StateFileError(f"상태 파일이 없다: {self.path}")
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateFileError(f"상태 파일을 읽지 못했다: {self.path} ({exc})") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StateFileError(f"상태 파일이 깨졌다: {self.path} ({exc})") from exc
        if not isinstance(data, dict):
            raise StateFileError(f"상태 파일이 객체가 아니다: {self.path}")
        return TaskState.from_json_object(data)

    def save(self, state: TaskState) -> None:
        state.updated_at = now_text()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.to_json_object(), ensure_ascii=False, indent=2) + "\n"
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=self.path.name + ".",
            suffix=".tmp",
            delete=False,
        )
        try:
            with handle as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(handle.name, self.path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise

    def transition(self, target: RunState, *, note: str = "") -> TaskState:
        state = self.load()
        if is_terminal(state.state):
            raise InvalidTransition(state.state, target)
        record = TransitionRecord(
            at=now_text(),
            previous=str(state.state),
            current=str(target),
            note=note,
        )
        state.history.append(record)
        state.state = target
        state.note = note
        self.save(state)
        return state

    def record_artifact(self, key: str, path: str | Path) -> TaskState:
        state = self.load()
        state.artifacts[key] = str(path)
        self.save(state)
        return state

    def bump_retry(self, *, limit: int) -> TaskState:
        state = self.load()
        state.retry_count += 1
        if state.retry_count > limit:
            state.state = RunState.MAX_RETRY_EXCEEDED
            state.note = f"재시도 {limit}회를 넘겼다"
        self.save(state)
        return state

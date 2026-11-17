from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import PromptFileError, UnknownAdapter

PLANNER = "planner"
IMPLEMENTER = "implementer"
REVIEWER = "reviewer"
FIXER = "fixer"

ROLE_TIMEOUT_SECONDS = {
    PLANNER: 900,
    IMPLEMENTER: 1200,
    REVIEWER: 600,
    FIXER: 1200,
}
FALLBACK_TIMEOUT_SECONDS = 900
DEFAULT_STALL_SECONDS = 180

POLL_SECONDS = 0.2
TERM_GRACE_SECONDS = 5.0

OK = "ok"
FAILED = "failed"
TIMEOUT = "timeout"
STALLED = "stalled"
MISSING_COMMAND = "missing_command"

READ_ONLY_CLAUDE_TOOLS = (
    "Read",
    "Glob",
    "Grep",
    "Bash(git diff:*)",
    "Bash(git status:*)",
    "Bash(git log:*)",
)
WRITE_CLAUDE_TOOLS = ("Read", "Glob", "Grep", "Write", "Edit", "Bash")


def default_timeout_seconds(role: str) -> int:
    return ROLE_TIMEOUT_SECONDS.get(role, FALLBACK_TIMEOUT_SECONDS)


@dataclass(frozen=True)
class AgentRequest:
    role: str
    prompt_file: Path
    log_file: Path
    cwd: Path
    timeout_seconds: int | None = None
    stall_seconds: int | None = None
    read_only: bool = False
    model: str | None = None

    @property
    def timeout(self) -> int:
        if self.timeout_seconds is None:
            return default_timeout_seconds(self.role)
        return self.timeout_seconds

    @property
    def stall(self) -> int:
        if self.stall_seconds is None:
            return DEFAULT_STALL_SECONDS
        return self.stall_seconds


@dataclass(frozen=True)
class AgentResult:
    role: str
    command: tuple[str, ...]
    outcome: str
    returncode: int | None
    duration_seconds: float
    log_file: Path
    log_bytes: int
    detail: str

    @property
    def ok(self) -> bool:
        return self.outcome == OK

    def to_json_object(self) -> dict:
        return {
            "role": self.role,
            "command": list(self.command),
            "outcome": self.outcome,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration_seconds, 3),
            "log_file": str(self.log_file),
            "log_bytes": self.log_bytes,
            "detail": self.detail,
        }


def read_prompt(path: Path) -> str:
    path = Path(path)
    if not path.is_file():
        raise PromptFileError(f"프롬프트 파일이 없다: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise PromptFileError(f"프롬프트 파일이 비어 있다: {path}")
    return text


def run_command(
    command: list[str], request: AgentRequest, *, watch_stall: bool = True
) -> AgentResult:
    log_file = Path(request.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    try:
        with log_file.open("wb") as log:
            process = subprocess.Popen(
                command,
                cwd=str(request.cwd),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                outcome, detail = _watch(
                    process, log_file, request, started, watch_stall=watch_stall
                )
            except BaseException:
                _terminate(process)
                raise
    except FileNotFoundError:
        return _result(
            request,
            command,
            MISSING_COMMAND,
            None,
            time.monotonic() - started,
            log_file,
            f"명령을 찾지 못했다: {command[0]}",
        )

    returncode = process.returncode
    if outcome == OK and returncode != 0:
        outcome = FAILED
        detail = f"종료 코드 {returncode}"

    return _result(
        request,
        command,
        outcome,
        returncode,
        time.monotonic() - started,
        log_file,
        detail,
    )


class Adapter:
    name = ""

    # 출력이 도는 동안 흘러나오는가. False 면 무활동 감지를 쓰지 않는다.
    # 끝에 한 번에 뱉는 도구는 "로그가 자란다"는 신호 자체가 없어서,
    # 신호가 없는 것을 멈춤으로 읽는다. 그런 도구는 전체 제한 시간에 맡긴다.
    streams_output = True

    def build_command(self, request: AgentRequest, prompt: str) -> list[str]:
        raise NotImplementedError

    def run(self, request: AgentRequest) -> AgentResult:
        prompt = read_prompt(request.prompt_file)
        return run_command(
            self.build_command(request, prompt), request, watch_stall=self.streams_output
        )


@dataclass(frozen=True)
class CodexAdapter(Adapter):
    executable: str = "codex"

    name = "codex"

    def build_command(self, request: AgentRequest, prompt: str) -> list[str]:
        sandbox = "read-only" if request.read_only else "workspace-write"
        command = [self.executable, "exec", "-s", sandbox]
        if request.model:
            command.extend(["-m", request.model])
        command.append(prompt)
        return command


@dataclass(frozen=True)
class ClaudeAdapter(Adapter):
    executable: str = "claude"

    name = "claude"
    # claude -p 는 끝날 때 한 번에 출력한다. 2026-11-17 CalcMoney 작업에서
    # 180초를 넘긴 리뷰가 stalled 로 끊겼다.
    streams_output = False

    def build_command(self, request: AgentRequest, prompt: str) -> list[str]:
        command = [self.executable, "-p", prompt]
        if request.model:
            command.extend(["--model", request.model])
        command.append("--allowed-tools")
        command.extend(READ_ONLY_CLAUDE_TOOLS if request.read_only else WRITE_CLAUDE_TOOLS)
        return command


def adapter_for(name: str) -> Adapter:
    if name == CodexAdapter.name:
        return CodexAdapter()
    if name == ClaudeAdapter.name:
        return ClaudeAdapter()
    raise UnknownAdapter(name)


def _watch(
    process: subprocess.Popen,
    log_file: Path,
    request: AgentRequest,
    started: float,
    *,
    watch_stall: bool = True,
) -> tuple[str, str]:
    timeout = request.timeout
    stall = request.stall if watch_stall else 0
    last_size = -1
    last_growth = started

    while True:
        if process.poll() is not None:
            return OK, ""

        now = time.monotonic()
        if timeout > 0 and now - started >= timeout:
            _terminate(process)
            return TIMEOUT, f"{timeout}초 안에 끝나지 않았다"

        size = _size(log_file)
        if size != last_size:
            last_size = size
            last_growth = now
        elif stall > 0 and now - last_growth >= stall:
            _terminate(process)
            return STALLED, f"로그가 {stall}초 동안 자라지 않았다"

        time.sleep(POLL_SECONDS)


def _terminate(process: subprocess.Popen) -> None:
    _signal_group(process, signal.SIGTERM)
    if _reaped(process):
        return
    _signal_group(process, signal.SIGKILL)
    _reaped(process)


def _signal_group(process: subprocess.Popen, number: int) -> None:
    group = _group_of(process)
    if group is not None and group != os.getpgrp():
        try:
            os.killpg(group, number)
            return
        except OSError:
            pass
    try:
        process.send_signal(number)
    except OSError:
        pass


def _group_of(process: subprocess.Popen) -> int | None:
    try:
        return os.getpgid(process.pid)
    except OSError:
        return None


def _reaped(process: subprocess.Popen) -> bool:
    try:
        process.wait(timeout=TERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return False
    return True


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _result(
    request: AgentRequest,
    command: list[str],
    outcome: str,
    returncode: int | None,
    duration: float,
    log_file: Path,
    detail: str,
) -> AgentResult:
    return AgentResult(
        role=request.role,
        command=tuple(command),
        outcome=outcome,
        returncode=returncode,
        duration_seconds=duration,
        log_file=log_file,
        log_bytes=_size(log_file),
        detail=detail,
    )

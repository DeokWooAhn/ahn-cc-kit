from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import ledger
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

# 재시도 때 올려 잡을 추론 강도. 두 CLI 가 같은 등급 이름을 받는다 —
# claude --effort 는 low·medium·high·xhigh·max 를, codex 의
# model_reasoning_effort 는 none·minimal·low·medium·high·xhigh·max 를 받는다.
#
# 바닥이 아니라 기본값 "위"에서 시작해야 한다. 2026-11-20 에 기록을 세어 보니
# 사다리가 제자리걸음이었다 — codex 는 config.toml 이 이미 high 였고,
# claude 는 기본 모델이 이미 오푸스라 --model opus 가 같은 자리였다.
# high 는 흔한 기본값이라 사다리의 칸이 될 수 없다.
EFFORT_LADDER = ("xhigh", "max")


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
    attempt: int = 0
    # 이 호출에만 더할 환경 변수. 지금 환경 위에 얹는다.
    env: dict[str, str] = field(default_factory=dict)

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


def log_header(command: list[str], request: AgentRequest, prompt: str | None) -> str:
    """무엇이 어떤 강도로 돌았는지 로그 첫 줄에 남긴다.

    codex 는 자기 배너에 모델과 강도를 찍지만 claude 는 아무것도 안 남긴다.
    그래서 끝난 뒤에는 로그만 보고 어느 도구가 돌았는지 가릴 수 없었다.
    프롬프트는 통째로 들어 있어 길므로 파일 이름으로 바꿔 적는다.
    """
    shown = [
        f"@{Path(request.prompt_file).name}" if prompt is not None and arg == prompt else arg
        for arg in command
    ]
    attempt = "첫 시도" if request.attempt <= 0 else f"재시도 {request.attempt}"
    return (
        f"# orch {request.role} · {attempt}\n"
        f"# {shlex.join(shown)}\n"
        "# ---\n"
    )


def run_command(
    command: list[str],
    request: AgentRequest,
    *,
    watch_stall: bool = True,
    prompt: str | None = None,
    effort: str | None = None,
) -> AgentResult:
    log_file = Path(request.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    try:
        with log_file.open("wb") as log:
            # 에이전트 호출에만 머리말을 단다. 검증 로그는 그대로 리뷰 브리프에
            # 실려서, 사람이 쓴 명령의 출력에 우리 줄을 섞으면 안 된다.
            # 자식이 이어 쓰게 먼저 밀어낸다. flush 를 빠뜨리면 순서가 섞인다.
            if prompt is not None:
                log.write(log_header(command, request, prompt).encode("utf-8"))
                log.flush()
            process = subprocess.Popen(
                command,
                cwd=str(request.cwd),
                env={**os.environ, **request.env} if request.env else None,
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
        return _recorded(
            _result(
                request,
                command,
                MISSING_COMMAND,
                None,
                time.monotonic() - started,
                log_file,
                f"명령을 찾지 못했다: {command[0]}",
            ),
            request,
            command,
            prompt=prompt,
            effort=effort,
        )

    returncode = process.returncode
    if outcome == OK and returncode != 0:
        outcome = FAILED
        detail = f"종료 코드 {returncode}"

    return _recorded(
        _result(
            request,
            command,
            outcome,
            returncode,
            time.monotonic() - started,
            log_file,
            detail,
        ),
        request,
        command,
        prompt=prompt,
        effort=effort,
    )


def _recorded(
    result: AgentResult,
    request: AgentRequest,
    command: list[str],
    *,
    prompt: str | None,
    effort: str | None,
) -> AgentResult:
    """장부에 한 줄 남기고 결과를 그대로 돌려준다."""
    task_dir = Path(request.log_file).parent
    ledger.record(
        task_dir,
        ledger.Call(
            at=ledger.now(),
            task_id=task_dir.name,
            role=request.role,
            kind=ledger.AGENT if prompt is not None else ledger.VERIFY,
            tool=Path(command[0]).name if command else "",
            effort=effort,
            attempt=request.attempt,
            outcome=result.outcome,
            seconds=round(result.duration_seconds, 1),
            log_bytes=result.log_bytes,
        ),
    )
    return result


class Adapter:
    name = ""

    # 출력이 도는 동안 흘러나오는가. False 면 무활동 감지를 쓰지 않는다.
    # 끝에 한 번에 뱉는 도구는 "로그가 자란다"는 신호 자체가 없어서,
    # 신호가 없는 것을 멈춤으로 읽는다. 그런 도구는 전체 제한 시간에 맡긴다.
    streams_output = True

    # 재시도 때 올려 잡을 추론 강도. 첫 시도는 비워 두어 도구의 기본 설정을 그대로 쓴다.
    # 판본 이름이 아니라 등급만 적어서, 모델이 새로 나와도 이 줄은 그대로 둔다.
    # 모델은 사람이 `--model` 로 고른다. 사다리는 강도만 건드린다.
    ladder: tuple[str, ...] = ()

    def rung(self, attempt: int) -> str | None:
        if attempt <= 0 or not self.ladder:
            return None
        return self.ladder[min(attempt - 1, len(self.ladder) - 1)]

    def build_command(self, request: AgentRequest, prompt: str) -> list[str]:
        raise NotImplementedError

    def run(self, request: AgentRequest) -> AgentResult:
        prompt = read_prompt(request.prompt_file)
        return run_command(
            self.build_command(request, prompt),
            request,
            watch_stall=self.streams_output,
            prompt=prompt,
            effort=self.rung(request.attempt),
        )


@dataclass(frozen=True)
class CodexAdapter(Adapter):
    executable: str = "codex"

    name = "codex"
    # codex 의 -m 은 판본 이름만 받아 별칭이 없다. 모델 대신 추론 강도를 올린다.
    ladder = EFFORT_LADDER

    def build_command(self, request: AgentRequest, prompt: str) -> list[str]:
        sandbox = "read-only" if request.read_only else "workspace-write"
        command = [self.executable, "exec", "-s", sandbox]
        if request.model:
            command.extend(["-m", request.model])
        effort = self.rung(request.attempt)
        if effort:
            command.extend(["-c", f"model_reasoning_effort={effort}"])
        command.append(prompt)
        return command


@dataclass(frozen=True)
class ClaudeAdapter(Adapter):
    executable: str = "claude"

    name = "claude"
    # claude -p 는 끝날 때 한 번에 출력한다. 2026-11-17 CalcMoney 작업에서
    # 180초를 넘긴 리뷰가 stalled 로 끊겼다.
    streams_output = False
    # 모델이 아니라 강도를 올린다. --model opus 는 기본값이 이미 오푸스면
    # 같은 자리라서 재시도가 올라가지 않는다. --effort 에는 올릴 칸이 남아 있다.
    # 잘못된 등급을 주면 claude 는 막지 않고 경고만 찍고 무시한다. 상수로만 둔다.
    ladder = EFFORT_LADDER

    def build_command(self, request: AgentRequest, prompt: str) -> list[str]:
        command = [self.executable, "-p", prompt]
        if request.model:
            command.extend(["--model", request.model])
        effort = self.rung(request.attempt)
        if effort:
            command.extend(["--effort", effort])
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

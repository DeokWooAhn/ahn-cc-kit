from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import guards, prompts, scope
from .adapters import (
    FIXER,
    IMPLEMENTER,
    PLANNER,
    REVIEWER,
    Adapter,
    AgentRequest,
    AgentResult,
    adapter_for,
    run_command,
)
from .errors import PipelineError
from .gitio import ensure_repository
from .state import RunState, StateStore, TaskState, is_blocked, is_terminal, needs_human

ORCHESTRATE_DIR = Path(".orchestrate")

STATE_FILE = "state.json"
TASK_FILE = "task.txt"
PLAN = "01-plan.md"
PLAN_PROMPT = "01-plan-prompt.txt"
PLAN_LOG = "01-plan.log"
IMPLEMENT_PROMPT = "02-implement-prompt.txt"
IMPLEMENT_LOG = "02-implement.log"
SNAPSHOT = "02-snapshot.json"
GIT_BEFORE = "02-git-before.json"
REVIEW_PROMPT = "03-review-prompt.txt"
REVIEW_LOG = "03-review.log"
FIX_PLAN = "04-fix-plan.md"
FIX_PROMPT = "05-fix-prompt.txt"
FIX_LOG = "05-fix.log"
VERIFY_LOG = "verify-{index}.log"

DEFAULT_ROUTING = {
    PLANNER: "claude",
    IMPLEMENTER: "codex",
    REVIEWER: "claude",
    FIXER: "codex",
}

MAX_STEPS = 12

VERIFY_ROLE = "verify"
VERIFY_TIMEOUT_SECONDS = 1800
DEFAULT_RETRY_LIMIT = 2


@dataclass(frozen=True)
class TaskPaths:
    root: Path

    def __truediv__(self, name: str) -> Path:
        return self.root / name

    @property
    def state(self) -> Path:
        return self.root / STATE_FILE

    @property
    def plan(self) -> Path:
        return self.root / PLAN

    @property
    def fix_plan(self) -> Path:
        return self.root / FIX_PLAN

    @property
    def task_file(self) -> Path:
        return self.root / TASK_FILE


@dataclass
class Settings:
    repo: Path
    task_id: str
    task: str = ""
    orchestrate_dir: Path = ORCHESTRATE_DIR
    plugin_dir: Path | None = None
    routing: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ROUTING))
    retry_limit: int = DEFAULT_RETRY_LIMIT
    timeouts: dict[str, int] = field(default_factory=dict)
    stall_seconds: dict[str, int] = field(default_factory=dict)
    adapters: dict[str, Adapter] = field(default_factory=dict)

    def adapter(self, role: str) -> Adapter:
        if role in self.adapters:
            return self.adapters[role]
        return adapter_for(self.routing[role])

    @property
    def paths(self) -> TaskPaths:
        return TaskPaths(Path(self.repo) / self.orchestrate_dir / self.task_id)

    @property
    def store(self) -> StateStore:
        return StateStore(self.paths.state)

    def ignore(self) -> tuple[str, ...]:
        return (str(self.orchestrate_dir),)


@dataclass(frozen=True)
class StepResult:
    state: RunState
    did: str
    detail: str = ""
    stopped: bool = False
    agent: AgentResult | None = None

    @property
    def ok(self) -> bool:
        return not is_blocked(self.state)


def init(settings: Settings, *, plan: Path | None = None) -> TaskState:
    repo = ensure_repository(settings.repo)
    paths = settings.paths
    paths.root.mkdir(parents=True, exist_ok=True)
    exclude_orchestrate(repo, settings.orchestrate_dir)

    if settings.task:
        paths.task_file.write_text(settings.task.strip() + "\n", encoding="utf-8")

    if plan is not None:
        source = Path(plan)
        if not source.is_file():
            raise PipelineError(f"계획 파일이 없다: {source}")
        if source.resolve() != paths.plan.resolve():
            paths.plan.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    store = settings.store
    if store.exists():
        return store.load()
    return store.create(settings.task_id)


def exclude_orchestrate(repo: Path, orchestrate_dir: Path) -> None:
    exclude = Path(repo) / ".git/info/exclude"
    line = f"{orchestrate_dir}/"
    if not exclude.parent.is_dir():
        return
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if line in existing.splitlines():
        return
    prefix = "" if existing.endswith("\n") or not existing else "\n"
    exclude.write_text(f"{existing}{prefix}{line}\n", encoding="utf-8")


def stored_task(settings: Settings) -> str:
    path = settings.paths.task_file
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def step(settings: Settings) -> StepResult:
    store = settings.store
    task = store.load()
    state = task.state

    if is_terminal(state):
        return StepResult(state, "끝난 작업이다", stopped=True)
    if is_blocked(state):
        return StepResult(state, "막힌 상태다", task.note, stopped=True)
    if needs_human(state):
        return StepResult(state, "사람을 기다린다", waiting_hint(settings, state), stopped=True)

    handler = _HANDLERS.get(state)
    if handler is None:
        raise PipelineError(f"{state}에서 할 일이 정해져 있지 않다")
    return handler(settings, task)


def run(
    settings: Settings,
    *,
    max_steps: int = MAX_STEPS,
    before: Callable[[RunState], None] | None = None,
    after: Callable[[StepResult], None] | None = None,
) -> list[StepResult]:
    results: list[StepResult] = []
    for _ in range(max_steps):
        if before is not None:
            before(settings.store.load().state)
        result = step(settings)
        results.append(result)
        if after is not None:
            after(result)
        if result.stopped:
            return results
    raise PipelineError(
        f"{max_steps}걸음 안에 멈추지 않았다. `orch status`로 보고 `orch step`으로 한 걸음씩 간다"
    )


def approve(settings: Settings, *, note: str = "") -> StepResult:
    store = settings.store
    task = store.load()
    if task.state != RunState.PLAN_APPROVAL:
        raise PipelineError(f"승인할 자리가 아니다: {task.state}")
    if not settings.paths.plan.is_file():
        raise PipelineError(f"계획 파일이 없다: {settings.paths.plan}")
    store.transition(RunState.IMPLEMENTING, note=note or "사람이 계획을 승인했다")
    return StepResult(RunState.IMPLEMENTING, "계획을 승인했다")


def request_fix(settings: Settings) -> StepResult:
    store = settings.store
    task = store.load()
    if task.state != RunState.WAITING_HUMAN:
        raise PipelineError(f"수정으로 넘길 자리가 아니다: {task.state}")
    if not settings.paths.fix_plan.is_file():
        raise PipelineError(
            f"수정 계획이 없다: {settings.paths.fix_plan}\n"
            "리뷰 지적 중 반영할 것만 추려 그 파일에 쓴다. 전부 반영이 기본값이 아니다."
        )
    store.transition(RunState.FIXING, note="사람이 수정 계획을 넘겼다")
    return StepResult(RunState.FIXING, "수정 계획을 받았다")


def request_verify(settings: Settings) -> StepResult:
    store = settings.store
    task = store.load()
    if task.state != RunState.WAITING_HUMAN:
        raise PipelineError(f"검증으로 넘길 자리가 아니다: {task.state}")
    store.transition(RunState.VERIFYING, note="사람이 검증으로 넘겼다")
    return StepResult(RunState.VERIFYING, "검증으로 넘어간다")


def resume(settings: Settings) -> StepResult:
    store = settings.store
    task = store.load()
    if not is_blocked(task.state):
        raise PipelineError(f"막힌 상태가 아니다: {task.state}")
    if not task.history:
        raise PipelineError("되돌아갈 자리가 없다")
    target = RunState(task.history[-1].previous)
    store.transition(target, note=f"사람이 {task.state}에서 재개했다")
    return StepResult(target, f"{target}에서 다시 시작한다")


def _plan(settings: Settings, task: TaskState) -> StepResult:
    paths = settings.paths
    description = settings.task.strip() or stored_task(settings)
    if not description:
        raise PipelineError(
            "계획을 세울 작업 설명이 없다. `orch init <이름> --task \"...\"`로 주거나 "
            f"{paths.plan}에 계획을 직접 쓴다"
        )
    plugin_dir = prompts.find_plugin_dir(settings.plugin_dir)
    prompt = prompts.plan_prompt(description, paths.plan, plugin_dir)
    result = _call(settings, PLANNER, prompt, paths / PLAN_PROMPT, paths / PLAN_LOG)
    if not result.ok:
        return _agent_failed(settings, PLANNER, result)
    if not paths.plan.is_file():
        return _block(
            settings,
            RunState.FAILED_AGENT,
            f"계획 파일이 생기지 않았다: {paths.plan}",
            agent=result,
        )
    settings.store.record_artifact("plan", paths.plan)
    settings.store.transition(RunState.PLAN_APPROVAL, note="계획이 나왔다")
    return StepResult(
        RunState.PLAN_APPROVAL, "계획을 세웠다", waiting_hint(settings, RunState.PLAN_APPROVAL),
        stopped=True, agent=result,
    )


def _created(settings: Settings, task: TaskState) -> StepResult:
    paths = settings.paths
    if paths.plan.is_file():
        settings.store.record_artifact("plan", paths.plan)
        settings.store.transition(RunState.PLAN_APPROVAL, note="계획 파일을 받았다")
        return StepResult(
            RunState.PLAN_APPROVAL, "계획 파일이 이미 있다",
            waiting_hint(settings, RunState.PLAN_APPROVAL), stopped=True,
        )
    settings.store.transition(RunState.PLANNING, note="계획부터 세운다")
    return _plan(settings, settings.store.load())


def _implement(settings: Settings, task: TaskState) -> StepResult:
    paths = settings.paths
    repo = ensure_repository(settings.repo)

    scope.write_snapshot(repo, paths / SNAPSHOT, ignore=settings.ignore())
    before = guards.capture(repo)
    (paths / GIT_BEFORE).write_text(
        json.dumps(before.to_json_object(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    plugin_dir = prompts.find_plugin_dir(settings.plugin_dir)
    prompt = prompts.implement_prompt(paths.plan, plugin_dir)
    result = _call(settings, IMPLEMENTER, prompt, paths / IMPLEMENT_PROMPT, paths / IMPLEMENT_LOG)
    if not result.ok:
        return _agent_failed(settings, IMPLEMENTER, result)

    settings.store.record_artifact("implement_log", result.log_file)
    settings.store.transition(RunState.SCOPE_CHECK, note="구현을 넘겼다")
    return StepResult(RunState.SCOPE_CHECK, "구현을 넘겼다", agent=result)


def _fix(settings: Settings, task: TaskState) -> StepResult:
    paths = settings.paths
    repo = ensure_repository(settings.repo)

    bumped = settings.store.bump_retry(limit=settings.retry_limit)
    if bumped.state == RunState.MAX_RETRY_EXCEEDED:
        return StepResult(RunState.MAX_RETRY_EXCEEDED, "재시도 한도를 넘겼다", bumped.note, stopped=True)

    scope.write_snapshot(repo, paths / SNAPSHOT, ignore=settings.ignore())
    before = guards.capture(repo)
    (paths / GIT_BEFORE).write_text(
        json.dumps(before.to_json_object(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    plugin_dir = prompts.find_plugin_dir(settings.plugin_dir)
    prompt = prompts.fix_prompt(paths.fix_plan, plugin_dir)
    result = _call(settings, FIXER, prompt, paths / FIX_PROMPT, paths / FIX_LOG)
    if not result.ok:
        return _agent_failed(settings, FIXER, result)

    settings.store.record_artifact("fix_log", result.log_file)
    settings.store.transition(RunState.SCOPE_CHECK, note="수정을 넘겼다")
    return StepResult(RunState.SCOPE_CHECK, "수정을 넘겼다", agent=result)


def _scope_check(settings: Settings, task: TaskState) -> StepResult:
    paths = settings.paths
    repo = ensure_repository(settings.repo)

    before = guards.GitSnapshot.from_json_object(
        json.loads((paths / GIT_BEFORE).read_text(encoding="utf-8"))
    )
    violations = guards.check(repo, before)
    if violations:
        detail = "\n".join(f"- {item.kind}: {item.detail}" for item in violations)
        return _block(settings, RunState.BLOCKED_GIT, detail)

    result = scope.check(repo, paths.plan, paths / SNAPSHOT)
    if result.nothing_changed:
        return _block(settings, RunState.BLOCKED_SCOPE, "아무 파일도 바뀌지 않았다")
    if result.violations:
        listed = "\n".join(f"- {path}" for path in sorted(result.violations))
        return _block(settings, RunState.BLOCKED_SCOPE, f"계획에 없는 파일이 바뀌었다\n{listed}")

    settings.store.transition(RunState.REVIEWING, note=f"범위 검사 통과 ({len(result.changed)}개)")
    return StepResult(RunState.REVIEWING, "범위 검사를 통과했다", f"바뀐 파일 {len(result.changed)}개")


def _review(settings: Settings, task: TaskState) -> StepResult:
    paths = settings.paths
    repo = ensure_repository(settings.repo)

    changed = sorted(scope.compare(repo, scope.read_snapshot(paths / SNAPSHOT)))
    plugin_dir = prompts.find_plugin_dir(settings.plugin_dir)
    prompt = prompts.review_prompt(paths.plan, changed, plugin_dir)
    result = _call(
        settings, REVIEWER, prompt, paths / REVIEW_PROMPT, paths / REVIEW_LOG, read_only=True
    )
    if not result.ok:
        return _agent_failed(settings, REVIEWER, result)

    settings.store.record_artifact("review", result.log_file)
    settings.store.transition(RunState.WAITING_HUMAN, note="리뷰가 나왔다")
    return StepResult(
        RunState.WAITING_HUMAN, "리뷰를 받았다",
        waiting_hint(settings, RunState.WAITING_HUMAN), stopped=True, agent=result,
    )


def _verify(settings: Settings, task: TaskState) -> StepResult:
    paths = settings.paths
    repo = ensure_repository(settings.repo)
    commands = prompts.verify_commands(paths.plan)
    if not commands:
        return _block(settings, RunState.FAILED_VERIFY, "계획에 검증 명령이 없다")

    for index, command in enumerate(commands, start=1):
        log = paths / VERIFY_LOG.format(index=index)
        request = AgentRequest(
            role=VERIFY_ROLE,
            prompt_file=paths.plan,
            log_file=log,
            cwd=repo,
            timeout_seconds=settings.timeouts.get(VERIFY_ROLE, VERIFY_TIMEOUT_SECONDS),
            stall_seconds=settings.stall_seconds.get(VERIFY_ROLE, 0),
        )
        result = run_command(["sh", "-c", command], request)
        settings.store.record_artifact(f"verify_{index}", log)
        if not result.ok:
            return _block(
                settings,
                RunState.FAILED_VERIFY,
                f"검증 {index}번이 실패했다: {command}\n{result.detail}\n로그: {log}",
                agent=result,
            )

    settings.store.transition(RunState.COMPLETED, note=f"검증 {len(commands)}개 통과")
    return StepResult(RunState.COMPLETED, "검증을 통과했다", f"명령 {len(commands)}개")


def _call(
    settings: Settings,
    role: str,
    prompt: str,
    prompt_file: Path,
    log_file: Path,
    *,
    read_only: bool = False,
) -> AgentResult:
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")
    request = AgentRequest(
        role=role,
        prompt_file=prompt_file,
        log_file=log_file,
        cwd=ensure_repository(settings.repo),
        timeout_seconds=settings.timeouts.get(role),
        stall_seconds=settings.stall_seconds.get(role),
        read_only=read_only,
    )
    return settings.adapter(role).run(request)


def _agent_failed(settings: Settings, role: str, result: AgentResult) -> StepResult:
    detail = f"{role} 호출이 {result.outcome}로 끝났다: {result.detail}\n로그: {result.log_file}"
    return _block(settings, RunState.FAILED_AGENT, detail, agent=result)


def _block(
    settings: Settings, state: RunState, detail: str, *, agent: AgentResult | None = None
) -> StepResult:
    settings.store.transition(state, note=detail)
    return StepResult(state, "막혔다", detail, stopped=True, agent=agent)


def waiting_hint(settings: Settings, state: RunState) -> str:
    if state == RunState.PLAN_APPROVAL:
        lines = [
            f"계획: {settings.paths.plan}",
            "읽고 나서 `orch approve`로 구현에 넘긴다.",
        ]
        try:
            commands = prompts.verify_commands(settings.paths.plan)
        except Exception:
            commands = []
        if commands:
            lines.append("")
            lines.append("이 작업이 돌릴 검증 명령:")
            lines += [f"  {command}" for command in commands]
        return "\n".join(lines)
    if state == RunState.WAITING_HUMAN:
        return "\n".join(
            [
                f"리뷰: {settings.paths.root / REVIEW_LOG}",
                "지적을 추려 수정 계획을 쓰려면 "
                f"{settings.paths.fix_plan}에 쓰고 `orch fix`.",
                "고칠 것이 없으면 `orch verify`.",
            ]
        )
    return ""


_HANDLERS = {
    RunState.CREATED: _created,
    RunState.PLANNING: _plan,
    RunState.IMPLEMENTING: _implement,
    RunState.SCOPE_CHECK: _scope_check,
    RunState.REVIEWING: _review,
    RunState.FIXING: _fix,
    RunState.VERIFYING: _verify,
}

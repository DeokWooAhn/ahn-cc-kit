from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ledger, pipeline
from .errors import OrchestratorError
from .pipeline import Settings, StepResult
from .state import RunState, is_blocked

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_ERROR = 2


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except OrchestratorError as error:
        print(str(error), file=sys.stderr)
        return EXIT_ERROR


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orch", description="에이전트 왕복을 지휘한다")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("init", help="작업 디렉터리와 상태 파일을 만든다")
    start.add_argument("task_id")
    start.add_argument("--plan", type=Path, help="이미 쓴 계획 파일을 가져온다")
    start.add_argument("--task", default="", help="계획부터 세울 때 넘길 작업 설명")
    _common(start)
    start.set_defaults(handler=_init)

    auto = sub.add_parser("run", help="멈출 자리까지 자동으로 진행한다")
    auto.add_argument("task_id", nargs="?")
    auto.add_argument(
        "--max-steps", type=int, default=pipeline.MAX_STEPS,
        help=f"이 걸음 수를 넘기면 멈춘다 (기본 {pipeline.MAX_STEPS})",
    )
    _common(auto)
    auto.set_defaults(handler=_run)

    stats = sub.add_parser("stats", help="호출 장부를 모아 역할·등급별로 센다")
    stats.add_argument("task_id", nargs="?", help="주지 않으면 모든 작업을 모은다")
    _common(stats)
    stats.set_defaults(handler=_stats)

    for name, handler, help_text in (
        ("step", _step, "다음 한 걸음을 간다"),
        ("status", _status, "지금 상태와 다음에 할 일을 보여 준다"),
        ("approve", _approve, "계획을 승인해 구현으로 넘긴다"),
        ("fix", _fix, "수정 계획을 넘겨 다시 구현시킨다"),
        ("verify", _verify, "검증 명령을 돌린다"),
        ("resume", _resume, "막힌 자리에서 다시 시작한다"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("task_id", nargs="?")
        _common(command)
        command.set_defaults(handler=handler)

    return parser


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--plugin-dir", type=Path, default=None)
    parser.add_argument(
        "--orchestrate-dir", type=Path, default=pipeline.ORCHESTRATE_DIR,
        help="산출물 디렉터리 (저장소 기준 상대 경로)",
    )
    parser.add_argument(
        "--route", action="append", default=[], metavar="역할=어댑터",
        help="역할이 쓸 어댑터를 바꾼다. 예: --route reviewer=codex",
    )
    parser.add_argument(
        "--model", action="append", default=[], metavar="역할=별칭",
        help="그 역할이 쓸 모델. 주지 않으면 도구의 기본 설정을 쓴다. 예: --model reviewer=opus",
    )
    parser.add_argument(
        "--retry-limit", type=int, default=None,
        help="자동 수정 횟수. 주지 않으면 계획의 위험도가 정한다",
    )
    parser.add_argument(
        "--stall-seconds", action="append", default=[], metavar="역할=초",
        help="그 역할의 무활동 감지 시간. 0 이면 끈다. 예: --stall-seconds verify=0",
    )
    parser.add_argument(
        "--timeout", action="append", default=[], metavar="역할=초",
        help=(
            "그 역할의 전체 제한 시간. 0 이면 끈다. "
            "주지 않으면 역할 기본값(implementer·fixer 1200, planner 900, reviewer 600, verify 1800). "
            "예: --timeout implementer=3600"
        ),
    )
    parser.add_argument(
        "--no-verify-before-review", action="store_true",
        help="리뷰어에게 검증 결과를 주지 않는다. 검증이 오래 걸리는 프로젝트에서 쓴다",
    )


def _settings(args, task_id: str) -> Settings:
    return Settings(
        repo=args.repo,
        task_id=task_id,
        task=getattr(args, "task", "") or "",
        orchestrate_dir=args.orchestrate_dir,
        plugin_dir=args.plugin_dir,
        routing=_routing(args.route),
        models=_models(args.model),
        retry_limit=args.retry_limit,
        stall_seconds=_stall_seconds(args.stall_seconds),
        timeouts=_timeouts(args.timeout),
        verify_before_review=not getattr(args, "no_verify_before_review", False),
    )


def _stall_seconds(pairs: list[str]) -> dict[str, int]:
    return _role_seconds(pairs, "--stall-seconds")


def _timeouts(pairs: list[str]) -> dict[str, int]:
    return _role_seconds(pairs, "--timeout")


def _role_seconds(pairs: list[str], option: str) -> dict[str, int]:
    known = set(pipeline.DEFAULT_ROUTING) | {pipeline.VERIFY_ROLE}
    found: dict[str, int] = {}
    for pair in pairs:
        role, separator, value = pair.partition("=")
        if not separator or not value:
            raise OrchestratorError(f"{option} 형식은 역할=초다: {pair}")
        if role not in known:
            raise OrchestratorError(f"모르는 역할: {role} (있는 것: {', '.join(sorted(known))})")
        try:
            seconds = int(value)
        except ValueError:
            raise OrchestratorError(f"초는 숫자로 적는다: {pair}") from None
        if seconds < 0:
            raise OrchestratorError(f"초는 0 이상이어야 한다: {pair}")
        found[role] = seconds
    return found


def _models(pairs: list[str]) -> dict[str, str]:
    known = set(pipeline.DEFAULT_ROUTING)
    found: dict[str, str] = {}
    for pair in pairs:
        role, separator, model = pair.partition("=")
        if not separator or not model:
            raise OrchestratorError(f"--model 형식은 역할=별칭이다: {pair}")
        if role not in known:
            raise OrchestratorError(f"모르는 역할: {role} (있는 것: {', '.join(sorted(known))})")
        found[role] = model
    return found


def _routing(pairs: list[str]) -> dict[str, str]:
    routing = dict(pipeline.DEFAULT_ROUTING)
    for pair in pairs:
        role, separator, adapter = pair.partition("=")
        if not separator or not adapter:
            raise OrchestratorError(f"--route 형식은 역할=어댑터다: {pair}")
        if role not in routing:
            known = ", ".join(sorted(routing))
            raise OrchestratorError(f"모르는 역할: {role} (있는 것: {known})")
        routing[role] = adapter
    return routing


def _resolve(args) -> Settings:
    task_id = args.task_id or _only_task(args)
    return _settings(args, task_id)


def _only_task(args) -> str:
    root = Path(args.repo) / args.orchestrate_dir
    if not root.is_dir():
        raise OrchestratorError(f"작업 디렉터리가 없다: {root}")
    found = sorted(path.name for path in root.iterdir() if (path / pipeline.STATE_FILE).is_file())
    if not found:
        raise OrchestratorError(f"시작된 작업이 없다: {root}")
    if len(found) > 1:
        listed = ", ".join(found)
        raise OrchestratorError(f"작업이 여럿이다. 하나를 적는다: {listed}")
    return found[0]


def _init(args) -> int:
    settings = _settings(args, args.task_id)
    state = pipeline.init(settings, plan=args.plan)
    print(f"작업 {state.task_id} 준비 ({settings.paths.root})")
    if state.state == RunState.PLAN_APPROVAL:
        print()
        print(pipeline.waiting_hint(settings, state.state))
    elif settings.paths.plan.is_file():
        print(f"계획: {settings.paths.plan}")
    elif settings.task:
        print("계획부터 세운다. `orch step`")
    else:
        print(f"계획을 {settings.paths.plan}에 쓰거나, --task 로 계획부터 세운다")
    return EXIT_OK


def _step(args) -> int:
    return _report(pipeline.step(_resolve(args)))


def _stats(args) -> int:
    """장부를 모아 센다. 어디에 시간이 가는지 보려는 것이다."""
    root = Path(args.repo) / args.orchestrate_dir
    if args.task_id:
        calls = ledger.read_task(root / args.task_id)
        where = f"{root / args.task_id}"
    else:
        calls = ledger.read(root)
        where = f"{root}"
    if not calls:
        print(f"장부가 비었다: {where}")
        print("`orch` 로 돌린 호출이 아직 없거나, 장부를 넣기 전에 돈 작업뿐이다")
        return EXIT_OK

    tasks = len({call.task_id for call in calls})
    total = sum(call.seconds for call in calls)
    print(f"작업 {tasks}건 · 호출 {len(calls)}회 · 합계 {ledger.spoken(total)}")
    print()
    for line in ledger.table(ledger.summarize(calls)):
        print(line)

    default_rungs = sum(1 for call in calls if call.effort is None and call.kind == ledger.AGENT)
    if default_rungs:
        print()
        print(
            f"{ledger.TOOL_DEFAULT} 는 등급을 주지 않고 부른 {default_rungs}회다. "
            "그 호출이 실제로 어느 등급이었는지는 런타임이 모른다"
        )
    return EXIT_OK


def _run(args) -> int:
    return _drive(_resolve(args), getattr(args, "max_steps", pipeline.MAX_STEPS))


def _drive(settings: Settings, max_steps: int = pipeline.MAX_STEPS) -> int:
    """멈출 자리까지 간다. 상태만 바꿔 놓고 끝내지 않으려는 것이다."""
    results = pipeline.run(
        settings,
        max_steps=max_steps,
        before=_announce,
        after=_report,
    )
    return EXIT_BLOCKED if is_blocked(results[-1].state) else EXIT_OK


def _announce(state: RunState) -> None:
    print(f"→ {state} …", flush=True)


def _approve(args) -> int:
    return _report(pipeline.approve(_resolve(args)))


def _fix(args) -> int:
    settings = _resolve(args)
    result = pipeline.request_fix(settings)
    _report(result)
    if is_blocked(result.state):
        return EXIT_BLOCKED
    return _drive(settings)


def _verify(args) -> int:
    settings = _resolve(args)
    result = pipeline.request_verify(settings)
    _report(result)
    if is_blocked(result.state):
        return EXIT_BLOCKED
    return _drive(settings)


def _resume(args) -> int:
    settings = _resolve(args)
    result = pipeline.resume(settings)
    _report(result)
    if is_blocked(result.state):
        return EXIT_BLOCKED
    return _drive(settings)


def _status(args) -> int:
    settings = _resolve(args)
    task = settings.store.load()

    print(f"작업: {task.task_id}")
    print(f"상태: {task.state}")
    print(f"갱신: {task.updated_at}")
    if task.retry_count:
        print(f"재시도: {task.retry_count}")
    if task.note:
        print()
        print(task.note)

    hint = pipeline.waiting_hint(settings, task.state)
    if hint:
        print()
        print(hint)
    elif is_blocked(task.state):
        print()
        failure = pipeline.read_failure(settings)
        if failure is not None:
            print(failure.describe())
        else:
            print("고친 뒤 `orch resume`으로 직전 자리에서 다시 시작한다")
    elif task.state != RunState.COMPLETED:
        print()
        print("`orch step`으로 다음 걸음을 간다")

    if task.artifacts:
        print()
        print("산출물")
        for key, path in sorted(task.artifacts.items()):
            print(f"  {key}: {path}")

    return EXIT_BLOCKED if is_blocked(task.state) else EXIT_OK


def _report(result: StepResult) -> int:
    print(f"[{result.state}] {result.did}", flush=True)
    if result.agent is not None:
        agent = result.agent
        print(
            f"  {agent.role}: {agent.outcome} "
            f"({agent.duration_seconds:.0f}초, {agent.log_bytes}바이트) {agent.log_file}"
        )
    if result.detail:
        print()
        print(result.detail)
    return EXIT_BLOCKED if is_blocked(result.state) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

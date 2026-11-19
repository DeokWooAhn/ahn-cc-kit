from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator import pipeline, prompts
from orchestrator.adapters import FIXER, IMPLEMENTER, PLANNER, REVIEWER
from orchestrator.errors import PipelineError
from orchestrator.pipeline import Settings
from orchestrator.state import RunState
from support import ScriptedAdapter, TempRepo, plan_text

TASK_ID = "20261116-시험작업"


class PipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)
        self.repo = self._repo.path

        tmp = tempfile.TemporaryDirectory(prefix="orchestrator-plugin-")
        self.addCleanup(tmp.cleanup)
        references = Path(tmp.name) / prompts.REFERENCE_DIR
        references.mkdir(parents=True)
        (references / prompts.PLAN_TEMPLATE).write_text("계획 템플릿", encoding="utf-8")
        (references / prompts.GOTCHAS).write_text("함정 본문", encoding="utf-8")
        self.plugin = Path(tmp.name)

    def settings(self, scripts: dict[str, str] | None = None, **overrides) -> Settings:
        adapters = {role: ScriptedAdapter(script) for role, script in (scripts or {}).items()}
        values = {
            "repo": self.repo,
            "task_id": TASK_ID,
            "plugin_dir": self.plugin,
            "adapters": adapters,
        }
        values.update(overrides)
        return Settings(**values)

    def start(self, settings: Settings, *, verify: str = "true", paths=("a.txt",)) -> Settings:
        pipeline.init(settings)
        settings.paths.plan.write_text(plan_text(list(paths), verify=verify), encoding="utf-8")
        return settings

    def reach_implementing(self, settings: Settings, **start) -> Settings:
        self.start(settings, **start)
        pipeline.step(settings)
        pipeline.approve(settings)
        return settings


class InitTest(PipelineTestCase):
    def test_creates_the_task_directory_and_state(self) -> None:
        settings = self.settings()

        state = pipeline.init(settings)

        self.assertEqual(state.state, RunState.CREATED)
        self.assertTrue(settings.paths.state.is_file())

    def test_adds_the_output_directory_to_git_exclude(self) -> None:
        settings = self.settings()

        pipeline.init(settings)

        exclude = (self.repo / ".git/info/exclude").read_text(encoding="utf-8")
        self.assertIn(".orchestrate/", exclude.splitlines())

    def test_exclude_is_not_added_twice(self) -> None:
        settings = self.settings()

        pipeline.init(settings)
        pipeline.init(settings)

        exclude = (self.repo / ".git/info/exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.count(".orchestrate/"), 1)

    def test_copies_a_plan_that_was_written_elsewhere(self) -> None:
        settings = self.settings()
        source = self.repo.parent / "손으로쓴계획.md"
        source.write_text(plan_text(["a.txt"]), encoding="utf-8")

        pipeline.init(settings, plan=source)

        self.assertIn("건드릴 파일", settings.paths.plan.read_text(encoding="utf-8"))

    def test_a_missing_plan_is_an_error(self) -> None:
        settings = self.settings()

        with self.assertRaises(PipelineError):
            pipeline.init(settings, plan=self.repo / "없는계획.md")

    def test_init_twice_keeps_the_state(self) -> None:
        settings = self.settings()
        pipeline.init(settings)
        settings.store.transition(RunState.PLANNING)

        state = pipeline.init(settings)

        self.assertEqual(state.state, RunState.PLANNING)


class PlanningTest(PipelineTestCase):
    def test_an_existing_plan_goes_straight_to_approval(self) -> None:
        settings = self.start(self.settings())

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.PLAN_APPROVAL)
        self.assertTrue(result.stopped)

    def test_approval_shows_the_verify_commands(self) -> None:
        settings = self.start(self.settings(), verify="./gradlew test")

        result = pipeline.step(settings)

        self.assertIn("./gradlew test", result.detail)

    def test_without_a_plan_the_planner_is_called(self) -> None:
        plan_body = plan_text(["a.txt"]).replace("'", "")
        settings = self.settings(
            {PLANNER: f"cat > .orchestrate/{TASK_ID}/01-plan.md <<'EOF'\n{plan_body}\nEOF"},
            task="환율 로딩을 고친다",
        )
        pipeline.init(settings)

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.PLAN_APPROVAL)
        self.assertTrue(settings.paths.plan.is_file())
        self.assertIn("환율 로딩을 고친다", settings.adapters[PLANNER].prompts[0])

    def test_a_planner_that_writes_nothing_is_a_failure(self) -> None:
        settings = self.settings({PLANNER: "true"}, task="무언가 한다")
        pipeline.init(settings)

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.FAILED_AGENT)

    def test_planning_without_a_task_description_is_an_error(self) -> None:
        settings = self.settings({PLANNER: "true"})
        pipeline.init(settings)

        with self.assertRaises(PipelineError):
            pipeline.step(settings)

    def test_step_at_approval_does_not_move(self) -> None:
        settings = self.start(self.settings())
        pipeline.step(settings)

        again = pipeline.step(settings)

        self.assertEqual(again.state, RunState.PLAN_APPROVAL)
        self.assertTrue(again.stopped)

    def test_approve_moves_to_implementing(self) -> None:
        settings = self.start(self.settings())
        pipeline.step(settings)

        result = pipeline.approve(settings)

        self.assertEqual(result.state, RunState.IMPLEMENTING)

    def test_approve_elsewhere_is_an_error(self) -> None:
        settings = self.start(self.settings())

        with self.assertRaises(PipelineError):
            pipeline.approve(settings)


class ImplementTest(PipelineTestCase):
    def test_snapshot_is_taken_right_before_handing_off(self) -> None:
        settings = self.reach_implementing(self.settings({IMPLEMENTER: "echo 고침 >> a.txt"}))

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.SCOPE_CHECK)
        self.assertTrue((settings.paths.root / pipeline.SNAPSHOT).is_file())
        self.assertTrue((settings.paths.root / pipeline.GIT_BEFORE).is_file())

    def test_the_implementer_gets_the_plan_path_not_the_plan(self) -> None:
        settings = self.reach_implementing(self.settings({IMPLEMENTER: "echo 고침 >> a.txt"}))

        pipeline.step(settings)

        prompt = settings.adapters[IMPLEMENTER].prompts[0]
        plan_body = settings.paths.plan.read_text(encoding="utf-8")
        self.assertIn(str(settings.paths.plan), prompt)
        self.assertIn("시험한다.", plan_body)
        self.assertNotIn("시험한다.", prompt)

    def test_a_failing_agent_blocks(self) -> None:
        settings = self.reach_implementing(self.settings({IMPLEMENTER: "exit 7"}))

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.FAILED_AGENT)
        self.assertIn("7", result.detail)


class ScopeCheckTest(PipelineTestCase):
    def run_implement(self, script: str, *, paths=("a.txt",)) -> Settings:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: script}), paths=paths
        )
        pipeline.step(settings)
        return settings

    def test_changes_inside_the_plan_pass(self) -> None:
        settings = self.run_implement("echo 고침 >> a.txt")

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.REVIEWING)

    def test_a_file_outside_the_plan_blocks(self) -> None:
        settings = self.run_implement("echo 고침 >> a.txt; echo 침범 > b.txt")

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_SCOPE)
        self.assertIn("b.txt", result.detail)

    def test_changing_nothing_blocks(self) -> None:
        settings = self.run_implement("true")

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_SCOPE)
        self.assertIn("아무 파일도", result.detail)

    def test_a_commit_blocks_even_when_the_files_are_allowed(self) -> None:
        settings = self.run_implement("echo 고침 >> a.txt; git add a.txt; git commit -m 몰래")

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_GIT)
        self.assertIn("commit", result.detail)

    def test_staging_blocks(self) -> None:
        settings = self.run_implement("echo 고침 >> a.txt; git add a.txt")

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_GIT)
        self.assertIn("staged", result.detail)

    def test_the_output_directory_is_not_a_violation(self) -> None:
        settings = self.run_implement("echo 고침 >> a.txt")

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.REVIEWING)


class ReviewTest(PipelineTestCase):
    def reach_review(self, review_script: str = "echo 지적 없음") -> Settings:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: review_script})
        )
        pipeline.step(settings)
        pipeline.step(settings)
        return settings

    def test_review_stops_for_the_human(self) -> None:
        settings = self.reach_review()

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.WAITING_HUMAN)
        self.assertTrue(result.stopped)

    def test_the_reviewer_runs_read_only(self) -> None:
        settings = self.reach_review()
        pipeline.step(settings)

        self.assertEqual(settings.adapters[REVIEWER].read_only, [True])

    def test_the_review_brief_lists_the_changed_files(self) -> None:
        settings = self.reach_review()
        pipeline.step(settings)

        self.assertIn("`a.txt`", settings.adapters[REVIEWER].prompts[0])

    def test_the_review_is_recorded_as_an_artifact(self) -> None:
        settings = self.reach_review()
        pipeline.step(settings)

        artifacts = settings.store.load().artifacts
        self.assertIn("review", artifacts)
        self.assertIn("지적 없음", Path(artifacts["review"]).read_text(encoding="utf-8"))


class AfterReviewTest(PipelineTestCase):
    def reach_waiting(self, **scripts) -> Settings:
        base = {IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"}
        base.update(scripts)
        settings = self.reach_implementing(self.settings(base))
        for _ in range(3):
            pipeline.step(settings)
        return settings

    def test_verify_runs_the_plan_commands(self) -> None:
        settings = self.reach_waiting()

        pipeline.request_verify(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.COMPLETED)

    def test_a_failing_verify_blocks(self) -> None:
        settings = self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        self.reach_implementing(settings, verify="false")
        for _ in range(3):
            pipeline.step(settings)

        pipeline.request_verify(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.FAILED_VERIFY)

    def test_fix_needs_a_fix_plan(self) -> None:
        settings = self.reach_waiting()

        with self.assertRaises(PipelineError) as caught:
            pipeline.request_fix(settings)

        self.assertIn("전부 반영이 기본값이 아니다", str(caught.exception))

    def test_fix_hands_the_fix_plan_to_the_fixer(self) -> None:
        settings = self.reach_waiting(**{FIXER: "echo 또 고침 >> a.txt"})
        settings.paths.fix_plan.write_text("# 수정 계획\n\n하나만 고친다\n", encoding="utf-8")

        pipeline.request_fix(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.SCOPE_CHECK)
        self.assertIn(str(settings.paths.fix_plan), settings.adapters[FIXER].prompts[0])

    def test_the_fix_plan_widens_the_scope(self) -> None:
        # 리뷰 뒤에 넓어진 범위를 원 계획으로만 재면 정상 흐름이 막힌다.
        settings = self.reach_waiting(**{FIXER: "echo 또 고침 >> b.txt"})
        settings.paths.fix_plan.write_text(plan_text(["b.txt"]), encoding="utf-8")

        pipeline.request_fix(settings)
        pipeline.step(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.REVIEWING)

    def test_a_file_in_neither_plan_is_still_a_violation(self) -> None:
        settings = self.reach_waiting(**{FIXER: "echo 몰래 >> c.txt"})
        settings.paths.fix_plan.write_text(plan_text(["b.txt"]), encoding="utf-8")

        pipeline.request_fix(settings)
        pipeline.step(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_SCOPE)
        self.assertIn("c.txt", result.detail)
        self.assertIn("04-fix-plan.md", result.detail)

    def test_a_fix_runs_on_the_raised_rung(self) -> None:
        settings = self.reach_waiting(**{FIXER: "echo 또 고침 >> a.txt"})
        settings.paths.fix_plan.write_text("# 수정 계획\n\n하나만 고친다\n", encoding="utf-8")

        pipeline.request_fix(settings)
        pipeline.step(settings)

        self.assertEqual(settings.adapters[FIXER].attempts, [1])

    def test_the_first_implementation_stays_on_the_bottom_rung(self) -> None:
        settings = self.reach_waiting()

        self.assertEqual(settings.adapters[IMPLEMENTER].attempts, [0])

    def test_the_retry_limit_stops_the_loop(self) -> None:
        settings = self.reach_waiting(**{FIXER: "echo 또 고침 >> a.txt"})
        settings.paths.fix_plan.write_text("# 수정 계획\n", encoding="utf-8")
        settings.retry_limit = 1

        for _ in range(2):
            pipeline.request_fix(settings)
            pipeline.step(settings)
            pipeline.step(settings)
            pipeline.step(settings)

        self.assertEqual(settings.store.load().state, RunState.MAX_RETRY_EXCEEDED)


class ResumeTest(PipelineTestCase):
    def test_resume_goes_back_to_the_state_before_the_block(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 고침 >> a.txt; echo 침범 > b.txt"})
        )
        pipeline.step(settings)
        blocked = pipeline.step(settings)
        self.assertEqual(blocked.state, RunState.BLOCKED_SCOPE)

        (self.repo / "b.txt").unlink()
        result = pipeline.resume(settings)

        self.assertEqual(result.state, RunState.SCOPE_CHECK)
        self.assertEqual(pipeline.step(settings).state, RunState.REVIEWING)

    def test_resume_outside_a_block_is_an_error(self) -> None:
        settings = self.start(self.settings())

        with self.assertRaises(PipelineError):
            pipeline.resume(settings)


class WholeRunTest(PipelineTestCase):
    def test_one_task_goes_from_created_to_completed(self) -> None:
        settings = self.start(
            self.settings(
                {
                    IMPLEMENTER: "echo 고침 >> a.txt",
                    REVIEWER: "echo 지적 없음",
                },
            ),
            verify="test -s a.txt",
        )

        seen = [pipeline.step(settings).state]
        pipeline.approve(settings)
        seen.append(settings.store.load().state)
        seen.append(pipeline.step(settings).state)
        seen.append(pipeline.step(settings).state)
        seen.append(pipeline.step(settings).state)
        pipeline.request_verify(settings)
        seen.append(pipeline.step(settings).state)

        self.assertEqual(
            seen,
            [
                RunState.PLAN_APPROVAL,
                RunState.IMPLEMENTING,
                RunState.SCOPE_CHECK,
                RunState.REVIEWING,
                RunState.WAITING_HUMAN,
                RunState.COMPLETED,
            ],
        )

    def test_a_completed_task_does_not_move(self) -> None:
        settings = self.start(
            self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        )
        for _ in range(4):
            pipeline.step(settings)
        pipeline.approve(settings)
        for _ in range(3):
            pipeline.step(settings)
        pipeline.request_verify(settings)
        pipeline.step(settings)

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.COMPLETED)
        self.assertTrue(result.stopped)

class RunTest(PipelineTestCase):
    def test_run_stops_at_the_approval(self) -> None:
        settings = self.start(self.settings())

        results = pipeline.run(settings)

        self.assertEqual(results[-1].state, RunState.PLAN_APPROVAL)
        self.assertTrue(results[-1].stopped)

    def test_run_goes_from_implementing_to_the_review_wait(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        )

        results = pipeline.run(settings)

        self.assertEqual(
            [result.state for result in results],
            [RunState.SCOPE_CHECK, RunState.REVIEWING, RunState.WAITING_HUMAN],
        )

    def test_run_stops_when_it_is_blocked(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 고침 >> a.txt; echo 침범 > b.txt"})
        )

        results = pipeline.run(settings)

        self.assertEqual(results[-1].state, RunState.BLOCKED_SCOPE)
        self.assertFalse(results[-1].ok)

    def test_run_never_passes_the_approval_on_its_own(self) -> None:
        settings = self.start(self.settings({IMPLEMENTER: "echo 고침 >> a.txt"}))

        pipeline.run(settings)
        again = pipeline.run(settings)

        self.assertEqual(settings.store.load().state, RunState.PLAN_APPROVAL)
        self.assertEqual(len(again), 1)

    def test_a_step_budget_that_is_too_small_is_an_error(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        )

        with self.assertRaises(PipelineError) as caught:
            pipeline.run(settings, max_steps=1)

        self.assertIn("1걸음", str(caught.exception))

    def test_the_callbacks_see_every_step(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        )
        entered: list[RunState] = []
        finished: list[RunState] = []

        pipeline.run(
            settings,
            before=entered.append,
            after=lambda result: finished.append(result.state),
        )

        self.assertEqual(
            entered, [RunState.IMPLEMENTING, RunState.SCOPE_CHECK, RunState.REVIEWING]
        )
        self.assertEqual(
            finished, [RunState.SCOPE_CHECK, RunState.REVIEWING, RunState.WAITING_HUMAN]
        )

    def test_run_on_a_finished_task_does_nothing(self) -> None:
        settings = self.start(self.settings())
        settings.store.transition(RunState.COMPLETED, note="끝났다")

        results = pipeline.run(settings)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].stopped)

    def test_the_task_description_survives_until_the_next_command(self) -> None:
        settings = self.settings({PLANNER: "true"}, task="환율 로딩을 고친다")
        pipeline.init(settings)

        later = self.settings({PLANNER: "true"})

        self.assertEqual(pipeline.stored_task(later), "환율 로딩을 고친다")

    def test_a_stored_task_reaches_the_planner(self) -> None:
        plan_body = plan_text(["a.txt"]).replace("'", "")
        written = self.settings(task="환율 로딩을 고친다")
        pipeline.init(written)

        later = self.settings(
            {PLANNER: f"cat > .orchestrate/{TASK_ID}/01-plan.md <<'EOF'\n{plan_body}\nEOF"}
        )
        result = pipeline.step(later)

        self.assertEqual(result.state, RunState.PLAN_APPROVAL)
        self.assertIn("환율 로딩을 고친다", later.adapters[PLANNER].prompts[0])

class ReviewBriefTest(PipelineTestCase):
    def two_rounds(self) -> Settings:
        settings = self.reach_implementing(
            self.settings(
                {
                    IMPLEMENTER: "echo 첫째 >> a.txt",
                    REVIEWER: "echo 리뷰",
                    FIXER: "echo 둘째 >> b.txt",
                }
            ),
            paths=("a.txt", "b.txt"),
        )
        for _ in range(3):
            pipeline.step(settings)
        settings.paths.fix_plan.write_text("# 수정 계획\n", encoding="utf-8")
        pipeline.request_fix(settings)
        for _ in range(3):
            pipeline.step(settings)
        return settings

    def test_the_second_review_still_sees_the_first_round_changes(self) -> None:
        settings = self.two_rounds()

        first, second = settings.adapters[REVIEWER].prompts

        self.assertIn("`a.txt`", first)
        self.assertNotIn("`b.txt`", first)
        self.assertIn("`a.txt`", second)
        self.assertIn("`b.txt`", second)

    def test_a_fix_does_not_overwrite_the_baseline(self) -> None:
        settings = self.reach_implementing(
            self.settings(
                {
                    IMPLEMENTER: "echo 첫째 >> a.txt",
                    REVIEWER: "echo 리뷰",
                    FIXER: "echo 둘째 >> b.txt",
                }
            ),
            paths=("a.txt", "b.txt"),
        )
        for _ in range(3):
            pipeline.step(settings)
        baseline = settings.paths / pipeline.BASELINE
        taken_at_start = baseline.read_text(encoding="utf-8")

        settings.paths.fix_plan.write_text("# 수정 계획\n", encoding="utf-8")
        pipeline.request_fix(settings)
        pipeline.step(settings)

        self.assertEqual(baseline.read_text(encoding="utf-8"), taken_at_start)

    def test_the_scope_check_still_looks_at_the_latest_handoff(self) -> None:
        settings = self.two_rounds()

        self.assertEqual(settings.store.load().state, RunState.WAITING_HUMAN)


class VerifyReportTest(PipelineTestCase):
    def test_verify_reports_time_and_log_size_per_command(self) -> None:
        settings = self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        self.reach_implementing(settings, verify="echo 검증했다")
        for _ in range(3):
            pipeline.step(settings)

        pipeline.request_verify(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.COMPLETED)
        self.assertIn("echo 검증했다", result.detail)
        self.assertIn("초", result.detail)
        self.assertIn("바이트", result.detail)

    def test_verify_warns_that_a_build_cache_may_be_reused(self) -> None:
        settings = self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        self.reach_implementing(settings)
        for _ in range(3):
            pipeline.step(settings)

        pipeline.request_verify(settings)
        result = pipeline.step(settings)

        self.assertIn("캐시", result.detail)

class CommandGateTest(PipelineTestCase):
    def reach_waiting(self, verify: str) -> Settings:
        settings = self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        self.reach_implementing(settings, verify=verify)
        for _ in range(3):
            pipeline.step(settings)
        return settings

    def test_a_refused_command_blocks_before_anything_runs(self) -> None:
        settings = self.reach_waiting("echo 흔적 > 돌았다.txt; git push")

        pipeline.request_verify(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_POLICY)
        self.assertIn("원격", result.detail)
        self.assertFalse((self.repo / "돌았다.txt").exists(), "막혔는데 명령이 돌았다")

    def test_an_allowance_lets_it_through(self) -> None:
        settings = self.reach_waiting("git push --dry-run")
        settings.allow_commands = ("git push --dry-run",)

        pipeline.request_verify(settings)
        result = pipeline.step(settings)

        self.assertNotEqual(result.state, RunState.BLOCKED_POLICY)

    def test_the_approval_hint_warns_before_approving(self) -> None:
        settings = self.start(self.settings(), verify="rm -rf build")

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.PLAN_APPROVAL)
        self.assertIn("정책에 막히는 명령", result.detail)
        self.assertIn("재귀", result.detail)

    def test_an_ordinary_plan_shows_no_warning(self) -> None:
        settings = self.start(self.settings(), verify="./gradlew test")

        result = pipeline.step(settings)

        self.assertNotIn("정책에 막히는", result.detail)

class FailureRecordTest(PipelineTestCase):
    def test_a_provider_failure_is_classified_and_saved(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 'Failed to authenticate: OAuth session expired' >&2; exit 1"})
        )

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.FAILED_AGENT)
        self.assertIn("provider", result.detail)
        saved = pipeline.read_failure(settings)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.kind, "provider")
        self.assertIn("failure", settings.store.load().artifacts)

    def test_an_environment_failure_is_not_retryable(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 'command not found: codex' >&2; exit 127"})
        )

        pipeline.step(settings)
        saved = pipeline.read_failure(settings)

        self.assertEqual(saved.kind, "environment")
        self.assertFalse(saved.retryable)

    def test_resume_warns_when_the_failure_was_not_retryable(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo 'Could not resolve host: example.invalid' >&2; exit 1"})
        )
        pipeline.step(settings)

        result = pipeline.resume(settings)

        self.assertIn("environment", result.detail)
        self.assertIn("또 막힌다", result.detail)

    def test_resume_stays_quiet_after_a_retryable_failure(self) -> None:
        settings = self.reach_implementing(
            self.settings({IMPLEMENTER: "echo '3 tests completed, 1 failed' >&2; exit 1"})
        )
        pipeline.step(settings)

        result = pipeline.resume(settings)

        self.assertEqual(result.detail, "")

    def test_a_failing_verify_is_classified_too(self) -> None:
        settings = self.settings({IMPLEMENTER: "echo 고침 >> a.txt", REVIEWER: "echo 리뷰"})
        self.reach_implementing(settings, verify="echo 'JAVA_HOME is not set' >&2; exit 1")
        for _ in range(3):
            pipeline.step(settings)

        pipeline.request_verify(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.FAILED_VERIFY)
        self.assertIn("environment", result.detail)

class PlanCheckTest(PipelineTestCase):
    def write_plan(self, body: str) -> Settings:
        settings = self.settings()
        pipeline.init(settings)
        settings.paths.plan.write_text(body, encoding="utf-8")
        return settings

    def test_a_plan_without_a_verify_section_blocks(self) -> None:
        settings = self.write_plan(
            "# 시험\n\n## 목적\n\n고친다.\n\n## 건드릴 파일\n\n```\na.txt\n```\n"
        )

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_PLAN)
        self.assertIn("검증", result.detail)

    def test_a_plan_with_an_empty_file_list_blocks(self) -> None:
        settings = self.write_plan(
            "# 시험\n\n## 목적\n\n고친다.\n\n## 건드릴 파일\n\n```\n```\n"
            "\n## 검증\n\n```\ntrue\n```\n"
        )

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_PLAN)
        self.assertIn("건드릴 파일", result.detail)

    def test_a_fixed_plan_passes_on_resume(self) -> None:
        settings = self.write_plan("# 시험\n\n## 목적\n\n고친다.\n")
        self.assertEqual(pipeline.step(settings).state, RunState.BLOCKED_PLAN)

        settings.paths.plan.write_text(plan_text(["a.txt"]), encoding="utf-8")
        pipeline.resume(settings)
        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.PLAN_APPROVAL)

    def test_a_planner_that_writes_a_malformed_plan_blocks(self) -> None:
        settings = self.settings(
            {PLANNER: f"printf '# 계획\\n' > .orchestrate/{TASK_ID}/01-plan.md"},
            task="무언가 한다",
        )
        pipeline.init(settings)

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.BLOCKED_PLAN)
        self.assertIn("형식이 맞지 않다", result.detail)

    def test_the_approval_hint_names_missing_advisory_sections(self) -> None:
        settings = self.start(self.settings())

        result = pipeline.step(settings)

        self.assertEqual(result.state, RunState.PLAN_APPROVAL)
        self.assertIn("권고 절이 빠졌다", result.detail)
        self.assertIn("확인할 수 없는 것", result.detail)

class RiskPolicyTest(PipelineTestCase):
    def plan_with_risk(self, risk: str) -> str:
        body = plan_text(["a.txt", "b.txt"])
        return body.replace("## 목적", f"## 위험도\n\n{risk}\n\n## 목적", 1)

    def start_with_risk(self, risk: str, scripts: dict[str, str]) -> Settings:
        settings = self.settings(scripts)
        pipeline.init(settings)
        settings.paths.plan.write_text(self.plan_with_risk(risk), encoding="utf-8")
        pipeline.step(settings)
        pipeline.approve(settings)
        return settings

    def fix_rounds_until_blocked(self, settings: Settings, limit: int = 6) -> int:
        settings.paths.fix_plan.write_text("# 수정 계획\n", encoding="utf-8")
        rounds = 0
        for _ in range(limit):
            if settings.store.load().state != RunState.WAITING_HUMAN:
                break
            pipeline.request_fix(settings)
            for _ in range(3):
                pipeline.step(settings)
            rounds += 1
            if settings.store.load().state == RunState.MAX_RETRY_EXCEEDED:
                break
        return rounds

    def test_high_risk_allows_one_fix_round(self) -> None:
        settings = self.start_with_risk(
            "high",
            {IMPLEMENTER: "echo 첫 >> a.txt", REVIEWER: "echo 리뷰", FIXER: "echo 또 >> b.txt"},
        )
        for _ in range(3):
            pipeline.step(settings)

        rounds = self.fix_rounds_until_blocked(settings)

        self.assertEqual(settings.store.load().state, RunState.MAX_RETRY_EXCEEDED)
        self.assertEqual(rounds, 2)

    def test_low_risk_allows_more(self) -> None:
        settings = self.start_with_risk(
            "low",
            {IMPLEMENTER: "echo 첫 >> a.txt", REVIEWER: "echo 리뷰", FIXER: "echo 또 >> b.txt"},
        )
        for _ in range(3):
            pipeline.step(settings)

        rounds = self.fix_rounds_until_blocked(settings)

        self.assertEqual(rounds, 4)

    def test_an_explicit_setting_overrides_the_plan(self) -> None:
        settings = self.settings()
        pipeline.init(settings)
        settings.paths.plan.write_text(self.plan_with_risk("low"), encoding="utf-8")
        settings.retry_limit = 1

        self.assertEqual(settings.retry_limit_for(settings.paths.plan), 1)

    def test_the_plan_decides_when_nothing_is_set(self) -> None:
        settings = self.settings()
        pipeline.init(settings)
        settings.paths.plan.write_text(self.plan_with_risk("high"), encoding="utf-8")

        self.assertEqual(settings.retry_limit_for(settings.paths.plan), 1)

    def test_the_approval_hint_shows_the_risk(self) -> None:
        settings = self.settings()
        pipeline.init(settings)
        settings.paths.plan.write_text(self.plan_with_risk("high"), encoding="utf-8")

        result = pipeline.step(settings)

        self.assertIn("위험도: high", result.detail)
        self.assertIn("1회까지", result.detail)
        self.assertIn("사람이 다시 본다", result.detail)

    def test_the_approval_hint_says_when_the_risk_is_a_default(self) -> None:
        settings = self.start(self.settings())

        result = pipeline.step(settings)

        self.assertIn("위험도: medium", result.detail)
        self.assertIn("기본값", result.detail)

class RetryResumeTest(PipelineTestCase):
    def reach_exceeded(self) -> Settings:
        settings = self.reach_implementing(
            self.settings(
                {
                    IMPLEMENTER: "echo 첫 >> a.txt",
                    REVIEWER: "echo 리뷰",
                    FIXER: "echo 또 >> b.txt",
                }
            ),
            paths=("a.txt", "b.txt"),
        )
        settings.retry_limit = 1
        for _ in range(3):
            pipeline.step(settings)
        settings.paths.fix_plan.write_text("# 수정 계획\n", encoding="utf-8")
        for _ in range(2):
            if settings.store.load().state != RunState.WAITING_HUMAN:
                break
            pipeline.request_fix(settings)
            for _ in range(3):
                pipeline.step(settings)
        return settings

    def test_resume_goes_back_to_fixing_not_the_review_wait(self) -> None:
        settings = self.reach_exceeded()
        self.assertEqual(settings.store.load().state, RunState.MAX_RETRY_EXCEEDED)

        result = pipeline.resume(settings)

        self.assertEqual(result.state, RunState.FIXING)

    def test_a_blocked_attempt_does_not_eat_the_count(self) -> None:
        settings = self.reach_exceeded()

        self.assertEqual(settings.store.load().retry_count, 1)

    def test_raising_the_limit_gives_exactly_one_more_round(self) -> None:
        settings = self.reach_exceeded()
        pipeline.resume(settings)
        settings.retry_limit = 2

        for _ in range(3):
            pipeline.step(settings)

        self.assertEqual(settings.store.load().state, RunState.WAITING_HUMAN)
        self.assertEqual(settings.store.load().retry_count, 2)


if __name__ == "__main__":
    unittest.main()

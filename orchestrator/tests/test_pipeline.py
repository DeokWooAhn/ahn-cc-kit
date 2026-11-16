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
        self.assertIn(".claude/orchestrate/", exclude.splitlines())

    def test_exclude_is_not_added_twice(self) -> None:
        settings = self.settings()

        pipeline.init(settings)
        pipeline.init(settings)

        exclude = (self.repo / ".git/info/exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.count(".claude/orchestrate/"), 1)

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
            {PLANNER: f"cat > .claude/orchestrate/{TASK_ID}/01-plan.md <<'EOF'\n{plan_body}\nEOF"},
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


if __name__ == "__main__":
    unittest.main()

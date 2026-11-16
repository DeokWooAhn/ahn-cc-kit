from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from orchestrator import pipeline, prompts
from orchestrator.__main__ import EXIT_BLOCKED, EXIT_ERROR, EXIT_OK, main
from orchestrator.pipeline import Settings
from orchestrator.state import RunState
from support import TempRepo, plan_text

TASK_ID = "20261116-cli"


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)
        self.repo = self._repo.path

        tmp = tempfile.TemporaryDirectory(prefix="orchestrator-plugin-")
        self.addCleanup(tmp.cleanup)
        references = Path(tmp.name) / prompts.REFERENCE_DIR
        references.mkdir(parents=True)
        (references / prompts.PLAN_TEMPLATE).write_text("계획 템플릿", encoding="utf-8")
        (references / prompts.GOTCHAS).write_text("함정", encoding="utf-8")
        self.plugin = Path(tmp.name)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--repo", str(self.repo), "--plugin-dir", str(self.plugin)])
        return code, out.getvalue(), err.getvalue()

    def settings(self, task_id: str = TASK_ID) -> Settings:
        return Settings(repo=self.repo, task_id=task_id, plugin_dir=self.plugin)

    def write_plan(self, task_id: str = TASK_ID, *, verify: str = "true") -> Settings:
        settings = self.settings(task_id)
        settings.paths.root.mkdir(parents=True, exist_ok=True)
        settings.paths.plan.write_text(plan_text(["a.txt"], verify=verify), encoding="utf-8")
        return settings

    def test_init_reports_where_it_put_things(self) -> None:
        code, out, _ = self.run_cli("init", TASK_ID)

        self.assertEqual(code, EXIT_OK)
        self.assertIn(TASK_ID, out)
        self.assertTrue(self.settings().paths.state.is_file())

    def test_init_points_at_the_plan_it_still_needs(self) -> None:
        _, out, _ = self.run_cli("init", TASK_ID)

        self.assertIn("01-plan.md", out)

    def test_status_shows_the_state(self) -> None:
        self.run_cli("init", TASK_ID)

        code, out, _ = self.run_cli("status", TASK_ID)

        self.assertEqual(code, EXIT_OK)
        self.assertIn("created", out)
        self.assertIn("orch step", out)

    def test_the_task_id_can_be_left_out_when_there_is_one(self) -> None:
        self.run_cli("init", TASK_ID)

        code, out, _ = self.run_cli("status")

        self.assertEqual(code, EXIT_OK)
        self.assertIn(TASK_ID, out)

    def test_two_tasks_need_the_name(self) -> None:
        self.run_cli("init", TASK_ID)
        self.run_cli("init", "20261116-다른작업")

        code, _, err = self.run_cli("status")

        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("작업이 여럿이다", err)

    def test_no_task_at_all_is_an_error(self) -> None:
        code, _, err = self.run_cli("status")

        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("작업", err)

    def test_step_stops_at_approval(self) -> None:
        self.write_plan()
        self.run_cli("init", TASK_ID)

        code, out, _ = self.run_cli("step", TASK_ID)

        self.assertEqual(code, EXIT_OK)
        self.assertIn("plan_approval", out)

    def test_approval_prints_the_verify_commands(self) -> None:
        self.write_plan(verify="./gradlew detekt")
        self.run_cli("init", TASK_ID)

        _, out, _ = self.run_cli("step", TASK_ID)

        self.assertIn("./gradlew detekt", out)

    def test_approve_moves_on(self) -> None:
        self.write_plan()
        self.run_cli("init", TASK_ID)
        self.run_cli("step", TASK_ID)

        code, out, _ = self.run_cli("approve", TASK_ID)

        self.assertEqual(code, EXIT_OK)
        self.assertIn("implementing", out)

    def test_approve_at_the_wrong_time_is_an_error(self) -> None:
        self.run_cli("init", TASK_ID)

        code, _, err = self.run_cli("approve", TASK_ID)

        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("승인할 자리가 아니다", err)

    def test_verify_runs_the_commands_and_completes(self) -> None:
        settings = self.write_plan(verify="echo 검증했다")
        self.run_cli("init", TASK_ID)
        settings.store.transition(RunState.WAITING_HUMAN, note="리뷰까지 끝났다 치고")

        code, out, _ = self.run_cli("verify", TASK_ID)

        self.assertEqual(code, EXIT_OK)
        self.assertIn("completed", out)
        log = settings.paths.root / pipeline.VERIFY_LOG.format(index=1)
        self.assertIn("검증했다", log.read_text(encoding="utf-8"))

    def test_a_failing_verify_exits_nonzero(self) -> None:
        settings = self.write_plan(verify="false")
        self.run_cli("init", TASK_ID)
        settings.store.transition(RunState.WAITING_HUMAN, note="리뷰까지 끝났다 치고")

        code, out, _ = self.run_cli("verify", TASK_ID)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("failed_verify", out)

    def test_status_exits_nonzero_while_blocked(self) -> None:
        settings = self.write_plan()
        self.run_cli("init", TASK_ID)
        settings.store.transition(RunState.BLOCKED_SCOPE, note="계획에 없는 파일이 바뀌었다")

        code, out, _ = self.run_cli("status", TASK_ID)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("orch resume", out)

    def test_resume_goes_back(self) -> None:
        settings = self.write_plan()
        self.run_cli("init", TASK_ID)
        settings.store.transition(RunState.SCOPE_CHECK)
        settings.store.transition(RunState.BLOCKED_SCOPE, note="막혔다")

        code, out, _ = self.run_cli("resume", TASK_ID)

        self.assertEqual(code, EXIT_OK)
        self.assertIn("scope_check", out)

    def test_status_lists_artifacts(self) -> None:
        settings = self.write_plan()
        self.run_cli("init", TASK_ID)
        settings.store.record_artifact("plan", settings.paths.plan)

        _, out, _ = self.run_cli("status", TASK_ID)

        self.assertIn("산출물", out)
        self.assertIn("01-plan.md", out)

    def test_route_changes_the_adapter_for_a_role(self) -> None:
        from orchestrator.__main__ import _routing

        routing = _routing(["reviewer=codex"])

        self.assertEqual(routing["reviewer"], "codex")
        self.assertEqual(routing["implementer"], "codex")
        self.assertEqual(routing["planner"], "claude")

    def test_route_needs_a_pair(self) -> None:
        code, _, err = self.run_cli("status", TASK_ID, "--route", "reviewer")

        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("역할=어댑터", err)

    def test_route_rejects_an_unknown_role(self) -> None:
        code, _, err = self.run_cli("status", TASK_ID, "--route", "tester=codex")

        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("모르는 역할", err)

    def test_run_stops_at_the_approval(self) -> None:
        self.write_plan()
        self.run_cli("init", TASK_ID)

        code, out, _ = self.run_cli("run", TASK_ID)

        self.assertEqual(code, EXIT_OK)
        self.assertIn("plan_approval", out)
        self.assertIn("→", out)

    def test_run_exits_nonzero_when_blocked(self) -> None:
        settings = self.write_plan()
        self.run_cli("init", TASK_ID)
        settings.store.transition(RunState.BLOCKED_GIT, note="커밋이 생겼다")

        code, out, _ = self.run_cli("run", TASK_ID)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("blocked_git", out)

    def test_run_takes_a_step_budget(self) -> None:
        self.write_plan()
        self.run_cli("init", TASK_ID)

        code, _, _ = self.run_cli("run", TASK_ID, "--max-steps", "3")

        self.assertEqual(code, EXIT_OK)


if __name__ == "__main__":
    unittest.main()

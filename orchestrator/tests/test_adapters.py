from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import adapters
from orchestrator.adapters import (
    FAILED,
    FALLBACK_TIMEOUT_SECONDS,
    IMPLEMENTER,
    MISSING_COMMAND,
    OK,
    PLANNER,
    REVIEWER,
    STALLED,
    TIMEOUT,
    Adapter,
    AgentRequest,
    ClaudeAdapter,
    CodexAdapter,
    adapter_for,
    read_prompt,
    run_command,
)
from orchestrator.errors import PromptFileError, UnknownAdapter


def alive(pid: int, *, within: float = 3.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        time.sleep(0.05)
    return True


def sleeping(seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="orchestrator-adapter-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.log = self.dir / "logs" / "02-implement.log"

    def request(self, **overrides) -> AgentRequest:
        values = {
            "role": IMPLEMENTER,
            "prompt_file": self.dir / "prompt.txt",
            "log_file": self.log,
            "cwd": self.dir,
            "timeout_seconds": 10,
            "stall_seconds": 0,
        }
        values.update(overrides)
        return AgentRequest(**values)

    def log_text(self) -> str:
        return self.log.read_text(encoding="utf-8")


class RequestDefaultsTest(unittest.TestCase):
    def make(self, role: str, **overrides) -> AgentRequest:
        return AgentRequest(
            role=role,
            prompt_file=Path("prompt.txt"),
            log_file=Path("run.log"),
            cwd=Path("."),
            **overrides,
        )

    def test_implementer_gets_the_longest_budget(self) -> None:
        self.assertEqual(self.make(IMPLEMENTER).timeout, 1200)

    def test_reviewer_gets_a_shorter_budget(self) -> None:
        self.assertEqual(self.make(REVIEWER).timeout, 600)

    def test_planner_budget(self) -> None:
        self.assertEqual(self.make(PLANNER).timeout, 900)

    def test_unknown_role_falls_back(self) -> None:
        self.assertEqual(self.make("설명가").timeout, FALLBACK_TIMEOUT_SECONDS)

    def test_explicit_timeout_wins(self) -> None:
        self.assertEqual(self.make(IMPLEMENTER, timeout_seconds=5).timeout, 5)

    def test_stall_has_a_default(self) -> None:
        self.assertEqual(self.make(IMPLEMENTER).stall, 180)

    def test_stall_can_be_turned_off(self) -> None:
        self.assertEqual(self.make(IMPLEMENTER, stall_seconds=0).stall, 0)


class ReadPromptTest(WorkspaceTestCase):
    def test_reads_and_strips(self) -> None:
        path = self.dir / "prompt.txt"
        path.write_text("\n계획을 읽어라\n\n", encoding="utf-8")

        self.assertEqual(read_prompt(path), "계획을 읽어라")

    def test_missing_file_is_an_error(self) -> None:
        with self.assertRaises(PromptFileError):
            read_prompt(self.dir / "없는파일.txt")

    def test_empty_file_is_an_error(self) -> None:
        path = self.dir / "prompt.txt"
        path.write_text("   \n", encoding="utf-8")

        with self.assertRaises(PromptFileError):
            read_prompt(path)


class BuildCommandTest(unittest.TestCase):
    def request(self, **overrides) -> AgentRequest:
        values = {
            "role": IMPLEMENTER,
            "prompt_file": Path("prompt.txt"),
            "log_file": Path("run.log"),
            "cwd": Path("."),
        }
        values.update(overrides)
        return AgentRequest(**values)

    def test_codex_writes_in_the_workspace_by_default(self) -> None:
        command = CodexAdapter().build_command(self.request(), "넘길 말")

        self.assertEqual(command, ["codex", "exec", "-s", "workspace-write", "넘길 말"])

    def test_codex_read_only_narrows_the_sandbox(self) -> None:
        command = CodexAdapter().build_command(self.request(read_only=True), "넘길 말")

        self.assertEqual(command[:4], ["codex", "exec", "-s", "read-only"])

    def test_codex_takes_a_model(self) -> None:
        command = CodexAdapter().build_command(self.request(model="gpt-5"), "넘길 말")

        self.assertEqual(command[4:6], ["-m", "gpt-5"])
        self.assertEqual(command[-1], "넘길 말")

    def test_claude_runs_headless(self) -> None:
        command = ClaudeAdapter().build_command(self.request(), "구현해라")

        self.assertEqual(command[:3], ["claude", "-p", "구현해라"])

    def test_claude_always_names_its_tools(self) -> None:
        command = ClaudeAdapter().build_command(self.request(), "구현해라")

        self.assertIn("--allowed-tools", command)
        self.assertIn("Write", command)
        self.assertIn("Bash", command)

    def test_claude_read_only_keeps_write_tools_out(self) -> None:
        command = ClaudeAdapter().build_command(
            self.request(role=REVIEWER, read_only=True), "리뷰해라"
        )

        self.assertEqual(command[3], "--allowed-tools")
        self.assertNotIn("Write", command)
        self.assertNotIn("Edit", command)
        self.assertNotIn("Bash", command)

    def test_claude_read_only_still_sees_the_diff(self) -> None:
        command = ClaudeAdapter().build_command(
            self.request(role=REVIEWER, read_only=True), "리뷰해라"
        )

        self.assertIn("Bash(git diff:*)", command)

    def test_prompt_is_one_argument(self) -> None:
        prompt = "여러 줄\n짜리 프롬프트 'quoted' $HOME"
        command = CodexAdapter().build_command(self.request(), prompt)

        self.assertEqual(command.count(prompt), 1)

    def test_a_first_attempt_leaves_the_tool_default_alone(self) -> None:
        codex = CodexAdapter().build_command(self.request(), "넘길 말")
        claude = ClaudeAdapter().build_command(self.request(), "넘길 말")

        self.assertNotIn("-c", codex)
        self.assertNotIn("--model", claude)

    def test_a_retry_raises_the_claude_model(self) -> None:
        command = ClaudeAdapter().build_command(self.request(attempt=1), "고쳐라")

        self.assertEqual(command[3:5], ["--model", "opus"])

    def test_a_retry_raises_the_codex_effort(self) -> None:
        command = CodexAdapter().build_command(self.request(attempt=1), "고쳐라")

        self.assertEqual(command[4:6], ["-c", "model_reasoning_effort=high"])
        self.assertEqual(command[-1], "고쳐라")

    def test_an_explicit_model_beats_the_ladder(self) -> None:
        command = ClaudeAdapter().build_command(
            self.request(attempt=2, model="sonnet"), "고쳐라"
        )

        self.assertEqual(command[3:5], ["--model", "sonnet"])
        self.assertEqual(command.count("--model"), 1)

    def test_an_explicit_codex_model_still_gets_the_effort(self) -> None:
        command = CodexAdapter().build_command(
            self.request(attempt=1, model="gpt-5"), "고쳐라"
        )

        self.assertEqual(command[4:8], ["-m", "gpt-5", "-c", "model_reasoning_effort=high"])

    def test_the_ladder_stops_at_the_top(self) -> None:
        once = ClaudeAdapter().build_command(self.request(attempt=1), "고쳐라")
        many = ClaudeAdapter().build_command(self.request(attempt=9), "고쳐라")

        self.assertEqual(once, many)

    def test_an_adapter_without_a_ladder_adds_nothing(self) -> None:
        self.assertIsNone(Adapter().rung(3))

    def test_adapter_for_known_names(self) -> None:
        self.assertIsInstance(adapter_for("codex"), CodexAdapter)
        self.assertIsInstance(adapter_for("claude"), ClaudeAdapter)

    def test_adapter_for_unknown_name(self) -> None:
        with self.assertRaises(UnknownAdapter):
            adapter_for("cursor")


class RunCommandTest(WorkspaceTestCase):
    def test_success_is_reported_with_the_log(self) -> None:
        result = run_command(["sh", "-c", "echo 끝났다"], self.request())

        self.assertTrue(result.ok)
        self.assertEqual(result.outcome, OK)
        self.assertEqual(result.returncode, 0)
        self.assertIn("끝났다", self.log_text())
        self.assertGreater(result.log_bytes, 0)

    def test_failure_keeps_the_return_code(self) -> None:
        result = run_command(["sh", "-c", "exit 3"], self.request())

        self.assertFalse(result.ok)
        self.assertEqual(result.outcome, FAILED)
        self.assertEqual(result.returncode, 3)
        self.assertIn("3", result.detail)

    def test_stdin_is_closed(self) -> None:
        result = run_command(["sh", "-c", "cat"], self.request(timeout_seconds=5))

        self.assertEqual(result.outcome, OK)
        self.assertLess(result.duration_seconds, 5)

    def test_stderr_lands_in_the_same_log(self) -> None:
        run_command(["sh", "-c", "echo 밖으로 >&2"], self.request())

        self.assertIn("밖으로", self.log_text())

    def test_log_directory_is_created(self) -> None:
        self.assertFalse(self.log.parent.exists())

        run_command(["sh", "-c", "echo 처음"], self.request())

        self.assertTrue(self.log.is_file())

    def test_log_is_not_appended_to(self) -> None:
        run_command(["sh", "-c", "echo 지난번"], self.request())
        run_command(["sh", "-c", "echo 이번"], self.request())

        text = self.log_text()
        self.assertNotIn("지난번", text)
        self.assertIn("이번", text)

    def test_runs_in_the_requested_directory(self) -> None:
        nested = self.dir / "작업"
        nested.mkdir()

        run_command(["sh", "-c", "pwd"], self.request(cwd=nested))

        self.assertIn("작업", self.log_text())

    def test_large_output_does_not_deadlock(self) -> None:
        result = run_command(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 200000)"],
            self.request(),
        )

        self.assertEqual(result.outcome, OK)
        self.assertEqual(result.log_bytes, 200000)

    def test_missing_command_is_reported_not_raised(self) -> None:
        result = run_command(["orchestrator-없는명령"], self.request())

        self.assertEqual(result.outcome, MISSING_COMMAND)
        self.assertIsNone(result.returncode)
        self.assertIn("orchestrator-없는명령", result.detail)

    def test_adapter_puts_the_prompt_file_into_the_command(self) -> None:
        (self.dir / "prompt.txt").write_text("계획 파일을 읽어라\n", encoding="utf-8")

        result = CodexAdapter(executable="/bin/echo").run(self.request())

        self.assertEqual(result.outcome, OK)
        self.assertIn("계획 파일을 읽어라", self.log_text())

    def test_result_survives_json(self) -> None:
        result = run_command(["sh", "-c", "echo 끝"], self.request())
        data = result.to_json_object()

        self.assertEqual(data["outcome"], OK)
        self.assertEqual(data["returncode"], 0)
        self.assertEqual(data["command"], ["sh", "-c", "echo 끝"])


class TimeoutTest(WorkspaceTestCase):
    def test_hung_command_is_cut_on_time(self) -> None:
        result = run_command(sleeping(30), self.request(timeout_seconds=1))

        self.assertEqual(result.outcome, TIMEOUT)
        self.assertFalse(result.ok)
        self.assertLess(result.duration_seconds, 10)
        self.assertIn("1초", result.detail)

    def test_grandchild_is_killed_too(self) -> None:
        pid_file = self.dir / "grandchild.pid"
        script = f'sleep 30 & echo $! > "{pid_file}"; wait'

        result = run_command(["sh", "-c", script], self.request(timeout_seconds=1))

        self.assertEqual(result.outcome, TIMEOUT)
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        self.assertFalse(alive(pid), "넘긴 명령이 띄운 프로세스가 남았다")

    def test_a_command_inside_the_budget_is_left_alone(self) -> None:
        result = run_command(sleeping(0.3), self.request(timeout_seconds=10))

        self.assertEqual(result.outcome, OK)


class StallTest(WorkspaceTestCase):
    def test_silent_command_is_cut_without_waiting_for_the_timeout(self) -> None:
        result = run_command(
            sleeping(30), self.request(timeout_seconds=30, stall_seconds=1)
        )

        self.assertEqual(result.outcome, STALLED)
        self.assertLess(result.duration_seconds, 10)
        self.assertIn("1초", result.detail)

    def test_steady_output_is_not_mistaken_for_a_stall(self) -> None:
        ticking = [
            sys.executable,
            "-u",
            "-c",
            "import time\nfor _ in range(8):\n    print('진행 중')\n    time.sleep(0.2)",
        ]

        result = run_command(ticking, self.request(timeout_seconds=30, stall_seconds=2))

        self.assertEqual(result.outcome, OK)
        self.assertEqual(self.log_text().count("진행 중"), 8)

    def test_stall_detection_can_be_turned_off(self) -> None:
        result = run_command(
            sleeping(0.5), self.request(timeout_seconds=30, stall_seconds=0)
        )

        self.assertEqual(result.outcome, OK)


class ProcessGroupTest(WorkspaceTestCase):
    def test_our_own_process_group_is_never_signalled(self) -> None:
        process = subprocess.Popen(sleeping(30))
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)

        with mock.patch.object(adapters.os, "killpg") as killpg:
            adapters._signal_group(process, signal.SIGTERM)

        killpg.assert_not_called()
        self.assertEqual(process.wait(timeout=5), -signal.SIGTERM)

    def test_a_handed_off_command_gets_its_own_group(self) -> None:
        result = run_command(
            [sys.executable, "-c", "import os; print(os.getpgrp())"],
            self.request(),
        )

        self.assertEqual(result.outcome, OK)
        self.assertNotEqual(int(self.log_text().strip()), os.getpgrp())

class InterruptTest(WorkspaceTestCase):
    def test_an_interrupt_takes_the_child_down_with_it(self) -> None:
        pid_file = self.dir / "child.pid"
        script = f'echo $$ > "{pid_file}"; sleep 30'

        def interrupt_after_the_child_starts(*args, **kwargs):
            time.sleep(0.3)
            raise KeyboardInterrupt

        with mock.patch.object(adapters, "_watch", interrupt_after_the_child_starts):
            with self.assertRaises(KeyboardInterrupt):
                run_command(["sh", "-c", script], self.request())

        pid = int(pid_file.read_text(encoding="utf-8").strip())
        self.assertFalse(alive(pid), "중단했는데 넘긴 명령이 살아남았다")

class StreamingTest(WorkspaceTestCase):
    def test_codex_output_is_watched_for_stalls(self) -> None:
        self.assertTrue(CodexAdapter().streams_output)

    def test_claude_output_is_not(self) -> None:
        self.assertFalse(ClaudeAdapter().streams_output)

    def test_a_silent_command_is_cut_when_output_is_watched(self) -> None:
        result = run_command(
            sleeping(30), self.request(timeout_seconds=30, stall_seconds=1), watch_stall=True
        )

        self.assertEqual(result.outcome, STALLED)

    def test_a_silent_command_survives_when_output_is_not_watched(self) -> None:
        # stall(1초)보다 길게 자야 감지 여부가 결과를 가른다.
        result = run_command(
            sleeping(2), self.request(timeout_seconds=30, stall_seconds=1), watch_stall=False
        )

        self.assertEqual(result.outcome, OK)
        self.assertGreater(result.duration_seconds, 1)

    def test_the_timeout_still_applies_without_stall_watching(self) -> None:
        result = run_command(
            sleeping(30), self.request(timeout_seconds=1, stall_seconds=1), watch_stall=False
        )

        self.assertEqual(result.outcome, TIMEOUT)

    def test_an_adapter_that_does_not_stream_skips_stall_detection(self) -> None:
        (self.dir / "prompt.txt").write_text("아무 말\n", encoding="utf-8")

        class Quiet(ClaudeAdapter):
            def build_command(self, request, prompt):
                return sleeping(2)

        result = Quiet().run(self.request(timeout_seconds=30, stall_seconds=1))

        self.assertEqual(result.outcome, OK)
        self.assertGreater(result.duration_seconds, 1)


if __name__ == "__main__":
    unittest.main()

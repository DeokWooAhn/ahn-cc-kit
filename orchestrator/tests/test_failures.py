from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator import failures
from orchestrator.adapters import FAILED, MISSING_COMMAND, OK, STALLED, TIMEOUT, AgentResult


class ClassifyTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="orchestrator-failure-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.counter = 0

    def result(self, log: str, *, outcome: str = FAILED, detail: str = "종료 코드 1") -> AgentResult:
        self.counter += 1
        path = self.dir / f"{self.counter}.log"
        path.write_text(log, encoding="utf-8")
        return AgentResult(
            role="implementer",
            command=("x",),
            outcome=outcome,
            returncode=1,
            duration_seconds=1.0,
            log_file=path,
            log_bytes=len(log.encode("utf-8")),
            detail=detail,
        )

    def test_an_expired_login_is_a_provider_problem(self) -> None:
        failure = failures.classify(
            self.result("Failed to authenticate: OAuth session expired and could not be refreshed")
        )

        self.assertEqual(failure.kind, failures.PROVIDER)
        self.assertTrue(failure.retryable)
        self.assertIn("route", failure.next_step)

    def test_not_logged_in_is_a_provider_problem(self) -> None:
        failure = failures.classify(self.result("Not logged in · Please run /login"))

        self.assertEqual(failure.kind, failures.PROVIDER)

    def test_a_rate_limit_is_a_provider_problem(self) -> None:
        failure = failures.classify(self.result("Error: rate limit exceeded, retry after 60s"))

        self.assertEqual(failure.kind, failures.PROVIDER)

    def test_a_missing_simulator_is_an_environment_problem(self) -> None:
        failure = failures.classify(
            self.result("xcodebuild: error: Unable to find a destination matching the specifier")
        )

        self.assertEqual(failure.kind, failures.ENVIRONMENT)
        self.assertFalse(failure.retryable)
        self.assertIn("코드를 고쳐도", failure.next_step)

    def test_a_missing_command_is_an_environment_problem(self) -> None:
        failure = failures.classify(self.result("zsh: command not found: gradlew"))

        self.assertEqual(failure.kind, failures.ENVIRONMENT)

    def test_a_network_failure_is_an_environment_problem(self) -> None:
        failure = failures.classify(self.result("Could not resolve host: repo.maven.apache.org"))

        self.assertEqual(failure.kind, failures.ENVIRONMENT)

    def test_a_missing_executable_outcome_is_environmental(self) -> None:
        failure = failures.classify(
            self.result("", outcome=MISSING_COMMAND, detail="명령을 찾지 못했다: codex")
        )

        self.assertEqual(failure.kind, failures.ENVIRONMENT)
        self.assertFalse(failure.retryable)

    def test_an_ordinary_test_failure_stays_with_the_agent(self) -> None:
        failure = failures.classify(
            self.result("FAILED: :presentation:test\n3 tests completed, 1 failed")
        )

        self.assertEqual(failure.kind, failures.AGENT)
        self.assertTrue(failure.retryable)

    def test_a_verify_failure_is_labelled_as_such(self) -> None:
        failure = failures.classify(
            self.result("1 test failed"), role_failed=failures.VERIFY
        )

        self.assertEqual(failure.kind, failures.VERIFY)
        self.assertIn("코드 문제인지 테스트 문제인지", failure.next_step)

    def test_a_verify_failure_can_still_be_environmental(self) -> None:
        failure = failures.classify(
            self.result("JAVA_HOME is not set"), role_failed=failures.VERIFY
        )

        self.assertEqual(failure.kind, failures.ENVIRONMENT)

    def test_a_stall_is_reported_as_a_stall(self) -> None:
        failure = failures.classify(
            self.result("Reading additional input from stdin...", outcome=STALLED)
        )

        self.assertEqual(failure.kind, failures.AGENT)
        self.assertIn("자라지 않아", failure.summary)

    def test_a_timeout_is_reported_as_a_timeout(self) -> None:
        failure = failures.classify(self.result("작업 중...", outcome=TIMEOUT))

        self.assertIn("제한 시간", failure.summary)

    def test_provider_signs_win_over_the_outcome(self) -> None:
        failure = failures.classify(
            self.result("Failed to authenticate", outcome=TIMEOUT)
        )

        self.assertEqual(failure.kind, failures.PROVIDER)

    def test_the_evidence_quotes_the_log(self) -> None:
        failure = failures.classify(self.result("...\nNot logged in · Please run /login\n..."))

        self.assertIn("Not logged in", failure.evidence)
        self.assertIn("Not logged in", failure.describe())

    def test_only_the_tail_of_a_long_log_is_read(self) -> None:
        padding = "x" * (failures.LOG_TAIL_BYTES * 2)
        failure = failures.classify(self.result(f"Not logged in\n{padding}"))

        self.assertNotEqual(failure.kind, failures.PROVIDER)

    def test_json_round_trip(self) -> None:
        failure = failures.classify(self.result("Not logged in"))
        data = failure.to_json_object()

        self.assertEqual(data["kind"], failures.PROVIDER)
        self.assertTrue(data["retryable"])
        self.assertIn("next_step", data)


if __name__ == "__main__":
    unittest.main()

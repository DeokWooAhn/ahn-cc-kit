from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.errors import NotAGitRepository
from orchestrator.guards import BRANCH, COMMIT, PUSH, STAGED, GitSnapshot, capture, check
from support import TempBareRepo, TempRepo


class CaptureTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)

    def test_captures_head_and_branch(self) -> None:
        taken = capture(self._repo.path)

        self.assertEqual(taken.head, self._repo.head())
        self.assertEqual(taken.branch, "main")
        self.assertIsNone(taken.upstream)
        self.assertEqual(taken.staged, ())

    def test_detached_head_has_no_branch(self) -> None:
        self._repo.git("checkout", "--detach")

        self.assertIsNone(capture(self._repo.path).branch)

    def test_staged_paths_are_sorted(self) -> None:
        self._repo.write("b.txt", "b\n")
        self._repo.write("a.txt", "a\n")
        self._repo.git("add", "a.txt", "b.txt")

        self.assertEqual(capture(self._repo.path).staged, ("a.txt", "b.txt"))

    def test_outside_a_repository_is_an_error(self) -> None:
        with self.assertRaises(NotAGitRepository):
            capture(Path("/"))

    def test_json_round_trip(self) -> None:
        taken = capture(self._repo.path)

        self.assertEqual(GitSnapshot.from_json_object(taken.to_json_object()), taken)


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)
        self.before = capture(self._repo.path)

    def _kinds(self) -> list[str]:
        return [violation.kind for violation in check(self._repo.path, self.before)]

    def test_untouched_repository_has_no_violation(self) -> None:
        self.assertEqual(self._kinds(), [])

    def test_editing_files_alone_is_not_a_violation(self) -> None:
        self._repo.write("src/a.py", "x = 1\n")
        self._repo.write("README.md", "바뀐 내용\n")

        self.assertEqual(self._kinds(), [])

    def test_commit_is_caught(self) -> None:
        self._repo.write("src/a.py", "x = 1\n")
        self._repo.git("add", "src/a.py")
        self._repo.commit("몰래 커밋")

        kinds = self._kinds()

        self.assertIn(COMMIT, kinds)

    def test_branch_switch_is_caught(self) -> None:
        self._repo.git("switch", "-c", "mischief")

        self.assertIn(BRANCH, self._kinds())

    def test_staging_is_caught(self) -> None:
        self._repo.write("src/a.py", "x = 1\n")
        self._repo.git("add", "src/a.py")

        kinds = self._kinds()

        self.assertIn(STAGED, kinds)
        self.assertNotIn(COMMIT, kinds)

    def test_already_staged_file_is_not_reported_again(self) -> None:
        self._repo.write("src/a.py", "x = 1\n")
        self._repo.git("add", "src/a.py")
        before = capture(self._repo.path)

        self._repo.write("src/a.py", "x = 2\n")
        violations = check(self._repo.path, before)

        self.assertEqual(violations, ())

    def test_push_is_caught_through_upstream_change(self) -> None:
        remote = TempBareRepo().__enter__()
        self.addCleanup(remote.__exit__, None, None, None)
        self._repo.git("remote", "add", "origin", str(remote.path))
        self._repo.git("push", "-u", "origin", "main")
        before = capture(self._repo.path)

        self._repo.commit("새 커밋")
        self._repo.git("push", "origin", "main")
        violations = check(self._repo.path, before)

        self.assertIn(PUSH, [violation.kind for violation in violations])

    def test_detail_names_the_change(self) -> None:
        self._repo.git("switch", "-c", "mischief")

        detail = next(
            violation.detail
            for violation in check(self._repo.path, self.before)
            if violation.kind == BRANCH
        )

        self.assertIn("main", detail)
        self.assertIn("mischief", detail)


if __name__ == "__main__":
    unittest.main()

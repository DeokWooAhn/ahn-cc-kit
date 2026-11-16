from __future__ import annotations

import json
import unittest
from pathlib import Path

from orchestrator.errors import NotAGitRepository, PlanFormatError, SnapshotFileError
from orchestrator.scope import (
    MISSING,
    check,
    is_ignored,
    normalize_ignore,
    parse_allowed,
    read_snapshot,
    snapshot,
    write_snapshot,
)
from support import TempRepo, plan_text

WORK_DIR = ".orchestrate"


class ParseAllowedTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)

    def test_reads_paths_from_first_block(self) -> None:
        plan = self._repo.write("plan.md", plan_text(["src/a.py", "src/b.py"]))

        self.assertEqual(parse_allowed(plan), frozenset({"src/a.py", "src/b.py"}))

    def test_strips_trailing_note_in_parentheses(self) -> None:
        plan = self._repo.write("plan.md", plan_text(["src/a.py (새 파일)", "src/b.py"]))

        self.assertEqual(parse_allowed(plan), frozenset({"src/a.py", "src/b.py"}))

    def test_ignores_the_verification_block(self) -> None:
        plan = self._repo.write("plan.md", plan_text(["src/a.py"]))

        self.assertEqual(parse_allowed(plan), frozenset({"src/a.py"}))

    def test_missing_section_is_an_error(self) -> None:
        plan = self._repo.write("plan.md", "# 계획\n\n## 할 일\n\n없다\n")

        with self.assertRaises(PlanFormatError):
            parse_allowed(plan)

    def test_empty_block_is_an_error(self) -> None:
        plan = self._repo.write("plan.md", plan_text([]))

        with self.assertRaises(PlanFormatError):
            parse_allowed(plan)

    def test_missing_file_is_an_error(self) -> None:
        with self.assertRaises(PlanFormatError):
            parse_allowed(self._repo.path / "없는계획.md")


class IgnoreTest(unittest.TestCase):
    def test_normalize_strips_slashes_and_blanks(self) -> None:
        self.assertEqual(
            normalize_ignore([".orchestrate/", "  ", "docs"]),
            (".orchestrate", "docs"),
        )

    def test_matches_directory_boundary_only(self) -> None:
        ignore = (".orchestrate",)

        self.assertTrue(is_ignored(".orchestrate", ignore))
        self.assertTrue(is_ignored(".orchestrate/01-plan.md", ignore))
        self.assertFalse(is_ignored(".orchestrate-old/x.md", ignore))


class SnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)

    def test_clean_repository_has_empty_snapshot(self) -> None:
        self.assertEqual(snapshot(self._repo.path).files, {})

    def test_untracked_file_is_captured(self) -> None:
        self._repo.write("src/new.py", "x = 1\n")

        files = snapshot(self._repo.path).files

        self.assertIn("src/new.py", files)
        self.assertNotEqual(files["src/new.py"], MISSING)

    def test_deleted_tracked_file_is_missing(self) -> None:
        self._repo.remove("README.md")

        self.assertEqual(snapshot(self._repo.path).files["README.md"], MISSING)

    def test_path_with_space_is_handled(self) -> None:
        self._repo.write("src/두 단어.py", "x = 1\n")

        self.assertIn("src/두 단어.py", snapshot(self._repo.path).files)

    def test_ignored_paths_are_left_out(self) -> None:
        self._repo.write("src/new.py", "x = 1\n")
        self._repo.write(f"{WORK_DIR}/01-plan.md", "계획\n")

        files = snapshot(self._repo.path, ignore=[WORK_DIR]).files

        self.assertIn("src/new.py", files)
        self.assertNotIn(f"{WORK_DIR}/01-plan.md", files)

    def test_write_excludes_its_own_directory(self) -> None:
        self._repo.write("src/new.py", "x = 1\n")
        out = self._repo.path / WORK_DIR / "snap.json"

        written = write_snapshot(self._repo.path, out)

        self.assertIn(WORK_DIR, written.ignore)
        self.assertEqual(read_snapshot(out), written)

    def test_write_outside_the_repository_adds_no_ignore(self) -> None:
        other = TempRepo().__enter__()
        self.addCleanup(other.__exit__, None, None, None)

        written = write_snapshot(self._repo.path, other.path / "snap.json")

        self.assertEqual(written.ignore, ())

    def test_read_rejects_other_algorithm(self) -> None:
        out = self._repo.path / "snap.json"
        out.write_text(
            json.dumps({"schema_version": 1, "algorithm": "md5", "files": {}}),
            encoding="utf-8",
        )

        with self.assertRaises(SnapshotFileError):
            read_snapshot(out)

    def test_read_rejects_broken_json(self) -> None:
        out = self._repo.path / "snap.json"
        out.write_text("{", encoding="utf-8")

        with self.assertRaises(SnapshotFileError):
            read_snapshot(out)

    def test_read_without_file_is_an_error(self) -> None:
        with self.assertRaises(SnapshotFileError):
            read_snapshot(self._repo.path / "없는스냅샷.json")

    def test_outside_a_repository_is_an_error(self) -> None:
        with self.assertRaises(NotAGitRepository):
            snapshot(Path("/"))


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)
        self.snap = self._repo.path / WORK_DIR / "snap.json"

    def _plan(self, paths: list[str]) -> Path:
        return self._repo.write(f"{WORK_DIR}/01-plan.md", plan_text(paths))

    def test_change_inside_scope_passes(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("src/a.py", "x = 1\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertTrue(result.ok)
        self.assertEqual(result.changed, frozenset({"src/a.py"}))
        self.assertEqual(result.violations, frozenset())

    def test_change_outside_scope_is_a_violation(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("src/a.py", "x = 1\n")
        self._repo.write("src/sneaky.py", "x = 2\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertFalse(result.ok)
        self.assertEqual(result.violations, frozenset({"src/sneaky.py"}))

    def test_work_directory_changes_are_not_violations(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("src/a.py", "x = 1\n")
        self._repo.write(f"{WORK_DIR}/02-implement.log", "로그가 쌓인다\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertTrue(result.ok)
        self.assertEqual(result.changed, frozenset({"src/a.py"}))

    def test_no_change_is_not_ok(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)

        result = check(self._repo.path, plan, self.snap)

        self.assertTrue(result.nothing_changed)
        self.assertFalse(result.ok)

    def test_edit_to_already_untracked_file_is_caught(self) -> None:
        self._repo.write("src/draft.py", "x = 1\n")
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("src/draft.py", "x = 999\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertEqual(result.violations, frozenset({"src/draft.py"}))

    def test_tracked_file_edit_is_caught(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("README.md", "바뀐 내용\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertEqual(result.violations, frozenset({"README.md"}))

    def test_deletion_is_caught(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.remove("README.md")

        result = check(self._repo.path, plan, self.snap)

        self.assertEqual(result.violations, frozenset({"README.md"}))

    def test_revert_to_original_counts_as_change(self) -> None:
        self._repo.write("README.md", "임시로 바꿈\n")
        plan = self._plan(["README.md"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("README.md", "시작\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertEqual(result.changed, frozenset({"README.md"}))
        self.assertTrue(result.ok)

    def test_rename_reports_both_paths(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.git("mv", "README.md", "GUIDE.md")

        result = check(self._repo.path, plan, self.snap)

        self.assertEqual(result.violations, frozenset({"README.md", "GUIDE.md"}))


if __name__ == "__main__":
    unittest.main()

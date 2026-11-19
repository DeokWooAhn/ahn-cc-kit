from __future__ import annotations

import json
import unittest
from pathlib import Path

from orchestrator.errors import NotAGitRepository, PlanFormatError, SnapshotFileError
from orchestrator.scope import (
    MISSING,
    check,
    covers,
    is_ignored,
    missing_slash,
    normalize_ignore,
    parse_allowed,
    read_allowed,
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


class CoversTest(unittest.TestCase):
    def test_exact_path_matches(self) -> None:
        self.assertTrue(covers(["src/a.py"], "src/a.py"))
        self.assertFalse(covers(["src/a.py"], "src/b.py"))

    def test_trailing_slash_opens_the_directory(self) -> None:
        allowed = ["Assets.xcassets/Common/"]

        self.assertTrue(covers(allowed, "Assets.xcassets/Common/icon.imageset/Contents.json"))
        self.assertTrue(covers(allowed, "Assets.xcassets/Common/btn.imageset/btn@2x.png"))

    def test_a_directory_without_a_slash_stays_one_file(self) -> None:
        # presentation 이 모듈 전체를 조용히 여는 것을 막는다. 열려면 슬래시를 붙인다.
        self.assertFalse(covers(["presentation"], "presentation/src/Main.kt"))

    def test_the_slash_does_not_leak_to_a_sibling(self) -> None:
        self.assertFalse(covers(["src/ui/"], "src/ui-test/a.kt"))

    def test_missing_slash_names_what_to_fix(self) -> None:
        found = missing_slash(
            ["Assets.xcassets/Common", "src/a.py"], ["Assets.xcassets/Common/icon.png"]
        )

        self.assertEqual(found, ("Assets.xcassets/Common",))

    def test_missing_slash_is_quiet_when_nothing_would_help(self) -> None:
        self.assertEqual(missing_slash(["src/a.py"], ["other/b.py"]), ())


class ReadAllowedTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)

    def test_a_plan_without_the_section_is_empty_not_an_error(self) -> None:
        plan = self._repo.write("04-fix-plan.md", "# 수정 계획" + chr(10) * 2 + "## 할 일" + chr(10))

        self.assertEqual(read_allowed(plan), frozenset())


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


class CheckWithDirectoriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempRepo().__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)
        self.snap = self._repo.path / WORK_DIR / "snap.json"

    def _plan(self, paths: list[str], name: str = "01-plan.md") -> Path:
        return self._repo.write(f"{WORK_DIR}/{name}", plan_text(paths))

    def test_a_directory_entry_covers_the_files_under_it(self) -> None:
        plan = self._plan(["Assets.xcassets/Common/"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("Assets.xcassets/Common/icon.imageset/Contents.json", "{}\n")
        self._repo.write("Assets.xcassets/Common/btn.imageset/Contents.json", "{}\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertTrue(result.ok)
        self.assertEqual(result.violations, frozenset())

    def test_a_directory_entry_does_not_cover_a_sibling(self) -> None:
        plan = self._plan(["Assets.xcassets/Common/"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("Assets.xcassets/Common/icon.png", "x\n")
        self._repo.write("Assets.xcassets/Other/icon.png", "x\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertEqual(result.violations, frozenset({"Assets.xcassets/Other/icon.png"}))

    def test_the_fix_plan_widens_the_scope(self) -> None:
        # 리뷰를 거치며 범위가 넓어지는 것은 정상 흐름이다. 두 계획의 합집합으로 본다.
        plan = self._plan(["src/a.py"])
        fix = self._plan(["src/b.py"], name="04-fix-plan.md")
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("src/a.py", "x = 1\n")
        self._repo.write("src/b.py", "x = 2\n")

        result = check(self._repo.path, plan, self.snap, also=[fix])

        self.assertTrue(result.ok)
        self.assertEqual(len(result.sources), 2)

    def test_without_the_fix_plan_the_scope_stays_narrow(self) -> None:
        plan = self._plan(["src/a.py"])
        self._plan(["src/b.py"], name="04-fix-plan.md")
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("src/b.py", "x = 2\n")

        result = check(self._repo.path, plan, self.snap)

        self.assertEqual(result.violations, frozenset({"src/b.py"}))
        self.assertEqual(result.sources, (str(plan),))

    def test_a_fix_plan_that_is_not_there_changes_nothing(self) -> None:
        plan = self._plan(["src/a.py"])
        write_snapshot(self._repo.path, self.snap)
        self._repo.write("src/a.py", "x = 1\n")

        result = check(
            self._repo.path, plan, self.snap, also=[self._repo.path / "없는수정계획.md"]
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.sources, (str(plan),))


if __name__ == "__main__":
    unittest.main()

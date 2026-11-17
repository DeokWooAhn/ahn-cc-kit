"""도입·재실행이 사용자 파일과 프로젝트 경계를 보존하는지 확인한다."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "context_pack.py"
NAMES = {"task.md", "files.md", "rules.md", "tests.md", "done.md"}


class ContextPackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project with spaces"
        self.root.mkdir()

    def run_command(self, command, *args, ok=True, env=None):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), command, "--project", str(self.root), *args],
            capture_output=True, text=True, check=False,
            env={**os.environ, **env} if env else None,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_new_project_is_portable_and_repeated_setup_preserves_custom_files(self):
        self.run_command("setup")
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "@AGENTS.md\n")
        entry = (self.root / "AGENTS.md").read_text()
        self.assertIn(".context-pack/workflow.md", entry)
        self.assertFalse(entry.startswith("\n"), "새 지침 파일이 빈 줄로 시작하면 안 된다")
        guide = self.root / ".context-pack"
        self.assertTrue((guide / "workflow.md").is_file())
        self.assertTrue((guide / "integrations.md").is_file())
        self.assertEqual({p.name for p in (guide / "templates").iterdir()}, NAMES)
        (guide / "project.md").write_text("프로젝트에서 확인한 실제 경로\n")
        (guide / "templates/task.md").write_text("이 팀의 작업 양식\n")
        (guide / "workflow.md").write_text("기존 프로젝트의 보완 절차\n")
        before = self.files()
        self.run_command("setup")
        self.assertEqual(self.files(), before)

    def test_claude_only_keeps_existing_team_rules_and_adds_agent_entry(self):
        original = b"# Team\r\n\r\nDo not change production config.\r\n"
        (self.root / "CLAUDE.md").write_bytes(original)
        self.run_command("setup")
        self.assertTrue((self.root / "CLAUDE.md").read_bytes().startswith(original))
        self.assertIn("CLAUDE.md", (self.root / "AGENTS.md").read_text())
        before = self.files()
        self.run_command("setup")
        self.assertEqual(self.files(), before)

    def test_linked_instruction_entry_is_not_rewritten(self):
        (self.root / "AGENTS.md").write_text("# 팀 지침\n")
        original = "@AGENTS.md\n\n# Claude 전용\n"
        (self.root / "CLAUDE.md").write_text(original)
        self.run_command("setup")
        self.assertEqual((self.root / "CLAUDE.md").read_text(), original)

    def test_independent_instructions_need_an_explicit_source_before_any_write(self):
        (self.root / "AGENTS.md").write_text("팀 정본 후보\n")
        (self.root / "CLAUDE.md").write_text("다른 정본 후보\n")
        before = self.files()
        self.run_command("setup", ok=False)
        self.assertEqual(self.files(), before)
        self.run_command("setup", "--instructions", "AGENTS.md")
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "다른 정본 후보\n")

    def test_private_adoption_does_not_create_or_change_team_instructions(self):
        (self.root / "AGENTS.md").write_text("팀 규칙\n")
        (self.root / "CLAUDE.local.md").write_text("개인 규칙\n")
        self.run_command("setup", "--instructions", "CLAUDE.local.md")
        self.assertEqual((self.root / "AGENTS.md").read_text(), "팀 규칙\n")
        self.assertFalse((self.root / "CLAUDE.md").exists())
        self.assertTrue((self.root / "CLAUDE.local.md").read_text().startswith("개인 규칙\n"))

    def test_broken_managed_block_fails_before_copying_resources(self):
        (self.root / "AGENTS.md").write_text("# Team\n<!-- context-pack:start -->\n")
        before = self.files()
        self.run_command("setup", ok=False)
        self.assertEqual(self.files(), before)

    def test_standalone_new_creates_five_files_without_adopting_project(self):
        self.run_command("new", "--task", "fix-checkout")
        folder = self.root / "context/fix-checkout"
        self.assertEqual({p.name for p in folder.iterdir()}, NAMES)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".context-pack").exists())
        (folder / "task.md").write_text("AI가 근거로 채운 내용\n")
        before = self.files()
        self.run_command("new", "--task", "fix-checkout")
        self.assertEqual(self.files(), before)

    def test_new_uses_custom_project_templates(self):
        self.run_command("setup")
        (self.root / ".context-pack/templates/task.md").write_text("프로젝트 양식\n")
        self.run_command("new", "--task", "20261117-checkout")
        self.assertEqual((self.root / "context/20261117-checkout/task.md").read_text(), "프로젝트 양식\n")

    def test_incomplete_existing_pack_is_never_filled_or_replaced(self):
        folder = self.root / "context/existing"
        folder.mkdir(parents=True)
        (folder / "task.md").write_text("작성 중인 메모\n")
        before = self.files()
        self.run_command("new", "--task", "existing", ok=False)
        self.assertEqual(self.files(), before)

    def test_invalid_task_names_cannot_escape_project(self):
        for task in ("../outside", "/absolute", "a/b", ".", "", "-name", "name-", "x" * 81):
            with self.subTest(task=task):
                self.run_command("new", "--task", task, ok=False)
        self.assertFalse((self.root / "context").exists())

    def test_symlink_cannot_redirect_installed_resources_or_packs(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        for name, command, args in ((".context-pack", "setup", ()), ("context", "new", ("--task", "test"))):
            with self.subTest(name=name):
                link = self.root / name
                link.symlink_to(outside, target_is_directory=True)
                self.run_command(command, *args, ok=False)
                self.assertEqual(list(outside.iterdir()), [])
                link.unlink()

    def test_instruction_symlink_outside_project_is_not_written(self):
        outside = Path(self.temp.name) / "external.md"
        outside.write_text("공유하지 않은 개인 지침\n")
        (self.root / "AGENTS.md").symlink_to(outside)
        self.run_command("setup", ok=False)
        self.assertEqual(outside.read_text(), "공유하지 않은 개인 지침\n")
        self.assertFalse((self.root / ".context-pack").exists())

    def test_setup_succeeds_when_the_runtime_encoding_is_not_utf8(self):
        """UTF-8 모드가 꺼진 환경에서도 한국어 템플릿을 읽고 안내를 출력해야 한다."""
        ascii_only = {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
        self.run_command("setup", env=ascii_only)
        self.assertTrue((self.root / ".context-pack/project.md").is_file())
        self.assertIn(".context-pack/workflow.md", (self.root / "AGENTS.md").read_text())

    def test_file_in_directory_position_fails_before_writing(self):
        (self.root / ".context-pack").write_text("이름이 겹친 기존 파일\n")
        before = self.files()
        self.run_command("setup", ok=False)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()

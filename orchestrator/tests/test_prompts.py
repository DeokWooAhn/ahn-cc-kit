from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import prompts
from orchestrator.errors import PlanFormatError, PluginDocsMissing
from support import plan_text


class SectionTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="orchestrator-prompts-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, text: str) -> Path:
        path = self.dir / "01-plan.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_splits_on_headings(self) -> None:
        plan = self.write("# 제목\n\n## 목적\n\n고친다.\n\n## 할 일\n\n하나\n")

        found = prompts.read_sections(plan)

        self.assertEqual(found["목적"], "고친다.")
        self.assertEqual(found["할 일"], "하나")

    def test_a_heading_inside_a_code_block_is_not_a_section(self) -> None:
        plan = self.write(
            "## 목적\n\n설명한다.\n\n```markdown\n## 목적\n\n이건 예시다\n```\n\n## 검증\n\n```\ntrue\n```\n"
        )

        found = prompts.read_sections(plan)

        self.assertIn("```markdown", found["목적"])
        self.assertIn("이건 예시다", found["목적"])
        self.assertEqual(sorted(found), ["검증", "목적"])

    def test_missing_section_is_an_error(self) -> None:
        plan = self.write("## 목적\n\n고친다.\n")

        with self.assertRaises(PlanFormatError):
            prompts.section(plan, "검증")

    def test_optional_section_comes_back_empty(self) -> None:
        plan = self.write("## 목적\n\n고친다.\n")

        self.assertEqual(prompts.section(plan, "지킬 것", required=False), "")

    def test_first_block_only(self) -> None:
        body = "앞말\n\n```\n./gradlew test\n./gradlew detekt\n```\n\n```\n두 번째는 안 본다\n```"

        self.assertEqual(prompts.first_block(body), ["./gradlew test", "./gradlew detekt"])

    def test_verify_commands_come_from_the_plan(self) -> None:
        plan = self.write(plan_text(["a.txt"], verify="echo 통과"))

        self.assertEqual(prompts.verify_commands(plan), ["echo 통과"])


class PluginDirTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="orchestrator-plugin-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def make_plugin(self, root: Path) -> Path:
        references = root / prompts.REFERENCE_DIR
        references.mkdir(parents=True)
        (references / prompts.PLAN_TEMPLATE).write_text("# 계획 형식\n", encoding="utf-8")
        (references / prompts.GOTCHAS).write_text("# 함정\n", encoding="utf-8")
        return root

    def test_explicit_wins(self) -> None:
        plugin = self.make_plugin(self.dir / "plugin")

        self.assertEqual(prompts.find_plugin_dir(plugin), plugin)

    def test_environment_variable(self) -> None:
        plugin = self.make_plugin(self.dir / "from-env")

        with mock.patch.dict(os.environ, {prompts.PLUGIN_DIR_ENV: str(plugin)}):
            self.assertEqual(prompts.find_plugin_dir(), plugin)

    def test_a_directory_without_the_reference_is_skipped(self) -> None:
        empty = self.dir / "empty"
        empty.mkdir()
        plugin = self.make_plugin(self.dir / "real")

        with mock.patch.dict(os.environ, {prompts.PLUGIN_DIR_ENV: str(plugin)}):
            self.assertEqual(prompts.find_plugin_dir(empty), plugin)

    def test_missing_reference_file_is_an_error(self) -> None:
        plugin = self.make_plugin(self.dir / "plugin")

        with self.assertRaises(PluginDocsMissing):
            prompts.read_reference(plugin, "없는문서.md")


class BuiltPromptTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="orchestrator-built-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        references = self.dir / "plugin" / prompts.REFERENCE_DIR
        references.mkdir(parents=True)
        (references / prompts.PLAN_TEMPLATE).write_text("계획 템플릿 본문", encoding="utf-8")
        (references / prompts.GOTCHAS).write_text("함정 본문", encoding="utf-8")
        self.plugin = self.dir / "plugin"
        self.plan = self.dir / "01-plan.md"

    def write_plan(self, extra: str = "") -> Path:
        self.plan.write_text(
            "# 시험\n\n## 목적\n\n늦은 응답을 막는다.\n\n"
            "## 건드릴 파일\n\n```\na.txt\n```\n\n"
            "## 검증\n\n```\ntrue\n```\n" + extra,
            encoding="utf-8",
        )
        return self.plan

    def test_plan_prompt_carries_the_template(self) -> None:
        text = prompts.plan_prompt("환율 로딩을 고친다", self.plan, self.plugin)

        self.assertIn("환율 로딩을 고친다", text)
        self.assertIn("계획 템플릿 본문", text)
        self.assertIn(str(self.plan), text)
        self.assertIn("코드는 한 줄도 고치지 않는다", text)

    def test_implement_prompt_carries_the_gotchas_and_the_bans(self) -> None:
        text = prompts.implement_prompt(self.write_plan(), self.plugin)

        self.assertIn("함정 본문", text)
        self.assertIn("커밋하지 않는다", text)
        self.assertIn("겸사겸사 고치지 않는다", text)
        self.assertIn("틀렸으면 틀렸다고 드러나게 한다", text)

    def test_review_prompt_carries_the_purpose_and_the_files(self) -> None:
        text = prompts.review_prompt(self.write_plan(), ["a.txt", "b.txt"], self.plugin)

        self.assertIn("늦은 응답을 막는다", text)
        self.assertIn("`a.txt`", text)
        self.assertIn("`b.txt`", text)
        self.assertIn("통과하도록 짜인 것은 아닌가", text)
        self.assertIn("코드를 고치지 않는다", text)

    def test_review_prompt_leaves_out_the_implementer_conclusion(self) -> None:
        plan = self.write_plan("\n## 가설\n\n1. 지난 응답이 현재 로딩을 끈다 — 확정됐다\n")

        text = prompts.review_prompt(plan, ["a.txt"], self.plugin)

        self.assertNotIn("확정됐다", text)
        self.assertNotIn("가설", text)
        self.assertIn("구현자의 보고는 주어지지 않는다", text)

    def test_review_prompt_carries_the_limits_when_the_plan_has_them(self) -> None:
        plan = self.write_plan(
            "\n## 이 작업으로 확인할 수 없는 것\n\n실기기 동작은 보지 않는다.\n"
        )

        text = prompts.review_prompt(plan, ["a.txt"], self.plugin)

        self.assertIn("실기기 동작은 보지 않는다", text)

    def test_fix_prompt_narrows_to_the_fix_plan(self) -> None:
        fix_plan = self.dir / "04-fix-plan.md"

        text = prompts.fix_prompt(fix_plan, self.plugin)

        self.assertIn(str(fix_plan), text)
        self.assertIn("거기 적힌 것만 고친다", text)
        self.assertIn("빠진 지적을 겸사겸사 고치지 않는다", text)

class CheckPlanTest(SectionTest):
    def full_plan(self, **drop) -> str:
        parts = {
            "목적": "늦은 응답을 막는다.",
            "할 일": "1. 고친다",
            "건드릴 파일": "```\na.txt\n```",
            "지킬 것": "- 커밋하지 않는다",
            "검증": "```\ntrue\n```",
            "이 작업으로 확인할 수 없는 것": "- 실기기 동작",
            "완료 조건": "- 테스트가 통과한다",
        }
        parts.update(drop)
        body = "\n\n".join(
            f"## {name}\n\n{text}" for name, text in parts.items() if text is not None
        )
        return f"# 시험\n\n{body}\n"

    def test_a_complete_plan_passes(self) -> None:
        plan = self.write(self.full_plan())

        checked = prompts.check_plan(plan)

        self.assertTrue(checked.ok)
        self.assertEqual(checked.advisory, ())

    def test_a_missing_required_section_is_reported(self) -> None:
        plan = self.write(self.full_plan(검증=None))

        checked = prompts.check_plan(plan)

        self.assertFalse(checked.ok)
        self.assertIn("검증", checked.missing)
        self.assertIn("`## 검증`", checked.describe())

    def test_an_empty_required_section_counts_as_missing(self) -> None:
        plan = self.write(self.full_plan(목적="   "))

        self.assertIn("목적", prompts.check_plan(plan).missing)

    def test_an_empty_code_block_is_reported(self) -> None:
        plan = self.write(self.full_plan(**{"건드릴 파일": "```\n```"}))

        checked = prompts.check_plan(plan)

        self.assertFalse(checked.ok)
        self.assertIn("건드릴 파일", checked.empty_blocks)

    def test_a_section_without_a_code_block_is_reported(self) -> None:
        plan = self.write(self.full_plan(**{"건드릴 파일": "a.txt 를 고친다"}))

        self.assertIn("건드릴 파일", prompts.check_plan(plan).empty_blocks)

    def test_advisory_sections_do_not_block(self) -> None:
        plan = self.write(self.full_plan(**{"이 작업으로 확인할 수 없는 것": None}))

        checked = prompts.check_plan(plan)

        self.assertTrue(checked.ok)
        self.assertIn("이 작업으로 확인할 수 없는 것", checked.advisory)
        self.assertIn("막지는 않음", checked.describe())

    def test_the_sections_the_runtime_actually_parses_are_required(self) -> None:
        self.assertEqual(
            set(prompts.REQUIRED_SECTIONS),
            {prompts.PURPOSE_SECTION, prompts.ALLOWED_SECTION, prompts.VERIFY_SECTION},
        )

class RiskTest(SectionTest):
    def plan_with(self, risk_body: str | None) -> Path:
        risk = "" if risk_body is None else f"## 위험도\n\n{risk_body}\n\n"
        return self.write(f"# 시험\n\n## 목적\n\n고친다.\n\n{risk}## 검증\n\n```\ntrue\n```\n")

    def test_each_level_is_read(self) -> None:
        for body, expected in (("low", prompts.LOW), ("medium", prompts.MEDIUM), ("high", prompts.HIGH)):
            self.assertEqual(prompts.read_risk(self.plan_with(body)), expected)

    def test_a_sentence_around_the_word_still_reads(self) -> None:
        plan = self.plan_with("high — 결제 흐름에 닿는다")

        self.assertEqual(prompts.read_risk(plan), prompts.HIGH)

    def test_uppercase_is_read(self) -> None:
        self.assertEqual(prompts.read_risk(self.plan_with("HIGH")), prompts.HIGH)

    def test_the_highest_word_present_wins(self) -> None:
        plan = self.plan_with("low 가 아니라 high 다")

        self.assertEqual(prompts.read_risk(plan), prompts.HIGH)

    def test_a_missing_section_means_medium(self) -> None:
        plan = self.plan_with(None)

        self.assertEqual(prompts.read_risk(plan), prompts.MEDIUM)
        self.assertFalse(prompts.risk_is_stated(plan))

    def test_an_unreadable_section_means_medium(self) -> None:
        plan = self.plan_with("보통쯤 된다")

        self.assertEqual(prompts.read_risk(plan), prompts.MEDIUM)
        self.assertTrue(prompts.risk_is_stated(plan))

    def test_higher_risk_means_fewer_fix_rounds(self) -> None:
        limits = [prompts.risk_retry_limit(r) for r in (prompts.LOW, prompts.MEDIUM, prompts.HIGH)]

        self.assertEqual(limits, [3, 2, 1])
        self.assertEqual(sorted(limits, reverse=True), limits)

    def test_an_unknown_level_falls_back_to_medium(self) -> None:
        self.assertEqual(prompts.risk_retry_limit("치명적"), 2)


if __name__ == "__main__":
    unittest.main()

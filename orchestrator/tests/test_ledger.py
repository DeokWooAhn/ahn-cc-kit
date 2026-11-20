from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator import ledger
from orchestrator.ledger import Call


def call(**overrides) -> Call:
    values = {
        "at": "2026-11-20T01:00:00+00:00",
        "task_id": "20261120-일",
        "role": "implementer",
        "kind": ledger.AGENT,
        "tool": "claude",
        "effort": None,
        "attempt": 0,
        "outcome": "ok",
        "seconds": 60.0,
        "log_bytes": 1000,
    }
    values.update(overrides)
    return Call(**values)


class RecordTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_a_call_comes_back_as_it_went_in(self) -> None:
        ledger.record(self.dir, call(seconds=12.5, effort="xhigh", attempt=1))

        back = ledger.read_task(self.dir)

        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].seconds, 12.5)
        self.assertEqual(back[0].effort, "xhigh")
        self.assertEqual(back[0].attempt, 1)

    def test_calls_pile_up_instead_of_replacing(self) -> None:
        ledger.record(self.dir, call(role="implementer"))
        ledger.record(self.dir, call(role="reviewer"))

        self.assertEqual([one.role for one in ledger.read_task(self.dir)],
                         ["implementer", "reviewer"])

    def test_a_broken_line_does_not_take_the_rest_down(self) -> None:
        ledger.record(self.dir, call(role="implementer"))
        with (self.dir / ledger.LEDGER).open("a", encoding="utf-8") as handle:
            handle.write("{쓰다 끊긴 줄\n")
        ledger.record(self.dir, call(role="reviewer"))

        self.assertEqual(len(ledger.read_task(self.dir)), 2)

    def test_a_ledger_that_cannot_be_written_does_not_raise(self) -> None:
        # 재려다가 재는 대상을 망가뜨리면 안 된다.
        blocked = self.dir / "파일"
        blocked.write_text("디렉터리가 아니다", encoding="utf-8")

        ledger.record(blocked / "안쪽", call())

        self.assertEqual(ledger.read_task(blocked / "안쪽"), [])

    def test_no_ledger_reads_as_empty(self) -> None:
        self.assertEqual(ledger.read_task(self.dir / "없는곳"), [])
        self.assertEqual(ledger.read(self.dir / "없는곳"), [])

    def test_read_gathers_every_task(self) -> None:
        for name in ("20261120-가", "20261120-나"):
            ledger.record(self.dir / name, call(task_id=name))

        self.assertEqual(len(ledger.read(self.dir)), 2)

    def test_the_line_is_json_one_per_call(self) -> None:
        ledger.record(self.dir, call())

        text = (self.dir / ledger.LEDGER).read_text(encoding="utf-8")

        self.assertEqual(len(text.splitlines()), 1)
        self.assertEqual(json.loads(text)["role"], "implementer")


class SummaryTest(unittest.TestCase):
    def test_the_same_role_tool_and_rung_fall_in_one_row(self) -> None:
        rows = ledger.summarize([call(seconds=10), call(seconds=20)])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count, 2)
        self.assertEqual(rows[0].seconds, 30)
        self.assertEqual(rows[0].average, 15)

    def test_a_different_rung_is_a_different_row(self) -> None:
        rows = ledger.summarize([call(), call(effort="xhigh", attempt=1)])

        self.assertEqual(len(rows), 2)

    def test_the_heaviest_row_comes_first(self) -> None:
        rows = ledger.summarize([
            call(role="reviewer", seconds=10),
            call(role="implementer", seconds=100),
        ])

        self.assertEqual(rows[0].role, "implementer")

    def test_anything_but_ok_counts_as_failed(self) -> None:
        rows = ledger.summarize([call(outcome="ok"), call(outcome="timeout")])

        self.assertEqual(rows[0].failed, 1)

    def test_a_call_without_a_rung_says_it_took_the_tool_default(self) -> None:
        self.assertEqual(call(effort=None).rung, ledger.TOOL_DEFAULT)

    def test_verification_has_no_rung_at_all(self) -> None:
        # 사람이 계획에 적은 셸 명령이다. 등급이라는 것이 없다.
        self.assertEqual(call(kind=ledger.VERIFY, role="verify", tool="sh").rung, "-")


class SpokenTest(unittest.TestCase):
    def test_under_a_minute_stays_in_seconds(self) -> None:
        self.assertEqual(ledger.spoken(42), "42초")

    def test_minutes_carry_the_leftover_seconds(self) -> None:
        self.assertEqual(ledger.spoken(125), "2분 5초")

    def test_a_round_minute_drops_the_seconds(self) -> None:
        self.assertEqual(ledger.spoken(120), "2분")

    def test_hours_drop_the_seconds(self) -> None:
        self.assertEqual(ledger.spoken(3725), "1시간 2분")

    def test_a_round_hour_drops_the_minutes(self) -> None:
        self.assertEqual(ledger.spoken(3600), "1시간")


class TableTest(unittest.TestCase):
    def test_korean_columns_line_up(self) -> None:
        # 한글은 터미널에서 두 칸을 먹는다. 그걸 세지 않으면 표가 어긋난다.
        lines = ledger.table(ledger.summarize([
            call(role="implementer", seconds=100),
            call(role="reviewer", tool="codex", seconds=10),
        ]))

        self.assertEqual(len({ledger._width(line) for line in lines}), 1)

    def test_the_header_comes_first(self) -> None:
        lines = ledger.table(ledger.summarize([call()]))

        self.assertIn("역할", lines[0])
        self.assertEqual(len(lines), 2)

    def test_no_failure_shows_a_dash(self) -> None:
        lines = ledger.table(ledger.summarize([call(outcome="ok")]))

        self.assertTrue(lines[1].rstrip().endswith("-"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.errors import InvalidTransition, StateFileError
from orchestrator.state import (
    SCHEMA_VERSION,
    RunState,
    StateStore,
    is_blocked,
    is_terminal,
    needs_human,
)


class StateStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="orchestrator-state-")
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "nested" / "state.json"
        self.store = StateStore(self.path)

    def test_create_makes_parent_directories(self) -> None:
        state = self.store.create("20261115-sample")

        self.assertTrue(self.path.is_file())
        self.assertEqual(state.task_id, "20261115-sample")
        self.assertEqual(state.state, RunState.CREATED)

    def test_create_refuses_to_overwrite(self) -> None:
        self.store.create("first")

        with self.assertRaises(StateFileError):
            self.store.create("second")

        self.assertEqual(self.store.load().task_id, "first")

    def test_round_trip_keeps_fields(self) -> None:
        self.store.create("task")
        self.store.record_artifact("plan", "/tmp/01-plan.md")
        self.store.transition(RunState.PLANNING, note="계획 시작")

        loaded = self.store.load()

        self.assertEqual(loaded.state, RunState.PLANNING)
        self.assertEqual(loaded.artifacts["plan"], "/tmp/01-plan.md")
        self.assertEqual(loaded.note, "계획 시작")
        self.assertEqual(len(loaded.history), 1)
        self.assertEqual(loaded.history[0].previous, "created")
        self.assertEqual(loaded.history[0].current, "planning")

    def test_transition_appends_history_in_order(self) -> None:
        self.store.create("task")
        self.store.transition(RunState.PLANNING)
        self.store.transition(RunState.PLAN_APPROVAL)
        self.store.transition(RunState.IMPLEMENTING)

        history = self.store.load().history

        self.assertEqual(
            [record.current for record in history],
            ["planning", "plan_approval", "implementing"],
        )

    def test_terminal_state_refuses_further_transition(self) -> None:
        self.store.create("task")
        self.store.transition(RunState.COMPLETED)

        with self.assertRaises(InvalidTransition):
            self.store.transition(RunState.PLANNING)

    def test_blocked_state_can_still_move(self) -> None:
        self.store.create("task")
        self.store.transition(RunState.BLOCKED_SCOPE, note="범위 위반")

        self.store.transition(RunState.FIX_PLANNING)

        self.assertEqual(self.store.load().state, RunState.FIX_PLANNING)

    def test_bump_retry_marks_exceeded_past_limit(self) -> None:
        self.store.create("task")

        self.store.bump_retry(limit=2)
        self.store.bump_retry(limit=2)
        self.assertEqual(self.store.load().state, RunState.CREATED)

        state = self.store.bump_retry(limit=2)

        self.assertEqual(state.state, RunState.MAX_RETRY_EXCEEDED)
        # 막힌 시도는 돌지 않았으므로 세지 않는다.
        self.assertEqual(state.retry_count, 2)

    def test_bump_retry_records_the_transition(self) -> None:
        self.store.create("task")
        self.store.transition(RunState.FIXING)
        self.store.bump_retry(limit=1)

        self.store.bump_retry(limit=1)

        last = self.store.load().history[-1]
        self.assertEqual(last.previous, str(RunState.FIXING))
        self.assertEqual(last.current, str(RunState.MAX_RETRY_EXCEEDED))

    def test_a_raised_limit_allows_one_more_round(self) -> None:
        self.store.create("task")
        self.store.bump_retry(limit=1)
        self.store.bump_retry(limit=1)
        self.assertEqual(self.store.load().state, RunState.MAX_RETRY_EXCEEDED)

        self.store.transition(RunState.FIXING)
        state = self.store.bump_retry(limit=2)

        self.assertEqual(state.state, RunState.FIXING)
        self.assertEqual(state.retry_count, 2)

    def test_load_rejects_broken_json(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{ 이건 json이 아니다", encoding="utf-8")

        with self.assertRaises(StateFileError):
            self.store.load()

    def test_load_rejects_other_schema_version(self) -> None:
        self.store.create("task")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["schema_version"] = SCHEMA_VERSION + 1
        self.path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(StateFileError):
            self.store.load()

    def test_load_rejects_unknown_state(self) -> None:
        self.store.create("task")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["state"] = "날아가는중"
        self.path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(StateFileError):
            self.store.load()

    def test_load_without_file_is_an_error(self) -> None:
        with self.assertRaises(StateFileError):
            self.store.load()

    def test_save_leaves_no_temporary_files(self) -> None:
        self.store.create("task")
        self.store.transition(RunState.PLANNING)

        leftovers = [entry.name for entry in self.path.parent.iterdir() if entry.name.endswith(".tmp")]

        self.assertEqual(leftovers, [])

    def test_saved_file_is_readable_utf8_json(self) -> None:
        self.store.create("task")
        self.store.transition(RunState.BLOCKED_GIT, note="커밋이 생겼다")

        data = json.loads(self.path.read_text(encoding="utf-8"))

        self.assertEqual(data["note"], "커밋이 생겼다")
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)


class StateClassificationTest(unittest.TestCase):
    def test_blocked_states(self) -> None:
        self.assertTrue(is_blocked(RunState.BLOCKED_SCOPE))
        self.assertTrue(is_blocked(RunState.BLOCKED_GIT))
        self.assertTrue(is_blocked(RunState.FAILED_AGENT))
        self.assertFalse(is_blocked(RunState.REVIEWING))

    def test_human_states(self) -> None:
        self.assertTrue(needs_human(RunState.PLAN_APPROVAL))
        self.assertTrue(needs_human(RunState.WAITING_HUMAN))
        self.assertFalse(needs_human(RunState.IMPLEMENTING))

    def test_terminal_states(self) -> None:
        self.assertTrue(is_terminal(RunState.COMPLETED))
        self.assertFalse(is_terminal(RunState.BLOCKED_SCOPE))


if __name__ == "__main__":
    unittest.main()

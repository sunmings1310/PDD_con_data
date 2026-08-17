from __future__ import annotations

import unittest

from server.task_state import (
    ITEM_TERMINAL,
    TASK_TERMINAL,
    StateConflict,
    TaskItemStatus,
    TaskStatus,
    aggregate_task_result,
    map_android_completion,
    map_desktop_status,
    validate_item_transition,
    validate_task_transition,
    task_status,
    task_storage_status,
)
from task_runner import map_desktop_status_to_server


class TaskStateTest(unittest.TestCase):
    def test_initial_and_terminal_sets(self):
        self.assertEqual(TaskStatus.PENDING.value, "pending")
        self.assertIn(TaskStatus.TIMED_OUT, TASK_TERMINAL)
        self.assertIn(TaskItemStatus.NOT_MATCHED, ITEM_TERMINAL)

    def test_all_legal_task_transitions(self):
        legal = {
            (TaskStatus.PENDING, TaskStatus.RUNNING),
            (TaskStatus.PENDING, TaskStatus.CANCELLED),
            *((TaskStatus.RUNNING, value) for value in TASK_TERMINAL),
        }
        for current, requested in legal:
            with self.subTest(current=current, requested=requested):
                self.assertTrue(validate_task_transition(current, requested))

    def test_illegal_task_transitions_and_terminal_protection(self):
        for current in TaskStatus:
            for requested in TaskStatus:
                if current == requested:
                    self.assertFalse(validate_task_transition(current, requested))
                    continue
                legal = requested in ({TaskStatus.RUNNING, TaskStatus.CANCELLED} if current == TaskStatus.PENDING else TASK_TERMINAL if current == TaskStatus.RUNNING else set())
                if not legal:
                    with self.assertRaises(StateConflict):
                        validate_task_transition(current, requested)

    def test_legacy_done_is_idempotent_success(self):
        self.assertFalse(validate_task_transition("done", TaskStatus.SUCCEEDED))
        with self.assertRaises(StateConflict):
            validate_task_transition("done", TaskStatus.FAILED)

    def test_partial_success_uses_varchar16_storage_compatibility(self):
        self.assertEqual(task_storage_status(TaskStatus.PARTIALLY_SUCCEEDED), "partial_success")
        self.assertEqual(task_status("partial_success"), TaskStatus.PARTIALLY_SUCCEEDED)

    def test_item_transitions_and_terminal_protection(self):
        self.assertTrue(validate_item_transition("pending", "running"))
        for terminal in ITEM_TERMINAL:
            self.assertTrue(validate_item_transition("running", terminal))
            self.assertFalse(validate_item_transition(terminal, terminal))
            with self.assertRaises(StateConflict):
                validate_item_transition(terminal, TaskItemStatus.RUNNING)

    def test_task_item_aggregation(self):
        self.assertEqual(aggregate_task_result(["succeeded", "succeeded"]), TaskStatus.SUCCEEDED)
        self.assertEqual(aggregate_task_result(["succeeded", "failed"]), TaskStatus.PARTIALLY_SUCCEEDED)
        self.assertEqual(aggregate_task_result(["not_matched", "failed"]), TaskStatus.FAILED)
        self.assertEqual(aggregate_task_result([], success_count=2, fail_count=1), TaskStatus.PARTIALLY_SUCCEEDED)
        self.assertEqual(aggregate_task_result([], success_count=2), TaskStatus.SUCCEEDED)

    def test_android_mapping_and_unknown(self):
        self.assertEqual(map_android_completion("finished"), "complete")
        self.assertEqual(map_android_completion("stopped"), "cancelled")
        self.assertEqual(map_android_completion("failed"), "failed")
        with self.assertRaisesRegex(ValueError, "unknown Android"):
            map_android_completion("mystery")

    def test_desktop_mapping_and_unknown(self):
        expected = {
            "running": "running", "paused": "running", "stopped": "cancelled",
            "finished": "complete", "failed": "failed", "interrupted": "failed",
        }
        for local, server in expected.items():
            self.assertEqual(map_desktop_status(local), server)
            self.assertEqual(map_desktop_status_to_server(local), server)
        with self.assertRaisesRegex(ValueError, "unknown desktop"):
            map_desktop_status("mystery")


if __name__ == "__main__":
    unittest.main()

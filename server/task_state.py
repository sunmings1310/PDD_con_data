"""Authoritative task state definitions and transition helpers.

This module is deliberately independent from FastAPI and Oracle so the state
contract can be tested without infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TaskItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NOT_MATCHED = "not_matched"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


TASK_TERMINAL = frozenset(
    {
        TaskStatus.SUCCEEDED,
        TaskStatus.PARTIALLY_SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.TIMED_OUT,
    }
)
TASK_CANCELLABLE = frozenset({TaskStatus.PENDING, TaskStatus.RUNNING})
TASK_RETRYABLE = frozenset(
    {TaskStatus.PARTIALLY_SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT}
)
TASK_TRANSITIONS = {
    TaskStatus.PENDING: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: TASK_TERMINAL,
}

ITEM_TERMINAL = frozenset(
    {
        TaskItemStatus.SUCCEEDED,
        TaskItemStatus.NOT_MATCHED,
        TaskItemStatus.FAILED,
        TaskItemStatus.CANCELLED,
    }
)
ITEM_TRANSITIONS = {
    TaskItemStatus.PENDING: frozenset(
        {
            TaskItemStatus.RUNNING,
            TaskItemStatus.SUCCEEDED,
            TaskItemStatus.NOT_MATCHED,
            TaskItemStatus.FAILED,
            TaskItemStatus.CANCELLED,
        }
    ),
    TaskItemStatus.RUNNING: ITEM_TERMINAL,
}


@dataclass(frozen=True)
class StateConflict(ValueError):
    code: str
    current: str
    requested: str

    def __str__(self) -> str:
        return f"{self.code}: {self.current} -> {self.requested}"


def task_status(value: str | TaskStatus) -> TaskStatus:
    """Parse current storage values, including the deprecated successful value."""
    if value == "done":
        return TaskStatus.SUCCEEDED
    # Oracle baseline is VARCHAR2(16); keep the logical API value while schema
    # migration is explicitly outside T003.
    if value == "partial_success":
        return TaskStatus.PARTIALLY_SUCCEEDED
    return TaskStatus(value)


def task_storage_status(value: str | TaskStatus) -> str:
    parsed = task_status(value)
    return "partial_success" if parsed == TaskStatus.PARTIALLY_SUCCEEDED else parsed.value


def item_status(value: str | TaskItemStatus) -> TaskItemStatus:
    """Parse current storage values, including the deprecated successful value."""
    if value == "done":
        return TaskItemStatus.SUCCEEDED
    return TaskItemStatus(value)


def validate_task_transition(current: str | TaskStatus, requested: str | TaskStatus) -> bool:
    """Return False for an idempotent repeat; raise for a conflicting transition."""
    cur, new = task_status(current), task_status(requested)
    if cur == new:
        return False
    if new not in TASK_TRANSITIONS.get(cur, frozenset()):
        raise StateConflict("TASK_STATE_CONFLICT", cur.value, new.value)
    return True


def validate_item_transition(current: str | TaskItemStatus, requested: str | TaskItemStatus) -> bool:
    cur, new = item_status(current), item_status(requested)
    if cur == new:
        return False
    if new not in ITEM_TRANSITIONS.get(cur, frozenset()):
        raise StateConflict("TASK_ITEM_STATE_CONFLICT", cur.value, new.value)
    return True


def aggregate_task_result(
    statuses: Iterable[str | TaskItemStatus], *, success_count: int = 0, fail_count: int = 0
) -> TaskStatus:
    """Derive the completed task result from authoritative item/results counts."""
    parsed = [item_status(value) for value in statuses]
    succeeded = sum(value == TaskItemStatus.SUCCEEDED for value in parsed)
    unsuccessful = sum(
        value in {TaskItemStatus.NOT_MATCHED, TaskItemStatus.FAILED, TaskItemStatus.CANCELLED}
        for value in parsed
    )
    # Ordinary collection currently records products/counters rather than item results.
    succeeded = max(succeeded, max(0, int(success_count)))
    unsuccessful = max(unsuccessful, max(0, int(fail_count)))
    if succeeded and unsuccessful:
        return TaskStatus.PARTIALLY_SUCCEEDED
    if succeeded:
        return TaskStatus.SUCCEEDED
    return TaskStatus.FAILED


ANDROID_COMPLETION_MAP = {
    "finished": "complete",
    "failed": TaskStatus.FAILED.value,
    "stopped": TaskStatus.CANCELLED.value,
}

DESKTOP_STATUS_MAP = {
    "running": TaskStatus.RUNNING.value,
    "paused": TaskStatus.RUNNING.value,
    "pause": TaskStatus.RUNNING.value,
    "stopped": TaskStatus.CANCELLED.value,
    "stop": TaskStatus.CANCELLED.value,
    "finished": "complete",
    "failed": TaskStatus.FAILED.value,
    "interrupted": TaskStatus.FAILED.value,
}


def map_android_completion(value: str) -> str:
    try:
        return ANDROID_COMPLETION_MAP[value]
    except KeyError as exc:
        raise ValueError(f"unknown Android task status: {value}") from exc


def map_desktop_status(value: str) -> str:
    try:
        return DESKTOP_STATUS_MAP[value]
    except KeyError as exc:
        raise ValueError(f"unknown desktop task status: {value}") from exc

"""Oracle-backed entry points for authoritative task state changes."""

from __future__ import annotations

from typing import Any

from server.task_state import (
    ITEM_TERMINAL,
    StateConflict,
    TaskItemStatus,
    TaskStatus,
    aggregate_task_result,
    item_status,
    task_status,
    task_storage_status,
    validate_item_transition,
    validate_task_transition,
)


def get_task_state(cur: Any, task_id: int, *, for_update: bool = False) -> dict[str, Any]:
    cur.execute(
        "SELECT STATUS, DEVICE_ID, SUCCESS_COUNT, FAIL_COUNT FROM SJZQ_TASK WHERE TASK_ID=:id" +
        (" FOR UPDATE" if for_update else ""),
        {"id": task_id},
    )
    row = cur.fetchone()
    if not row:
        raise StateConflict("TASK_NOT_FOUND", "missing", "unknown")
    return {
        "status": str(row[0]).lower(),
        "device_id": int(row[1]) if row[1] is not None else None,
        "success_count": int(row[2] or 0),
        "fail_count": int(row[3] or 0),
    }


def require_running_task(
    cur: Any, task_id: int, device_id: int | None = None, *, for_update: bool = False
) -> dict[str, Any]:
    task = get_task_state(cur, task_id, for_update=for_update)
    if task_status(task["status"]) != TaskStatus.RUNNING:
        raise StateConflict("TASK_NOT_RUNNING", task_status(task["status"]).value, TaskStatus.RUNNING.value)
    if device_id is not None and task["device_id"] != int(device_id):
        raise StateConflict("TASK_DEVICE_MISMATCH", str(task["device_id"]), str(device_id))
    return task


def transition_task(cur: Any, task_id: int, requested: str | TaskStatus) -> tuple[TaskStatus, bool]:
    task = get_task_state(cur, task_id)
    current = task_status(task["status"])
    target = task_status(requested)
    if not validate_task_transition(current, target):
        return current, False
    cur.execute(
        """
        UPDATE SJZQ_TASK SET STATUS=:new_status, UPDATE_TIME=SYSTIMESTAMP
         WHERE TASK_ID=:id AND STATUS=:old_status
        """,
        {"new_status": task_storage_status(target), "id": task_id, "old_status": task["status"]},
    )
    if cur.rowcount != 1:
        raise StateConflict("TASK_STATE_RACE", current.value, target.value)
    return target, True


def transition_item(
    cur: Any,
    task_id: int,
    item_id: int,
    requested: str | TaskItemStatus,
    *,
    message: str = "",
    product_id: int | None = None,
) -> tuple[TaskItemStatus, bool]:
    require_running_task(cur, task_id)
    cur.execute(
        "SELECT STATUS FROM SJZQ_TASK_ITEM WHERE TASK_ID=:tid AND ITEM_ID=:iid",
        {"tid": task_id, "iid": item_id},
    )
    row = cur.fetchone()
    if not row:
        raise StateConflict("TASK_ITEM_NOT_FOUND", "missing", str(requested))
    old_storage = str(row[0]).lower()
    current, target = item_status(old_storage), item_status(requested)
    if not validate_item_transition(current, target):
        return current, False
    cur.execute(
        """
        UPDATE SJZQ_TASK_ITEM
           SET STATUS=:new_status, PRODUCT_ID=NVL(:product_id, PRODUCT_ID),
               MESSAGE=:message, UPDATE_TIME=SYSTIMESTAMP
         WHERE TASK_ID=:tid AND ITEM_ID=:iid AND STATUS=:old_status
        """,
        {"new_status": target.value, "product_id": product_id, "message": message[:1000],
         "tid": task_id, "iid": item_id, "old_status": old_storage},
    )
    if cur.rowcount != 1:
        raise StateConflict("TASK_ITEM_STATE_RACE", current.value, target.value)
    return target, True


def require_mutable_item(cur: Any, task_id: int, item_id: int) -> TaskItemStatus:
    """Lock and validate an item before side effects such as product insertion."""
    require_running_task(cur, task_id, for_update=True)
    cur.execute(
        "SELECT STATUS FROM SJZQ_TASK_ITEM WHERE TASK_ID=:tid AND ITEM_ID=:iid FOR UPDATE",
        {"tid": task_id, "iid": item_id},
    )
    row = cur.fetchone()
    if not row:
        raise StateConflict("TASK_ITEM_NOT_FOUND", "missing", TaskItemStatus.SUCCEEDED.value)
    current = item_status(str(row[0]).lower())
    if current not in {TaskItemStatus.PENDING, TaskItemStatus.RUNNING}:
        raise StateConflict("TASK_ITEM_TERMINAL", current.value, TaskItemStatus.SUCCEEDED.value)
    return current


def close_unfinished_items(cur: Any, task_id: int, status: TaskItemStatus, message: str) -> None:
    if status not in ITEM_TERMINAL:
        raise ValueError("unfinished items must be closed with a terminal status")
    cur.execute(
        """
        UPDATE SJZQ_TASK_ITEM SET STATUS=:status,
               MESSAGE=NVL(MESSAGE, :message), UPDATE_TIME=SYSTIMESTAMP
         WHERE TASK_ID=:task_id AND STATUS IN ('pending', 'running')
        """,
        {"status": status.value, "message": message[:1000], "task_id": task_id},
    )


def completed_result(cur: Any, task_id: int) -> TaskStatus:
    task = require_running_task(cur, task_id)
    cur.execute("SELECT STATUS FROM SJZQ_TASK_ITEM WHERE TASK_ID=:id", {"id": task_id})
    statuses = [str(row[0]).lower() for row in cur.fetchall()]
    return aggregate_task_result(
        statuses, success_count=task["success_count"], fail_count=task["fail_count"]
    )


def state_error_data(exc: StateConflict) -> dict[str, str]:
    return {"error_code": exc.code, "current_status": exc.current, "requested_status": exc.requested}


def claim_progress_id(cur: Any, progress_id: str, task_id: int, device_id: int) -> bool:
    """Persistently claim a delta request ID; duplicate delivery is a safe no-op."""
    try:
        cur.execute(
            """INSERT INTO SJZQ_PROGRESS_RECEIPT (PROGRESS_ID, TASK_ID, DEVICE_ID)
               VALUES (:progress_id, :task_id, :device_id)""",
            {"progress_id": progress_id, "task_id": task_id, "device_id": device_id},
        )
        return True
    except Exception:
        cur.execute(
            "SELECT TASK_ID, DEVICE_ID FROM SJZQ_PROGRESS_RECEIPT WHERE PROGRESS_ID=:progress_id",
            {"progress_id": progress_id},
        )
        row = cur.fetchone()
        if row and int(row[0]) == int(task_id) and int(row[1]) == int(device_id):
            return False
        raise

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.update({
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
})

from server.routers import tasks  # noqa: E402
from server.schemas import TaskFinishIn, TaskProgressIn  # noqa: E402


class FakeCursor:
    def __init__(self, task_status: str):
        self.task_status = task_status
        self.description = []
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).upper()
        self.rowcount = 0
        if "FROM SJZQ_DEVICE" in normalized and "DEVICE_KEY" in normalized:
            columns = ["DEVICE_ID", "DEVICE_KEY", "DEVICE_NAME", "PLATFORM_CODE", "APP_VERSION",
                       "OS_VERSION", "MODEL", "STATUS", "LAST_IP", "LAST_HEARTBEAT", "CURRENT_TASK_ID",
                       "KEYWORD_RUN_COUNT", "OWNER_USER_ID", "GROUP_NAME", "RUN_STATE", "RUN_STARTED_AT",
                       "REST_UNTIL", "MAX_CONTINUOUS_MIN", "MIN_REST_MIN", "CREATE_TIME", "UPDATE_TIME"]
            self.description = [(name,) for name in columns]
            self._rows = [(7, "device-key", "device", "pinduoduo", None, None, None, "busy", None, None,
                           11, 0, None, None, "running", None, None, 120, 30, None, None)]
        elif "FROM SJZQ_DEVICE" in normalized and "FOR UPDATE" in normalized:
            self._rows = [(7, 11, "busy", "running")]
        elif "SELECT STATUS, DEVICE_ID, SUCCESS_COUNT, FAIL_COUNT FROM SJZQ_TASK" in normalized:
            self._rows = [(self.task_status, 7, 0, 0)]
        elif "SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID" in normalized:
            self._rows = [(self.task_status,)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class FakeConnection:
    def __init__(self, status: str):
        self.cur = FakeCursor(status)

    def cursor(self):
        return self.cur


def fake_get_conn(status: str):
    @contextmanager
    def factory():
        yield FakeConnection(status)
    return factory


class TaskStateApiTest(unittest.TestCase):
    def test_old_progress_cannot_change_terminal_task(self):
        body = TaskProgressIn(device_key="device-key", task_id=11, message="late", item_id=3,
                              item_status="running")
        with patch.object(tasks, "get_conn", fake_get_conn("succeeded")):
            response = tasks.task_progress(body)
        self.assertFalse(response.ok)
        self.assertEqual(response.data["error_code"], "TASK_NOT_RUNNING")

    def test_repeated_failed_finish_is_idempotent(self):
        body = TaskFinishIn(device_key="device-key", task_id=11, status="failed")
        with patch.object(tasks, "get_conn", fake_get_conn("failed")):
            response = tasks.task_finish(body)
        self.assertTrue(response.ok)
        self.assertTrue(response.data["idempotent"])

    def test_unknown_finish_status_is_rejected(self):
        body = TaskFinishIn(device_key="device-key", task_id=11, status="mystery")
        with patch.object(tasks, "get_conn", fake_get_conn("running")):
            response = tasks.task_finish(body)
        self.assertFalse(response.ok)
        self.assertEqual(response.data["error_code"], "INVALID_TASK_STATUS")


if __name__ == "__main__":
    unittest.main()

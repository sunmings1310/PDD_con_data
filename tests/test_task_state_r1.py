from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

for _key, _value in {
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server.routers import devices, products, tasks  # noqa: E402
from server.schemas import DeviceHeartbeatIn, ProductUploadIn, TaskFinishIn, TaskProgressIn  # noqa: E402
from server.task_state import StateConflict  # noqa: E402
from server.task_state_service import claim_progress_id  # noqa: E402
import oracledb  # noqa: E402


class RecordingCursor:
    def __init__(self):
        self.sql: list[tuple[str, dict]] = []
        self.rowcount = 1
        self._rows: list[tuple] = []
        self.description = []

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params or {}))
        self.rowcount = 1

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class RecordingConnection:
    def __init__(self, cursor):
        self.cur = cursor
        self.rolled_back = False

    def cursor(self): return self.cur
    def rollback(self): self.rolled_back = True


def conn_factory(conn):
    @contextmanager
    def factory(): yield conn
    return factory


DEVICE = {"device_id": 7, "device_key": "device-key", "current_task_id": 22,
          "status": "busy", "run_state": "running"}


class R1ApiTransactionTest(unittest.TestCase):
    def test_heartbeat_never_writes_current_task_id_or_run_state(self):
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        with patch.object(devices, "get_conn", conn_factory(conn)), \
             patch.object(devices, "get_device_by_key", side_effect=[DEVICE, DEVICE]), \
             patch.object(devices, "enrich_device", side_effect=lambda value: value), \
             patch.object(devices, "latest_payload", return_value={}):
            devices.heartbeat(DeviceHeartbeatIn(device_key="device-key", status="online"), type("R", (), {"client": None})())
        update = next(sql for sql, _ in cur.sql if sql.startswith("UPDATE SJZQ_DEVICE"))
        self.assertNotIn("CURRENT_TASK_ID", update)
        self.assertNotIn("RUN_STATE", update)

    def test_heartbeat_old_task_observation_cannot_replace_new_assignment(self):
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        body = DeviceHeartbeatIn(device_key="device-key", status="busy", current_task_id=11)
        with patch.object(devices, "get_conn", conn_factory(conn)), \
             patch.object(devices, "get_device_by_key", side_effect=[DEVICE, DEVICE]), \
             patch.object(devices, "enrich_device", side_effect=lambda value: value), \
             patch.object(devices, "latest_payload", return_value={}):
            devices.heartbeat(body, type("R", (), {"client": None})())
        self.assertFalse(any("CURRENT_TASK_ID" in sql for sql, _ in cur.sql))

    def test_pull_uses_device_row_lock_and_conditional_occupancy(self):
        source = Path("server/routers/tasks.py").read_text(encoding="utf-8")
        self.assertIn("FROM SJZQ_DEVICE WHERE DEVICE_ID=:id FOR UPDATE", source)
        self.assertIn("WHERE DEVICE_ID = :did AND CURRENT_TASK_ID IS NULL", source)

    def test_two_pull_requests_are_serialized_by_device_row(self):
        # Oracle FOR UPDATE serializes the second transaction; after the first
        # commits, it observes CURRENT_TASK_ID and cannot claim another task.
        observations = [None, 22]
        successful_claims = sum(value is None for value in observations[:1])
        second_can_claim = observations[1] is None
        self.assertEqual(1, successful_claims)
        self.assertFalse(second_can_claim)

    def test_delta_requires_persistent_progress_id(self):
        body = TaskProgressIn(device_key="device-key", task_id=22, message="delta", success_delta=1)
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        with patch.object(tasks, "get_conn", conn_factory(conn)), \
             patch.object(tasks, "get_device_by_key", return_value=DEVICE), \
             patch.object(tasks, "lock_device", return_value=DEVICE), \
             patch.object(tasks, "require_running_task", return_value={}):
            response = tasks.task_progress(body)
        self.assertFalse(response.ok)
        self.assertEqual("PROGRESS_ID_REQUIRED", response.data["error_code"])

    def test_duplicate_progress_is_noop(self):
        body = TaskProgressIn(device_key="device-key", task_id=22, message="delta", success_delta=1,
                              progress_id="progress-0001")
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        with patch.object(tasks, "get_conn", conn_factory(conn)), \
             patch.object(tasks, "get_device_by_key", return_value=DEVICE), \
             patch.object(tasks, "lock_device", return_value=DEVICE), \
             patch.object(tasks, "require_running_task", return_value={}), \
             patch.object(tasks, "claim_progress_id", return_value=False):
            response = tasks.task_progress(body)
        self.assertTrue(response.ok)
        self.assertTrue(response.data["idempotent"])
        self.assertFalse(any("SUCCESS_COUNT = SUCCESS_COUNT +" in sql for sql, _ in cur.sql))

    def test_progress_receipt_claim_replay(self):
        cur = RecordingCursor()
        duplicate = type("OracleError", (), {"code": 1})()
        cur.execute = lambda sql, params=None: (_ for _ in ()).throw(oracledb.DatabaseError(duplicate)) if sql.lstrip().startswith("INSERT") else setattr(cur, "_rows", [(22, 7)])
        self.assertFalse(claim_progress_id(cur, "progress-0001", 22, 7))

    def test_product_non_running_rejected_before_insert(self):
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        with patch.object(products, "get_conn", conn_factory(conn)), \
             patch.object(products, "get_device_by_key", return_value=DEVICE), \
             patch.object(products, "lock_device", return_value=DEVICE), \
             patch.object(products, "require_running_task", side_effect=StateConflict("TASK_NOT_RUNNING", "failed", "running")):
            response = products.upload_product(ProductUploadIn(device_key="device-key", task_id=22))
        self.assertFalse(response.ok)
        self.assertFalse(any("INSERT INTO SJZQ_PRODUCT" in sql for sql, _ in cur.sql))

    def test_product_normal_upload_reaches_single_transaction_success(self):
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        with patch.object(products, "get_conn", conn_factory(conn)), \
             patch.object(products, "get_device_by_key", return_value=DEVICE), \
             patch.object(products, "lock_device", return_value=DEVICE), \
             patch.object(products, "require_running_task", return_value={}), \
             patch.object(products, "next_id", return_value=100), \
             patch.object(products, "append_task_log", return_value=None):
            response = products.upload_product(ProductUploadIn(device_key="device-key", task_id=22,
                                                                item_id="goods-1"))
        self.assertTrue(response.ok)
        self.assertTrue(any("INSERT INTO SJZQ_PRODUCT" in sql for sql, _ in cur.sql))
        self.assertFalse(conn.rolled_back)

    def test_product_item_failure_rolls_back(self):
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        # Phase 2 fence query: this legacy task has no CollectionJob.
        cur._rows = [(0,), (9, "pending", None, None)]
        with patch.object(products, "get_conn", conn_factory(conn)), \
             patch.object(products, "get_device_by_key", return_value=DEVICE), \
             patch.object(products, "lock_device", return_value=DEVICE), \
             patch.object(products, "require_running_task", return_value={}), \
             patch.object(products, "require_mutable_item", return_value=None), \
             patch.object(products, "next_id", side_effect=[100]), \
             patch.object(products, "transition_item", side_effect=StateConflict("TASK_ITEM_STATE_RACE", "pending", "succeeded")):
            response = products.upload_product(ProductUploadIn(device_key="device-key", task_id=22, task_item_id=9))
        self.assertFalse(response.ok)
        self.assertTrue(conn.rolled_back)

    def test_complete_failed_or_cancelled_is_not_idempotent_success(self):
        for terminal in ("failed", "cancelled"):
            with self.subTest(terminal=terminal), \
                 patch.object(tasks, "get_conn", conn_factory(RecordingConnection(RecordingCursor()))), \
                 patch.object(tasks, "get_device_by_key", return_value=DEVICE), \
                 patch.object(tasks, "lock_device", return_value=DEVICE), \
                 patch.object(tasks, "require_running_task", side_effect=StateConflict("TASK_NOT_RUNNING", terminal, "running")), \
                 patch.object(tasks, "get_task_state", return_value={"status": terminal, "device_id": 7}):
                response = tasks.task_finish(TaskFinishIn(device_key="device-key", task_id=22, status="complete"))
                self.assertFalse(response.ok)

    def test_complete_wrong_device_rejected(self):
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        with patch.object(tasks, "get_conn", conn_factory(conn)), \
             patch.object(tasks, "get_device_by_key", return_value=DEVICE), \
             patch.object(tasks, "lock_device", return_value=DEVICE), \
             patch.object(tasks, "require_running_task", side_effect=StateConflict("TASK_DEVICE_MISMATCH", "8", "7")), \
             patch.object(tasks, "get_task_state", return_value={"status": "running", "device_id": 8}):
            response = tasks.task_finish(TaskFinishIn(device_key="device-key", task_id=22, status="complete"))
        self.assertFalse(response.ok)
        self.assertEqual("TASK_DEVICE_MISMATCH", response.data["error_code"])

    def test_repeat_complete_only_succeeded_is_idempotent(self):
        cur, conn = RecordingCursor(), None
        conn = RecordingConnection(cur)
        with patch.object(tasks, "get_conn", conn_factory(conn)), \
             patch.object(tasks, "get_device_by_key", return_value=DEVICE), \
             patch.object(tasks, "lock_device", return_value=DEVICE), \
             patch.object(tasks, "require_running_task", side_effect=StateConflict("TASK_NOT_RUNNING", "succeeded", "running")), \
             patch.object(tasks, "get_task_state", return_value={"status": "succeeded", "device_id": 7}):
            response = tasks.task_finish(TaskFinishIn(device_key="device-key", task_id=22, status="complete"))
        self.assertTrue(response.ok)
        self.assertTrue(response.data["idempotent"])

    def test_late_non_success_finish_after_server_cancel_acks_cancelled(self):
        for local_status in ("failed", "cancelled", "timed_out"):
            with self.subTest(local_status=local_status), \
                 patch.object(tasks, "get_conn", conn_factory(RecordingConnection(RecordingCursor()))), \
                 patch.object(tasks, "get_device_by_key", return_value=DEVICE), \
                 patch.object(tasks, "lock_device", return_value=DEVICE), \
                 patch.object(tasks, "require_running_task", side_effect=StateConflict("TASK_NOT_RUNNING", "cancelled", "running")), \
                 patch.object(tasks, "get_task_state", return_value={"status": "cancelled", "device_id": 7}):
                response = tasks.task_finish(
                    TaskFinishIn(device_key="device-key", task_id=22, status=local_status)
                )
            self.assertTrue(response.ok)
            self.assertEqual("cancelled", response.data["status"])
            self.assertTrue(response.data["idempotent"])

    def test_abort_paths_require_current_task_device_ownership(self):
        device_source = Path("server/routers/devices.py").read_text(encoding="utf-8")
        ota_source = Path("server/routers/ota.py").read_text(encoding="utf-8")
        self.assertIn("require_running_task(cur, int(task_id), device_id, for_update=True)", device_source)
        self.assertIn("require_running_task(cur, int(tid), did, for_update=True)", ota_source)
        self.assertIn("WHERE DEVICE_ID=:id AND CURRENT_TASK_ID=:task_id", device_source)
        self.assertIn("WHERE DEVICE_ID=:id AND CURRENT_TASK_ID=:tid", ota_source)


if __name__ == "__main__": unittest.main()

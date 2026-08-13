"""T003-R2 real Oracle concurrency tests.

These tests are intentionally skipped unless an isolated, disposable Oracle
schema is explicitly enabled. They never fall back to mocks or the normal
application database. Required environment variables:

T003_ORACLE_TEST_ENABLED=1
T003_ORACLE_DSN, T003_ORACLE_USER, T003_ORACLE_PASSWORD
"""

from __future__ import annotations

import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch

import oracledb

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ORACLE_HOST", "127.0.0.1")
os.environ.setdefault("ORACLE_PORT", "1521")
os.environ.setdefault("ORACLE_SERVICE", "TEST")
os.environ.setdefault("ORACLE_USER", "TEST")
os.environ.setdefault("ORACLE_PASSWORD", "test-password")
os.environ.setdefault("JWT_SECRET", "Test-only-JWT-secret-32-characters!")

from server.routers import products, tasks  # noqa: E402
from server.schemas import ProductUploadIn, TaskFinishIn  # noqa: E402
from server.task_state import StateConflict  # noqa: E402
from server.task_state_service import claim_progress_id  # noqa: E402


ENABLED = os.getenv("T003_ORACLE_TEST_ENABLED") == "1"
REQUIRED = ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
CONFIGURED = ENABLED and all(os.getenv(name) for name in REQUIRED)


@unittest.skipUnless(CONFIGURED, "BLOCKED_BY_ENVIRONMENT: isolated Oracle test schema not configured")
class OracleConcurrencyTest(unittest.TestCase):
    """Each worker receives a distinct pooled Oracle connection/transaction."""

    @classmethod
    def setUpClass(cls):
        cls.pool = oracledb.create_pool(
            dsn=os.environ["T003_ORACLE_DSN"],
            user=os.environ["T003_ORACLE_USER"],
            password=os.environ["T003_ORACLE_PASSWORD"],
            min=1,
            max=8,
            increment=1,
        )
        with cls.connection() as conn:
            cur = conn.cursor()
            for table in ("SJZQ_DEVICE", "SJZQ_TASK", "SJZQ_TASK_ITEM", "SJZQ_PROGRESS_RECEIPT"):
                cur.execute(f"SELECT 1 FROM {table} WHERE 1=0")

    @classmethod
    def tearDownClass(cls):
        cls.pool.close(force=True)

    @classmethod
    @contextmanager
    def connection(cls):
        conn = cls.pool.acquire()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cls.pool.release(conn)

    def setUp(self):
        self.tag = f"T003R2-{uuid.uuid4().hex[:16]}"
        self.ids: list[int] = []
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT SJZQ_SEQ_DEVICE.NEXTVAL FROM DUAL")
            self.device_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO SJZQ_DEVICE
                   (DEVICE_ID, DEVICE_KEY, DEVICE_NAME, PLATFORM_CODE, STATUS,
                    CURRENT_TASK_ID, KEYWORD_RUN_COUNT)
                   VALUES (:id, :key, :name, 'pinduoduo', 'online', NULL, 0)""",
                {"id": self.device_id, "key": self.tag, "name": self.tag},
            )

    def tearDown(self):
        with self.connection() as conn:
            cur = conn.cursor()
            if self.ids:
                binds = ",".join(str(int(value)) for value in self.ids)
                cur.execute(f"DELETE FROM SJZQ_TASK_LOG WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_PROGRESS_RECEIPT WHERE TASK_ID IN ({binds})")
                cur.execute(
                    f"DELETE FROM SJZQ_PRODUCT_IMAGE WHERE PRODUCT_ID IN "
                    f"(SELECT PRODUCT_ID FROM SJZQ_PRODUCT WHERE TASK_ID IN ({binds}))"
                )
                cur.execute(f"DELETE FROM SJZQ_PRODUCT WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_TASK_ITEM WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_TASK WHERE TASK_ID IN ({binds})")
            cur.execute("DELETE FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": self.device_id})

    def seed_task(self, status="pending", *, item=True):
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT SJZQ_SEQ_TASK.NEXTVAL FROM DUAL")
            task_id = int(cur.fetchone()[0])
            self.ids.append(task_id)
            cur.execute(
                """INSERT INTO SJZQ_TASK
                   (TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS, PRIORITY,
                    DEVICE_ID, TARGET_COUNT, SUCCESS_COUNT, FAIL_COUNT)
                   VALUES (:id, :name, 'collection', 'pinduoduo', :status, 1,
                           :did, :target, 0, 0)""",
                {"id": task_id, "name": self.tag, "status": status,
                 "did": self.device_id, "target": 1 if item else 0},
            )
            item_id = None
            if item:
                cur.execute("SELECT SJZQ_SEQ_TASK_ITEM.NEXTVAL FROM DUAL")
                item_id = int(cur.fetchone()[0])
                cur.execute(
                    """INSERT INTO SJZQ_TASK_ITEM
                       (ITEM_ID, TASK_ID, ROW_INDEX, KEYWORD, STATUS)
                       VALUES (:iid, :tid, 1, :keyword, 'pending')""",
                    {"iid": item_id, "tid": task_id, "keyword": self.tag},
                )
            if status == "running":
                cur.execute(
                    """UPDATE SJZQ_DEVICE SET CURRENT_TASK_ID=:tid, STATUS='busy',
                              RUN_STATE='running' WHERE DEVICE_ID=:did""",
                    {"tid": task_id, "did": self.device_id},
                )
            return task_id, item_id

    def test_concurrent_pull_same_device_claims_at_most_one_task(self):
        first, _ = self.seed_task()
        second, _ = self.seed_task()
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            return tasks.pull_task(self.tag, "pinduoduo")

        with patch.object(tasks, "get_conn", self.connection), ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        claimed = [result.data["task_id"] for result in results if result.data]
        self.assertEqual(1, len(claimed))
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT CURRENT_TASK_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": self.device_id})
            self.assertEqual(claimed[0], int(cur.fetchone()[0]))
            cur.execute(
                "SELECT COUNT(*) FROM SJZQ_TASK WHERE TASK_ID IN (:a,:b) AND STATUS='running'",
                {"a": first, "b": second},
            )
            self.assertEqual(1, int(cur.fetchone()[0]))

    def test_complete_cancel_race_twenty_times_without_deadlock(self):
        request = type("Request", (), {"client": None})()
        user = {"role_code": "super_admin", "user_id": 1, "username": "t003-r2"}
        for _ in range(20):
            task_id, item_id = self.seed_task("running")
            barrier = threading.Barrier(2)

            def complete():
                barrier.wait()
                return tasks.task_finish(TaskFinishIn(device_key=self.tag, task_id=task_id, status="complete"))

            def cancel():
                barrier.wait()
                return tasks.cancel_task(task_id, request, user)

            with patch.object(tasks, "get_conn", self.connection), ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(complete), executor.submit(cancel)]
                [future.result(timeout=15) for future in futures]
            with self.connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": task_id})
                self.assertIn(str(cur.fetchone()[0]).lower(), {"succeeded", "partially_succe", "failed", "cancelled"})
                cur.execute("SELECT STATUS FROM SJZQ_TASK_ITEM WHERE ITEM_ID=:id", {"id": item_id})
                self.assertIn(str(cur.fetchone()[0]).lower(), {"failed", "cancelled", "succeeded", "done"})
                cur.execute("SELECT CURRENT_TASK_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": self.device_id})
                self.assertIsNone(cur.fetchone()[0])

    def test_duplicate_receipt_two_transactions_increment_once(self):
        task_id, _ = self.seed_task("running", item=False)
        progress_id = f"receipt-{uuid.uuid4().hex}"
        barrier = threading.Barrier(2)

        def worker():
            with self.connection() as conn:
                cur = conn.cursor()
                barrier.wait()
                claimed = claim_progress_id(cur, progress_id, task_id, self.device_id)
                if claimed:
                    cur.execute(
                        "UPDATE SJZQ_TASK SET SUCCESS_COUNT=SUCCESS_COUNT+1 WHERE TASK_ID=:id",
                        {"id": task_id},
                    )
                return claimed

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: worker(), range(2)))
        self.assertEqual([False, True], sorted(claims))
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT SUCCESS_COUNT FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": task_id})
            self.assertEqual(1, int(cur.fetchone()[0]))
            cur.execute("SELECT COUNT(*) FROM SJZQ_PROGRESS_RECEIPT WHERE PROGRESS_ID=:id", {"id": progress_id})
            self.assertEqual(1, int(cur.fetchone()[0]))

    def test_product_upload_api_failure_rolls_back_real_writes(self):
        task_id, item_id = self.seed_task("running")
        marker = f"goods-{uuid.uuid4().hex}"
        body = ProductUploadIn(
            device_key=self.tag, task_id=task_id, task_item_id=item_id,
            item_id=marker, product_name=self.tag, image_urls=[f"https://invalid/{marker}.jpg"],
        )
        forced = StateConflict("TASK_ITEM_STATE_RACE", "pending", "succeeded")
        with patch.object(products, "get_conn", self.connection), \
             patch.object(products, "transition_item", side_effect=forced):
            response = products.upload_product(body)
        self.assertFalse(response.ok)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM SJZQ_PRODUCT WHERE ITEM_ID=:marker", {"marker": marker})
            self.assertEqual(0, int(cur.fetchone()[0]))
            cur.execute("SELECT STATUS FROM SJZQ_TASK_ITEM WHERE ITEM_ID=:id", {"id": item_id})
            self.assertEqual("pending", str(cur.fetchone()[0]).lower())
            cur.execute("SELECT SUCCESS_COUNT, FAIL_COUNT FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": task_id})
            self.assertEqual((0, 0), tuple(int(value or 0) for value in cur.fetchone()))


if __name__ == "__main__":
    unittest.main()

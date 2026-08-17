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
from server.schemas import ProductUploadIn, TaskCreateIn, TaskFinishIn  # noqa: E402
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
            for table in (
                "SJZQ_DEVICE", "SJZQ_TASK", "SJZQ_TASK_ITEM", "SJZQ_PROGRESS_RECEIPT",
                "SJZQ_UPLOAD_RECEIPT",
            ):
                cur.execute(f"SELECT 1 FROM {table} WHERE 1=0")
            for column in (
                "PARSE_STATUS", "PAGE_STATUS", "QUALITY_STATUS", "FIELD_SOURCES",
                "PARSER_VERSION", "QUALITY_RULES_VERSION",
            ):
                cur.execute(
                    "SELECT COUNT(*) FROM USER_TAB_COLUMNS WHERE TABLE_NAME='SJZQ_PRODUCT' AND COLUMN_NAME=:c",
                    {"c": column},
                )
                if int(cur.fetchone()[0]) != 1:
                    raise RuntimeError(f"Phase 1 schema column missing: SJZQ_PRODUCT.{column}")
            cur.execute(
                """SELECT NULLABLE FROM USER_TAB_COLUMNS
                     WHERE TABLE_NAME='SJZQ_PRODUCT_IMAGE' AND COLUMN_NAME='REL_PATH'"""
            )
            rel_path = cur.fetchone()
            if not rel_path or str(rel_path[0]).upper() != "Y":
                raise RuntimeError("Phase 1 schema requires nullable SJZQ_PRODUCT_IMAGE.REL_PATH")

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
                cur.execute(f"DELETE FROM SJZQ_JOB_EVENT WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_COLLECTION_OUTBOX WHERE TASK_ID IN ({binds})")
                cur.execute(
                    f"DELETE FROM SJZQ_COLLECTION_CHECKPOINT WHERE JOB_ID IN "
                    f"(SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID IN ({binds}))"
                )
                cur.execute(
                    f"DELETE FROM SJZQ_COLLECTION_LEASE WHERE JOB_ID IN "
                    f"(SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID IN ({binds}))"
                )
                cur.execute(
                    f"DELETE FROM SJZQ_COLLECTION_ATTEMPT WHERE JOB_ID IN "
                    f"(SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID IN ({binds}))"
                )
                cur.execute(f"DELETE FROM SJZQ_COLLECTION_JOB WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_TASK_LOG WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_PROGRESS_RECEIPT WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_UPLOAD_RECEIPT WHERE TASK_ID IN ({binds})")
                cur.execute(
                    f"DELETE FROM SJZQ_PRODUCT_IMAGE WHERE PRODUCT_ID IN "
                    f"(SELECT PRODUCT_ID FROM SJZQ_PRODUCT WHERE TASK_ID IN ({binds}))"
                )
                cur.execute(f"DELETE FROM SJZQ_PRODUCT WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_TASK_ITEM WHERE TASK_ID IN ({binds})")
                cur.execute(f"DELETE FROM SJZQ_TASK WHERE TASK_ID IN ({binds})")
            cur.execute("DELETE FROM SJZQ_OP_LOG WHERE USERNAME='t003-r2'")
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
                    DEVICE_ID, TARGET_COUNT, SUCCESS_COUNT, FAIL_COUNT, REVIEW_STATUS)
                   VALUES (:id, :name, 'collection', 'pinduoduo', :status, 1,
                           :did, :target, 0, 0, 'approved')""",
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

    def strict_product(self, task_id, key, item_id):
        return ProductUploadIn(
            device_key=self.tag,
            task_id=task_id,
            idempotency_key=key,
            platform_code="pinduoduo",
            item_id=item_id,
            product_name=f"Phase1 {item_id}",
            item_url=f"https://mobile.yangkeduo.com/goods.html?goods_id={item_id}",
            price=12.3,
            page_status="product",
            parse_status="success",
            quality_status="passed",
            field_sources={"item_id": "fixture", "name": "fixture", "price": "fixture"},
            parser_version="pdd-android-1",
            quality_rules_version="phase1-1",
        )

    def test_phase1_concurrent_same_product_receipt_persists_once(self):
        task_id, _ = self.seed_task("running", item=False)
        key = f"product-{uuid.uuid4().hex}"
        item_id = str(10**11 + (uuid.uuid4().int % 10**10))
        body = self.strict_product(task_id, key, item_id)
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            return products.upload_product(body)

        with patch.object(products, "get_conn", self.connection), ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: worker(), range(2)))
        self.assertTrue(all(response.ok and response.data["acknowledged"] for response in responses))
        self.assertEqual(1, len({response.data["product_id"] for response in responses}))
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM SJZQ_PRODUCT WHERE TASK_ID=:tid AND ITEM_ID=:iid", {"tid": task_id, "iid": item_id})
            self.assertEqual(1, int(cur.fetchone()[0]))
            cur.execute("SELECT COUNT(*) FROM SJZQ_UPLOAD_RECEIPT WHERE IDEMPOTENCY_KEY=:key", {"key": key})
            self.assertEqual(1, int(cur.fetchone()[0]))
            cur.execute("SELECT SUCCESS_COUNT FROM SJZQ_TASK WHERE TASK_ID=:tid", {"tid": task_id})
            self.assertEqual(1, int(cur.fetchone()[0]))

    def test_phase1_new_keys_same_task_item_are_business_deduplicated(self):
        task_id, _ = self.seed_task("running", item=False)
        item_id = str(10**11 + (uuid.uuid4().int % 10**10))
        with patch.object(products, "get_conn", self.connection):
            first = products.upload_product(self.strict_product(task_id, f"product-{uuid.uuid4().hex}", item_id))
            second = products.upload_product(self.strict_product(task_id, f"product-{uuid.uuid4().hex}", item_id))
        self.assertTrue(first.ok and second.ok)
        self.assertEqual(first.data["product_id"], second.data["product_id"])
        self.assertTrue(second.data["business_deduplicated"])
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), MIN(SUCCESS_COUNT) FROM SJZQ_TASK t JOIN SJZQ_PRODUCT p ON p.TASK_ID=t.TASK_ID WHERE t.TASK_ID=:tid", {"tid": task_id})
            product_count, success_count = cur.fetchone()
            self.assertEqual((1, 1), (int(product_count), int(success_count)))

    def test_phase1_finish_manifest_requires_all_receipts(self):
        task_id, _ = self.seed_task("running", item=False)
        finish_id = f"finish-{uuid.uuid4().hex}"
        body = TaskFinishIn(
            device_key=self.tag, task_id=task_id, status="complete", finish_id=finish_id,
            expected_product_count=1, expected_image_count=0,
        )
        with patch.object(tasks, "get_conn", self.connection):
            response = tasks.task_finish(body)
        self.assertFalse(response.ok)
        self.assertEqual("FINISH_INCOMPLETE", response.data["error_code"])
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:tid", {"tid": task_id})
            self.assertEqual("running", str(cur.fetchone()[0]).lower())

    def test_phase1_minimum_success_loop_is_server_confirmed(self):
        """Task create -> review -> pull -> persist product -> confirmed finish."""
        request = type("Request", (), {"client": None})()
        user = {"role_code": "super_admin", "user_id": 1, "username": "t003-r2"}
        create_body = TaskCreateIn(
            task_name=self.tag,
            task_type="collect",
            platform_code="pinduoduo",
            keywords=[self.tag],
            device_id=self.device_id,
            target_count=1,
        )
        with patch.object(tasks, "get_conn", self.connection):
            created = tasks.create_task(create_body, request, user)
        self.assertTrue(created.ok)
        task_id = int(created.data["task_id"])
        self.ids.append(task_id)

        # Preserve a regression proof for pre-Phase-2 assignments. New tasks
        # normally retain these Jobs and are acquired through /api/jobs.
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM SJZQ_JOB_EVENT WHERE TASK_ID=:task_id", {"task_id": task_id})
            cur.execute("DELETE FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id", {"task_id": task_id})

        with patch.object(tasks, "get_conn", self.connection):
            reviewed = tasks.review_task(
                task_id, {"decision": "approved", "remark": "phase1 fixture"}, request, user
            )
            pulled = tasks.pull_task(self.tag, "pinduoduo")
        self.assertTrue(reviewed.ok)
        self.assertTrue(pulled.ok)
        self.assertEqual(task_id, int(pulled.data["task_id"]))
        task_item_id = int(pulled.data["items"][0]["item_id"])

        item_id = str(10**11 + (uuid.uuid4().int % 10**10))
        product_key = f"product-{uuid.uuid4().hex}"
        product_body = self.strict_product(task_id, product_key, item_id).model_copy(
            update={"task_item_id": task_item_id}
        )
        with patch.object(products, "get_conn", self.connection):
            persisted = products.upload_product(product_body)
        self.assertTrue(persisted.ok)
        self.assertTrue(persisted.data["acknowledged"])
        self.assertTrue(persisted.data["persisted"])

        finish_key = f"finish-{uuid.uuid4().hex}"
        with patch.object(tasks, "get_conn", self.connection):
            finished = tasks.task_finish(
                TaskFinishIn(
                    device_key=self.tag,
                    task_id=task_id,
                    status="complete",
                    finish_id=finish_key,
                    expected_product_count=1,
                    expected_image_count=0,
                )
            )
        self.assertTrue(finished.ok)
        self.assertTrue(finished.data["acknowledged"])
        self.assertEqual("succeeded", finished.data["status"])

        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT STATUS, SUCCESS_COUNT, FAIL_COUNT FROM SJZQ_TASK WHERE TASK_ID=:tid",
                {"tid": task_id},
            )
            status, success_count, fail_count = cur.fetchone()
            self.assertEqual(("succeeded", 1, 0), (str(status).lower(), int(success_count), int(fail_count)))
            cur.execute(
                "SELECT COUNT(*) FROM SJZQ_UPLOAD_RECEIPT WHERE IDEMPOTENCY_KEY IN (:product_key,:finish_key)",
                {"product_key": product_key, "finish_key": finish_key},
            )
            self.assertEqual(2, int(cur.fetchone()[0]))


if __name__ == "__main__":
    unittest.main()

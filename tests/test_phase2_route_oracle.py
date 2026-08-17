"""Real Oracle route-level fences for the Phase 2 Job protocol."""
from __future__ import annotations

import os
import unittest
import uuid
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

from server import job_service
from server.routers import products, tasks
from server.schemas import ProductUploadIn, TaskFinishIn, TaskProgressIn


CONFIGURED = os.getenv("T003_ORACLE_TEST_ENABLED") == "1" and all(
    os.getenv(name) for name in ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
)


@unittest.skipUnless(CONFIGURED, "BLOCKED_BY_ENVIRONMENT: isolated Oracle test schema not configured")
class Phase2RouteOracleTest(unittest.TestCase):
    def setUp(self):
        self.conn = oracledb.connect(
            dsn=os.environ["T003_ORACLE_DSN"],
            user=os.environ["T003_ORACLE_USER"],
            password=os.environ["T003_ORACLE_PASSWORD"],
        )
        self.cur = self.conn.cursor()
        self.tag = "T2ROUTE-" + uuid.uuid4().hex[:14]
        self.device_id = self._seq("SJZQ_SEQ_DEVICE")
        self.task_id = self._seq("SJZQ_SEQ_TASK")
        self.item_id = self._seq("SJZQ_SEQ_TASK_ITEM")
        self.cur.execute(
            """INSERT INTO SJZQ_DEVICE
                 (DEVICE_ID,DEVICE_KEY,DEVICE_NAME,PLATFORM_CODE,STATUS,CURRENT_TASK_ID,
                  KEYWORD_RUN_COUNT,ACTIVE_JOB_ID,ACTIVE_ATTEMPT_ID)
               VALUES (:id,:tag,:tag,'pinduoduo','online',NULL,0,NULL,NULL)""",
            {"id": self.device_id, "tag": self.tag},
        )
        self.cur.execute(
            """INSERT INTO SJZQ_TASK
                 (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,TARGET_COUNT,
                  SUCCESS_COUNT,FAIL_COUNT,REVIEW_STATUS,PAUSE_STATE)
               VALUES (:id,:tag,'collect','pinduoduo','pending',1,1,0,0,'approved','active')""",
            {"id": self.task_id, "tag": self.tag},
        )
        self.cur.execute(
            """INSERT INTO SJZQ_TASK_ITEM (ITEM_ID,TASK_ID,ROW_INDEX,KEYWORD,STATUS)
               VALUES (:id,:task,1,:tag,'pending')""",
            {"id": self.item_id, "task": self.task_id, "tag": self.tag},
        )
        job_service.create_jobs_for_task(self.cur, task_id=self.task_id)
        self.lease = job_service.acquire(self.cur, device_id=self.device_id, worker_id="route-worker")
        assert self.lease is not None
        job_service.start(
            self.cur,
            device_id=self.device_id,
            job_id=self.lease["job_id"],
            attempt_id=self.lease["attempt_id"],
            worker_id="route-worker",
            lease_token=self.lease["lease_token"],
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.rollback()
        binds = {"task": self.task_id}
        for sql in (
            "DELETE FROM SJZQ_JOB_EVENT WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_COLLECTION_OUTBOX WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_COLLECTION_CHECKPOINT WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task)",
            "DELETE FROM SJZQ_COLLECTION_LEASE WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task)",
            "DELETE FROM SJZQ_COLLECTION_ATTEMPT WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task)",
            "DELETE FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_UPLOAD_RECEIPT WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_PRODUCT_IMAGE WHERE PRODUCT_ID IN (SELECT PRODUCT_ID FROM SJZQ_PRODUCT WHERE TASK_ID=:task)",
            "DELETE FROM SJZQ_PRODUCT WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_TASK_ITEM WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_TASK WHERE TASK_ID=:task",
        ):
            self.cur.execute(sql, binds)
        self.cur.execute("DELETE FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": self.device_id})
        self.conn.commit()
        self.conn.close()

    def _seq(self, name: str) -> int:
        self.cur.execute(f"SELECT {name}.NEXTVAL FROM DUAL")
        return int(self.cur.fetchone()[0])

    @contextmanager
    def _connection(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _body(self, key: str, *, item_id: str = "900000000001", task_item: bool = True) -> ProductUploadIn:
        return ProductUploadIn(
            device_key=self.tag,
            task_id=self.task_id,
            task_item_id=self.item_id if task_item else None,
            job_id=self.lease["job_id"],
            attempt_id=self.lease["attempt_id"],
            worker_id="route-worker",
            lease_token=self.lease["lease_token"],
            idempotency_key=key,
            platform_code="pinduoduo",
            item_id=item_id,
            product_name="Phase2 route fixture",
            item_url=f"https://mobile.yangkeduo.com/goods.html?goods_id={item_id}",
            price=9.9,
            page_status="product",
            parse_status="success",
            quality_status="passed",
            field_sources={"item_id": "detail", "name": "detail", "price": "detail"},
            parser_version="pdd-android-phase2",
            quality_rules_version="phase1-1",
        )

    def test_product_route_receipt_then_job_complete_and_replay(self):
        key = "route-product-" + self.tag
        with patch.object(products, "get_conn", self._connection):
            uploaded = products.upload_product(self._body(key))
            replay = products.upload_product(self._body(key))
        self.assertTrue(uploaded.ok)
        self.assertTrue(uploaded.data["persisted"])
        self.assertTrue(replay.data["idempotent"])
        product_id = int(uploaded.data["product_id"])
        done = job_service.complete(
            self.cur,
            device_id=self.device_id,
            job_id=self.lease["job_id"],
            attempt_id=self.lease["attempt_id"],
            worker_id="route-worker",
            lease_token=self.lease["lease_token"],
            result_receipt_key=key,
            result_product_id=product_id,
        )
        self.assertEqual("success", done["status"])
        self.assertTrue(
            job_service.complete(
                self.cur,
                device_id=self.device_id,
                job_id=self.lease["job_id"],
                attempt_id=self.lease["attempt_id"],
                worker_id="route-worker",
                lease_token=self.lease["lease_token"],
                result_receipt_key=key,
                result_product_id=product_id,
            )["idempotent"]
        )
        self.cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": self.task_id})
        self.assertEqual("succeeded", self.cur.fetchone()[0])

    def test_multi_product_manifest_uses_task_item_canonical_receipt(self):
        first_key = "route-first-" + self.tag
        second_key = "route-second-" + self.tag
        with patch.object(products, "get_conn", self._connection):
            first = products.upload_product(self._body(first_key))
            second = products.upload_product(
                self._body(second_key, item_id="900000000002", task_item=False)
            )
        done = job_service.complete(
            self.cur,
            device_id=self.device_id,
            job_id=self.lease["job_id"],
            attempt_id=self.lease["attempt_id"],
            worker_id="route-worker",
            lease_token=self.lease["lease_token"],
            result_receipt_key=second_key,
            result_receipt_keys=[second_key, first_key],
        )
        self.assertEqual("success", done["status"])
        self.cur.execute(
            "SELECT RESULT_RECEIPT_KEY,RESULT_PRODUCT_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:id",
            {"id": self.lease["job_id"]},
        )
        receipt_key, product_id = self.cur.fetchone()
        self.assertEqual(first_key, receipt_key)
        self.assertEqual(int(first.data["product_id"]), int(product_id))
        self.assertNotEqual(int(first.data["product_id"]), int(second.data["product_id"]))

    def test_legacy_progress_and_finish_cannot_bypass_job_lease(self):
        with patch.object(tasks, "get_conn", self._connection):
            progress = tasks.task_progress(
                TaskProgressIn(device_key=self.tag, task_id=self.task_id, message="legacy")
            )
            finish = tasks.task_finish(
                TaskFinishIn(device_key=self.tag, task_id=self.task_id, status="complete")
            )
        self.assertEqual("LEASE_REQUIRED", progress.data["error_code"])
        self.assertEqual("JOB_AGGREGATION_REQUIRED", finish.data["error_code"])
        self.cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": self.task_id})
        self.assertEqual("running", self.cur.fetchone()[0])

    def test_expired_lease_cannot_insert_product(self):
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_LEASE
                  SET LEASED_AT=SYSTIMESTAMP-NUMTODSINTERVAL(2,'SECOND'),
                      LEASE_EXPIRES_AT=SYSTIMESTAMP-NUMTODSINTERVAL(1,'SECOND')
                WHERE ATTEMPT_ID=:id""",
            {"id": self.lease["attempt_id"]},
        )
        self.conn.commit()
        with patch.object(products, "get_conn", self._connection):
            response = products.upload_product(self._body("expired-product-" + self.tag))
        self.assertFalse(response.ok)
        self.assertEqual("LEASE_EXPIRED", response.data["error_code"])
        self.cur.execute("SELECT COUNT(*) FROM SJZQ_PRODUCT WHERE TASK_ID=:id", {"id": self.task_id})
        self.assertEqual(0, int(self.cur.fetchone()[0]))


if __name__ == "__main__":
    unittest.main()

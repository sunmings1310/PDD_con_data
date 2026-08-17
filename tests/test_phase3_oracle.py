"""Real Oracle Product/Snapshot/Provenance/Quarantine integration."""
from __future__ import annotations

import json
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
from server.routers import products
from server.schemas import ProductUploadIn


CONFIGURED = os.getenv("T003_ORACLE_TEST_ENABLED") == "1" and all(
    os.getenv(name) for name in ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
)


@unittest.skipUnless(CONFIGURED, "BLOCKED_BY_ENVIRONMENT: isolated Oracle test schema not configured")
class Phase3OracleTest(unittest.TestCase):
    def setUp(self):
        self.conn = oracledb.connect(
            dsn=os.environ["T003_ORACLE_DSN"], user=os.environ["T003_ORACLE_USER"],
            password=os.environ["T003_ORACLE_PASSWORD"],
        )
        self.cur = self.conn.cursor()
        self.tag = "T3DQ-" + uuid.uuid4().hex[:16]
        self.platform_item = str(700000000000 + uuid.uuid4().int % 100000000000)
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
        self.lease = job_service.acquire(self.cur, device_id=self.device_id, worker_id="phase3-worker")
        assert self.lease is not None
        job_service.start(
            self.cur, device_id=self.device_id, job_id=self.lease["job_id"],
            attempt_id=self.lease["attempt_id"], worker_id="phase3-worker",
            lease_token=self.lease["lease_token"],
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.rollback()
        task = {"task": self.task_id}
        # Phase 3 append-only children first; all rows are selected only through this test Task.
        for sql in (
            "DELETE FROM SJZQ_SNAPSHOT_DIFF WHERE SNAPSHOT_ID IN (SELECT SNAPSHOT_ID FROM SJZQ_PRODUCT_SNAPSHOT WHERE TASK_ID=:task)",
            "DELETE FROM SJZQ_FIELD_PROVENANCE WHERE SNAPSHOT_ID IN (SELECT SNAPSHOT_ID FROM SJZQ_PRODUCT_SNAPSHOT WHERE TASK_ID=:task)",
            "DELETE FROM SJZQ_DATA_QUARANTINE WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_QUALITY_RESULT WHERE RAW_ID IN (SELECT RAW_ID FROM SJZQ_RAW_COLLECTION WHERE TASK_ID=:task)",
            "DELETE FROM SJZQ_PRODUCT_SNAPSHOT WHERE TASK_ID=:task",
            "DELETE FROM SJZQ_RAW_COLLECTION WHERE TASK_ID=:task",
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
            self.cur.execute(sql, task)
        self.cur.execute(
            """DELETE FROM SJZQ_ENTERPRISE_PRODUCT WHERE IDENTITY_ID IN
                 (SELECT MASTER_PRODUCT_ID FROM SJZQ_PRODUCT_MASTER
                   WHERE PLATFORM_CODE='pinduoduo' AND PLATFORM_PRODUCT_ID=:item)""",
            {"item": self.platform_item},
        )
        self.cur.execute(
            "DELETE FROM SJZQ_PRODUCT_MASTER WHERE PLATFORM_CODE='pinduoduo' AND PLATFORM_PRODUCT_ID=:item",
            {"item": self.platform_item},
        )
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

    def _body(self, key: str, *, price: float | None = 12.3, parser: str = "pdd-android-1", task_item=True, sources=None):
        return ProductUploadIn(
            device_key=self.tag, task_id=self.task_id,
            task_item_id=self.item_id if task_item else None,
            job_id=self.lease["job_id"], attempt_id=self.lease["attempt_id"],
            worker_id="phase3-worker", lease_token=self.lease["lease_token"],
            idempotency_key=key, platform_code="pinduoduo", item_id=self.platform_item,
            sell_name="Phase3 商品", shop_name="Phase3 店铺", shop_id="shop-phase3",
            item_url=f"https://mobile.yangkeduo.com/goods.html?goods_id={self.platform_item}",
            display_price=price, sales_num=10,
            sku_prices='[{"sku_id":"s1","price":12.3}]', page_status="product",
            parse_status="success", quality_status="passed",
            field_sources=sources or {
                "item_id": "embedded_json", "name": "detail_text", "price": "embedded_json",
                "sales_num": "dom", "shop": "detail_response", "sku": "sku_panel",
            },
            parser_version=parser, quality_rules_version="phase1-1",
        )

    def test_identity_snapshots_provenance_diff_and_replay(self):
        key1, key2 = "t3-first-" + self.tag, "t3-second-" + self.tag
        with patch.object(products, "get_conn", self._connection):
            first = products.upload_product(self._body(key1))
            replay = products.upload_product(self._body(key1))
            second = products.upload_product(self._body(key2, price=10.5, parser="pdd-android-2", task_item=False))
        self.assertTrue(first.ok and replay.ok and second.ok)
        self.assertEqual(first.data["snapshot_id"], replay.data["snapshot_id"])
        self.assertEqual(first.data["master_product_id"], second.data["master_product_id"])
        self.assertNotEqual(first.data["snapshot_id"], second.data["snapshot_id"])
        self.assertIn("price", second.data["changed_fields"])
        self.cur.execute(
            "SELECT COUNT(*) FROM SJZQ_PRODUCT_MASTER WHERE PLATFORM_CODE='pinduoduo' AND PLATFORM_PRODUCT_ID=:item",
            {"item": self.platform_item},
        )
        self.assertEqual(1, int(self.cur.fetchone()[0]))
        self.cur.execute(
            "SELECT SNAPSHOT_ID,DISPLAY_PRICE,PARSER_VERSION,QUALITY_RULES_VERSION FROM SJZQ_PRODUCT_SNAPSHOT WHERE MASTER_PRODUCT_ID=:id ORDER BY SNAPSHOT_ID",
            {"id": first.data["master_product_id"]},
        )
        snapshots = self.cur.fetchall()
        self.assertEqual(2, len(snapshots))
        self.assertEqual([12.3, 10.5], [float(row[1]) for row in snapshots])
        self.assertEqual(["pdd-android-1", "pdd-android-2"], [row[2] for row in snapshots])
        self.assertTrue(all(row[3] == "phase3-1" for row in snapshots))
        self.cur.execute(
            "SELECT FIELD_NAME,SOURCE_TYPE FROM SJZQ_FIELD_PROVENANCE WHERE SNAPSHOT_ID=:id",
            {"id": first.data["snapshot_id"]},
        )
        provenance = dict(self.cur.fetchall())
        self.assertEqual("embedded_json", provenance["price"])
        self.assertEqual("detail_text", provenance["title"])
        self.cur.execute(
            "SELECT PRICE_CHANGED,SALES_CHANGED FROM SJZQ_SNAPSHOT_DIFF WHERE SNAPSHOT_ID=:id",
            {"id": second.data["snapshot_id"]},
        )
        self.assertEqual((1, 0), tuple(int(v) for v in self.cur.fetchone()))

    def test_quality_rejection_is_idempotently_quarantined_without_snapshot(self):
        key = "t3-quarantine-" + self.tag
        bad_sources = {"item_id": "embedded_json", "name": "detail_text"}
        with patch.object(products, "get_conn", self._connection):
            rejected = products.upload_product(self._body(key, price=None, sources=bad_sources))
            replay = products.upload_product(self._body(key, price=None, sources=bad_sources))
        self.assertFalse(rejected.ok or replay.ok)
        self.assertTrue(rejected.data["quarantined"] and rejected.data["persisted"])
        self.assertEqual(rejected.data["quarantine_id"], replay.data["quarantine_id"])
        self.assertTrue(replay.data["idempotent"])
        self.cur.execute("SELECT COUNT(*) FROM SJZQ_PRODUCT WHERE TASK_ID=:task", {"task": self.task_id})
        self.assertEqual(0, int(self.cur.fetchone()[0]))
        self.cur.execute("SELECT COUNT(*) FROM SJZQ_PRODUCT_SNAPSHOT WHERE TASK_ID=:task", {"task": self.task_id})
        self.assertEqual(0, int(self.cur.fetchone()[0]))
        self.cur.execute(
            "SELECT FAILURE_REASON,ERROR_CODES_JSON,PARSER_VERSION,QUALITY_RULES_VERSION FROM SJZQ_DATA_QUARANTINE WHERE QUARANTINE_ID=:id",
            {"id": rejected.data["quarantine_id"]},
        )
        reason, errors, parser_version, rules_version = self.cur.fetchone()
        error_text = errors.read() if hasattr(errors, "read") else errors
        self.assertTrue(reason)
        self.assertIn("FIELD_SOURCE_MISSING:price", json.loads(error_text))
        self.assertEqual("pdd-android-1", parser_version)
        self.assertEqual("phase3-1", rules_version)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ORACLE_HOST", "127.0.0.1")
os.environ.setdefault("ORACLE_PORT", "1521")
os.environ.setdefault("ORACLE_SERVICE", "TEST")
os.environ.setdefault("ORACLE_USER", "TEST")
os.environ.setdefault("ORACLE_PASSWORD", "test-password")
os.environ.setdefault("JWT_SECRET", "Test-only-JWT-secret-32-characters!")

from server import job_service as svc
from server.schemas import JobAcquireIn, JobCheckpointIn


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 1
        self._row = None

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params or {}))
        self.rowcount = 1
        if "SELECT TASK_ID FROM SJZQ_TASK t" in compact:
            self._row = (11,)
        elif "SELECT JOB_ID FROM SJZQ_COLLECTION_JOB j" in compact:
            self._row = (21,)
        elif "SJZQ_UPLOAD_RECEIPT" in compact:
            self._row = (1,)
        elif "SJZQ_PRODUCT" in compact:
            self._row = (1,)
        elif "SELECT VERSION,PAYLOAD_SHA256" in compact:
            self._row = None
        else:
            self._row = None

    def fetchone(self):
        value, self._row = self._row, None
        return value


class JobServiceTest(unittest.TestCase):
    def setUp(self):
        self.job = {"id": 21, "task_id": 11, "key": "collect_item:task/11/item/1", "type": "collect_item", "payload": '{"keyword":"药"}', "status": "leased", "max_attempts": 5, "attempt_count": 0, "active_attempt_id": 31, "token_hash": "x", "checkpoint_version": 0, "receipt": None, "pause_requested": False}
        self.attempt = {"id": 31, "job_id": 21, "no": 1, "device_id": 7, "worker_id": "worker-a", "token_hash": "x", "trace_id": "trace", "status": "leased"}

    def test_acquire_uses_skip_locked_and_inserts_attempt_and_lease(self):
        cur = FakeCursor()
        job = dict(self.job, status="pending", active_attempt_id=None, token_hash="")
        with patch.object(svc, "_lock_device", return_value=(7, None, None)), \
             patch.object(svc, "_lock_task", return_value=("approved", "active")), \
             patch.object(svc, "_lock_job", return_value=job), \
             patch.object(svc, "next_id", side_effect=[31, 41, 51]), \
             patch.object(svc.secrets, "token_urlsafe", return_value="a" * 43), \
             patch.object(svc.uuid, "uuid4") as uuid4:
            uuid4.return_value.hex = "trace"
            result = svc.acquire(cur, device_id=7, worker_id="worker-a")
        self.assertEqual(result["attempt_id"], 31)
        self.assertEqual(result["lease_id"], 41)
        sql = "\n".join(x[0] for x in cur.calls)
        self.assertIn("FOR UPDATE SKIP LOCKED", sql)
        self.assertIn("INSERT INTO SJZQ_COLLECTION_ATTEMPT", sql)
        self.assertIn("INSERT INTO SJZQ_COLLECTION_LEASE", sql)
        self.assertIn("ACTIVE_ATTEMPT_ID", sql)
        self.assertNotIn(result["lease_token"], sql)
        self.assertNotIn("retry_wait", sql.lower())
        self.assertEqual(result["checkpoint"], {})

    def test_old_lease_is_rejected_before_business_write(self):
        cur = FakeCursor()
        stale_job = dict(self.job, token_hash=svc._hash("new-token-" + "x" * 32))
        attempt = dict(self.attempt, token_hash=stale_job["token_hash"])
        lease = {"id": 41, "job_id": 21, "attempt_id": 31, "device_id": 7, "worker_id": "worker-a", "token_hash": stale_job["token_hash"], "status": "active"}
        with patch.object(svc, "_lock_device", return_value=(7, 21, 31)), \
             patch.object(svc, "_task_for_job", return_value=11), \
             patch.object(svc, "_lock_task", return_value=("approved", "active")), \
             patch.object(svc, "_lock_job", return_value=stale_job), \
             patch.object(svc, "_lock_attempt", return_value=attempt), \
             patch.object(svc, "_lock_lease", return_value=lease):
            with self.assertRaisesRegex(svc.JobProtocolError, "STALE_LEASE"):
                svc._context(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a", lease_token="old-token-" + "x" * 32)
        self.assertEqual(cur.calls, [])

    def test_checkpoint_is_monotonic_and_idempotent(self):
        cur = FakeCursor()
        running_job = dict(self.job, status="running", checkpoint_version=2)
        running_attempt = dict(self.attempt, status="running")
        with patch.object(svc, "_context", return_value=(running_job, running_attempt)), patch.object(svc, "next_id", side_effect=[51, 52]):
            result = svc.checkpoint(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a", lease_token="x" * 43, version=3, idempotency_key="checkpoint-3", payload={"page": 3})
        self.assertEqual(result, {"version": 3, "idempotent": False})
        with patch.object(svc, "_context", return_value=(running_job, running_attempt)):
            with self.assertRaisesRegex(svc.JobProtocolError, "CHECKPOINT_VERSION_CONFLICT"):
                svc.checkpoint(FakeCursor(), device_id=7, job_id=21, attempt_id=31, worker_id="worker-a", lease_token="x" * 43, version=4, idempotency_key="checkpoint-4", payload={})

    def test_complete_requires_confirmed_receipt(self):
        cur = FakeCursor()
        running_job = dict(self.job, status="running")
        running_attempt = dict(self.attempt, status="running")
        with patch.object(svc, "_complete_replay", return_value=False), patch.object(svc, "_context", return_value=(running_job, running_attempt)), patch.object(svc, "_aggregate_task_from_jobs", return_value=None), patch.object(svc, "next_id", return_value=50):
            result = svc.complete(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a", lease_token="x" * 43, result_receipt_key="receipt-123")
        self.assertEqual(result["status"], "success")
        self.assertTrue(any("SJZQ_UPLOAD_RECEIPT" in sql for sql, _ in cur.calls))

    def test_complete_accepts_full_confirmed_receipt_manifest(self):
        cur = FakeCursor()
        running_job = dict(self.job, status="running", item_id=None)
        running_attempt = dict(self.attempt, status="running")
        with patch.object(svc, "_complete_replay", return_value=False), \
             patch.object(svc, "_context", return_value=(running_job, running_attempt)), \
             patch.object(svc, "_aggregate_task_from_jobs", return_value=None), \
             patch.object(svc, "next_id", return_value=50):
            result = svc.complete(
                cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                lease_token="x" * 43, result_receipt_key="receipt-first",
                result_receipt_keys=["receipt-first", "receipt-second"],
            )
        self.assertEqual(result["status"], "success")
        receipt_queries = [params["key"] for sql, params in cur.calls if "SJZQ_UPLOAD_RECEIPT" in sql]
        self.assertEqual(receipt_queries, ["receipt-first", "receipt-second"])

    def test_fail_uses_bounded_transient_retry_and_permanent_failure(self):
        running_job = dict(self.job, status="running")
        running_attempt = dict(self.attempt, status="running")
        with patch.object(svc, "_context", return_value=(running_job, running_attempt)), patch.object(svc, "_aggregate_task_from_jobs", return_value=None), patch.object(svc, "next_id", return_value=50):
            transient = svc.fail(FakeCursor(), device_id=7, job_id=21, attempt_id=31, worker_id="worker-a", lease_token="x" * 43, error_class="transient", error_code="HTTP_500")
        self.assertEqual(transient["status"], "retry_wait")
        with patch.object(svc, "_context", return_value=(running_job, running_attempt)), patch.object(svc, "_aggregate_task_from_jobs", return_value=None), patch.object(svc, "next_id", return_value=50):
            permanent = svc.fail(FakeCursor(), device_id=7, job_id=21, attempt_id=31, worker_id="worker-a", lease_token="x" * 43, error_class="permanent", error_code="BAD_REQUEST")
        self.assertEqual(permanent["status"], "failed")

    def test_protocol_models_require_lease_identity(self):
        self.assertEqual(JobAcquireIn(device_key="device-key", worker_id="w").lease_seconds, 120)
        with self.assertRaises(Exception):
            JobCheckpointIn(device_key="device-key", worker_id="w", job_id=1, attempt_id=2, lease_token="x" * 31, version=1, idempotency_key="checkpoint-1")


if __name__ == "__main__":
    unittest.main()








# Real Oracle integration is opt-in and only runs in the isolated schema used by
# the project baseline.  It intentionally verifies the SQL service, not mocks.
_ORACLE_JOB_CONFIGURED = os.getenv("T003_ORACLE_TEST_ENABLED") == "1" and all(
    os.getenv(name) for name in ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
)


@unittest.skipUnless(_ORACLE_JOB_CONFIGURED, "BLOCKED_BY_ENVIRONMENT: isolated Oracle test schema not configured")
class OracleJobServiceTest(unittest.TestCase):
    def setUp(self):
        import oracledb
        self.conn = oracledb.connect(dsn=os.environ["T003_ORACLE_DSN"], user=os.environ["T003_ORACLE_USER"], password=os.environ["T003_ORACLE_PASSWORD"])
        self.cur = self.conn.cursor()
        self.tag = "T2JS-" + __import__("uuid").uuid4().hex[:16]
        self.ids: dict[str, int] = {}

    def tearDown(self):
        task_id = self.ids.get("task", -1)
        for sql in (
            "DELETE FROM SJZQ_JOB_EVENT WHERE TASK_ID=:task_id",
            "DELETE FROM SJZQ_COLLECTION_CHECKPOINT WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id)",
            "DELETE FROM SJZQ_COLLECTION_LEASE WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id)",
            "DELETE FROM SJZQ_COLLECTION_ATTEMPT WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id)",
            "DELETE FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id",
            "DELETE FROM SJZQ_UPLOAD_RECEIPT WHERE TASK_ID=:task_id",
            "DELETE FROM SJZQ_PRODUCT WHERE TASK_ID=:task_id",
            "DELETE FROM SJZQ_TASK_ITEM WHERE TASK_ID=:task_id",
            "DELETE FROM SJZQ_TASK WHERE TASK_ID=:task_id",
        ):
            self.cur.execute(sql, {"task_id": task_id})
        if "device" in self.ids:
            self.cur.execute("DELETE FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": self.ids["device"]})
        self.conn.commit()
        self.conn.close()

    def _seq(self, name: str) -> int:
        self.cur.execute(f"SELECT {name}.NEXTVAL FROM DUAL")
        return int(self.cur.fetchone()[0])

    def _seed(self):
        self.ids["device"] = self._seq("SJZQ_SEQ_DEVICE")
        self.cur.execute("""INSERT INTO SJZQ_DEVICE (DEVICE_ID,DEVICE_KEY,DEVICE_NAME,PLATFORM_CODE,STATUS,CURRENT_TASK_ID,KEYWORD_RUN_COUNT,ACTIVE_JOB_ID,ACTIVE_ATTEMPT_ID)
                         VALUES (:id,:tag,:tag,'pinduoduo','online',NULL,0,NULL,NULL)""", {"id":self.ids["device"],"tag":self.tag})
        self.ids["task"] = self._seq("SJZQ_SEQ_TASK")
        self.cur.execute("""INSERT INTO SJZQ_TASK (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,TARGET_COUNT,SUCCESS_COUNT,FAIL_COUNT,REVIEW_STATUS,PAUSE_STATE)
                         VALUES (:id,:tag,'collect','pinduoduo','pending',1,1,0,0,'approved','active')""", {"id":self.ids["task"],"tag":self.tag})
        self.ids["item"] = self._seq("SJZQ_SEQ_TASK_ITEM")
        self.cur.execute("INSERT INTO SJZQ_TASK_ITEM (ITEM_ID,TASK_ID,ROW_INDEX,KEYWORD,STATUS) VALUES (:id,:task,1,:tag,'pending')", {"id":self.ids["item"],"task":self.ids["task"],"tag":self.tag})
        svc.create_jobs_for_task(self.cur, task_id=self.ids["task"])

    def test_real_flow_receipt_fence_and_completion_ack_replay(self):
        self._seed()
        lease = svc.acquire(self.cur, device_id=self.ids["device"], worker_id="oracle-job-test")
        self.assertIsNotNone(lease)
        assert lease is not None
        self.assertEqual("running", svc.start(self.cur, device_id=self.ids["device"], job_id=lease["job_id"], attempt_id=lease["attempt_id"], worker_id="oracle-job-test", lease_token=lease["lease_token"])["status"])
        self.assertEqual(1, svc.checkpoint(self.cur, device_id=self.ids["device"], job_id=lease["job_id"], attempt_id=lease["attempt_id"], worker_id="oracle-job-test", lease_token=lease["lease_token"], version=1, idempotency_key="checkpoint-" + self.tag, payload={"page_or_cursor":"1"})["version"])
        product_id = self._seq("SJZQ_SEQ_PRODUCT")
        self.cur.execute("INSERT INTO SJZQ_PRODUCT (PRODUCT_ID,TASK_ID,DEVICE_ID,PLATFORM_CODE,ITEM_ID,PRODUCT_NAME,PRICE) VALUES (:id,:task,:device,'pinduoduo','oracle-job',:tag,1)", {"id":product_id,"task":self.ids["task"],"device":self.ids["device"],"tag":self.tag})
        self.cur.execute("UPDATE SJZQ_TASK_ITEM SET PRODUCT_ID=:product_id WHERE ITEM_ID=:item_id", {"product_id":product_id,"item_id":self.ids["item"]})
        receipt = "receipt-" + self.tag
        self.cur.execute("""INSERT INTO SJZQ_UPLOAD_RECEIPT (IDEMPOTENCY_KEY,TASK_ID,DEVICE_ID,OP_TYPE,PAYLOAD_SHA256,PRODUCT_ID,RESULT_JSON,STATUS)
                         VALUES (:key,:task,:device,'product',RPAD('a',64,'a'),:product,'{}','acked')""", {"key":receipt,"task":self.ids["task"],"device":self.ids["device"],"product":product_id})
        done = svc.complete(self.cur, device_id=self.ids["device"], job_id=lease["job_id"], attempt_id=lease["attempt_id"], worker_id="oracle-job-test", lease_token=lease["lease_token"], result_receipt_key=receipt, result_product_id=product_id)
        self.assertEqual({"status":"success","idempotent":False}, done)
        self.assertTrue(svc.complete(self.cur, device_id=self.ids["device"], job_id=lease["job_id"], attempt_id=lease["attempt_id"], worker_id="oracle-job-test", lease_token=lease["lease_token"], result_receipt_key=receipt, result_product_id=product_id)["idempotent"])
        self.cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:id", {"id":self.ids["task"]})
        self.assertEqual("succeeded", self.cur.fetchone()[0])

    def test_real_expired_lease_rejects_old_worker_before_checkpoint(self):
        self._seed()
        lease = svc.acquire(self.cur, device_id=self.ids["device"], worker_id="oracle-job-test")
        assert lease is not None
        self.cur.execute("UPDATE SJZQ_COLLECTION_LEASE SET LEASED_AT=SYSTIMESTAMP-NUMTODSINTERVAL(2,'SECOND'),LEASE_EXPIRES_AT=SYSTIMESTAMP-NUMTODSINTERVAL(1,'SECOND') WHERE ATTEMPT_ID=:id", {"id":lease["attempt_id"]})
        with self.assertRaisesRegex(svc.JobProtocolError, "LEASE_EXPIRED"):
            svc.checkpoint(self.cur, device_id=self.ids["device"], job_id=lease["job_id"], attempt_id=lease["attempt_id"], worker_id="oracle-job-test", lease_token=lease["lease_token"], version=1, idempotency_key="expired-" + self.tag, payload={})
        self.cur.execute("SELECT COUNT(*) FROM SJZQ_COLLECTION_CHECKPOINT WHERE JOB_ID=:id", {"id":lease["job_id"]})
        self.assertEqual(0, int(self.cur.fetchone()[0]))

"""Real Oracle coverage for restored reconciliation compatibility paths."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import unittest
import uuid

import oracledb

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ORACLE_HOST", "127.0.0.1")
os.environ.setdefault("ORACLE_PORT", "1521")
os.environ.setdefault("ORACLE_SERVICE", "TEST")
os.environ.setdefault("ORACLE_USER", "TEST")
os.environ.setdefault("ORACLE_PASSWORD", "test-password")
os.environ.setdefault("JWT_SECRET", "Test-only-JWT-secret-32-characters!")

from server import job_service
from server.job_reconciliation import JobInconsistency, OracleReconciliationStore


CONFIGURED = os.getenv("T003_ORACLE_TEST_ENABLED") == "1" and all(
    os.getenv(name) for name in ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
)


@unittest.skipUnless(CONFIGURED, "BLOCKED_BY_ENVIRONMENT: isolated Oracle test schema not configured")
class OracleReconciliationIntegrationTest(unittest.TestCase):
    """Execute production reconciliation SQL against the isolated Oracle schema."""

    def setUp(self):
        self.conn = oracledb.connect(
            dsn=os.environ["T003_ORACLE_DSN"],
            user=os.environ["T003_ORACLE_USER"],
            password=os.environ["T003_ORACLE_PASSWORD"],
        )
        self.cur = self.conn.cursor()
        self.tag = "RECON-" + uuid.uuid4().hex[:12]
        self.scopes = {
            "A": self._create_scope("A"),
            "B": self._create_scope("B"),
        }

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def _seq(self, name: str) -> int:
        self.cur.execute(f"SELECT {name}.NEXTVAL FROM DUAL")
        return int(self.cur.fetchone()[0])

    def _create_scope(self, label: str) -> dict[str, int]:
        enterprise_id = self._seq("SJZQ_SEQ_ENTERPRISE")
        workspace_id = self._seq("SJZQ_SEQ_WORKSPACE")
        device_id = self._seq("SJZQ_SEQ_DEVICE")
        code = f"{self.tag}-{label}".lower()
        self.cur.execute(
            """INSERT INTO SJZQ_ENTERPRISE
                 (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME,STATUS)
               VALUES (:id,:code,:name,'active')""",
            {"id": enterprise_id, "code": code, "name": code},
        )
        self.cur.execute(
            """INSERT INTO SJZQ_WORKSPACE
                 (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME,STATUS)
               VALUES (:workspace_id,:enterprise_id,:code,:name,'active')""",
            {
                "workspace_id": workspace_id,
                "enterprise_id": enterprise_id,
                "code": code,
                "name": code,
            },
        )
        self.cur.execute(
            """INSERT INTO SJZQ_DEVICE
                 (DEVICE_ID,DEVICE_KEY,DEVICE_NAME,PLATFORM_CODE,STATUS,CURRENT_TASK_ID,
                  KEYWORD_RUN_COUNT,ACTIVE_JOB_ID,ACTIVE_ATTEMPT_ID,ENTERPRISE_ID,WORKSPACE_ID)
               VALUES (:device_id,:device_key,:device_name,'pinduoduo','online',NULL,0,NULL,NULL,
                       :enterprise_id,:workspace_id)""",
            {
                "device_id": device_id,
                "device_key": code,
                "device_name": code,
                "enterprise_id": enterprise_id,
                "workspace_id": workspace_id,
            },
        )
        return {
            "enterprise_id": enterprise_id,
            "workspace_id": workspace_id,
            "device_id": device_id,
        }

    def _new_job(self, label: str) -> dict[str, int]:
        scope = self.scopes[label]
        task_id = self._seq("SJZQ_SEQ_TASK")
        item_id = self._seq("SJZQ_SEQ_TASK_ITEM")
        name = f"{self.tag}-{label}-{task_id}"
        self.cur.execute(
            """INSERT INTO SJZQ_TASK
                 (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,TARGET_COUNT,
                  SUCCESS_COUNT,FAIL_COUNT,REVIEW_STATUS,PAUSE_STATE,ENTERPRISE_ID,WORKSPACE_ID)
               VALUES (:task_id,:name,'collect','pinduoduo','pending',1,1,0,0,'approved','active',
                       :enterprise_id,:workspace_id)""",
            {
                "task_id": task_id,
                "name": name,
                "enterprise_id": scope["enterprise_id"],
                "workspace_id": scope["workspace_id"],
            },
        )
        self.cur.execute(
            """INSERT INTO SJZQ_TASK_ITEM
                 (ITEM_ID,TASK_ID,ROW_INDEX,KEYWORD,STATUS,ENTERPRISE_ID,WORKSPACE_ID)
               VALUES (:item_id,:task_id,1,:keyword,'pending',:enterprise_id,:workspace_id)""",
            {
                "item_id": item_id,
                "task_id": task_id,
                "keyword": name,
                "enterprise_id": scope["enterprise_id"],
                "workspace_id": scope["workspace_id"],
            },
        )
        jobs = job_service.create_jobs_for_task(self.cur, task_id=task_id)
        self.assertEqual(1, len(jobs))
        return {**scope, "task_id": task_id, "item_id": item_id, "job_id": jobs[0]}

    def _running_job(self, label: str) -> dict[str, object]:
        fixture = self._new_job(label)
        lease = job_service.acquire(
            self.cur,
            device_id=int(fixture["device_id"]),
            worker_id=f"recon-worker-{label}",
        )
        self.assertIsNotNone(lease)
        assert lease is not None
        job_service.start(
            self.cur,
            device_id=int(fixture["device_id"]),
            job_id=lease["job_id"],
            attempt_id=lease["attempt_id"],
            worker_id=f"recon-worker-{label}",
            lease_token=lease["lease_token"],
        )
        return {**fixture, **lease, "worker_id": f"recon-worker-{label}"}

    def _event_scope(self, job_id: int, event_type: str) -> tuple[int, int, int]:
        self.cur.execute(
            """SELECT COUNT(*),MIN(ENTERPRISE_ID),MIN(WORKSPACE_ID)
                 FROM SJZQ_JOB_EVENT WHERE JOB_ID=:job_id AND EVENT_TYPE=:event_type""",
            {"job_id": job_id, "event_type": event_type},
        )
        row = self.cur.fetchone()
        return int(row[0]), int(row[1]), int(row[2])

    def test_expired_leases_executes_real_alias_mapping_and_tenant_identity(self):
        expired = self._running_job("A")
        future = self._running_job("B")
        for table in ("SJZQ_COLLECTION_JOB", "SJZQ_COLLECTION_ATTEMPT"):
            key = "JOB_ID" if table.endswith("JOB") else "ATTEMPT_ID"
            value = expired["job_id"] if key == "JOB_ID" else expired["attempt_id"]
            self.cur.execute(
                f"""UPDATE {table}
                        SET LEASED_AT=SYSTIMESTAMP-NUMTODSINTERVAL(120,'SECOND'),
                            LEASE_EXPIRES_AT=SYSTIMESTAMP-NUMTODSINTERVAL(60,'SECOND')
                      WHERE {key}=:id""",
                {"id": value},
            )
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_LEASE
                  SET LEASED_AT=SYSTIMESTAMP-NUMTODSINTERVAL(120,'SECOND'),
                      LEASE_EXPIRES_AT=SYSTIMESTAMP-NUMTODSINTERVAL(60,'SECOND')
                WHERE ATTEMPT_ID=:attempt_id""",
            {"attempt_id": expired["attempt_id"]},
        )

        candidates = OracleReconciliationStore(self.cur).expired_leases(limit=1000)
        matched = [item for item in candidates if item.job_id == expired["job_id"]]
        self.assertEqual(1, len(matched))
        self.assertEqual(expired["task_id"], matched[0].task_id)
        self.assertEqual(expired["attempt_id"], matched[0].attempt_id)
        self.assertEqual("running", matched[0].job_status)
        self.assertEqual("running", matched[0].attempt_status)
        self.assertNotIn(future["job_id"], {item.job_id for item in candidates})
        self.cur.execute(
            """SELECT j.ENTERPRISE_ID,j.WORKSPACE_ID,a.ENTERPRISE_ID,a.WORKSPACE_ID,
                      l.ENTERPRISE_ID,l.WORKSPACE_ID
                 FROM SJZQ_COLLECTION_JOB j
                 JOIN SJZQ_COLLECTION_ATTEMPT a ON a.ATTEMPT_ID=j.ACTIVE_ATTEMPT_ID
                 JOIN SJZQ_COLLECTION_LEASE l ON l.ATTEMPT_ID=a.ATTEMPT_ID
                WHERE j.JOB_ID=:job_id""",
            {"job_id": expired["job_id"]},
        )
        self.assertEqual(
            (expired["enterprise_id"], expired["workspace_id"]) * 3,
            tuple(int(value) for value in self.cur.fetchone()),
        )

    def test_promote_due_retry_preserves_next_run_at_and_other_tenant(self):
        due = self._new_job("A")
        future = self._new_job("B")
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_JOB SET STATUS='retry_wait',
                      NEXT_RUN_AT=SYSTIMESTAMP-NUMTODSINTERVAL(1,'SECOND')
                WHERE JOB_ID=:job_id""",
            {"job_id": due["job_id"]},
        )
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_JOB SET STATUS='retry_wait',
                      NEXT_RUN_AT=SYSTIMESTAMP+NUMTODSINTERVAL(300,'SECOND')
                WHERE JOB_ID=:job_id""",
            {"job_id": future["job_id"]},
        )
        store = OracleReconciliationStore(self.cur)
        candidates = store.due_retry_jobs(limit=1000)
        candidate = next(item for item in candidates if item.job_id == due["job_id"])
        self.assertNotIn(future["job_id"], {item.job_id for item in candidates})
        self.assertTrue(store.promote_due_retry(candidate, now=datetime.now(timezone.utc)))
        self.assertFalse(store.promote_due_retry(candidate, now=datetime.now(timezone.utc)))

        self.cur.execute(
            """SELECT STATUS,CASE WHEN NEXT_RUN_AT IS NOT NULL THEN 1 ELSE 0 END
                 FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id""",
            {"job_id": due["job_id"]},
        )
        row = self.cur.fetchone()
        self.assertEqual(("pending", 1), (str(row[0]).lower(), int(row[1])))
        self.cur.execute("SELECT STATUS FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:id", {"id": future["job_id"]})
        self.assertEqual("retry_wait", str(self.cur.fetchone()[0]).lower())
        self.assertEqual(
            (1, due["enterprise_id"], due["workspace_id"]),
            self._event_scope(int(due["job_id"]), "RETRY_WAIT_ELAPSED"),
        )

    def test_mark_confirmed_result_success_preserves_receipt_checkpoint_and_idempotency(self):
        fixture = self._new_job("A")
        product_id = self._seq("SJZQ_SEQ_PRODUCT")
        checkpoint_id = self._seq("SJZQ_SEQ_COLLECTION_CHECKPOINT")
        receipt_key = f"receipt-{self.tag}"
        checkpoint_key = f"checkpoint-{self.tag}"
        self.cur.execute(
            """INSERT INTO SJZQ_PRODUCT
                 (PRODUCT_ID,TASK_ID,DEVICE_ID,PLATFORM_CODE,ITEM_ID,PRODUCT_NAME,PRICE,
                  ENTERPRISE_ID,WORKSPACE_ID)
               VALUES (:product_id,:task_id,:device_id,'pinduoduo',:item_id,:name,9.9,
                       :enterprise_id,:workspace_id)""",
            {
                "product_id": product_id,
                "task_id": fixture["task_id"],
                "device_id": fixture["device_id"],
                "item_id": self.tag,
                "name": self.tag,
                "enterprise_id": fixture["enterprise_id"],
                "workspace_id": fixture["workspace_id"],
            },
        )
        self.cur.execute(
            """INSERT INTO SJZQ_UPLOAD_RECEIPT
                 (IDEMPOTENCY_KEY,TASK_ID,DEVICE_ID,OP_TYPE,PAYLOAD_SHA256,PRODUCT_ID,
                  RESULT_JSON,STATUS,ENTERPRISE_ID,WORKSPACE_ID)
               VALUES (:key,:task_id,:device_id,'product',RPAD('a',64,'a'),:product_id,
                       '{}','acked',:enterprise_id,:workspace_id)""",
            {
                "key": receipt_key,
                "task_id": fixture["task_id"],
                "device_id": fixture["device_id"],
                "product_id": product_id,
                "enterprise_id": fixture["enterprise_id"],
                "workspace_id": fixture["workspace_id"],
            },
        )
        self.cur.execute(
            """INSERT INTO SJZQ_COLLECTION_CHECKPOINT
                 (CHECKPOINT_ID,JOB_ID,ATTEMPT_ID,VERSION,IDEMPOTENCY_KEY,PAYLOAD_SHA256,
                  PAYLOAD_JSON,ENTERPRISE_ID,WORKSPACE_ID)
               VALUES (:checkpoint_id,:job_id,NULL,1,:key,RPAD('b',64,'b'),'{}',
                       :enterprise_id,:workspace_id)""",
            {
                "checkpoint_id": checkpoint_id,
                "job_id": fixture["job_id"],
                "key": checkpoint_key,
                "enterprise_id": fixture["enterprise_id"],
                "workspace_id": fixture["workspace_id"],
            },
        )
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_JOB
                  SET STATUS='retry_wait',NEXT_RUN_AT=SYSTIMESTAMP,
                      CHECKPOINT_VERSION=1,CHECKPOINT_JSON='{}',
                      RESULT_RECEIPT_KEY=:receipt_key,RESULT_PRODUCT_ID=:product_id
                WHERE JOB_ID=:job_id""",
            {"receipt_key": receipt_key, "product_id": product_id, "job_id": fixture["job_id"]},
        )
        store = OracleReconciliationStore(self.cur)
        candidate = next(
            item for item in store.confirmed_result_without_success(limit=1000)
            if item.job_id == fixture["job_id"]
        )
        self.assertTrue(store.mark_confirmed_result_success(candidate, now=datetime.now(timezone.utc)))
        self.assertFalse(store.mark_confirmed_result_success(candidate, now=datetime.now(timezone.utc)))

        self.cur.execute(
            """SELECT STATUS,RESULT_RECEIPT_KEY,RESULT_PRODUCT_ID,CHECKPOINT_VERSION,
                      CASE WHEN NEXT_RUN_AT IS NOT NULL THEN 1 ELSE 0 END
                 FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id""",
            {"job_id": fixture["job_id"]},
        )
        row = self.cur.fetchone()
        self.assertEqual(("success", receipt_key, product_id, 1, 1),
                         (str(row[0]).lower(), str(row[1]), int(row[2]), int(row[3]), int(row[4])))
        self.cur.execute(
            "SELECT COUNT(*) FROM SJZQ_COLLECTION_CHECKPOINT WHERE CHECKPOINT_ID=:id AND JOB_ID=:job_id",
            {"id": checkpoint_id, "job_id": fixture["job_id"]},
        )
        self.assertEqual(1, int(self.cur.fetchone()[0]))
        self.assertEqual(
            (1, fixture["enterprise_id"], fixture["workspace_id"]),
            self._event_scope(int(fixture["job_id"]), "RESULT_RECEIPT_REPAIRED"),
        )

    def test_mark_job_dead_reclaims_attempt_lease_and_preserves_other_tenant(self):
        broken = self._running_job("A")
        other = self._running_job("B")
        self.cur.execute(
            "UPDATE SJZQ_COLLECTION_JOB SET LEASE_TOKEN_HASH=NULL WHERE JOB_ID=:job_id",
            {"job_id": broken["job_id"]},
        )
        store = OracleReconciliationStore(self.cur)
        candidate = next(
            item for item in store.invalid_job_leases(limit=1000)
            if item.job_id == broken["job_id"]
        )
        self.assertTrue(store.mark_job_dead(
            candidate,
            reason="REAL_ORACLE_INVALID_LEASE",
            now=datetime.now(timezone.utc),
        ))
        self.assertFalse(store.mark_job_dead(
            candidate,
            reason="REAL_ORACLE_INVALID_LEASE",
            now=datetime.now(timezone.utc),
        ))

        self.cur.execute(
            """SELECT STATUS,ACTIVE_ATTEMPT_ID,LEASE_TOKEN_HASH,LEASE_EXPIRES_AT,
                      CASE WHEN NEXT_RUN_AT IS NOT NULL THEN 1 ELSE 0 END
                 FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id""",
            {"job_id": broken["job_id"]},
        )
        row = self.cur.fetchone()
        self.assertEqual(("dead", None, None, None, 1),
                         (str(row[0]).lower(), row[1], row[2], row[3], int(row[4])))
        self.cur.execute(
            "SELECT STATUS FROM SJZQ_COLLECTION_ATTEMPT WHERE ATTEMPT_ID=:id",
            {"id": broken["attempt_id"]},
        )
        self.assertEqual("reclaimed", str(self.cur.fetchone()[0]).lower())
        self.cur.execute(
            "SELECT STATUS FROM SJZQ_COLLECTION_LEASE WHERE ATTEMPT_ID=:id",
            {"id": broken["attempt_id"]},
        )
        self.assertEqual("reclaimed", str(self.cur.fetchone()[0]).lower())
        self.cur.execute("SELECT STATUS FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:id", {"id": other["job_id"]})
        self.assertEqual("running", str(self.cur.fetchone()[0]).lower())
        self.cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": broken["task_id"]})
        self.assertEqual("running", str(self.cur.fetchone()[0]).lower())
        self.assertEqual(
            (1, broken["enterprise_id"], broken["workspace_id"]),
            self._event_scope(int(broken["job_id"]), "RECONCILIATION_MANUAL_REQUIRED"),
        )

    def test_nonretryable_fail_satisfies_real_next_run_at_not_null_constraint(self):
        failed = self._running_job("A")
        other = self._running_job("B")
        result = job_service.fail(
            self.cur,
            device_id=int(failed["device_id"]),
            job_id=int(failed["job_id"]),
            attempt_id=int(failed["attempt_id"]),
            worker_id=str(failed["worker_id"]),
            lease_token=str(failed["lease_token"]),
            error_class="permanent",
            error_code="REAL_ORACLE_NONRETRYABLE",
        )
        self.assertEqual({"status": "failed", "retryable": False, "delay_seconds": None}, result)
        self.cur.execute(
            """SELECT STATUS,CASE WHEN NEXT_RUN_AT IS NOT NULL THEN 1 ELSE 0 END
                 FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id""",
            {"job_id": failed["job_id"]},
        )
        row = self.cur.fetchone()
        self.assertEqual(("failed", 1), (str(row[0]).lower(), int(row[1])))
        self.cur.execute("SELECT STATUS FROM SJZQ_COLLECTION_ATTEMPT WHERE ATTEMPT_ID=:id",
                         {"id": failed["attempt_id"]})
        self.assertEqual("failed", str(self.cur.fetchone()[0]).lower())
        self.cur.execute("SELECT STATUS FROM SJZQ_COLLECTION_LEASE WHERE ATTEMPT_ID=:id",
                         {"id": failed["attempt_id"]})
        self.assertEqual("released", str(self.cur.fetchone()[0]).lower())
        self.cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": failed["task_id"]})
        self.assertEqual("failed", str(self.cur.fetchone()[0]).lower())
        self.cur.execute("SELECT STATUS FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:id", {"id": other["job_id"]})
        self.assertEqual("running", str(self.cur.fetchone()[0]).lower())
        self.assertEqual(
            (1, failed["enterprise_id"], failed["workspace_id"]),
            self._event_scope(int(failed["job_id"]), "job_failed"),
        )


if __name__ == "__main__":
    unittest.main()

"""Phase 2 failure-injection matrix.

These tests intentionally exercise the service boundary with controllable fake
transactions.  They do not turn a network/DB exception into a success: every
scenario asserts a recoverable or terminal server truth and no duplicate
business-completion side effect.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import patch

# server.config validates import-time settings; keep this suite isolated from
# developer and production environments.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ORACLE_HOST", "127.0.0.1")
os.environ.setdefault("ORACLE_PORT", "1521")
os.environ.setdefault("ORACLE_SERVICE", "TEST")
os.environ.setdefault("ORACLE_USER", "TEST")
os.environ.setdefault("ORACLE_PASSWORD", "test-password")
os.environ.setdefault("JWT_SECRET", "Test-only-JWT-secret-32-characters!")

from server import job_service as svc
from server.job_reconciliation import ExpiredLease, JobInconsistency, ReconciliationStore, StaleOutbox, reconcile
from server.job_state import JobStatus


NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, *, receipt: bool = False, checkpoint_prior=None, fail_on: str | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.rowcount = 1
        self._row = None
        self.receipt = receipt
        self.checkpoint_prior = checkpoint_prior
        self.fail_on = fail_on

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params or {}))
        self.rowcount = 1
        if self.fail_on and self.fail_on in compact:
            raise ConnectionError("injected database outage")
        if "FROM SJZQ_UPLOAD_RECEIPT" in compact:
            self._row = (101,) if self.receipt else None
        elif "SELECT 1 FROM SJZQ_PRODUCT" in compact:
            self._row = (1,) if self.receipt else None
        elif "SELECT VERSION,PAYLOAD_SHA256" in compact:
            self._row = self.checkpoint_prior
        elif "CASE WHEN LEASE_EXPIRES_AT>SYSTIMESTAMP" in compact:
            self._row = (0,)
        elif "SELECT LEASE_ID FROM SJZQ_COLLECTION_LEASE" in compact:
            self._row = (41,)
        else:
            self._row = None

    def fetchone(self):
        result, self._row = self._row, None
        return result


class ReconcileStore(ReconciliationStore):
    """Stateful fake CAS store used to inject expiry/reclaim/outbox races."""
    def __init__(self, *, expired=(), stale_outbox=(), reject_reclaim=False):
        self.expired = list(expired)
        self.outbox = list(stale_outbox)
        self.reject_reclaim = reject_reclaim
        self.calls: list[tuple] = []

    def expired_leases(self, *, limit): return self.expired[:limit]
    def reclaim_expired(self, candidate, decision, *, now):
        self.calls.append(("reclaim", candidate.job_id, decision.target.value))
        return not self.reject_reclaim
    def terminal_task_active_jobs(self, *, limit): return []
    def success_without_result(self, *, limit): return []
    def confirmed_result_without_success(self, *, limit): return []
    def mark_confirmed_result_success(self, candidate, *, now): return True
    def duplicate_active_attempts(self, *, limit): return []
    def reclaim_stray_attempts(self, candidate, *, now): return True
    def orphan_device_claims(self, *, limit): return []
    def clear_orphan_device_claim(self, candidate, *, now): return True
    def invalid_job_leases(self, *, limit): return []
    def mark_job_dead(self, candidate, *, reason, now): return True
    def record_manual_inconsistency(self, candidate, *, reason, now): return True
    def due_retry_jobs(self, *, limit): return []
    def promote_due_retry(self, candidate, *, now): return True
    def stale_outbox(self, *, limit): return self.outbox[:limit]
    def recover_stale_outbox(self, candidate, *, now):
        self.calls.append(("outbox", candidate.outbox_id, candidate.lease_valid))
        return True


class Phase2FaultInjectionTest(unittest.TestCase):
    def setUp(self):
        self.job = {
            "id": 21, "task_id": 11, "key": "collect_item:task/11/item/1", "type": "collect_item",
            "payload": "{}", "status": "running", "max_attempts": 5, "attempt_count": 1,
            "active_attempt_id": 31, "token_hash": "hash", "checkpoint_version": 0,
            "receipt": None, "pause_requested": False,
        }
        self.attempt = {
            "id": 31, "job_id": 21, "no": 1, "device_id": 7, "worker_id": "worker-a",
            "token_hash": "hash", "trace_id": "trace-a", "status": "running",
        }

    def _lease(self, *, attempt_no=1, max_attempts=5, paused=False):
        return ExpiredLease(21, 11, 31, attempt_no, max_attempts, "running", "running",
                            paused=paused, device_id=7, lease_id=41)

    # 1. Worker performs work while disconnected: only confirmed work may win;
    # expiry creates a retryable state rather than a silent permanent running Job.
    def test_01_worker_execution_network_loss_reclaims_without_data_drop(self):
        store = ReconcileStore(expired=[self._lease()])
        report = reconcile(store, now=NOW)
        self.assertEqual(["lease_reclaimed"], [a.kind for a in report.actions])
        self.assertEqual(("reclaim", 21, "retry_wait"), store.calls[0])

    # 2. Product/upload call loses network before a receipt: Job cannot complete.
    def test_02_upload_network_failure_keeps_job_uncompleted(self):
        cur = Cursor(receipt=False)
        with patch.object(svc, "_complete_replay", return_value=False), \
             patch.object(svc, "_context", return_value=(self.job, self.attempt)):
            with self.assertRaisesRegex(svc.JobProtocolError, "RESULT_RECEIPT_NOT_CONFIRMED"):
                svc.complete(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                             lease_token="x" * 43, result_receipt_key="receipt-001")
        self.assertFalse(any("STATUS='success'" in sql for sql, _ in cur.calls))

    # 3. Dropped heartbeat is authority-neutral; expiry rejects the old execution.
    def test_03_heartbeat_loss_rejects_expired_lease_before_write(self):
        token = "x" * 43
        token_hash = svc._hash(token)
        job, attempt = dict(self.job, token_hash=token_hash), dict(self.attempt, token_hash=token_hash)
        lease = {"id": 41, "job_id": 21, "attempt_id": 31, "device_id": 7,
                 "worker_id": "worker-a", "token_hash": token_hash, "status": "active"}
        cur = Cursor()
        with patch.object(svc, "_lock_device", return_value=(7, 21, 31)), \
             patch.object(svc, "_task_for_job", return_value=11), \
             patch.object(svc, "_lock_task", return_value=("approved", "active")), \
             patch.object(svc, "_lock_job", return_value=job), \
             patch.object(svc, "_lock_attempt", return_value=attempt), \
             patch.object(svc, "_lock_lease", return_value=lease):
            with self.assertRaisesRegex(svc.JobProtocolError, "LEASE_EXPIRED"):
                svc.heartbeat(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a", lease_token=token)
        self.assertFalse(any("UPDATE SJZQ_COLLECTION_JOB" in sql for sql, _ in cur.calls))

    # 4. Android/App kill leaves the server lease to be reclaimed.
    def test_04_app_kill_leaves_reclaimable_server_work(self):
        report = reconcile(ReconcileStore(expired=[self._lease()]), now=NOW)
        self.assertEqual("lease_reclaimed", report.actions[0].kind)
        self.assertNotEqual("success", report.actions[0].detail)

    # 5. Agent process crash behaves identically; no fabricated finish call occurs.
    def test_05_agent_process_crash_never_fabricates_complete(self):
        store = ReconcileStore(expired=[self._lease(attempt_no=5, max_attempts=5)])
        report = reconcile(store, now=NOW)
        self.assertEqual("lease_reclaimed", report.actions[0].kind)
        self.assertEqual(("reclaim", 21, "failed"), store.calls[0])

    # 6. Completion ACK replay uses the stable receipt branch and emits no second write.
    def test_06_completion_ack_loss_replay_is_idempotent(self):
        cur = Cursor(receipt=True)
        with patch.object(svc, "_complete_replay", return_value=True), \
             patch.object(svc, "_context", side_effect=AssertionError("replay must bypass released lease guard")):
            result = svc.complete(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                                  lease_token="x" * 43, result_receipt_key="receipt-006")
        self.assertEqual({"status": "success", "idempotent": True}, result)
        self.assertFalse(any("UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='success'" in sql for sql, _ in cur.calls))

    # 7. Server 500 maps to finite transient retry rather than success.
    def test_07_server_500_uses_bounded_transient_retry(self):
        with patch.object(svc, "_context", return_value=(self.job, self.attempt)), patch.object(svc, "next_id", return_value=91):
            result = svc.fail(Cursor(), device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                              lease_token="x" * 43, error_class="transient", error_code="HTTP_500")
        self.assertEqual("retry_wait", result["status"])
        self.assertTrue(result["retryable"])

    # 8. A Worker requesting again while it owns a lease gets no duplicate Job.
    def test_08_same_worker_duplicate_acquire_has_no_second_attempt(self):
        cur = Cursor()
        with patch.object(svc, "_lock_device", return_value=(7, 21, 31)):
            self.assertIsNone(svc.acquire(cur, device_id=7, worker_id="worker-a"))
        self.assertEqual([], cur.calls)

    # 9. A second device must be fenced by the active-device unique constraint.
    def test_09_two_devices_cannot_create_two_active_attempts(self):
        schema = (ROOT / "server" / "init_schema.py").read_text(encoding="utf-8")
        self.assertIn("UQ_SJZQ_ATTEMPT_ACTIVE_JOB", schema)
        self.assertIn("UQ_SJZQ_ATTEMPT_ACTIVE_DEVICE", schema)
        self.assertIn("CASE WHEN STATUS IN ('leased', 'running') THEN JOB_ID", schema)

    # 10. Just-expired stale Worker submission has no business side effect.
    def test_10_expired_old_worker_complete_is_rejected(self):
        cur = Cursor()
        with patch.object(svc, "_complete_replay", return_value=False), \
             patch.object(svc, "_context", side_effect=svc.JobProtocolError("LEASE_EXPIRED", "expired")):
            with self.assertRaisesRegex(svc.JobProtocolError, "LEASE_EXPIRED"):
                svc.complete(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                             lease_token="x" * 43, result_receipt_key="receipt-010")
        self.assertEqual([], cur.calls)

    # 11. After reclaim/new acquire, the old lease gets a stable stale error.
    def test_11_reclaimed_worker_cannot_override_new_attempt(self):
        cur = Cursor()
        with patch.object(svc, "_context", side_effect=svc.JobProtocolError("STALE_LEASE", "reclaimed", "leased")):
            with self.assertRaisesRegex(svc.JobProtocolError, "STALE_LEASE"):
                svc.checkpoint(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                               lease_token="x" * 43, version=1, idempotency_key="checkpoint-011", payload={})
        self.assertEqual([], cur.calls)

    # 12. User pause does not cancel a running attempt immediately; it requests a safe yield.
    def test_12_pause_with_running_job_requests_checkpoint_yield(self):
        cur = Cursor()
        with patch.object(svc, "_lock_task", return_value=("approved", "active")), patch.object(svc, "next_id", return_value=92):
            svc.pause_task(cur, task_id=11)
        sql = "\n".join(statement for statement, _ in cur.calls)
        self.assertIn("PAUSE_REQUESTED=1", sql)
        self.assertIn("STATUS IN ('leased','running')", sql)
        self.assertNotIn("STATUS='cancelled'", sql)

    # 13. Resume only makes safely paused Jobs eligible again.
    def test_13_resume_returns_paused_jobs_to_pending(self):
        cur = Cursor()
        with patch.object(svc, "_lock_task", return_value=("approved", "paused")), patch.object(svc, "next_id", return_value=93):
            svc.resume_task(cur, task_id=11)
        sql = "\n".join(statement for statement, _ in cur.calls)
        self.assertIn("STATUS='pending'", sql)
        self.assertIn("STATUS='paused'", sql)

    # 14. Crash before checkpoint insert leaves no checkpoint-version mutation.
    def test_14_checkpoint_crash_before_write_does_not_advance_version(self):
        cur = Cursor(fail_on="INSERT INTO SJZQ_COLLECTION_CHECKPOINT")
        with patch.object(svc, "_context", return_value=(self.job, self.attempt)), patch.object(svc, "next_id", return_value=94):
            with self.assertRaises(ConnectionError):
                svc.checkpoint(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                               lease_token="x" * 43, version=1, idempotency_key="checkpoint-014", payload={"page": 1})
        self.assertFalse(any("SET CHECKPOINT_VERSION" in sql for sql, _ in cur.calls))

    # 15. ACK loss after persisted checkpoint replays the same receipt/version.
    def test_15_checkpoint_ack_loss_replays_without_second_version(self):
        payload = {"page": 1}
        digest = svc._hash(svc._json(payload))
        cur = Cursor(checkpoint_prior=(1, digest))
        with patch.object(svc, "_context", return_value=(self.job, self.attempt)):
            result = svc.checkpoint(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                                    lease_token="x" * 43, version=1, idempotency_key="checkpoint-015", payload=payload)
        self.assertEqual({"version": 1, "idempotent": True}, result)
        self.assertFalse(any("INSERT INTO SJZQ_COLLECTION_CHECKPOINT" in sql for sql, _ in cur.calls))

    # 16. Restart uses persisted Oracle time/lease state, not process-local time.
    def test_16_server_restart_reconciliation_uses_database_time(self):
        source = (ROOT / "server" / "job_reconciliation.py").read_text(encoding="utf-8")
        self.assertIn("SJZQ_COLLECTION_LEASE", source)
        self.assertIn("LEASE_EXPIRES_AT <= SYSTIMESTAMP", source)
        self.assertNotIn("datetime.now() <=", source)

    # 17. DB outage propagates so get_conn transaction logic can roll back; it is never completion.
    def test_17_database_failure_propagates_without_complete(self):
        cur = Cursor(receipt=True, fail_on="UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='success'")
        with patch.object(svc, "_complete_replay", return_value=False), \
             patch.object(svc, "_context", return_value=(self.job, self.attempt)):
            with self.assertRaises(ConnectionError):
                svc.complete(cur, device_id=7, job_id=21, attempt_id=31, worker_id="worker-a",
                             lease_token="x" * 43, result_receipt_key="receipt-017")
        self.assertFalse(any("SJZQ_COLLECTION_JOB SET STATUS='success'" in sql for sql, _ in cur.calls))

    # 18. An outbox delivery timeout is recovered/dead-lettered once; its event key stays unique.
    def test_18_outbox_duplicate_delivery_has_single_recovery_effect(self):
        store = ReconcileStore(stale_outbox=[StaleOutbox(501, 21, 31, True)])
        report = reconcile(store, now=NOW)
        self.assertEqual(["outbox_recovered"], [action.kind for action in report.actions])
        self.assertEqual([("outbox", 501, True)], store.calls)
        schema = (ROOT / "server" / "init_schema.py").read_text(encoding="utf-8")
        self.assertIn("UK_SJZQ_OUTBOX_EVENT UNIQUE (EVENT_KEY)", schema)


if __name__ == "__main__":
    unittest.main()

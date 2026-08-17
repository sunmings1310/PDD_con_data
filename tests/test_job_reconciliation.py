from __future__ import annotations

from datetime import datetime, timezone
import unittest

from server.job_reconciliation import (
    DuplicateAttempt,
    ExpiredLease,
    JobInconsistency,
    OracleReconciliationStore,
    StaleOutbox,
    reconcile,
)
from server.job_state import JobStatus, RetryDecision


NOW = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self):
        self.expired: list[ExpiredLease] = []
        self.terminal: list[JobInconsistency] = []
        self.missing: list[JobInconsistency] = []
        self.confirmed: list[JobInconsistency] = []
        self.duplicates: list[DuplicateAttempt] = []
        self.orphans: list[JobInconsistency] = []
        self.invalid: list[JobInconsistency] = []
        self.due: list[JobInconsistency] = []
        self.outbox: list[StaleOutbox] = []
        self.calls: list[tuple] = []
        self.reject: set[tuple[str, int]] = set()

    def _ok(self, operation: str, job_id: int) -> bool:
        self.calls.append((operation, job_id))
        return (operation, job_id) not in self.reject

    def expired_leases(self, *, limit): return self.expired[:limit]
    def reclaim_expired(self, candidate, decision, *, now):
        self.calls.append(("reclaim", candidate.job_id, decision))
        return ("reclaim", candidate.job_id) not in self.reject
    def terminal_task_active_jobs(self, *, limit): return self.terminal[:limit]
    def success_without_result(self, *, limit): return self.missing[:limit]
    def confirmed_result_without_success(self, *, limit): return self.confirmed[:limit]
    def mark_confirmed_result_success(self, candidate, *, now): return self._ok("result_success", candidate.job_id)
    def duplicate_active_attempts(self, *, limit): return self.duplicates[:limit]
    def reclaim_stray_attempts(self, candidate, *, now): return self._ok("stray", candidate.job_id)
    def orphan_device_claims(self, *, limit): return self.orphans[:limit]
    def clear_orphan_device_claim(self, candidate, *, now): return self._ok("clear_device", candidate.job_id)
    def invalid_job_leases(self, *, limit): return self.invalid[:limit]
    def mark_job_dead(self, candidate, *, reason, now):
        self.calls.append(("dead", candidate.job_id, reason))
        return ("dead", candidate.job_id) not in self.reject
    def record_manual_inconsistency(self, candidate, *, reason, now):
        self.calls.append(("manual", candidate.job_id, reason))
        return ("manual", candidate.job_id) not in self.reject
    def due_retry_jobs(self, *, limit): return self.due[:limit]
    def promote_due_retry(self, candidate, *, now): return self._ok("promote", candidate.job_id)
    def stale_outbox(self, *, limit): return self.outbox[:limit]
    def recover_stale_outbox(self, candidate, *, now): return self._ok("outbox", candidate.job_id)


class RecordingCursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.sql: list[tuple[str, dict]] = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params or {}))

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class JobReconciliationTest(unittest.TestCase):
    def test_expired_lease_retries_then_later_scan_promotes(self):
        store = FakeStore()
        store.expired = [ExpiredLease(11, 7, 101, 1, 5, "running", "running", lease_id=1001)]
        store.due = [JobInconsistency(11, 7)]

        report = reconcile(store, now=NOW)

        self.assertEqual(["lease_reclaimed", "retry_promoted"], [a.kind for a in report.actions])
        decision = next(call[2] for call in store.calls if call[0] == "reclaim")
        self.assertEqual(JobStatus.RETRY_WAIT, decision.target)
        self.assertTrue(decision.retryable)
        self.assertGreaterEqual(decision.delay_seconds or 0, 15)
        self.assertEqual(1, report.scanned["expired_leases"])

    def test_reclaim_is_bounded_and_pause_never_retries(self):
        store = FakeStore()
        store.expired = [
            ExpiredLease(12, 7, 102, 5, 5, "running", "running", lease_id=1002),
            ExpiredLease(13, 7, 103, 1, 5, "leased", "leased", paused=True, lease_id=1003),
        ]
        reconcile(store, now=NOW)
        decisions = {call[1]: call[2] for call in store.calls if call[0] == "reclaim"}
        self.assertEqual(JobStatus.FAILED, decisions[12].target)
        self.assertEqual("max_attempts_exhausted", decisions[12].reason)
        self.assertEqual(JobStatus.PAUSED, decisions[13].target)
        self.assertFalse(decisions[13].retryable)

    def test_stale_compare_and_set_produces_no_false_repaired_event(self):
        store = FakeStore()
        store.expired = [ExpiredLease(14, 7, 104, 1, 5, "running", "running", lease_id=1004)]
        store.reject.add(("reclaim", 14))  # heartbeat/reclaim race won elsewhere
        report = reconcile(store, now=NOW)
        self.assertEqual([], report.actions)

    def test_inconsistencies_only_auto_fix_deterministic_cases(self):
        store = FakeStore()
        store.terminal = [JobInconsistency(21, 7, 201)]
        store.missing = [JobInconsistency(22, 7, 202)]
        store.confirmed = [JobInconsistency(23, 7, 203)]
        store.duplicates = [
            DuplicateAttempt(24, 7, 204, (204, 205)),
            DuplicateAttempt(25, 7, None, (206, 207)),
        ]
        store.orphans = [JobInconsistency(26, 7, 208, device_id=3)]
        store.invalid = [JobInconsistency(27, 7, 209)]
        store.outbox = [StaleOutbox(301, 28, 210, True), StaleOutbox(302, 29, 211, False)]

        report = reconcile(store, now=NOW)

        self.assertEqual(
            [
                "manual_required", "manual_required", "job_success_repaired",
                "stray_attempts_reclaimed", "manual_required", "orphan_device_claim_cleared",
                "manual_required", "outbox_recovered", "outbox_dead_lettered",
            ],
            [a.kind for a in report.actions],
        )
        dead_reasons = {(call[1], call[2]) for call in store.calls if call[0] == "dead"}
        self.assertEqual(
            {
                (21, "TERMINAL_TASK_WITH_ACTIVE_JOB"),
                (25, "MULTIPLE_ACTIVE_ATTEMPTS"),
                (27, "INVALID_ACTIVE_LEASE"),
            },
            dead_reasons,
        )
        self.assertIn(("manual", 22, "SUCCESS_MISSING_CONFIRMED_RESULT"), store.calls)

    def test_batch_limit_and_invalid_limit(self):
        store = FakeStore()
        store.expired = [ExpiredLease(30, 7, 301, 1, 5, "running", "running", lease_id=1301)] * 2
        self.assertEqual(1, len(reconcile(store, limit=1, now=NOW).actions))
        with self.assertRaises(ValueError):
            reconcile(store, limit=0, now=NOW)

    def test_oracle_expired_scan_uses_lease_as_authority(self):
        cur = RecordingCursor([(1, 2, 3, 1, 5, "running", "running", 0, 9, 42)])
        store = OracleReconciliationStore(cur)
        rows = store.expired_leases(limit=4)
        self.assertEqual(42, rows[0].lease_id)
        sql = cur.sql[0][0]
        self.assertIn("SJZQ_COLLECTION_LEASE", sql)
        self.assertIn("l.STATUS='active'", sql)
        self.assertIn("SYSTIMESTAMP", sql)
        self.assertEqual({"limit": 4}, cur.sql[0][1])

    def test_oracle_result_scans_require_receipt_and_business_row(self):
        cur = RecordingCursor()
        store = OracleReconciliationStore(cur)
        store.success_without_result(limit=9)
        store.confirmed_result_without_success(limit=9)
        sql = "\n".join(statement for statement, _ in cur.sql)
        self.assertIn("SJZQ_UPLOAD_RECEIPT", sql)
        self.assertIn("RESULT_RECEIPT_KEY", sql)
        self.assertIn("SJZQ_PRODUCT", sql)

    def test_oracle_reclaim_uses_lock_order_and_lease_compare_and_set(self):
        # device lock, task lock, job lock, attempt lock, lease lock, then
        # lease lock then an idempotent audit MERGE.
        cur = RecordingCursor([(9,), (2,), ("running", 3), ("running", 9), ("active",)])
        store = OracleReconciliationStore(cur)
        lease = ExpiredLease(1, 2, 3, 1, 5, "running", "running", device_id=9, lease_id=4)
        decision = RetryDecision(JobStatus.RETRY_WAIT, True, 17, "transient_backoff")

        self.assertTrue(store.reclaim_expired(lease, decision, now=NOW))

        sql = [statement for statement, _ in cur.sql]
        positions = [
            next(i for i, statement in enumerate(sql) if needle in statement)
            for needle in (
                "FROM SJZQ_DEVICE WHERE DEVICE_ID=:id FOR UPDATE",
                "FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE",
                "FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id FOR UPDATE",
                "FROM SJZQ_COLLECTION_ATTEMPT",
                "FROM SJZQ_COLLECTION_LEASE",
            )
        ]
        self.assertEqual(sorted(positions), positions)
        lease_update = next(i for i, statement in enumerate(sql) if "UPDATE SJZQ_COLLECTION_LEASE" in statement)
        attempt_update = next(i for i, statement in enumerate(sql) if "UPDATE SJZQ_COLLECTION_ATTEMPT" in statement)
        self.assertLess(lease_update, attempt_update)
        self.assertIn("LEASE_EXPIRES_AT <= SYSTIMESTAMP", sql[lease_update])
        self.assertIn("ACTIVE_ATTEMPT_ID=:attempt_id", "\n".join(sql))


if __name__ == "__main__":
    unittest.main()

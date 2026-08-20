"""Authoritative Phase 2 reconciliation and lease reclaim service.

The reconciliation scheduler and an operator-triggered API call the same pure
``reconcile`` function.  The Oracle adapter performs every compare-and-set
mutation in its own transaction; therefore an item found by a scan is only a
candidate, never permission to overwrite a newer lease.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Protocol, Sequence

from server.job_state import ErrorClass, JobStatus, RetryDecision, decide_retry

ACTIVE_JOB_STATUSES = frozenset({JobStatus.LEASED.value, JobStatus.RUNNING.value})
ACTIVE_ATTEMPT_STATUSES = frozenset({"leased", "running"})
TERMINAL_TASK_STATUSES = frozenset({"succeeded", "partially_succeeded", "failed", "cancelled", "archived"})


@dataclass(frozen=True)
class ExpiredLease:
    job_id: int
    task_id: int
    attempt_id: int
    attempt_no: int
    max_attempts: int
    job_status: str
    attempt_status: str
    paused: bool = False
    device_id: int | None = None
    lease_id: int | None = None


@dataclass(frozen=True)
class JobInconsistency:
    job_id: int
    task_id: int
    attempt_id: int | None = None
    device_id: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class DuplicateAttempt:
    job_id: int
    task_id: int
    active_attempt_id: int | None
    attempt_ids: tuple[int, ...]


@dataclass(frozen=True)
class StaleOutbox:
    outbox_id: int
    job_id: int
    attempt_id: int | None
    lease_valid: bool


@dataclass(frozen=True)
class ReconciliationAction:
    kind: str
    job_id: int | None = None
    attempt_id: int | None = None
    detail: str = ""


@dataclass
class ReconciliationReport:
    started_at: datetime
    actions: list[ReconciliationAction] = field(default_factory=list)
    scanned: dict[str, int] = field(default_factory=dict)

    @property
    def repaired(self) -> int:
        return len(self.actions)

    def add(self, kind: str, *, job_id: int | None = None, attempt_id: int | None = None, detail: str = "") -> None:
        self.actions.append(ReconciliationAction(kind, job_id, attempt_id, detail))


class ReconciliationStore(Protocol):
    """Compare-and-set persistence boundary.

    Every mutating method returns False when a concurrent worker changed the
    row after the scan. A scheduler can safely run multiple copies because a
    scan result is never execution authority.
    """

    def expired_leases(self, *, limit: int) -> Sequence[ExpiredLease]: ...
    def reclaim_expired(self, candidate: ExpiredLease, decision: RetryDecision, *, now: datetime) -> bool: ...
    def terminal_task_active_jobs(self, *, limit: int) -> Sequence[JobInconsistency]: ...
    def success_without_result(self, *, limit: int) -> Sequence[JobInconsistency]: ...
    def confirmed_result_without_success(self, *, limit: int) -> Sequence[JobInconsistency]: ...
    def mark_confirmed_result_success(self, candidate: JobInconsistency, *, now: datetime) -> bool: ...
    def duplicate_active_attempts(self, *, limit: int) -> Sequence[DuplicateAttempt]: ...
    def reclaim_stray_attempts(self, candidate: DuplicateAttempt, *, now: datetime) -> bool: ...
    def orphan_device_claims(self, *, limit: int) -> Sequence[JobInconsistency]: ...
    def clear_orphan_device_claim(self, candidate: JobInconsistency, *, now: datetime) -> bool: ...
    def invalid_job_leases(self, *, limit: int) -> Sequence[JobInconsistency]: ...
    def mark_job_dead(self, candidate: JobInconsistency, *, reason: str, now: datetime) -> bool: ...
    def record_manual_inconsistency(self, candidate: JobInconsistency, *, reason: str, now: datetime) -> bool: ...
    def due_retry_jobs(self, *, limit: int) -> Sequence[JobInconsistency]: ...
    def promote_due_retry(self, candidate: JobInconsistency, *, now: datetime) -> bool: ...
    def stale_outbox(self, *, limit: int) -> Sequence[StaleOutbox]: ...
    def recover_stale_outbox(self, candidate: StaleOutbox, *, now: datetime) -> bool: ...
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def reclaim_decision(candidate: ExpiredLease) -> RetryDecision:
    """Translate an expired execution right into the ADR's Job state policy."""
    if candidate.paused:
        return RetryDecision(JobStatus.PAUSED, False, None, "pause_requested")
    return decide_retry(
        ErrorClass.TRANSIENT,
        attempt_no=candidate.attempt_no,
        max_attempts=candidate.max_attempts,
        identity=f"job/{candidate.job_id}",
    )


def reconcile(store: ReconciliationStore, *, limit: int = 100, now: datetime | None = None) -> ReconciliationReport:
    """Reconcile bounded batches without trusting Worker or client time.

    ``now`` is injected only for tests/event timestamps.  Oracle comparison
    predicates use ``SYSTIMESTAMP`` inside each persistence method, which is
    the source of truth for whether a lease is still expired.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    report = ReconciliationReport(started_at=now or utc_now())

    def scan(name: str, values: Sequence[object]) -> Sequence[object]:
        report.scanned[name] = len(values)
        return values

    for lease in scan("expired_leases", store.expired_leases(limit=limit)):
        assert isinstance(lease, ExpiredLease)
        decision = reclaim_decision(lease)
        if store.reclaim_expired(lease, decision, now=report.started_at):
            report.add("lease_reclaimed", job_id=lease.job_id, attempt_id=lease.attempt_id, detail=decision.reason)

    # A terminal Task with a live Job has competing authority.  Cancelling it
    # automatically could hide unconfirmed business output, so it is dead-lettered.
    for item in scan("terminal_task_active_jobs", store.terminal_task_active_jobs(limit=limit)):
        assert isinstance(item, JobInconsistency)
        if store.mark_job_dead(item, reason="TERMINAL_TASK_WITH_ACTIVE_JOB", now=report.started_at):
            report.add("manual_required", job_id=item.job_id, attempt_id=item.attempt_id, detail="terminal_task_active_job")

    for item in scan("success_without_result", store.success_without_result(limit=limit)):
        assert isinstance(item, JobInconsistency)
        # Success is terminal and must not be silently rewritten.  Preserve it
        # as evidence, emit a durable manual event, and let an operator choose
        # an explicit compensating Job rather than losing a confirmed result.
        if store.record_manual_inconsistency(item, reason="SUCCESS_MISSING_CONFIRMED_RESULT", now=report.started_at):
            report.add("manual_required", job_id=item.job_id, attempt_id=item.attempt_id, detail="success_missing_result")

    # A complete result receipt is a stronger fact than an unfinished Job.
    # The adapter only returns rows whose receipt manifest is explicitly final.
    for item in scan("confirmed_result_without_success", store.confirmed_result_without_success(limit=limit)):
        assert isinstance(item, JobInconsistency)
        if store.mark_confirmed_result_success(item, now=report.started_at):
            report.add("job_success_repaired", job_id=item.job_id, attempt_id=item.attempt_id, detail="confirmed_result")

    for duplicate in scan("duplicate_active_attempts", store.duplicate_active_attempts(limit=limit)):
        assert isinstance(duplicate, DuplicateAttempt)
        if duplicate.active_attempt_id and store.reclaim_stray_attempts(duplicate, now=report.started_at):
            report.add("stray_attempts_reclaimed", job_id=duplicate.job_id, attempt_id=duplicate.active_attempt_id)
        else:
            inconsistency = JobInconsistency(duplicate.job_id, duplicate.task_id, duplicate.active_attempt_id)
            if store.mark_job_dead(inconsistency, reason="MULTIPLE_ACTIVE_ATTEMPTS", now=report.started_at):
                report.add("manual_required", job_id=duplicate.job_id, attempt_id=duplicate.active_attempt_id, detail="multiple_active_attempts")

    for item in scan("orphan_device_claims", store.orphan_device_claims(limit=limit)):
        assert isinstance(item, JobInconsistency)
        if store.clear_orphan_device_claim(item, now=report.started_at):
            report.add("orphan_device_claim_cleared", job_id=item.job_id, attempt_id=item.attempt_id)

    for item in scan("invalid_job_leases", store.invalid_job_leases(limit=limit)):
        assert isinstance(item, JobInconsistency)
        if store.mark_job_dead(item, reason="INVALID_ACTIVE_LEASE", now=report.started_at):
            report.add("manual_required", job_id=item.job_id, attempt_id=item.attempt_id, detail="invalid_active_lease")

    for item in scan("due_retry_jobs", store.due_retry_jobs(limit=limit)):
        assert isinstance(item, JobInconsistency)
        if store.promote_due_retry(item, now=report.started_at):
            report.add("retry_promoted", job_id=item.job_id)

    for item in scan("stale_outbox", store.stale_outbox(limit=limit)):
        assert isinstance(item, StaleOutbox)
        if store.recover_stale_outbox(item, now=report.started_at):
            report.add("outbox_recovered" if item.lease_valid else "outbox_dead_lettered", job_id=item.job_id, attempt_id=item.attempt_id)

    return report


class OracleReconciliationStore:
    """Oracle implementation using lease-token-hash/Attempt compare-and-set guards.

    The schema is additive and all SQL references the Phase 2 collection
    tables.  Callers must wrap ``reconcile`` in ``get_conn()`` so one bounded
    batch commits atomically with its audit events.
    """

    def __init__(self, cur):
        self.cur = cur

    @staticmethod
    def _rows(cur) -> list[tuple]:
        return list(cur.fetchall())

    def expired_leases(self, *, limit: int) -> Sequence[ExpiredLease]:
        self.cur.execute(
            """
            SELECT * FROM (
              SELECT j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID, a.ATTEMPT_NO,
                     j.MAX_ATTEMPTS, j.STATUS AS JOB_STATUS, a.STATUS AS ATTEMPT_STATUS,
                     CASE WHEN NVL(j.PAUSE_REQUESTED, 0)=1 OR NVL(t.PAUSE_STATE, 'active')='paused'
                          THEN 1 ELSE 0 END AS IS_PAUSED,
                     a.DEVICE_ID, l.LEASE_ID
                FROM SJZQ_COLLECTION_JOB j
                JOIN SJZQ_COLLECTION_ATTEMPT a ON a.ATTEMPT_ID=j.ACTIVE_ATTEMPT_ID
                JOIN SJZQ_COLLECTION_LEASE l ON l.ATTEMPT_ID=a.ATTEMPT_ID
                JOIN SJZQ_TASK t ON t.TASK_ID=j.TASK_ID
               WHERE j.STATUS IN ('leased', 'running')
                 AND a.STATUS IN ('leased', 'running')
                 AND l.STATUS='active' AND l.LEASE_EXPIRES_AT <= SYSTIMESTAMP
                 AND j.LEASE_EXPIRES_AT <= SYSTIMESTAMP
               ORDER BY j.LEASE_EXPIRES_AT, j.JOB_ID
            ) WHERE ROWNUM <= :limit
            """,
            {"limit": limit},
        )
        return [
            ExpiredLease(int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]), str(row[5]).lower(), str(row[6]).lower(), bool(row[7]), int(row[8]) if row[8] is not None else None, int(row[9]))
            for row in self._rows(self.cur)
        ]

    def _event(self, *, job_id: int, task_id: int, attempt_id: int | None, event: str, old: str | None, new: str | None, error_code: str | None = None, detail: str = "") -> None:
        event_key = hashlib.sha256(
            f"reconciliation:{event}:{job_id}:{attempt_id}:{error_code or ''}".encode()
        ).hexdigest()
        self.cur.execute(
            """MERGE INTO SJZQ_JOB_EVENT target
               USING (SELECT :event_key AS EVENT_KEY FROM DUAL) source
                  ON (target.EVENT_KEY=source.EVENT_KEY)
               WHEN NOT MATCHED THEN INSERT
                 (EVENT_ID, EVENT_KEY, TASK_ID, JOB_ID, ATTEMPT_ID, EVENT_TYPE, OLD_STATUS, NEW_STATUS,
                  ERROR_CODE, DETAIL_JSON, CREATE_TIME)
               VALUES
                 (SJZQ_SEQ_JOB_EVENT.NEXTVAL, :event_key, :task_id, :job_id, :attempt_id, :event, :old, :new,
                  :error_code, :detail, SYSTIMESTAMP)""",
            {"event_key": event_key, "task_id": task_id, "job_id": job_id, "attempt_id": attempt_id,
             "event": event, "old": old, "new": new, "error_code": error_code, "detail": detail[:2000]},
        )

    def reclaim_expired(self, candidate: ExpiredLease, decision: RetryDecision, *, now: datetime) -> bool:
        # Lock in the ADR order Device -> Task -> Job -> Attempt -> Lease.
        # Candidates are not locks: a late heartbeat that refreshes the Lease
        # makes this operation return False with no destructive side effect.
        device_id = candidate.device_id
        if device_id is not None:
            self.cur.execute("SELECT DEVICE_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id FOR UPDATE", {"id": device_id})
            if not self.cur.fetchone():
                return False
        self.cur.execute("SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE", {"id": candidate.task_id})
        if not self.cur.fetchone():
            return False
        self.cur.execute(
            """SELECT STATUS, ACTIVE_ATTEMPT_ID FROM SJZQ_COLLECTION_JOB
                 WHERE JOB_ID=:job_id FOR UPDATE""",
            {"job_id": candidate.job_id},
        )
        job = self.cur.fetchone()
        if not job or int(job[1] or -1) != candidate.attempt_id or str(job[0]).lower() not in ACTIVE_JOB_STATUSES:
            return False
        self.cur.execute(
            """SELECT STATUS, DEVICE_ID FROM SJZQ_COLLECTION_ATTEMPT
                 WHERE ATTEMPT_ID=:attempt_id AND JOB_ID=:job_id FOR UPDATE""",
            {"attempt_id": candidate.attempt_id, "job_id": candidate.job_id},
        )
        attempt = self.cur.fetchone()
        if not attempt or str(attempt[0]).lower() not in ACTIVE_ATTEMPT_STATUSES:
            return False
        if device_id != (int(attempt[1]) if attempt[1] is not None else None) or candidate.lease_id is None:
            return False
        self.cur.execute(
            """SELECT STATUS FROM SJZQ_COLLECTION_LEASE
                 WHERE LEASE_ID=:lease_id AND JOB_ID=:job_id AND ATTEMPT_ID=:attempt_id FOR UPDATE""",
            {"lease_id": candidate.lease_id, "job_id": candidate.job_id, "attempt_id": candidate.attempt_id},
        )
        lease = self.cur.fetchone()
        if not lease or str(lease[0]).lower() != "active":
            return False
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_LEASE
                   SET STATUS='reclaimed', RELEASED_AT=SYSTIMESTAMP, RECLAIMED_AT=SYSTIMESTAMP,
                       RELEASE_REASON='LEASE_EXPIRED'
                 WHERE LEASE_ID=:lease_id AND STATUS='active' AND LEASE_EXPIRES_AT <= SYSTIMESTAMP""",
            {"lease_id": candidate.lease_id},
        )
        if self.cur.rowcount != 1:
            return False
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_ATTEMPT
                   SET STATUS='reclaimed', FINISHED_AT=SYSTIMESTAMP,
                       ERROR_CLASS='transient', ERROR_CODE='LEASE_EXPIRED'
                 WHERE ATTEMPT_ID=:attempt_id AND STATUS IN ('leased','running')
                   AND LEASE_EXPIRES_AT <= SYSTIMESTAMP""",
            {"attempt_id": candidate.attempt_id},
        )
        if self.cur.rowcount != 1:
            raise RuntimeError("active lease had no reclaimable active attempt")
        target = decision.target.value
        params = {"job_id": candidate.job_id, "target": target, "delay": decision.delay_seconds}
        next_run = "SYSTIMESTAMP + NUMTODSINTERVAL(:delay, 'SECOND')" if decision.target == JobStatus.RETRY_WAIT else "NULL"
        self.cur.execute(
            f"""UPDATE SJZQ_COLLECTION_JOB
                    SET STATUS=:target, ACTIVE_ATTEMPT_ID=NULL, LEASE_TOKEN_HASH=NULL,
                        LEASE_EXPIRES_AT=NULL, NEXT_RUN_AT={next_run},
                        LAST_ERROR_CLASS='transient', LAST_ERROR_CODE='LEASE_EXPIRED',
                        UPDATE_TIME=SYSTIMESTAMP
                  WHERE JOB_ID=:job_id AND ACTIVE_ATTEMPT_ID=:attempt_id
                    AND LEASE_EXPIRES_AT <= SYSTIMESTAMP""",
            {**params, "attempt_id": candidate.attempt_id},
        )
        if self.cur.rowcount != 1:
            raise RuntimeError("reclaim lost active-attempt invariant after lease reclaim")
        if device_id is not None:
            self.cur.execute(
                """UPDATE SJZQ_DEVICE SET ACTIVE_JOB_ID=NULL, ACTIVE_ATTEMPT_ID=NULL,
                       CURRENT_TASK_ID=NULL, RUN_STATE='idle'
                     WHERE DEVICE_ID=:device_id AND ACTIVE_JOB_ID=:job_id
                       AND ACTIVE_ATTEMPT_ID=:attempt_id""",
                {"device_id": device_id, "job_id": candidate.job_id, "attempt_id": candidate.attempt_id},
            )
        self._event(job_id=candidate.job_id, task_id=candidate.task_id, attempt_id=candidate.attempt_id,
                    event="LEASE_RECLAIMED", old=candidate.job_status, new=target,
                    error_code="LEASE_EXPIRED", detail=decision.reason)
        return True
    def terminal_task_active_jobs(self, *, limit: int) -> Sequence[JobInconsistency]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID, a.DEVICE_ID, t.STATUS
                   FROM SJZQ_COLLECTION_JOB j JOIN SJZQ_TASK t ON t.TASK_ID=j.TASK_ID
                   LEFT JOIN SJZQ_COLLECTION_ATTEMPT a ON a.ATTEMPT_ID=j.ACTIVE_ATTEMPT_ID
                  WHERE LOWER(t.STATUS) IN ('succeeded','partially_succeeded','partially_succe','failed','cancelled','archived')
                    AND j.STATUS IN ('leased','running')
                  ORDER BY j.JOB_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [JobInconsistency(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None, int(r[3]) if r[3] is not None else None, str(r[4])) for r in self._rows(self.cur)]

    def success_without_result(self, *, limit: int) -> Sequence[JobInconsistency]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID
                   FROM SJZQ_COLLECTION_JOB j
                   WHERE j.STATUS='success'
                     AND (j.RESULT_RECEIPT_KEY IS NULL OR j.RESULT_PRODUCT_ID IS NULL
                          OR NOT EXISTS (SELECT 1 FROM SJZQ_UPLOAD_RECEIPT r
                                          WHERE r.IDEMPOTENCY_KEY=j.RESULT_RECEIPT_KEY
                                            AND r.STATUS='acked'
                                            AND r.PRODUCT_ID=j.RESULT_PRODUCT_ID)
                          OR NOT EXISTS (SELECT 1 FROM SJZQ_PRODUCT p
                                          WHERE p.PRODUCT_ID=j.RESULT_PRODUCT_ID
                                            AND p.TASK_ID=j.TASK_ID))
                  ORDER BY j.JOB_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [JobInconsistency(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None) for r in self._rows(self.cur)]

    def confirmed_result_without_success(self, *, limit: int) -> Sequence[JobInconsistency]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID
                   FROM SJZQ_COLLECTION_JOB j
                   WHERE j.STATUS IN ('retry_wait','pending')
                     AND j.RESULT_RECEIPT_KEY IS NOT NULL AND j.RESULT_PRODUCT_ID IS NOT NULL
                     AND EXISTS (SELECT 1 FROM SJZQ_UPLOAD_RECEIPT r
                                 JOIN SJZQ_PRODUCT p ON p.PRODUCT_ID=j.RESULT_PRODUCT_ID
                                                   AND p.TASK_ID=j.TASK_ID
                                  WHERE r.IDEMPOTENCY_KEY=j.RESULT_RECEIPT_KEY
                                    AND r.STATUS='acked' AND r.PRODUCT_ID=j.RESULT_PRODUCT_ID)
                  ORDER BY j.JOB_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [JobInconsistency(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None) for r in self._rows(self.cur)]

    def mark_confirmed_result_success(self, candidate: JobInconsistency, *, now: datetime) -> bool:
        self.cur.execute("SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE", {"id": candidate.task_id})
        if not self.cur.fetchone():
            return False
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_JOB SET STATUS='success', NEXT_RUN_AT=SYSTIMESTAMP, UPDATE_TIME=SYSTIMESTAMP
                 WHERE JOB_ID=:job_id AND STATUS IN ('pending','retry_wait')
                   AND RESULT_RECEIPT_KEY IS NOT NULL AND RESULT_PRODUCT_ID IS NOT NULL
                   AND EXISTS (SELECT 1 FROM SJZQ_UPLOAD_RECEIPT r
                               JOIN SJZQ_PRODUCT p ON p.PRODUCT_ID=SJZQ_COLLECTION_JOB.RESULT_PRODUCT_ID
                                                 AND p.TASK_ID=SJZQ_COLLECTION_JOB.TASK_ID
                                WHERE r.IDEMPOTENCY_KEY=SJZQ_COLLECTION_JOB.RESULT_RECEIPT_KEY
                                  AND r.STATUS='acked' AND r.PRODUCT_ID=SJZQ_COLLECTION_JOB.RESULT_PRODUCT_ID)""",
            {"job_id": candidate.job_id},
        )
        if self.cur.rowcount != 1:
            return False
        self._event(job_id=candidate.job_id, task_id=candidate.task_id, attempt_id=candidate.attempt_id,
                    event="RESULT_RECEIPT_REPAIRED", old=None, new="success")
        return True

    def duplicate_active_attempts(self, *, limit: int) -> Sequence[DuplicateAttempt]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID,
                        LISTAGG(a.ATTEMPT_ID, ',') WITHIN GROUP (ORDER BY a.ATTEMPT_ID) AS IDS
                   FROM SJZQ_COLLECTION_JOB j JOIN SJZQ_COLLECTION_ATTEMPT a ON a.JOB_ID=j.JOB_ID
                  WHERE a.STATUS IN ('leased','running')
                  GROUP BY j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID
                 HAVING COUNT(*) > 1
                  ORDER BY j.JOB_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [DuplicateAttempt(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None, tuple(int(x) for x in str(r[3]).split(","))) for r in self._rows(self.cur)]

    def reclaim_stray_attempts(self, candidate: DuplicateAttempt, *, now: datetime) -> bool:
        if candidate.active_attempt_id not in candidate.attempt_ids:
            return False
        self.cur.execute("SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE", {"id": candidate.task_id})
        if not self.cur.fetchone(): return False
        self.cur.execute("SELECT ACTIVE_ATTEMPT_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:id FOR UPDATE", {"id": candidate.job_id})
        row = self.cur.fetchone()
        if not row or int(row[0] or -1) != candidate.active_attempt_id: return False
        ids = [v for v in candidate.attempt_ids if v != candidate.active_attempt_id]
        if not ids: return False
        binds = {f"id{i}": value for i, value in enumerate(ids)}
        in_clause = ", ".join(f":id{i}" for i in range(len(ids)))
        self.cur.execute(
            f"""UPDATE SJZQ_COLLECTION_LEASE SET STATUS='reclaimed', RELEASED_AT=SYSTIMESTAMP,
                       RECLAIMED_AT=SYSTIMESTAMP, RELEASE_REASON='STRAY_ACTIVE_ATTEMPT'
                 WHERE JOB_ID=:job_id AND ATTEMPT_ID IN ({in_clause}) AND STATUS='active'""",
            {"job_id": candidate.job_id, **binds},
        )
        if self.cur.rowcount != len(ids): return False
        self.cur.execute(
            f"""UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='reclaimed', FINISHED_AT=SYSTIMESTAMP,
                       ERROR_CLASS='transient', ERROR_CODE='STRAY_ACTIVE_ATTEMPT'
                 WHERE JOB_ID=:job_id AND ATTEMPT_ID IN ({in_clause}) AND STATUS IN ('leased','running')""",
            {"job_id": candidate.job_id, **binds},
        )
        if self.cur.rowcount != len(ids): return False
        self._event(job_id=candidate.job_id, task_id=candidate.task_id, attempt_id=candidate.active_attempt_id,
                    event="STRAY_ATTEMPTS_RECLAIMED", old=None, new=None, error_code="STRAY_ACTIVE_ATTEMPT")
        return True

    def orphan_device_claims(self, *, limit: int) -> Sequence[JobInconsistency]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT d.ACTIVE_JOB_ID, d.CURRENT_TASK_ID, d.ACTIVE_ATTEMPT_ID, d.DEVICE_ID
                   FROM SJZQ_DEVICE d
                  WHERE d.ACTIVE_ATTEMPT_ID IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM SJZQ_COLLECTION_JOB j
                                    WHERE j.JOB_ID=d.ACTIVE_JOB_ID
                                      AND j.ACTIVE_ATTEMPT_ID=d.ACTIVE_ATTEMPT_ID
                                      AND j.STATUS IN ('leased','running'))
                  ORDER BY d.DEVICE_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [JobInconsistency(int(r[0]) if r[0] is not None else -1, int(r[1]) if r[1] is not None else -1, int(r[2]), int(r[3])) for r in self._rows(self.cur)]

    def clear_orphan_device_claim(self, candidate: JobInconsistency, *, now: datetime) -> bool:
        if candidate.device_id is None: return False
        self.cur.execute("SELECT DEVICE_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id FOR UPDATE", {"id": candidate.device_id})
        if not self.cur.fetchone(): return False
        self.cur.execute(
            """UPDATE SJZQ_DEVICE SET ACTIVE_JOB_ID=NULL, ACTIVE_ATTEMPT_ID=NULL,
                       CURRENT_TASK_ID=NULL, RUN_STATE='idle'
                 WHERE DEVICE_ID=:device_id AND ACTIVE_ATTEMPT_ID=:attempt_id
                   AND NOT EXISTS (SELECT 1 FROM SJZQ_COLLECTION_JOB j
                                   WHERE j.JOB_ID=ACTIVE_JOB_ID AND j.ACTIVE_ATTEMPT_ID=ACTIVE_ATTEMPT_ID
                                     AND j.STATUS IN ('leased','running'))""",
            {"device_id": candidate.device_id, "attempt_id": candidate.attempt_id},
        )
        return self.cur.rowcount == 1

    def invalid_job_leases(self, *, limit: int) -> Sequence[JobInconsistency]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID
                   FROM SJZQ_COLLECTION_JOB j
                  WHERE j.STATUS IN ('leased','running')
                    AND (j.ACTIVE_ATTEMPT_ID IS NULL OR j.LEASE_TOKEN_HASH IS NULL
                         OR j.LEASE_EXPIRES_AT IS NULL
                          OR NOT EXISTS (SELECT 1 FROM SJZQ_COLLECTION_ATTEMPT a
                                         WHERE a.ATTEMPT_ID=j.ACTIVE_ATTEMPT_ID
                                           AND a.JOB_ID=j.JOB_ID
                                           AND a.STATUS IN ('leased','running'))
                          OR NOT EXISTS (SELECT 1 FROM SJZQ_COLLECTION_LEASE l
                                         WHERE l.ATTEMPT_ID=j.ACTIVE_ATTEMPT_ID
                                           AND l.JOB_ID=j.JOB_ID
                                           AND l.LEASE_TOKEN_HASH=j.LEASE_TOKEN_HASH
                                           AND l.STATUS='active'))
                  ORDER BY j.JOB_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [JobInconsistency(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None) for r in self._rows(self.cur)]

    def mark_job_dead(self, candidate: JobInconsistency, *, reason: str, now: datetime) -> bool:
        # Only mutable/active states can become dead. Success is intentionally
        # not rewritten by a monitoring scan.
        self.cur.execute("SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE", {"id": candidate.task_id})
        if not self.cur.fetchone(): return False
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_JOB SET STATUS='dead', ACTIVE_ATTEMPT_ID=NULL,
                       LEASE_TOKEN_HASH=NULL, LEASE_EXPIRES_AT=NULL, NEXT_RUN_AT=SYSTIMESTAMP,
                       LAST_ERROR_CLASS='manual_intervention_required', LAST_ERROR_CODE=:reason,
                       UPDATE_TIME=SYSTIMESTAMP
                 WHERE JOB_ID=:job_id AND STATUS IN ('pending','leased','running','retry_wait','paused')""",
            {"job_id": candidate.job_id, "reason": reason},
        )
        if self.cur.rowcount != 1: return False
        if candidate.attempt_id is not None:
            self.cur.execute(
                """UPDATE SJZQ_COLLECTION_LEASE SET STATUS='reclaimed', RELEASED_AT=SYSTIMESTAMP,
                           RECLAIMED_AT=SYSTIMESTAMP, RELEASE_REASON=:reason
                     WHERE ATTEMPT_ID=:attempt_id AND STATUS='active'""",
                {"attempt_id": candidate.attempt_id, "reason": reason},
            )
            self.cur.execute(
                """UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='reclaimed', FINISHED_AT=SYSTIMESTAMP,
                           ERROR_CLASS='manual_intervention_required', ERROR_CODE=:reason
                     WHERE ATTEMPT_ID=:attempt_id AND STATUS IN ('leased','running')""",
                {"attempt_id": candidate.attempt_id, "reason": reason},
            )
        self._event(job_id=candidate.job_id, task_id=candidate.task_id, attempt_id=candidate.attempt_id,
                    event="RECONCILIATION_MANUAL_REQUIRED", old=None, new="dead", error_code=reason)
        return True

    def record_manual_inconsistency(self, candidate: JobInconsistency, *, reason: str, now: datetime) -> bool:
        """Audit a terminal inconsistency without illegally reopening it."""
        self.cur.execute("SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE", {"id": candidate.task_id})
        if not self.cur.fetchone():
            return False
        self.cur.execute(
            "SELECT STATUS FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id FOR UPDATE",
            {"job_id": candidate.job_id},
        )
        row = self.cur.fetchone()
        if not row or str(row[0]).lower() != "success":
            return False
        self._event(job_id=candidate.job_id, task_id=candidate.task_id, attempt_id=candidate.attempt_id,
                    event="RECONCILIATION_MANUAL_REQUIRED", old="success", new="success", error_code=reason)
        return True

    def due_retry_jobs(self, *, limit: int) -> Sequence[JobInconsistency]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT j.JOB_ID, j.TASK_ID, j.ACTIVE_ATTEMPT_ID
                   FROM SJZQ_COLLECTION_JOB j JOIN SJZQ_TASK t ON t.TASK_ID=j.TASK_ID
                  WHERE j.STATUS='retry_wait' AND j.NEXT_RUN_AT <= SYSTIMESTAMP
                    AND NVL(t.PAUSE_STATE, 'active') <> 'paused'
                  ORDER BY j.NEXT_RUN_AT, j.JOB_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [JobInconsistency(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None) for r in self._rows(self.cur)]

    def promote_due_retry(self, candidate: JobInconsistency, *, now: datetime) -> bool:
        self.cur.execute("SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE", {"id": candidate.task_id})
        if not self.cur.fetchone(): return False
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_JOB SET STATUS='pending', NEXT_RUN_AT=SYSTIMESTAMP, UPDATE_TIME=SYSTIMESTAMP
                 WHERE JOB_ID=:job_id AND STATUS='retry_wait' AND NEXT_RUN_AT <= SYSTIMESTAMP""",
            {"job_id": candidate.job_id},
        )
        event, new = "RETRY_WAIT_ELAPSED", "pending"
        if self.cur.rowcount != 1: return False
        self._event(job_id=candidate.job_id, task_id=candidate.task_id, attempt_id=candidate.attempt_id,
                    event=event, old=None, new=new)
        return True

    def stale_outbox(self, *, limit: int) -> Sequence[StaleOutbox]:
        self.cur.execute(
            """SELECT * FROM (
                 SELECT o.OUTBOX_ID, o.JOB_ID, o.ATTEMPT_ID,
                        CASE WHEN EXISTS (SELECT 1 FROM SJZQ_COLLECTION_JOB j
                                          WHERE j.JOB_ID=o.JOB_ID AND j.ACTIVE_ATTEMPT_ID=o.ATTEMPT_ID
                                            AND j.STATUS IN ('leased','running')
                                            AND j.LEASE_EXPIRES_AT > SYSTIMESTAMP) THEN 1 ELSE 0 END
                   FROM SJZQ_COLLECTION_OUTBOX o
                  WHERE o.STATUS='leased' AND o.LOCK_EXPIRES_AT <= SYSTIMESTAMP
                  ORDER BY o.LOCK_EXPIRES_AT, o.OUTBOX_ID
               ) WHERE ROWNUM <= :limit""",
            {"limit": limit},
        )
        return [StaleOutbox(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None, bool(r[3])) for r in self._rows(self.cur)]

    def recover_stale_outbox(self, candidate: StaleOutbox, *, now: datetime) -> bool:
        target = "pending" if candidate.lease_valid else "dead"
        self.cur.execute(
            """UPDATE SJZQ_COLLECTION_OUTBOX SET STATUS=:target, UPDATE_TIME=SYSTIMESTAMP,
                       AVAILABLE_AT=CASE WHEN :target='pending' THEN SYSTIMESTAMP ELSE AVAILABLE_AT END,
                       LOCK_TOKEN=NULL, LOCKED_AT=NULL, LOCK_EXPIRES_AT=NULL,
                       LAST_ERROR_CODE=:reason
                 WHERE OUTBOX_ID=:id AND STATUS='leased' AND LOCK_EXPIRES_AT <= SYSTIMESTAMP""",
            {"target": target, "reason": "RECONCILIATION_OUTBOX_TIMEOUT", "id": candidate.outbox_id},
        )
        return self.cur.rowcount == 1


def reconcile_oracle(cur, *, limit: int = 100) -> ReconciliationReport:
    """Convenience entrypoint for cron/API code inside an Oracle transaction."""
    return reconcile(OracleReconciliationStore(cur), limit=limit)

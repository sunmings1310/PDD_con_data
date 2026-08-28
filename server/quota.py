"""Transactional enterprise quota reservations and immutable usage ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import oracledb

from server.db import next_id

ACTIVE_TASK = "active_task"
DAILY_SNAPSHOT = "daily_snapshot"
STORAGE_BYTES = "storage_bytes"

_LIMIT_COLUMNS = {
    ACTIVE_TASK: "MAX_ACTIVE_TASKS",
    DAILY_SNAPSHOT: "MAX_DAILY_SNAPSHOTS",
    STORAGE_BYTES: "STORAGE_BYTES",
}


class QuotaExceeded(RuntimeError):
    def __init__(self, metric: str, limit: int, current: int, requested: int):
        self.metric, self.limit, self.current, self.requested = metric, limit, current, requested
        super().__init__(f"{metric.upper()}_QUOTA_EXCEEDED")


@dataclass(frozen=True)
class Reservation:
    reservation_id: int
    status: str
    amount: int
    idempotent: bool = False


def period_key(metric: str, today: date | None = None) -> str:
    return (today or date.today()).isoformat() if metric == DAILY_SNAPSHOT else "lifetime"


def _usage_row(cur: Any, enterprise_id: int, metric: str, period: str) -> tuple[int, int]:
    cur.execute(
        """SELECT USED_VALUE,RESERVED_VALUE FROM SJZQ_QUOTA_USAGE
             WHERE ENTERPRISE_ID=:enterprise_id AND METRIC_CODE=:metric AND PERIOD_KEY=:period
             FOR UPDATE""",
        {"enterprise_id": enterprise_id, "metric": metric, "period": period},
    )
    row = cur.fetchone()
    if row:
        return int(row[0] or 0), int(row[1] or 0)
    try:
        cur.execute(
            """INSERT INTO SJZQ_QUOTA_USAGE
                 (ENTERPRISE_ID,METRIC_CODE,PERIOD_KEY,USED_VALUE,RESERVED_VALUE)
                 VALUES (:enterprise_id,:metric,:period,0,0)""",
            {"enterprise_id": enterprise_id, "metric": metric, "period": period},
        )
    except oracledb.IntegrityError:
        # A concurrent creator won the unique key. Lock and use its row.
        cur.execute(
            """SELECT USED_VALUE,RESERVED_VALUE FROM SJZQ_QUOTA_USAGE
                 WHERE ENTERPRISE_ID=:enterprise_id AND METRIC_CODE=:metric AND PERIOD_KEY=:period
                 FOR UPDATE""",
            {"enterprise_id": enterprise_id, "metric": metric, "period": period},
        )
        row = cur.fetchone()
        if row:
            return int(row[0] or 0), int(row[1] or 0)
        raise
    return 0, 0


def _limit(cur: Any, enterprise_id: int, metric: str) -> int:
    column = _LIMIT_COLUMNS[metric]
    cur.execute(f"SELECT {column} FROM SJZQ_ENTERPRISE_QUOTA WHERE ENTERPRISE_ID=:enterprise_id FOR UPDATE",
                {"enterprise_id": enterprise_id})
    row = cur.fetchone()
    if not row:
        raise RuntimeError("ENTERPRISE_QUOTA_NOT_CONFIGURED")
    return int(row[0])


def lock_metric_scope(cur: Any, *, enterprise_id: int, metric: str) -> None:
    """Lock quota scope in the same usage -> enterprise order as reservations."""
    _usage_row(cur, enterprise_id, metric, period_key(metric))
    _limit(cur, enterprise_id, metric)


def _ledger(cur: Any, *, enterprise_id: int, workspace_id: int, metric: str, period: str,
            event_type: str, event_key: str, delta_used: int, delta_reserved: int,
            resource_type: str, resource_key: str) -> None:
    cur.execute(
        """INSERT INTO SJZQ_QUOTA_LEDGER
             (LEDGER_ID,ENTERPRISE_ID,WORKSPACE_ID,METRIC_CODE,PERIOD_KEY,EVENT_TYPE,
              EVENT_KEY,DELTA_USED,DELTA_RESERVED,RESOURCE_TYPE,RESOURCE_KEY)
             VALUES (:id,:enterprise_id,:workspace_id,:metric,:period,:event_type,
                     :event_key,:delta_used,:delta_reserved,:resource_type,:resource_key)""",
        {"id": next_id(cur, "SJZQ_SEQ_QUOTA_LEDGER"), "enterprise_id": enterprise_id,
         "workspace_id": workspace_id, "metric": metric, "period": period,
         "event_type": event_type, "event_key": event_key[:192], "delta_used": delta_used,
         "delta_reserved": delta_reserved, "resource_type": resource_type,
         "resource_key": resource_key[:128]},
    )


def reserve(cur: Any, *, enterprise_id: int, workspace_id: int, metric: str, amount: int,
            resource_type: str, resource_key: str, ttl_minutes: int = 15) -> Reservation:
    if metric not in _LIMIT_COLUMNS or amount <= 0:
        raise ValueError("invalid quota reservation")
    period = period_key(metric)
    # All quota paths use usage -> enterprise quota locking.  In particular a
    # canonical Task replay must not hold the enterprise row while a normal
    # reservation holds usage and waits for it.
    used, held = _usage_row(cur, enterprise_id, metric, period)
    maximum = _limit(cur, enterprise_id, metric)
    cur.execute(
        """SELECT RESERVATION_ID,STATUS,AMOUNT FROM SJZQ_QUOTA_RESERVATION
             WHERE ENTERPRISE_ID=:enterprise_id AND METRIC_CODE=:metric AND PERIOD_KEY=:period
               AND RESOURCE_TYPE=:resource_type AND RESOURCE_KEY=:resource_key FOR UPDATE""",
        {"enterprise_id": enterprise_id, "metric": metric, "period": period,
         "resource_type": resource_type, "resource_key": resource_key},
    )
    existing = cur.fetchone()
    if existing:
        return Reservation(int(existing[0]), str(existing[1]).lower(), int(existing[2]), True)
    if used + held + amount > maximum:
        raise QuotaExceeded(metric, maximum, used + held, amount)
    reservation_id = next_id(cur, "SJZQ_SEQ_QUOTA_RESERVATION")
    cur.execute(
        """INSERT INTO SJZQ_QUOTA_RESERVATION
             (RESERVATION_ID,ENTERPRISE_ID,WORKSPACE_ID,METRIC_CODE,PERIOD_KEY,AMOUNT,
              RESOURCE_TYPE,RESOURCE_KEY,STATUS,EXPIRES_AT)
             VALUES (:id,:enterprise_id,:workspace_id,:metric,:period,:amount,
                     :resource_type,:resource_key,'held',SYSTIMESTAMP+NUMTODSINTERVAL(:ttl,'MINUTE'))""",
        {"id": reservation_id, "enterprise_id": enterprise_id, "workspace_id": workspace_id,
         "metric": metric, "period": period, "amount": amount, "resource_type": resource_type,
         "resource_key": resource_key, "ttl": ttl_minutes},
    )
    cur.execute(
        """UPDATE SJZQ_QUOTA_USAGE SET RESERVED_VALUE=RESERVED_VALUE+:amount,
                  VERSION_NO=VERSION_NO+1,UPDATE_TIME=SYSTIMESTAMP
             WHERE ENTERPRISE_ID=:enterprise_id AND METRIC_CODE=:metric AND PERIOD_KEY=:period""",
        {"amount": amount, "enterprise_id": enterprise_id, "metric": metric, "period": period},
    )
    _ledger(cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=metric, period=period,
            event_type="reserve", event_key=f"reserve:{reservation_id}", delta_used=0,
            delta_reserved=amount, resource_type=resource_type, resource_key=resource_key)
    return Reservation(reservation_id, "held", amount)


def commit(cur: Any, reservation_id: int) -> Reservation:
    cur.execute(
        """SELECT ENTERPRISE_ID,WORKSPACE_ID,METRIC_CODE,PERIOD_KEY,AMOUNT,RESOURCE_TYPE,
                  RESOURCE_KEY,STATUS FROM SJZQ_QUOTA_RESERVATION
             WHERE RESERVATION_ID=:id FOR UPDATE""", {"id": reservation_id})
    row = cur.fetchone()
    if not row:
        raise RuntimeError("QUOTA_RESERVATION_NOT_FOUND")
    enterprise_id, workspace_id, metric, period, amount = int(row[0]), int(row[1]), str(row[2]), str(row[3]), int(row[4])
    resource_type, resource_key, status = str(row[5]), str(row[6]), str(row[7]).lower()
    if status == "committed":
        return Reservation(reservation_id, status, amount, True)
    if status != "held":
        raise RuntimeError("QUOTA_RESERVATION_NOT_HELD")
    _usage_row(cur, enterprise_id, metric, period)
    cur.execute(
        """UPDATE SJZQ_QUOTA_USAGE SET RESERVED_VALUE=RESERVED_VALUE-:amount,
                  USED_VALUE=USED_VALUE+:amount,VERSION_NO=VERSION_NO+1,UPDATE_TIME=SYSTIMESTAMP
             WHERE ENTERPRISE_ID=:enterprise_id AND METRIC_CODE=:metric AND PERIOD_KEY=:period""",
        {"amount": amount, "enterprise_id": enterprise_id, "metric": metric, "period": period})
    cur.execute("UPDATE SJZQ_QUOTA_RESERVATION SET STATUS='committed',COMMITTED_AT=SYSTIMESTAMP WHERE RESERVATION_ID=:id",
                {"id": reservation_id})
    _ledger(cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=metric, period=period,
            event_type="commit", event_key=f"commit:{reservation_id}", delta_used=amount,
            delta_reserved=-amount, resource_type=resource_type, resource_key=resource_key)
    return Reservation(reservation_id, "committed", amount)


def release(cur: Any, *, enterprise_id: int, metric: str, resource_type: str, resource_key: str) -> bool:
    period = period_key(metric)
    cur.execute(
        """SELECT RESERVATION_ID,WORKSPACE_ID,AMOUNT,STATUS FROM SJZQ_QUOTA_RESERVATION
             WHERE ENTERPRISE_ID=:enterprise_id AND METRIC_CODE=:metric AND PERIOD_KEY=:period
               AND RESOURCE_TYPE=:resource_type AND RESOURCE_KEY=:resource_key FOR UPDATE""",
        {"enterprise_id": enterprise_id, "metric": metric, "period": period,
         "resource_type": resource_type, "resource_key": resource_key})
    row = cur.fetchone()
    if not row or str(row[3]).lower() == "released":
        return False
    reservation_id, workspace_id, amount, status = int(row[0]), int(row[1]), int(row[2]), str(row[3]).lower()
    _usage_row(cur, enterprise_id, metric, period)
    field = "USED_VALUE" if status == "committed" else "RESERVED_VALUE"
    cur.execute(
        f"""UPDATE SJZQ_QUOTA_USAGE SET {field}=GREATEST(0,{field}-:amount),
                  VERSION_NO=VERSION_NO+1,UPDATE_TIME=SYSTIMESTAMP
             WHERE ENTERPRISE_ID=:enterprise_id AND METRIC_CODE=:metric AND PERIOD_KEY=:period""",
        {"amount": amount, "enterprise_id": enterprise_id, "metric": metric, "period": period})
    cur.execute("UPDATE SJZQ_QUOTA_RESERVATION SET STATUS='released',RELEASED_AT=SYSTIMESTAMP WHERE RESERVATION_ID=:id",
                {"id": reservation_id})
    _ledger(cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=metric, period=period,
            event_type="release", event_key=f"release:{reservation_id}",
            delta_used=-amount if status == "committed" else 0,
            delta_reserved=-amount if status == "held" else 0,
            resource_type=resource_type, resource_key=resource_key)
    return True


def reserve_and_commit(cur: Any, **kwargs: Any) -> Reservation:
    reservation = reserve(cur, **kwargs)
    return reservation if reservation.status == "committed" else commit(cur, reservation.reservation_id)


def adjust_used(cur: Any, *, enterprise_id: int, workspace_id: int, metric: str,
                amount_delta: int, event_key: str, resource_type: str, resource_key: str) -> None:
    """Record an idempotent correction such as physical file deletion."""
    if metric not in _LIMIT_COLUMNS or amount_delta == 0:
        return
    period = period_key(metric)
    cur.execute("SELECT COUNT(*) FROM SJZQ_QUOTA_LEDGER WHERE EVENT_KEY=:event_key", {"event_key": event_key})
    if int(cur.fetchone()[0] or 0):
        return
    used, _ = _usage_row(cur, enterprise_id, metric, period)
    applied = max(-used, amount_delta)
    cur.execute(
        """UPDATE SJZQ_QUOTA_USAGE SET USED_VALUE=USED_VALUE+:delta,VERSION_NO=VERSION_NO+1,
                  UPDATE_TIME=SYSTIMESTAMP WHERE ENTERPRISE_ID=:enterprise_id
                  AND METRIC_CODE=:metric AND PERIOD_KEY=:period""",
        {"delta": applied, "enterprise_id": enterprise_id, "metric": metric, "period": period})
    _ledger(cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=metric, period=period,
            event_type="adjust", event_key=event_key, delta_used=applied, delta_reserved=0,
            resource_type=resource_type, resource_key=resource_key)

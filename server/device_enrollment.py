"""One-time device enrollment credentials and revocation fences."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

from server.db import next_id


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_bearer() -> str:
    return "enr_" + secrets.token_urlsafe(32)


@dataclass(frozen=True)
class EnrollmentScope:
    token_id: int
    enterprise_id: int
    workspace_id: int


def issue(cur: Any, *, enterprise_id: int, workspace_id: int, issued_by: int,
          expires_minutes: int = 60) -> tuple[int, str]:
    bearer = new_bearer()
    token_id = next_id(cur, "SJZQ_SEQ_DEVICE_ENROLL")
    cur.execute(
        """INSERT INTO SJZQ_DEVICE_ENROLL_TOKEN
             (TOKEN_ID,ENTERPRISE_ID,WORKSPACE_ID,TOKEN_HASH,STATUS,EXPIRES_AT,ISSUED_BY)
             VALUES (:id,:enterprise_id,:workspace_id,:token_hash,'active',
                     SYSTIMESTAMP+NUMTODSINTERVAL(:minutes,'MINUTE'),:issued_by)""",
        {"id": token_id, "enterprise_id": enterprise_id, "workspace_id": workspace_id,
         "token_hash": token_hash(bearer), "minutes": expires_minutes, "issued_by": issued_by},
    )
    return token_id, bearer


def rotate(cur: Any, *, token_id: int, enterprise_id: int, workspace_id: int,
           issued_by: int, expires_minutes: int = 60) -> tuple[int, str]:
    cur.execute(
        """SELECT STATUS FROM SJZQ_DEVICE_ENROLL_TOKEN
             WHERE TOKEN_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
             FOR UPDATE""",
        {"id": token_id, "enterprise_id": enterprise_id, "workspace_id": workspace_id})
    row = cur.fetchone()
    if not row:
        raise LookupError("ENROLLMENT_TOKEN_NOT_FOUND")
    if str(row[0]).lower() != "active":
        raise ValueError("ENROLLMENT_TOKEN_NOT_ACTIVE")
    new_id, bearer = issue(cur, enterprise_id=enterprise_id, workspace_id=workspace_id,
                           issued_by=issued_by, expires_minutes=expires_minutes)
    cur.execute(
        """UPDATE SJZQ_DEVICE_ENROLL_TOKEN SET STATUS='revoked',REVOKED_AT=SYSTIMESTAMP,
                  REPLACED_BY_TOKEN_ID=:new_id WHERE TOKEN_ID=:id AND STATUS='active'""",
        {"new_id": new_id, "id": token_id})
    return new_id, bearer


def revoke(cur: Any, *, token_id: int, enterprise_id: int, workspace_id: int) -> bool:
    cur.execute(
        """UPDATE SJZQ_DEVICE_ENROLL_TOKEN SET STATUS='revoked',REVOKED_AT=SYSTIMESTAMP
             WHERE TOKEN_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
               AND STATUS='active'""",
        {"id": token_id, "enterprise_id": enterprise_id, "workspace_id": workspace_id})
    return cur.rowcount == 1


def consume(cur: Any, *, bearer: str, device_id: int) -> EnrollmentScope:
    if not bearer:
        raise ValueError("ENROLLMENT_TOKEN_REQUIRED")
    digest = token_hash(bearer)
    cur.execute(
        """SELECT TOKEN_ID,ENTERPRISE_ID,WORKSPACE_ID,STATUS,
                  CASE WHEN EXPIRES_AT>SYSTIMESTAMP THEN 1 ELSE 0 END
             FROM SJZQ_DEVICE_ENROLL_TOKEN WHERE TOKEN_HASH=:token_hash FOR UPDATE""",
        {"token_hash": digest})
    row = cur.fetchone()
    if not row:
        raise ValueError("ENROLLMENT_TOKEN_INVALID")
    token_id, enterprise_id, workspace_id = int(row[0]), int(row[1]), int(row[2])
    if str(row[3]).lower() != "active":
        raise ValueError("ENROLLMENT_TOKEN_ALREADY_USED_OR_REVOKED")
    if int(row[4] or 0) != 1:
        cur.execute("UPDATE SJZQ_DEVICE_ENROLL_TOKEN SET STATUS='expired' WHERE TOKEN_ID=:id", {"id": token_id})
        raise ValueError("ENROLLMENT_TOKEN_EXPIRED")
    cur.execute(
        """UPDATE SJZQ_DEVICE_ENROLL_TOKEN SET STATUS='used',USED_BY_DEVICE_ID=:device_id,
                  USED_AT=SYSTIMESTAMP WHERE TOKEN_ID=:id AND STATUS='active'""",
        {"device_id": device_id, "id": token_id})
    if cur.rowcount != 1:
        raise ValueError("ENROLLMENT_TOKEN_ALREADY_USED_OR_REVOKED")
    return EnrollmentScope(token_id, enterprise_id, workspace_id)

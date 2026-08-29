"""Authoritative Phase 2 CollectionJob / Attempt / Lease operations.

All mutable worker calls validate the current Lease in the database.  Lease tokens
are returned only at acquire time; Oracle stores SHA-256 digests and audit events.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import secrets
import uuid
from typing import Any

from server.db import next_id, rows_as_dicts
from server.job_state import AttemptStatus, ErrorClass, JobStateConflict, JobStatus, decide_retry, validate_attempt_transition, validate_job_transition

DEFAULT_LEASE_SECONDS = 120
MAX_LEASE_SECONDS = 900


@dataclass(frozen=True)
class JobProtocolError(RuntimeError):
    code: str
    message: str
    current_status: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def error_data(exc: JobProtocolError | JobStateConflict) -> dict[str, str]:
    if isinstance(exc, JobStateConflict):
        return {"error_code": exc.code, "current_status": exc.current, "requested_status": exc.requested}
    data = {"error_code": exc.code}
    if exc.current_status is not None:
        data["current_status"] = exc.current_status
    return data


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event(cur: Any, task_id: int, job_id: int | None, event: str, *, attempt_id: int | None = None,
           device_id: int | None = None, worker_id: str | None = None, token_hash: str | None = None,
           trace_id: str | None = None, old: str | None = None, new: str | None = None,
           error_class: str | None = None, error_code: str | None = None, detail: dict[str, Any] | None = None) -> None:
    """Append an event with a server-generated stable unique event key."""
    event_id = next_id(cur, "SJZQ_SEQ_JOB_EVENT")
    event_key = _hash(f"{task_id}:{job_id}:{attempt_id}:{event}:{event_id}")
    cur.execute(
        """INSERT INTO SJZQ_JOB_EVENT (
             EVENT_ID,EVENT_KEY,TASK_ID,JOB_ID,ATTEMPT_ID,DEVICE_ID,WORKER_ID,LEASE_TOKEN_HASH,TRACE_ID,
             EVENT_TYPE,OLD_STATUS,NEW_STATUS,ERROR_CLASS,ERROR_CODE,DETAIL_JSON,ENTERPRISE_ID,WORKSPACE_ID
           ) VALUES (:id,:event_key,:task_id,:job_id,:attempt_id,:device_id,:worker_id,:token_hash,:trace_id,
             :event,:old,:new,:error_class,:error_code,:detail,
             (SELECT ENTERPRISE_ID FROM SJZQ_TASK WHERE TASK_ID=:task_id),
             (SELECT WORKSPACE_ID FROM SJZQ_TASK WHERE TASK_ID=:task_id))""",
        {"id": event_id, "event_key": event_key, "task_id": task_id, "job_id": job_id,
         "attempt_id": attempt_id, "device_id": device_id, "worker_id": worker_id,
         "token_hash": token_hash, "trace_id": trace_id, "event": event, "old": old, "new": new,
         "error_class": error_class, "error_code": error_code, "detail": _json(detail or {})},
    )
def _lock_device(cur: Any, device_id: int) -> tuple[int, int | None, int | None, int, int]:
    cur.execute("SELECT DEVICE_ID,ACTIVE_JOB_ID,ACTIVE_ATTEMPT_ID,ENTERPRISE_ID,WORKSPACE_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id FOR UPDATE", {"id": device_id})
    row = cur.fetchone()
    if not row:
        raise JobProtocolError("DEVICE_NOT_FOUND", "device does not exist")
    return (int(row[0]), int(row[1]) if row[1] is not None else None,
            int(row[2]) if row[2] is not None else None,
            int(row[3]) if len(row) > 3 and row[3] is not None else 1,
            int(row[4]) if len(row) > 4 and row[4] is not None else 1)


def _device_lock_parts(value: tuple) -> tuple[int, int | None, int | None, int, int]:
    """Keep Phase 1-4 test/store adapters compatible while adding tenant fields."""
    return tuple(value)[:3] + tuple(value[3:5] if len(value) >= 5 else (1, 1))


def _task_for_job(cur: Any, job_id: int) -> int:
    cur.execute("SELECT TASK_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:id", {"id": job_id})
    row = cur.fetchone()
    if not row:
        raise JobProtocolError("JOB_NOT_FOUND", "job does not exist")
    return int(row[0])


def _lock_task(cur: Any, task_id: int) -> tuple[str, str]:
    cur.execute("SELECT REVIEW_STATUS,PAUSE_STATE FROM SJZQ_TASK WHERE TASK_ID=:id FOR UPDATE", {"id": task_id})
    row = cur.fetchone()
    if not row:
        raise JobProtocolError("TASK_NOT_FOUND", "task does not exist")
    return str(row[0] or "").lower(), str(row[1] or "").lower()


def _lock_job(cur: Any, job_id: int) -> dict[str, Any]:
    cur.execute(
        """SELECT JOB_ID,TASK_ID,TASK_ITEM_ID,JOB_KEY,JOB_TYPE,TARGET_JSON,STATUS,MAX_ATTEMPTS,ATTEMPT_COUNT,
                  ACTIVE_ATTEMPT_ID,LEASE_TOKEN_HASH,CHECKPOINT_VERSION,CHECKPOINT_JSON,RESULT_RECEIPT_KEY,PAUSE_REQUESTED
             FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:id FOR UPDATE""", {"id": job_id})
    r = cur.fetchone()
    if not r:
        raise JobProtocolError("JOB_NOT_FOUND", "job does not exist")
    return {"id": int(r[0]), "task_id": int(r[1]), "item_id": int(r[2]) if r[2] is not None else None,
            "key": str(r[3]), "type": str(r[4]), "payload": r[5], "status": str(r[6]).lower(),
            "max_attempts": int(r[7] or 5), "attempt_count": int(r[8] or 0),
            "active_attempt_id": int(r[9]) if r[9] is not None else None, "token_hash": str(r[10] or ""),
            "checkpoint_version": int(r[11] or 0), "checkpoint": r[12], "receipt": r[13], "pause_requested": bool(int(r[14] or 0))}


def _lock_attempt(cur: Any, attempt_id: int) -> dict[str, Any]:
    cur.execute(
        """SELECT ATTEMPT_ID,JOB_ID,ATTEMPT_NO,DEVICE_ID,WORKER_ID,LEASE_TOKEN_HASH,TRACE_ID,STATUS
             FROM SJZQ_COLLECTION_ATTEMPT WHERE ATTEMPT_ID=:id FOR UPDATE""", {"id": attempt_id})
    r = cur.fetchone()
    if not r:
        raise JobProtocolError("ATTEMPT_NOT_FOUND", "attempt does not exist")
    return {"id": int(r[0]), "job_id": int(r[1]), "no": int(r[2]), "device_id": int(r[3]), "worker_id": str(r[4]),
            "token_hash": str(r[5]), "trace_id": str(r[6]), "status": str(r[7]).lower()}


def _lock_lease(cur: Any, attempt_id: int) -> dict[str, Any]:
    cur.execute("SELECT LEASE_ID,JOB_ID,ATTEMPT_ID,DEVICE_ID,WORKER_ID,LEASE_TOKEN_HASH,STATUS FROM SJZQ_COLLECTION_LEASE WHERE ATTEMPT_ID=:id FOR UPDATE", {"id": attempt_id})
    r = cur.fetchone()
    if not r:
        raise JobProtocolError("LEASE_NOT_FOUND", "lease does not exist")
    return {"id": int(r[0]), "job_id": int(r[1]), "attempt_id": int(r[2]), "device_id": int(r[3]),
            "worker_id": str(r[4]), "token_hash": str(r[5]), "status": str(r[6]).lower()}


def _context(cur: Any, *, device_id: int, job_id: int, attempt_id: int, worker_id: str, lease_token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Lock Device -> Task -> Job -> Attempt -> Lease and prove current, unexpired ownership."""
    if len(lease_token or "") < 32:
        raise JobProtocolError("INVALID_LEASE_TOKEN", "lease_token is malformed")
    token_hash = _hash(lease_token)
    did, _active_job, active_attempt, _enterprise_id, _workspace_id = _device_lock_parts(_lock_device(cur, device_id))
    task_id = _task_for_job(cur, job_id)
    _lock_task(cur, task_id)
    job = _lock_job(cur, job_id)
    if job["task_id"] != task_id:
        raise JobProtocolError("JOB_STATE_RACE", "job task changed")
    attempt = _lock_attempt(cur, attempt_id)
    lease = _lock_lease(cur, attempt_id)
    if (attempt["job_id"], lease["job_id"], attempt["device_id"], lease["device_id"], attempt["worker_id"], lease["worker_id"]) != (job_id, job_id, did, did, worker_id, worker_id):
        raise JobProtocolError("LEASE_BINDING_MISMATCH", "lease identity does not match caller")
    if not all(secrets.compare_digest(v, token_hash) for v in (job["token_hash"], attempt["token_hash"], lease["token_hash"])):
        raise JobProtocolError("STALE_LEASE", "lease token is no longer current", job["status"])
    if active_attempt != attempt_id or job["active_attempt_id"] != attempt_id or lease["status"] != "active":
        raise JobProtocolError("STALE_LEASE", "attempt is no longer active", job["status"])
    cur.execute("SELECT CASE WHEN LEASE_EXPIRES_AT>SYSTIMESTAMP THEN 1 ELSE 0 END FROM SJZQ_COLLECTION_LEASE WHERE LEASE_ID=:id", {"id": lease["id"]})
    row = cur.fetchone()
    if not row or int(row[0]) != 1:
        raise JobProtocolError("LEASE_EXPIRED", "lease has expired", job["status"])
    return job, attempt


def require_active_lease(
    cur: Any,
    *,
    device_id: int,
    job_id: int,
    attempt_id: int,
    worker_id: str,
    lease_token: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Public side-effect fence for product/image/progress integrations."""
    return _context(
        cur,
        device_id=device_id,
        job_id=job_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )


def _payload(value: Any) -> dict[str, Any]:
    try:
        raw = value.read() if hasattr(value, "read") else value
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def acquire(cur: Any, *, device_id: int, worker_id: str, platform_code: str | None = None, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict[str, Any] | None:
    """Atomic acquire: Device lock, eligible Task `SKIP LOCKED`, Job `SKIP LOCKED`, Attempt+Lease insertion."""
    if not worker_id or len(worker_id) > 128:
        raise JobProtocolError("INVALID_WORKER_ID", "worker_id is required")
    seconds = max(15, min(MAX_LEASE_SECONDS, int(lease_seconds)))
    did, _job, active_attempt, enterprise_id, workspace_id = _device_lock_parts(_lock_device(cur, device_id))
    if active_attempt is not None:
        return None
    params: dict[str, Any] = {"device_id": did, "enterprise_id": enterprise_id, "workspace_id": workspace_id}
    platform = ""
    if platform_code:
        platform = " AND t2.PLATFORM_CODE=:platform"
        params["platform"] = platform_code
    cur.execute(f"""SELECT TASK_ID FROM SJZQ_TASK t WHERE t.ROWID=(
          SELECT rid FROM (SELECT t2.ROWID rid FROM SJZQ_TASK t2
            WHERE t2.REVIEW_STATUS='approved' AND NVL(t2.PAUSE_STATE,'active') <> 'paused'
              AND (t2.DEVICE_ID=:device_id OR t2.DEVICE_ID IS NULL)
              AND t2.ENTERPRISE_ID=:enterprise_id AND t2.WORKSPACE_ID=:workspace_id
              AND t2.STATUS NOT IN ('succeeded','partially_succeeded','failed','cancelled','timed_out') {platform}
              AND EXISTS (SELECT 1 FROM SJZQ_COLLECTION_JOB j WHERE j.TASK_ID=t2.TASK_ID
                           AND j.STATUS='pending')
            ORDER BY t2.PRIORITY,t2.CREATE_TIME,t2.TASK_ID) WHERE ROWNUM=1) FOR UPDATE SKIP LOCKED""", params)
    candidate = cur.fetchone()
    if not candidate:
        return None
    task_id = int(candidate[0])
    review, pause = _lock_task(cur, task_id)
    if review != "approved" or pause == "paused":
        return None
    cur.execute("""SELECT JOB_ID FROM SJZQ_COLLECTION_JOB j WHERE j.ROWID=(
        SELECT rid FROM (SELECT j2.ROWID rid FROM SJZQ_COLLECTION_JOB j2 WHERE j2.TASK_ID=:task_id
          AND j2.STATUS='pending'
          ORDER BY j2.PRIORITY,j2.JOB_ID) WHERE ROWNUM=1) FOR UPDATE SKIP LOCKED""", {"task_id": task_id})
    candidate = cur.fetchone()
    if not candidate:
        return None
    job = _lock_job(cur, int(candidate[0]))
    if job["status"] != "pending":
        return None
    if job["attempt_count"] >= job["max_attempts"]:
        raise JobProtocolError("MAX_ATTEMPTS_EXHAUSTED", "job retry budget exhausted", job["status"])
    # The Task remains a user-level aggregate, but entering execution is an
    # atomic part of the first Job lease; device/task mirrors are not the lease truth.
    cur.execute("""UPDATE SJZQ_TASK
                      SET STATUS=CASE WHEN STATUS='pending' THEN 'running' ELSE STATUS END,
                          DEVICE_ID=NVL(DEVICE_ID,:device_id),
                          START_TIME=NVL(START_TIME,SYSTIMESTAMP), UPDATE_TIME=SYSTIMESTAMP
                    WHERE TASK_ID=:task_id AND STATUS IN ('pending','running')
                      AND (DEVICE_ID IS NULL OR DEVICE_ID=:device_id)""",
                {"task_id": task_id, "device_id": did})
    if cur.rowcount != 1:
        raise JobProtocolError("TASK_DEVICE_MISMATCH", "Task is assigned to another device")
    cur.execute("""UPDATE SJZQ_DEVICE SET CURRENT_TASK_ID=:task_id,STATUS='busy',UPDATE_TIME=SYSTIMESTAMP
                   WHERE DEVICE_ID=:device_id AND ACTIVE_ATTEMPT_ID IS NULL
                     AND (CURRENT_TASK_ID IS NULL OR CURRENT_TASK_ID=:task_id)""", {"task_id":task_id,"device_id":did})
    if cur.rowcount != 1:
        raise JobProtocolError("DEVICE_TASK_OCCUPIED", "device is occupied by another task")
    attempt_id, lease_id = next_id(cur, "SJZQ_SEQ_COLLECTION_ATTEMPT"), next_id(cur, "SJZQ_SEQ_COLLECTION_LEASE")
    attempt_no, token, trace_id = job["attempt_count"] + 1, secrets.token_urlsafe(32), uuid.uuid4().hex
    token_hash = _hash(token)
    cur.execute("""INSERT INTO SJZQ_COLLECTION_ATTEMPT
      (ATTEMPT_ID,JOB_ID,ATTEMPT_NO,DEVICE_ID,WORKER_ID,LEASE_TOKEN_HASH,TRACE_ID,STATUS,LEASED_AT,LEASE_EXPIRES_AT,START_CHECKPOINT_VERSION,ENTERPRISE_ID,WORKSPACE_ID)
      VALUES (:attempt_id,:job_id,:attempt_no,:device_id,:worker_id,:token_hash,:trace_id,'leased',SYSTIMESTAMP,SYSTIMESTAMP+NUMTODSINTERVAL(:seconds,'SECOND'),:checkpoint_version,
      (SELECT ENTERPRISE_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id),(SELECT WORKSPACE_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id))""",
      {"attempt_id":attempt_id,"job_id":job["id"],"attempt_no":attempt_no,"device_id":did,"worker_id":worker_id,"token_hash":token_hash,"trace_id":trace_id,"seconds":seconds,"checkpoint_version":job["checkpoint_version"]})
    cur.execute("""INSERT INTO SJZQ_COLLECTION_LEASE
      (LEASE_ID,JOB_ID,ATTEMPT_ID,WORKER_ID,DEVICE_ID,LEASE_TOKEN_HASH,STATUS,LEASED_AT,LEASE_EXPIRES_AT,HEARTBEAT_AT,ENTERPRISE_ID,WORKSPACE_ID)
      VALUES (:lease_id,:job_id,:attempt_id,:worker_id,:device_id,:token_hash,'active',SYSTIMESTAMP,SYSTIMESTAMP+NUMTODSINTERVAL(:seconds,'SECOND'),SYSTIMESTAMP,
      (SELECT ENTERPRISE_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id),(SELECT WORKSPACE_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id))""",
      {"lease_id":lease_id,"job_id":job["id"],"attempt_id":attempt_id,"worker_id":worker_id,"device_id":did,"token_hash":token_hash,"seconds":seconds})
    cur.execute("""UPDATE SJZQ_COLLECTION_JOB SET STATUS='leased',ATTEMPT_COUNT=:attempt_no,ACTIVE_ATTEMPT_ID=:attempt_id,
      DEVICE_ID=:device_id,LEASE_TOKEN_HASH=:token_hash,LEASE_EXPIRES_AT=SYSTIMESTAMP+NUMTODSINTERVAL(:seconds,'SECOND'),UPDATE_TIME=SYSTIMESTAMP
      WHERE JOB_ID=:job_id AND STATUS='pending'""",
      {"attempt_no":attempt_no,"attempt_id":attempt_id,"device_id":did,"token_hash":token_hash,"seconds":seconds,"job_id":job["id"]})
    if cur.rowcount != 1:
        raise JobProtocolError("JOB_ACQUIRE_RACE", "job changed during acquire")
    cur.execute("UPDATE SJZQ_DEVICE SET ACTIVE_JOB_ID=:job_id,ACTIVE_ATTEMPT_ID=:attempt_id,UPDATE_TIME=SYSTIMESTAMP WHERE DEVICE_ID=:device_id AND ACTIVE_ATTEMPT_ID IS NULL", {"job_id":job["id"],"attempt_id":attempt_id,"device_id":did})
    if cur.rowcount != 1:
        raise JobProtocolError("DEVICE_ACQUIRE_RACE", "device changed during acquire")
    _event(cur, task_id, job["id"], "lease_acquired", attempt_id=attempt_id, device_id=did, worker_id=worker_id, token_hash=token_hash, trace_id=trace_id, old=job["status"], new="leased", detail={"attempt_no":attempt_no,"lease_seconds":seconds})
    return {"task_id":task_id,"job_id":job["id"],"job_key":job["key"],"job_type":job["type"],"payload":_payload(job["payload"]),"attempt_id":attempt_id,"attempt_no":attempt_no,"lease_id":lease_id,"lease_token":token,"trace_id":trace_id,"lease_seconds":seconds,"checkpoint_version":job["checkpoint_version"],"checkpoint":_payload(job.get("checkpoint"))}


def start(cur: Any, *, device_id: int, job_id: int, attempt_id: int, worker_id: str, lease_token: str) -> dict[str, Any]:
    job, attempt = _context(cur, device_id=device_id, job_id=job_id, attempt_id=attempt_id, worker_id=worker_id, lease_token=lease_token)
    if job["pause_requested"]:
        raise JobProtocolError("JOB_PAUSED", "pause has been requested", job["status"])
    if job["status"] == "running":
        return {"status":"running", "idempotent":True}
    try:
        validate_job_transition(job["status"], JobStatus.RUNNING)
        validate_attempt_transition(attempt["status"], AttemptStatus.RUNNING)
    except JobStateConflict as exc:
        raise JobProtocolError(exc.code, str(exc), job["status"]) from exc
    cur.execute("UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='running',STARTED_AT=NVL(STARTED_AT,SYSTIMESTAMP) WHERE ATTEMPT_ID=:id AND STATUS='leased'", {"id":attempt_id})
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET STATUS='running',UPDATE_TIME=SYSTIMESTAMP WHERE JOB_ID=:id AND STATUS='leased'", {"id":job_id})
    if cur.rowcount != 1:
        raise JobProtocolError("JOB_STATE_RACE", "job changed during start")
    if job.get("item_id") is not None:
        cur.execute("UPDATE SJZQ_TASK_ITEM SET STATUS='running',UPDATE_TIME=SYSTIMESTAMP WHERE ITEM_ID=:item_id AND STATUS='pending'", {"item_id":job["item_id"]})
    _event(cur, job["task_id"], job_id, "attempt_started", attempt_id=attempt_id, device_id=device_id, worker_id=worker_id, token_hash=attempt["token_hash"], trace_id=attempt["trace_id"], old="leased", new="running")
    return {"status":"running", "idempotent":False}


def heartbeat(cur: Any, *, device_id: int, job_id: int, attempt_id: int, worker_id: str, lease_token: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict[str, Any]:
    seconds = max(15, min(MAX_LEASE_SECONDS, int(lease_seconds)))
    job, attempt = _context(cur, device_id=device_id, job_id=job_id, attempt_id=attempt_id, worker_id=worker_id, lease_token=lease_token)
    if job["status"] not in {"leased", "running"}:
        raise JobProtocolError("STALE_LEASE", "job is no longer active", job["status"])
    for table, key in (("SJZQ_COLLECTION_LEASE","LEASE_ID"),("SJZQ_COLLECTION_ATTEMPT","ATTEMPT_ID")):
        ident = attempt_id if key == "ATTEMPT_ID" else None
        if key == "LEASE_ID":
            cur.execute("SELECT LEASE_ID FROM SJZQ_COLLECTION_LEASE WHERE ATTEMPT_ID=:id", {"id":attempt_id}); ident = int(cur.fetchone()[0])
        cur.execute(f"UPDATE {table} SET HEARTBEAT_AT=SYSTIMESTAMP,LEASE_EXPIRES_AT=GREATEST(LEASE_EXPIRES_AT,SYSTIMESTAMP+NUMTODSINTERVAL(:seconds,'SECOND')) WHERE {key}=:id", {"seconds":seconds,"id":ident})
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET LEASE_EXPIRES_AT=GREATEST(LEASE_EXPIRES_AT,SYSTIMESTAMP+NUMTODSINTERVAL(:seconds,'SECOND')),UPDATE_TIME=SYSTIMESTAMP WHERE JOB_ID=:job_id AND ACTIVE_ATTEMPT_ID=:attempt_id", {"seconds":seconds,"job_id":job_id,"attempt_id":attempt_id})
    _event(cur, job["task_id"], job_id, "heartbeat", attempt_id=attempt_id, device_id=device_id, worker_id=worker_id, token_hash=attempt["token_hash"], trace_id=attempt["trace_id"], detail={"lease_seconds":seconds})
    return {"status":job["status"],"lease_seconds":seconds,"pause_requested":job["pause_requested"]}


def checkpoint(cur: Any, *, device_id: int, job_id: int, attempt_id: int, worker_id: str, lease_token: str, version: int, idempotency_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    if len(idempotency_key or "") < 8:
        raise JobProtocolError("CHECKPOINT_IDEMPOTENCY_REQUIRED", "checkpoint idempotency_key is required")
    job, attempt = _context(cur, device_id=device_id, job_id=job_id, attempt_id=attempt_id, worker_id=worker_id, lease_token=lease_token)
    raw, digest = _json(payload), _hash(_json(payload))
    cur.execute("SELECT VERSION,PAYLOAD_SHA256 FROM SJZQ_COLLECTION_CHECKPOINT WHERE JOB_ID=:job_id AND IDEMPOTENCY_KEY=:key", {"job_id":job_id,"key":idempotency_key})
    prior = cur.fetchone()
    if prior:
        if str(prior[1]) != digest:
            raise JobProtocolError("CHECKPOINT_IDEMPOTENCY_CONFLICT", "idempotency key carries a different payload")
        return {"version":int(prior[0]),"idempotent":True}
    expected = job["checkpoint_version"] + 1
    if int(version) != expected:
        raise JobProtocolError("CHECKPOINT_VERSION_CONFLICT", f"expected version {expected}", str(job["checkpoint_version"]))
    checkpoint_id = next_id(cur, "SJZQ_SEQ_COLLECTION_CHECKPOINT")
    cur.execute("""INSERT INTO SJZQ_COLLECTION_CHECKPOINT
                   (CHECKPOINT_ID,JOB_ID,ATTEMPT_ID,VERSION,IDEMPOTENCY_KEY,PAYLOAD_SHA256,PAYLOAD_JSON,ENTERPRISE_ID,WORKSPACE_ID)
                   VALUES (:id,:job_id,:attempt_id,:version,:key,:digest,:payload,
                   (SELECT ENTERPRISE_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id),
                   (SELECT WORKSPACE_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_ID=:job_id))""",
                {"id":checkpoint_id,"job_id":job_id,"attempt_id":attempt_id,"version":version,
                 "key":idempotency_key,"digest":digest,"payload":raw})
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET CHECKPOINT_VERSION=:version,CHECKPOINT_JSON=:payload,UPDATE_TIME=SYSTIMESTAMP WHERE JOB_ID=:job_id AND ACTIVE_ATTEMPT_ID=:attempt_id AND CHECKPOINT_VERSION=:old", {"version":version,"payload":raw,"job_id":job_id,"attempt_id":attempt_id,"old":job["checkpoint_version"]})
    if cur.rowcount != 1:
        raise JobProtocolError("CHECKPOINT_STATE_RACE", "checkpoint changed concurrently")
    cur.execute("UPDATE SJZQ_COLLECTION_ATTEMPT SET FINAL_CHECKPOINT_VERSION=:version WHERE ATTEMPT_ID=:id", {"version":version,"id":attempt_id})
    _event(cur,job["task_id"],job_id,"checkpoint_confirmed",attempt_id=attempt_id,device_id=device_id,worker_id=worker_id,token_hash=attempt["token_hash"],trace_id=attempt["trace_id"],detail={"checkpoint_id":checkpoint_id,"version":version})
    return {"version":int(version),"idempotent":False}


def _finish_lease(cur: Any, job: dict[str, Any], attempt: dict[str, Any], *, device_id: int, reason: str) -> None:
    cur.execute("UPDATE SJZQ_COLLECTION_LEASE SET STATUS='released',RELEASED_AT=SYSTIMESTAMP,RELEASE_REASON=:reason WHERE ATTEMPT_ID=:attempt_id AND STATUS='active'", {"reason":reason[:128],"attempt_id":attempt["id"]})
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET ACTIVE_ATTEMPT_ID=NULL,LEASE_TOKEN_HASH=NULL,LEASE_EXPIRES_AT=NULL,DEVICE_ID=NULL,UPDATE_TIME=SYSTIMESTAMP WHERE JOB_ID=:job_id AND ACTIVE_ATTEMPT_ID=:attempt_id", {"job_id":job["id"],"attempt_id":attempt["id"]})
    cur.execute("UPDATE SJZQ_DEVICE SET ACTIVE_JOB_ID=NULL,ACTIVE_ATTEMPT_ID=NULL,UPDATE_TIME=SYSTIMESTAMP WHERE DEVICE_ID=:device_id AND ACTIVE_ATTEMPT_ID=:attempt_id", {"device_id":device_id,"attempt_id":attempt["id"]})


def complete(cur: Any, *, device_id: int, job_id: int, attempt_id: int, worker_id: str,
             lease_token: str, result_receipt_key: str,
             result_receipt_keys: list[str] | None = None,
             result_product_id: int | None = None) -> dict[str, Any]:
    manifest_keys = list(dict.fromkeys([result_receipt_key, *(result_receipt_keys or [])]))
    if not manifest_keys or any(len(key or "") < 8 or len(key) > 128 for key in manifest_keys):
        raise JobProtocolError("RESULT_RECEIPT_REQUIRED", "server-confirmed product receipt is required")
    # Do this first: after a committed success the lease is deliberately released.
    if any(_complete_replay(cur, device_id=device_id, job_id=job_id, attempt_id=attempt_id,
                            worker_id=worker_id, lease_token=lease_token, receipt_key=key)
           for key in manifest_keys):
        return {"status": "success", "idempotent": True}
    job, attempt = _context(cur, device_id=device_id, job_id=job_id, attempt_id=attempt_id,
                            worker_id=worker_id, lease_token=lease_token)
    receipts: dict[str, int] = {}
    for key in manifest_keys:
        cur.execute("""SELECT r.PRODUCT_ID FROM SJZQ_UPLOAD_RECEIPT r
                        JOIN SJZQ_PRODUCT p ON p.PRODUCT_ID=r.PRODUCT_ID AND p.TASK_ID=r.TASK_ID
                       WHERE r.IDEMPOTENCY_KEY=:key AND r.STATUS='acked' AND r.OP_TYPE='product'
                         AND r.TASK_ID=:task_id AND r.DEVICE_ID=:device_id""",
                    {"key": key, "task_id": job["task_id"], "device_id": device_id})
        receipt = cur.fetchone()
        if not receipt or receipt[0] is None:
            raise JobProtocolError("RESULT_RECEIPT_NOT_CONFIRMED", f"product receipt is not confirmed: {key}")
        receipts[key] = int(receipt[0])
    if result_product_id is not None and int(result_product_id) not in receipts.values():
        raise JobProtocolError("RESULT_PRODUCT_MISMATCH", "result product is absent from receipt manifest")
    canonical_product_id = int(result_product_id) if result_product_id is not None else receipts[manifest_keys[0]]
    if job.get("item_id") is not None:
        cur.execute("""SELECT PRODUCT_ID,TARGET_SPEC,TARGET_APPROVAL,TARGET_NAME,TARGET_MANUFACTURER
                         FROM SJZQ_TASK_ITEM WHERE ITEM_ID=:item_id AND TASK_ID=:task_id""",
                    {"item_id": job["item_id"], "task_id": job["task_id"]})
        item = cur.fetchone()
        if not item:
            raise JobProtocolError("RESULT_ITEM_MISMATCH", "job item product is absent from receipt manifest")
        prebound_product_id = int(item[0]) if item[0] is not None else None
        requires_prebound = any(str(value or "").strip() for value in item[1:])
        if requires_prebound and (prebound_product_id is None or prebound_product_id not in receipts.values()):
            raise JobProtocolError("RESULT_ITEM_MISMATCH", "matched job item product is absent from receipt manifest")
        if prebound_product_id is not None:
            if prebound_product_id not in receipts.values():
                raise JobProtocolError("RESULT_ITEM_MISMATCH", "job item product is absent from receipt manifest")
            canonical_product_id = prebound_product_id
    canonical_key = next(key for key in manifest_keys if receipts[key] == canonical_product_id)
    try:
        validate_job_transition(job["status"], JobStatus.SUCCESS)
        validate_attempt_transition(attempt["status"], AttemptStatus.SUCCESS)
    except JobStateConflict as exc:
        raise JobProtocolError(exc.code, str(exc), job["status"]) from exc
    cur.execute("UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='success',FINISHED_AT=SYSTIMESTAMP,FINAL_CHECKPOINT_VERSION=:version WHERE ATTEMPT_ID=:id AND STATUS IN ('leased','running')", {"version":job["checkpoint_version"],"id":attempt_id})
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET STATUS='success',RESULT_RECEIPT_KEY=:key,RESULT_PRODUCT_ID=:product_id,UPDATE_TIME=SYSTIMESTAMP WHERE JOB_ID=:job_id AND ACTIVE_ATTEMPT_ID=:attempt_id", {"key":canonical_key,"product_id":canonical_product_id,"job_id":job_id,"attempt_id":attempt_id})
    if cur.rowcount != 1:
        raise JobProtocolError("JOB_STATE_RACE", "job changed during complete")
    _finish_lease(cur,job,attempt,device_id=device_id,reason="completed")
    if job.get("item_id") is not None:
        cur.execute("UPDATE SJZQ_TASK_ITEM SET STATUS='succeeded',PRODUCT_ID=:product_id,UPDATE_TIME=SYSTIMESTAMP WHERE ITEM_ID=:item_id AND STATUS IN ('pending','running')", {"product_id":canonical_product_id,"item_id":job["item_id"]})
    _aggregate_task_from_jobs(cur, job["task_id"])
    _event(cur,job["task_id"],job_id,"job_completed",attempt_id=attempt_id,device_id=device_id,worker_id=worker_id,token_hash=attempt["token_hash"],trace_id=attempt["trace_id"],old=job["status"],new="success",detail={"result_receipt_key":canonical_key,"result_receipt_keys":manifest_keys,"product_id":canonical_product_id})
    return {"status":"success","idempotent":False}
def fail(cur: Any, *, device_id: int, job_id: int, attempt_id: int, worker_id: str, lease_token: str, error_class: str, error_code: str, error_message: str = "") -> dict[str, Any]:
    try:
        category = ErrorClass(error_class.lower())
    except ValueError as exc:
        raise JobProtocolError("INVALID_ERROR_CLASS", "unknown error class") from exc
    job, attempt = _context(cur, device_id=device_id,job_id=job_id,attempt_id=attempt_id,worker_id=worker_id,lease_token=lease_token)
    decision = decide_retry(category,attempt_no=attempt["no"],max_attempts=job["max_attempts"],identity=job["key"])
    try:
        validate_job_transition(job["status"],decision.target)
        validate_attempt_transition(attempt["status"],AttemptStatus.FAILED)
    except JobStateConflict as exc:
        raise JobProtocolError(exc.code,str(exc),job["status"]) from exc
    cur.execute("UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='failed',FINISHED_AT=SYSTIMESTAMP,ERROR_CLASS=:class,ERROR_CODE=:code,ERROR_MESSAGE=:message,RETRYABLE=:retryable,RETRY_DELAY_SECONDS=:delay WHERE ATTEMPT_ID=:id", {"class":category.value,"code":error_code[:128],"message":error_message[:2000],"retryable":int(decision.retryable),"delay":int(decision.delay_seconds or 0),"id":attempt_id})
    cur.execute("""UPDATE SJZQ_COLLECTION_JOB SET STATUS=:status,NEXT_RUN_AT=CASE WHEN :retryable=1 THEN SYSTIMESTAMP+NUMTODSINTERVAL(:delay,'SECOND') ELSE SYSTIMESTAMP END,
      LAST_ERROR_CLASS=:class,LAST_ERROR_CODE=:code,LAST_ERROR_MESSAGE=:message,UPDATE_TIME=SYSTIMESTAMP WHERE JOB_ID=:job_id AND ACTIVE_ATTEMPT_ID=:attempt_id""", {"status":decision.target.value,"retryable":int(decision.retryable),"delay":int(decision.delay_seconds or 0),"class":category.value,"code":error_code[:128],"message":error_message[:2000],"job_id":job_id,"attempt_id":attempt_id})
    _finish_lease(cur,job,attempt,device_id=device_id,reason=f"failed:{category.value}")
    target_not_matched = (
        category == ErrorClass.BUSINESS_REJECTION and error_code == "TARGET_NOT_MATCHED"
    )
    if decision.target.value in {"failed", "quarantined", "dead"} and job.get("item_id") is not None:
        if target_not_matched:
            cur.execute("UPDATE SJZQ_TASK_ITEM SET STATUS='not_matched',MESSAGE=:message,UPDATE_TIME=SYSTIMESTAMP WHERE ITEM_ID=:item_id AND STATUS IN ('pending','running')", {"message":error_code[:1000],"item_id":job["item_id"]})
        else:
            cur.execute("UPDATE SJZQ_TASK_ITEM SET STATUS='failed',MESSAGE=:message,UPDATE_TIME=SYSTIMESTAMP WHERE ITEM_ID=:item_id AND STATUS IN ('pending','running')", {"message":error_code[:1000],"item_id":job["item_id"]})
    if decision.target.value in {"failed", "quarantined", "dead", "cancelled"}:
        _aggregate_task_from_jobs(cur, job["task_id"])
    _event(cur,job["task_id"],job_id,"job_failed",attempt_id=attempt_id,device_id=device_id,worker_id=worker_id,token_hash=attempt["token_hash"],trace_id=attempt["trace_id"],old=job["status"],new=decision.target.value,error_class=category.value,error_code=error_code[:128],detail={"retryable":decision.retryable,"delay_seconds":decision.delay_seconds})
    return {"status":decision.target.value,"retryable":decision.retryable,"delay_seconds":decision.delay_seconds}


def yield_paused(
    cur: Any,
    *,
    device_id: int,
    job_id: int,
    attempt_id: int,
    worker_id: str,
    lease_token: str,
) -> dict[str, Any]:
    """Release a running Lease at a safe point after a user pause request."""
    job, attempt = _context(
        cur,
        device_id=device_id,
        job_id=job_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    _review, pause_state = _lock_task(cur, job["task_id"])
    if pause_state != "paused" and not job["pause_requested"]:
        raise JobProtocolError("PAUSE_NOT_REQUESTED", "Job cannot yield without Task pause")
    cur.execute(
        """UPDATE SJZQ_COLLECTION_ATTEMPT
              SET STATUS='cancelled', FINISHED_AT=SYSTIMESTAMP,
                  ERROR_CLASS='business_rejection', ERROR_CODE='USER_PAUSED',
                  RETRYABLE=0, FINAL_CHECKPOINT_VERSION=:version
            WHERE ATTEMPT_ID=:attempt_id AND STATUS IN ('leased','running')""",
        {"attempt_id": attempt_id, "version": job["checkpoint_version"]},
    )
    cur.execute(
        """UPDATE SJZQ_COLLECTION_JOB
              SET STATUS='paused', PAUSE_REQUESTED=0, UPDATE_TIME=SYSTIMESTAMP
            WHERE JOB_ID=:job_id AND ACTIVE_ATTEMPT_ID=:attempt_id
              AND STATUS IN ('leased','running')""",
        {"job_id": job_id, "attempt_id": attempt_id},
    )
    if cur.rowcount != 1:
        raise JobProtocolError("JOB_STATE_RACE", "Job changed during pause yield")
    _finish_lease(cur, job, attempt, device_id=device_id, reason="user_paused")
    _event(
        cur,
        job["task_id"],
        job_id,
        "job_paused",
        attempt_id=attempt_id,
        device_id=device_id,
        worker_id=worker_id,
        token_hash=attempt["token_hash"],
        trace_id=attempt["trace_id"],
        old=job["status"],
        new="paused",
        detail={"checkpoint_version": job["checkpoint_version"]},
    )
    return {"status": "paused", "checkpoint_version": job["checkpoint_version"]}


def recoverable_work(cur: Any, *, device_id: int, worker_id: str) -> list[dict[str, Any]]:
    _lock_device(cur,device_id)
    cur.execute("""SELECT j.JOB_ID,j.TASK_ID,j.JOB_KEY,j.JOB_TYPE,j.TARGET_JSON,j.CHECKPOINT_JSON,j.STATUS,j.ACTIVE_ATTEMPT_ID,a.ATTEMPT_NO,a.TRACE_ID,l.LEASE_ID,l.LEASE_EXPIRES_AT,j.CHECKPOINT_VERSION
      FROM SJZQ_COLLECTION_JOB j JOIN SJZQ_COLLECTION_ATTEMPT a ON a.ATTEMPT_ID=j.ACTIVE_ATTEMPT_ID JOIN SJZQ_COLLECTION_LEASE l ON l.ATTEMPT_ID=a.ATTEMPT_ID
      WHERE j.DEVICE_ID=:device_id AND a.WORKER_ID=:worker_id AND j.STATUS IN ('leased','running') AND l.STATUS='active' AND l.LEASE_EXPIRES_AT>SYSTIMESTAMP ORDER BY j.JOB_ID""", {"device_id":device_id,"worker_id":worker_id})
    work = rows_as_dicts(cur)
    for item in work:
        item["checkpoint"] = _payload(item.pop("checkpoint_json", None))
    return work


def pause_task(cur: Any, *, task_id: int) -> int:
    _lock_task(cur,task_id)
    cur.execute("UPDATE SJZQ_TASK SET PAUSE_STATE='paused',UPDATE_TIME=SYSTIMESTAMP WHERE TASK_ID=:id", {"id":task_id})
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET STATUS='paused',UPDATE_TIME=SYSTIMESTAMP WHERE TASK_ID=:id AND STATUS IN ('pending','retry_wait')", {"id":task_id})
    changed=int(cur.rowcount or 0)
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET PAUSE_REQUESTED=1,UPDATE_TIME=SYSTIMESTAMP WHERE TASK_ID=:id AND STATUS IN ('leased','running')", {"id":task_id})
    _event(cur,task_id,None,"task_pause_requested",detail={"paused_jobs":changed})
    return changed


def resume_task(cur: Any, *, task_id: int) -> int:
    _lock_task(cur,task_id)
    cur.execute("UPDATE SJZQ_TASK SET PAUSE_STATE='active',UPDATE_TIME=SYSTIMESTAMP WHERE TASK_ID=:id", {"id":task_id})
    cur.execute("UPDATE SJZQ_COLLECTION_JOB SET STATUS='pending',PAUSE_REQUESTED=0,UPDATE_TIME=SYSTIMESTAMP WHERE TASK_ID=:id AND STATUS='paused'", {"id":task_id})
    changed=int(cur.rowcount or 0)
    _event(cur,task_id,None,"task_resumed",detail={"resumed_jobs":changed})
    return changed




def _complete_replay(cur: Any, *, device_id: int, job_id: int, attempt_id: int, worker_id: str, lease_token: str, receipt_key: str) -> bool:
    """A lost complete ACK may be retried after the active lease has been released."""
    token_hash = _hash(lease_token)
    did, _active_job, _active_attempt, _enterprise_id, _workspace_id = _device_lock_parts(_lock_device(cur, device_id))
    task_id = _task_for_job(cur, job_id)
    _lock_task(cur, task_id)
    job = _lock_job(cur, job_id)
    attempt = _lock_attempt(cur, attempt_id)
    return bool(job["status"] == "success" and str(job["receipt"] or "") == receipt_key
                and attempt["job_id"] == job_id and attempt["device_id"] == did
                and attempt["worker_id"] == worker_id and secrets.compare_digest(attempt["token_hash"], token_hash))



def create_jobs_for_task(cur: Any, *, task_id: int) -> list[int]:
    """Idempotently materialize stable collect Jobs for a Task's existing items.

    The unique JOB_KEY is the business identity.  Calling this again after a
    process crash returns the prior rows rather than creating new semantics.
    """
    _lock_task(cur, task_id)
    cur.execute("SELECT PLATFORM_CODE,TASK_TYPE,CONFIG_JSON FROM SJZQ_TASK WHERE TASK_ID=:task_id", {"task_id":task_id})
    task_meta = cur.fetchone()
    if not task_meta:
        raise JobProtocolError("TASK_NOT_FOUND", "task does not exist")
    platform_code, task_type, config_json = str(task_meta[0]), str(task_meta[1]), task_meta[2]
    task_config = _payload(config_json)
    cur.execute("SELECT ITEM_ID,KEYWORD,TARGET_SPEC,TARGET_APPROVAL,TARGET_NAME,TARGET_MANUFACTURER FROM SJZQ_TASK_ITEM WHERE TASK_ID=:task_id ORDER BY ROW_INDEX,ITEM_ID", {"task_id": task_id})
    items = cur.fetchall()
    specs: list[tuple[int | None, str, dict[str, Any]]] = []
    if items:
        for row in items:
            item_id = int(row[0])
            item_payload = {"item_id": item_id, "keyword": row[1], "target_spec": row[2],
                            "target_approval": row[3], "target_name": row[4],
                            "target_manufacturer": row[5]}
            specs.append((item_id, f"collect_item:task/{task_id}/item/{item_id}", {
                **item_payload, "keywords": [row[1]], "items": [item_payload],
                "platform_code": platform_code, "task_type": task_type, "config": task_config,
            }))
    else:
        specs.append((None, f"collect_task:task/{task_id}/default", {
            "keywords": [], "items": [], "platform_code": platform_code,
            "task_type": task_type, "config": task_config,
        }))
    created: list[int] = []
    for item_id, key, target in specs:
        cur.execute("SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_KEY=:key", {"key": key})
        prior = cur.fetchone()
        if prior:
            created.append(int(prior[0]))
            continue
        job_id = next_id(cur, "SJZQ_SEQ_COLLECTION_JOB")
        try:
            cur.execute("""INSERT INTO SJZQ_COLLECTION_JOB
                (JOB_ID,TASK_ID,TASK_ITEM_ID,JOB_KEY,JOB_TYPE,TARGET_JSON,STATUS,PRIORITY,MAX_ATTEMPTS,ATTEMPT_COUNT,NEXT_RUN_AT,ENTERPRISE_ID,WORKSPACE_ID)
                VALUES (:job_id,:task_id,:item_id,:job_key,:job_type,:target_json,'pending',5,5,0,SYSTIMESTAMP,
                (SELECT ENTERPRISE_ID FROM SJZQ_TASK WHERE TASK_ID=:task_id),(SELECT WORKSPACE_ID FROM SJZQ_TASK WHERE TASK_ID=:task_id))""",
                {"job_id":job_id,"task_id":task_id,"item_id":item_id,"job_key":key,
                 "job_type":"collect_item" if item_id is not None else "collect_task","target_json":_json(target)})
            created.append(job_id)
            _event(cur, task_id, job_id, "job_materialized", detail={"job_key": key})
        except Exception:
            # A concurrent materializer can win the unique JOB_KEY race.  Re-read
            # only that identity; unrelated Oracle errors remain visible.
            cur.execute("SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE JOB_KEY=:key", {"key": key})
            raced = cur.fetchone()
            if not raced:
                raise
            created.append(int(raced[0]))
    return created



def _aggregate_task_from_jobs(cur: Any, task_id: int) -> str | None:
    """Close Task only after every Job is terminal and every success has a receipt/product.

    This is deliberately called inside the same Job completion/failure transaction;
    an open/retry/reclaimed Job leaves the aggregate Task running.
    """
    cur.execute("SELECT STATUS,ACTIVE_ATTEMPT_ID,RESULT_RECEIPT_KEY,RESULT_PRODUCT_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id FOR UPDATE", {"task_id":task_id})
    jobs = cur.fetchall()
    if not jobs:
        return None
    terminal = {"success", "failed", "cancelled", "dead", "quarantined"}
    if any(str(row[0]).lower() not in terminal or row[1] is not None for row in jobs):
        return None
    for status, _active, receipt_key, product_id in jobs:
        if str(status).lower() != "success":
            continue
        if not receipt_key or product_id is None:
            raise JobProtocolError("TASK_SUCCESS_INVARIANT_BROKEN", "successful job has no receipt/product")
        cur.execute("""SELECT 1 FROM SJZQ_UPLOAD_RECEIPT r JOIN SJZQ_PRODUCT p ON p.PRODUCT_ID=r.PRODUCT_ID
                       WHERE r.IDEMPOTENCY_KEY=:key AND r.STATUS='acked' AND r.OP_TYPE='product'
                         AND r.TASK_ID=:task_id AND r.PRODUCT_ID=:product_id AND p.TASK_ID=:task_id""",
                    {"key":receipt_key,"task_id":task_id,"product_id":product_id})
        if not cur.fetchone():
            raise JobProtocolError("TASK_SUCCESS_INVARIANT_BROKEN", "successful job receipt is not persisted")
    success_count = sum(str(row[0]).lower() == "success" for row in jobs)
    target = "succeeded" if success_count == len(jobs) else ("partially_succeeded" if success_count else "failed")
    storage_target = "partial_success" if target == "partially_succeeded" else target
    cur.execute("""UPDATE SJZQ_TASK SET STATUS=:status,SUCCESS_COUNT=:success_count,FAIL_COUNT=:fail_count,
                 END_TIME=SYSTIMESTAMP,UPDATE_TIME=SYSTIMESTAMP WHERE TASK_ID=:task_id AND STATUS='running'""",
                {"status":storage_target,"success_count":success_count,"fail_count":len(jobs)-success_count,"task_id":task_id})
    if cur.rowcount:
        cur.execute("SELECT ENTERPRISE_ID FROM SJZQ_TASK WHERE TASK_ID=:task_id", {"task_id": task_id})
        tenant_row = cur.fetchone()
        if tenant_row and tenant_row[0] is not None:
            from server.quota import ACTIVE_TASK, release
            release(cur, enterprise_id=int(tenant_row[0]), metric=ACTIVE_TASK,
                    resource_type="task", resource_key=str(task_id))
        cur.execute("UPDATE SJZQ_DEVICE SET CURRENT_TASK_ID=NULL,STATUS=CASE WHEN ACTIVE_ATTEMPT_ID IS NULL THEN 'online' ELSE STATUS END,UPDATE_TIME=SYSTIMESTAMP WHERE CURRENT_TASK_ID=:task_id AND ACTIVE_ATTEMPT_ID IS NULL", {"task_id":task_id})
        _event(cur,task_id,None,"task_aggregated",old="running",new=target,detail={"job_count":len(jobs),"success_count":success_count})
    return target

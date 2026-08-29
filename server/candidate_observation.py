"""Lease-fenced Raw-only persistence for unmatched candidate evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Callable
import oracledb

from server.db import next_id
from server.job_service import JobProtocolError, require_active_lease
from server.quota import STORAGE_BYTES, adjust_used, commit, reserve

SOURCE_TYPE = "candidate_observation"
RETENTION_DAYS = 30
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_PER_JOB = 3
_FIELDS = {"title", "spec", "approval", "manufacturer", "item_id", "price", "shop"}


class CandidateObservationError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _bounded_fields(value: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    result: dict[str, str | int | float | bool | None] = {}
    for key in sorted(_FIELDS & set(value)):
        raw = value.get(key)
        if raw is None or isinstance(raw, (int, float, bool)):
            result[key] = raw
        else:
            result[key] = str(raw)[:512]
    return result


def canonical_payload(body: Any) -> tuple[str, str, int]:
    if body.reason_code == "no_candidate" and body.candidate_present:
        raise CandidateObservationError("OBSERVATION_REASON_CONFLICT", "no_candidate cannot contain a candidate")
    if body.reason_code == "candidate_rejected" and not body.candidate_present:
        raise CandidateObservationError("OBSERVATION_REASON_CONFLICT", "candidate_rejected requires a candidate")
    no_candidate = body.reason_code == "no_candidate"
    screenshot_ref = None if no_candidate else body.screenshot_ref
    if screenshot_ref:
        path = PurePosixPath(str(body.screenshot_ref))
        expected_ref = "candidate-observations/" + hashlib.sha256(
            str(body.idempotency_key).encode("utf-8")
        ).hexdigest() + ".jpg"
        if path.is_absolute() or ".." in path.parts or str(path) != expected_ref:
            raise CandidateObservationError("INVALID_SCREENSHOT_REF", "screenshot_ref must be server-managed")
    public = {
        "contract_version": "candidate-observation-1",
        "task_id": int(body.task_id), "task_item_id": int(body.task_item_id),
        "job_id": int(body.job_id), "attempt_id": int(body.attempt_id),
        "trace_id": body.trace_id, "platform_code": body.platform_code,
        "candidate_present": bool(body.candidate_present), "matched": False,
        "reason_code": body.reason_code,
        "candidate_ordinal": 0 if no_candidate else int(body.candidate_ordinal),
        "expected_fields": _bounded_fields(body.expected_fields),
        "observed_fields": {} if no_candidate else _bounded_fields(body.observed_fields),
        "field_differences": {} if no_candidate else {
            key: str(value)[:128] for key, value in sorted(body.field_differences.items()) if key in _FIELDS
        },
        "source_summary": [
            {"type": str(item.get("type") or "")[:32],
             "source_identifier": str(item.get("source_identifier") or "")[:128]}
            for item in body.source_summary[:12]
        ],
        "collected_at_epoch_ms": int(body.collected_at_epoch_ms),
        "collector_version": body.collector_version,
        "parser_version": body.parser_version,
        "screenshot_ref": screenshot_ref,
        "retention_days": RETENTION_DAYS,
        "retention_until": (
            datetime.fromtimestamp(body.collected_at_epoch_ms / 1000, tz=timezone.utc)
            + timedelta(days=RETENTION_DAYS)
        ).replace(tzinfo=None).isoformat(timespec="seconds"),
    }
    public["payload_size_bytes"] = 0
    encoded = ""
    size = 0
    for _ in range(3):
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        size = len(encoded.encode("utf-8"))
        public["payload_size_bytes"] = size
    encoded = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    size = len(encoded.encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        raise CandidateObservationError("OBSERVATION_TOO_LARGE", "candidate observation exceeds 64 KiB")
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest(), size


def persist(cur: Any, *, body: Any, device: dict[str, Any]) -> dict[str, Any]:
    payload, payload_sha, payload_size = canonical_payload(body)
    enterprise_id = int(device["enterprise_id"])
    workspace_id = int(device["workspace_id"])
    cur.execute(
        """SELECT RAW_ID,PAYLOAD_SHA256,DEVICE_ID,ENTERPRISE_ID,WORKSPACE_ID
             FROM SJZQ_RAW_COLLECTION WHERE REQUEST_KEY=:key""",
        {"key": body.idempotency_key},
    )
    replay = cur.fetchone()
    if replay:
        if (str(replay[1]), int(replay[2]), int(replay[3]), int(replay[4])) != (
            payload_sha, int(device["device_id"]), enterprise_id, workspace_id
        ):
            raise CandidateObservationError("IDEMPOTENCY_CONFLICT", "candidate observation replay conflicts")
        return {"raw_id": int(replay[0]), "persisted": True, "acknowledged": True, "idempotent": True}

    job, _attempt = require_active_lease(
        cur, device_id=int(device["device_id"]), job_id=body.job_id,
        attempt_id=body.attempt_id, worker_id=body.worker_id, lease_token=body.lease_token,
    )
    if int(job["task_id"]) != int(body.task_id) or int(job.get("item_id") or 0) != int(body.task_item_id):
        raise JobProtocolError("JOB_ITEM_MISMATCH", "Job does not own candidate observation TaskItem")
    # Serialize the cross-attempt/cross-job per-Item cap on the authoritative
    # TaskItem row.  A plain COUNT followed by INSERT would race at the limit.
    cur.execute(
        """SELECT ITEM_ID FROM SJZQ_TASK_ITEM
             WHERE ITEM_ID=:item_id AND TASK_ID=:task_id
               AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
             FOR UPDATE""",
        {"item_id": body.task_item_id, "task_id": body.task_id,
         "enterprise_id": enterprise_id, "workspace_id": workspace_id},
    )
    if not cur.fetchone():
        raise JobProtocolError("JOB_ITEM_MISMATCH", "TaskItem tenant ownership mismatch")
    cur.execute(
        """SELECT COUNT(*),MAX(RAW_ID) FROM SJZQ_RAW_COLLECTION
             WHERE TASK_ID=:task_id AND SOURCE_TYPE=:source_type
               AND JSON_VALUE(RAW_JSON,'$.task_item_id' RETURNING NUMBER)=:item_id
               AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
        {"task_id": body.task_id, "item_id": body.task_item_id, "source_type": SOURCE_TYPE,
         "enterprise_id": enterprise_id, "workspace_id": workspace_id},
    )
    count, latest_raw_id = cur.fetchone()
    count = int(count or 0)
    if count >= MAX_PER_JOB:
        # The limit is an accepted, durable truncation outcome rather than a
        # protocol rejection.  ACK it so Android can finish the not-matched
        # Job, while retaining the truncation reason on the TaskItem.
        summary = f"candidate_observation_truncated(limit={MAX_PER_JOB})"
        cur.execute(
            """UPDATE SJZQ_TASK_ITEM SET MESSAGE=SUBSTR(
                   CASE WHEN INSTR(NVL(MESSAGE,''),:summary)>0 THEN MESSAGE
                        WHEN MESSAGE IS NULL THEN :summary ELSE MESSAGE||'; '||:summary END,1,1000),
                   UPDATE_TIME=SYSTIMESTAMP
                 WHERE ITEM_ID=:item_id AND TASK_ID=:task_id
                   AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
                   AND STATUS IN ('pending','running')""",
            {"summary": summary, "item_id": body.task_item_id, "task_id": body.task_id,
             "enterprise_id": enterprise_id, "workspace_id": workspace_id},
        )
        return {
            "raw_id": int(latest_raw_id), "persisted": False, "acknowledged": True,
            "idempotent": False, "truncated": True, "observation_count": count,
            "truncation_reason": "item_observation_limit",
        }
    reservation = reserve(
        cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=STORAGE_BYTES,
        amount=max(1, payload_size), resource_type=SOURCE_TYPE, resource_key=body.idempotency_key,
    )
    raw_id = next_id(cur, "SJZQ_SEQ_RAW_COLLECTION")
    try:
        cur.execute(
            """INSERT INTO SJZQ_RAW_COLLECTION
             (RAW_ID,REQUEST_KEY,TASK_ID,JOB_ID,ATTEMPT_ID,DEVICE_ID,SOURCE_TYPE,
              PAYLOAD_SHA256,RAW_JSON,COLLECTED_AT,ENTERPRISE_ID,WORKSPACE_ID)
             VALUES (:raw_id,:request_key,:task_id,:job_id,:attempt_id,:device_id,:source_type,
                     :payload_sha,:raw_json,SYSTIMESTAMP,:enterprise_id,:workspace_id)""",
            {"raw_id": raw_id, "request_key": body.idempotency_key, "task_id": body.task_id,
             "job_id": body.job_id, "attempt_id": body.attempt_id, "device_id": device["device_id"],
             "source_type": SOURCE_TYPE, "payload_sha": payload_sha, "raw_json": payload,
             "enterprise_id": enterprise_id, "workspace_id": workspace_id},
        )
    except oracledb.IntegrityError:
        # A concurrent replay can pass the initial lookup before the first
        # transaction commits.  Resolve the unique request key as the same ACK,
        # never as a second business write.
        cur.execute(
            """SELECT RAW_ID,PAYLOAD_SHA256,DEVICE_ID,ENTERPRISE_ID,WORKSPACE_ID
                 FROM SJZQ_RAW_COLLECTION WHERE REQUEST_KEY=:key""",
            {"key": body.idempotency_key},
        )
        raced = cur.fetchone()
        if raced and (str(raced[1]), int(raced[2]), int(raced[3]), int(raced[4])) == (
            payload_sha, int(device["device_id"]), enterprise_id, workspace_id
        ):
            return {"raw_id": int(raced[0]), "persisted": True, "acknowledged": True, "idempotent": True}
        raise CandidateObservationError("IDEMPOTENCY_CONFLICT", "candidate observation replay conflicts")
    if reservation.status != "committed":
        commit(cur, reservation.reservation_id)
    summary = "no_candidate" if not body.candidate_present else f"candidate_rejected#{body.candidate_ordinal}"
    cur.execute(
        """UPDATE SJZQ_TASK_ITEM SET MESSAGE=SUBSTR(
               CASE WHEN MESSAGE IS NULL THEN :summary ELSE MESSAGE||'; '||:summary END,1,1000),
               UPDATE_TIME=SYSTIMESTAMP
             WHERE ITEM_ID=:item_id AND TASK_ID=:task_id
               AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
               AND STATUS IN ('pending','running')""",
        {"summary": summary, "item_id": body.task_item_id, "task_id": body.task_id,
         "enterprise_id": enterprise_id, "workspace_id": workspace_id},
    )
    return {"raw_id": raw_id, "persisted": True, "acknowledged": True, "idempotent": False}


def cleanup_expired(
    cur: Any, *, limit: int = 100,
    delete_screenshot: Callable[[str], None] | None = None,
) -> list[str]:
    """Delete only candidate Raw older than 30 days; TaskItem summaries remain."""
    cur.execute(
        """SELECT RAW_ID,ENTERPRISE_ID,WORKSPACE_ID,REQUEST_KEY,
                  NVL(JSON_VALUE(RAW_JSON,'$.payload_size_bytes' RETURNING NUMBER),
                      DBMS_LOB.GETLENGTH(RAW_JSON)) RAW_SIZE,
                  JSON_VALUE(RAW_JSON,'$.screenshot_ref' RETURNING VARCHAR2(512)) SCREENSHOT_REF
             FROM SJZQ_RAW_COLLECTION
            WHERE SOURCE_TYPE=:source_type
              AND COLLECTED_AT < SYSTIMESTAMP-NUMTODSINTERVAL(:days,'DAY')
              AND ROWNUM<=:limit
            FOR UPDATE SKIP LOCKED""",
        {"source_type": SOURCE_TYPE, "days": RETENTION_DAYS, "limit": max(1, min(limit, 500))},
    )
    rows = list(cur.fetchall())
    screenshot_refs: list[str] = []
    for raw_id, enterprise_id, workspace_id, request_key, size, screenshot_ref in rows:
        if screenshot_ref:
            if delete_screenshot is None:
                continue
            try:
                delete_screenshot(str(screenshot_ref))
            except OSError:
                continue
        cur.execute(
            """DELETE FROM SJZQ_RAW_COLLECTION
                 WHERE RAW_ID=:raw_id AND SOURCE_TYPE=:source_type
                   AND COLLECTED_AT < SYSTIMESTAMP-NUMTODSINTERVAL(:days,'DAY')""",
            {"raw_id": raw_id, "source_type": SOURCE_TYPE, "days": RETENTION_DAYS},
        )
        if cur.rowcount != 1:
            continue
        adjust_used(
            cur, enterprise_id=int(enterprise_id), workspace_id=int(workspace_id), metric=STORAGE_BYTES,
            amount_delta=-max(1, int(size or 0)), event_key=f"candidate-expire:{raw_id}",
            resource_type=SOURCE_TYPE, resource_key=str(request_key),
        )
        if screenshot_ref:
            screenshot_refs.append(str(screenshot_ref))
    return screenshot_refs

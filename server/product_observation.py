"""Transactional persistence for Phase 3 quality observations.

The caller owns the Oracle transaction and must validate Task/Lease authority
before invoking any write function in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

import oracledb

from server.data_quality import (
    QualityDecision,
    SnapshotDiff,
    canonical_json,
    content_sha256,
    detect_difference,
    normalize_sources,
    normalized_snapshot,
)
from server.db import next_id
from server.quota import DAILY_SNAPSHOT, STORAGE_BYTES, commit, reserve


@dataclass(frozen=True)
class ObservationResult:
    master_product_id: int
    snapshot_id: int
    raw_id: int
    quality_result_id: int
    diff_id: int
    previous_snapshot_id: int | None
    changed_fields: tuple[str, ...]
    enterprise_product_id: int | None = None


@dataclass(frozen=True)
class QuarantineResult:
    quarantine_id: int
    raw_id: int
    quality_result_id: int
    idempotent: bool = False


def sanitized_raw_payload(body: Any) -> dict[str, Any]:
    payload = body.model_dump(mode="json") if hasattr(body, "model_dump") else dict(body)
    for secret in ("device_key", "lease_token"):
        payload.pop(secret, None)
    return payload


def _clob(value: Any) -> Any:
    return value.read() if hasattr(value, "read") else value


def _insert_raw(cur: Any, *, body: Any, device_id: int, payload_sha256: str,
                enterprise_id: int = 1, workspace_id: int = 1) -> int:
    raw_id = next_id(cur, "SJZQ_SEQ_RAW_COLLECTION")
    cur.execute(
        """INSERT INTO SJZQ_RAW_COLLECTION (
             RAW_ID,REQUEST_KEY,TASK_ID,JOB_ID,ATTEMPT_ID,DEVICE_ID,SOURCE_TYPE,
             PAYLOAD_SHA256,RAW_JSON,COLLECTED_AT,ENTERPRISE_ID,WORKSPACE_ID
           ) VALUES (:raw_id,:request_key,:task_id,:job_id,:attempt_id,:device_id,
             'agent_upload',:payload_sha256,:raw_json,SYSTIMESTAMP,:enterprise_id,:workspace_id)""",
        {
            "raw_id": raw_id,
            "request_key": body.idempotency_key,
            "task_id": body.task_id,
            "job_id": body.job_id,
            "attempt_id": body.attempt_id,
            "device_id": device_id,
            "payload_sha256": payload_sha256,
            "raw_json": canonical_json(sanitized_raw_payload(body)),
            "enterprise_id": enterprise_id, "workspace_id": workspace_id,
        },
    )
    return raw_id


def load_quarantine_replay(cur: Any, *, request_key: str) -> dict[str, Any] | None:
    cur.execute(
        """SELECT q.QUARANTINE_ID,q.RAW_ID,r.PAYLOAD_SHA256,r.DEVICE_ID,
                  q.ERROR_CODES_JSON,q.FAILURE_REASON,q.QUALITY_RESULT_ID
             FROM SJZQ_DATA_QUARANTINE q
             JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=q.RAW_ID
            WHERE q.REQUEST_KEY=:request_key""",
        {"request_key": request_key},
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "quarantine_id": int(row[0]), "raw_id": int(row[1]),
        "payload_sha256": str(row[2]), "device_id": int(row[3]),
        "error_codes": json.loads(_clob(row[4]) or "[]"), "failure_reason": str(row[5]),
        "quality_result_id": int(row[6]),
    }


def persist_quarantine(
    cur: Any,
    *,
    body: Any,
    device_id: int,
    payload_sha256: str,
    decision: QualityDecision,
    enterprise_id: int = 1,
    workspace_id: int = 1,
) -> QuarantineResult:
    raw_size = max(1, len(canonical_json(sanitized_raw_payload(body)).encode("utf-8")))
    storage_reservation = reserve(
        cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=STORAGE_BYTES,
        amount=raw_size, resource_type="raw", resource_key=str(body.idempotency_key),
    )
    raw_id = _insert_raw(cur, body=body, device_id=device_id, payload_sha256=payload_sha256,
                         enterprise_id=enterprise_id, workspace_id=workspace_id)
    quality_result_id = next_id(cur, "SJZQ_SEQ_QUALITY_RESULT")
    cur.execute(
        """INSERT INTO SJZQ_QUALITY_RESULT (
             QUALITY_RESULT_ID,RAW_ID,SNAPSHOT_ID,ACCEPTED,STATUS,PAGE_STATUS,PARSE_STATUS,
             QUALITY_STATUS,PARSER_VERSION,QUALITY_RULES_VERSION,MISSING_FIELDS_JSON,
             ERROR_CODES_JSON,WARNINGS_JSON,ENTERPRISE_ID,WORKSPACE_ID
           ) VALUES (:id,:raw_id,NULL,0,'quarantined',:page_status,:parse_status,:quality_status,
             :parser_version,:rules_version,:missing,:errors,:warnings,:enterprise_id,:workspace_id)""",
        {
            "id": quality_result_id, "raw_id": raw_id,
            "page_status": decision.page_status, "parse_status": decision.parse_status,
            "quality_status": decision.quality_status, "parser_version": decision.parser_version or "unknown",
            "rules_version": decision.quality_rules_version,
            "missing": canonical_json(list(decision.missing_fields)),
            "errors": canonical_json(list(decision.error_codes)),
            "warnings": canonical_json(list(decision.warnings)),
            "enterprise_id": enterprise_id, "workspace_id": workspace_id,
        },
    )
    quarantine_id = next_id(cur, "SJZQ_SEQ_DATA_QUARANTINE")
    primary_error = decision.error_codes[0] if decision.error_codes else (
        f"MISSING_{decision.missing_fields[0].upper()}" if decision.missing_fields else "QUALITY_REJECTED"
    )
    evidence = {
        "platform_code": str(getattr(body, "platform_code", "") or ""),
        "platform_product_id": str(getattr(body, "item_id", "") or ""),
        "missing_fields": list(decision.missing_fields),
        "error_codes": list(decision.error_codes),
        "warnings": list(decision.warnings),
    }
    cur.execute(
        """INSERT INTO SJZQ_DATA_QUARANTINE (
             QUARANTINE_ID,RAW_ID,MASTER_PRODUCT_ID,TASK_ID,JOB_ID,ATTEMPT_ID,REQUEST_KEY,
             QUALITY_RESULT_ID,PARSER_VERSION,QUALITY_RULES_VERSION,STATUS,FAILURE_REASON,
             ERROR_CODES_JSON,ERROR_MESSAGE,EVIDENCE_JSON,COLLECTED_AT,ENTERPRISE_ID,WORKSPACE_ID
           ) VALUES (:id,:raw_id,NULL,:task_id,:job_id,:attempt_id,:request_key,
             :quality_result_id,:parser_version,:rules_version,'open',:failure_reason,
             :error_codes,:error_message,:evidence,SYSTIMESTAMP,:enterprise_id,:workspace_id)""",
        {
            "id": quarantine_id, "raw_id": raw_id, "task_id": body.task_id,
            "job_id": body.job_id, "attempt_id": body.attempt_id,
            "request_key": body.idempotency_key, "quality_result_id": quality_result_id,
            "parser_version": decision.parser_version or "unknown",
            "rules_version": decision.quality_rules_version,
            "failure_reason": decision.failure_reason[:1000] or primary_error,
            "error_codes": canonical_json(list(decision.error_codes) or [primary_error]),
            "error_message": decision.failure_reason[:2000] or primary_error,
            "evidence": canonical_json(evidence),
            "enterprise_id": enterprise_id, "workspace_id": workspace_id,
        },
    )
    commit(cur, storage_reservation.reservation_id)
    return QuarantineResult(quarantine_id, raw_id, quality_result_id)


def _master(cur: Any, platform: str, platform_product_id: str) -> int:
    cur.execute(
        """SELECT MASTER_PRODUCT_ID FROM SJZQ_PRODUCT_MASTER
            WHERE PLATFORM_CODE=:platform AND PLATFORM_PRODUCT_ID=:product_id FOR UPDATE""",
        {"platform": platform, "product_id": platform_product_id},
    )
    row = cur.fetchone()
    if row:
        master_id = int(row[0])
        cur.execute(
            "UPDATE SJZQ_PRODUCT_MASTER SET LAST_SEEN_AT=SYSTIMESTAMP,UPDATE_TIME=SYSTIMESTAMP WHERE MASTER_PRODUCT_ID=:id",
            {"id": master_id},
        )
        return master_id
    master_id = next_id(cur, "SJZQ_SEQ_PRODUCT_MASTER")
    try:
        cur.execute(
            """INSERT INTO SJZQ_PRODUCT_MASTER (
                 MASTER_PRODUCT_ID,PLATFORM_CODE,PLATFORM_PRODUCT_ID,FIRST_SEEN_AT,LAST_SEEN_AT,STATUS
               ) VALUES (:id,:platform,:product_id,SYSTIMESTAMP,SYSTIMESTAMP,'active')""",
            {"id": master_id, "platform": platform, "product_id": platform_product_id},
        )
        return master_id
    except oracledb.IntegrityError as exc:
        error = exc.args[0] if exc.args else None
        if getattr(error, "code", None) != 1:
            raise
        # The database unique key is the final identity fence. A concurrent
        # creator has committed before ORA-00001 is raised; reuse that master.
        cur.execute(
            """SELECT MASTER_PRODUCT_ID FROM SJZQ_PRODUCT_MASTER
                WHERE PLATFORM_CODE=:platform AND PLATFORM_PRODUCT_ID=:product_id FOR UPDATE""",
            {"platform": platform, "product_id": platform_product_id},
        )
        raced = cur.fetchone()
        if not raced:
            raise
        return int(raced[0])


def _previous(cur: Any, master_product_id: int, enterprise_product_id: int,
              enterprise_id: int, workspace_id: int) -> tuple[int | None, Mapping[str, Any] | None]:
    cur.execute(
        """SELECT SNAPSHOT_ID,NORMALIZED_JSON FROM SJZQ_PRODUCT_SNAPSHOT
            WHERE MASTER_PRODUCT_ID=:id AND ENTERPRISE_PRODUCT_ID=:enterprise_product_id
              AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
            ORDER BY COLLECTED_AT DESC,SNAPSHOT_ID DESC
            FETCH FIRST 1 ROWS ONLY""",
        {"id": master_product_id, "enterprise_product_id": enterprise_product_id,
         "enterprise_id": enterprise_id, "workspace_id": workspace_id},
    )
    row = cur.fetchone()
    if not row:
        return None, None
    raw = _clob(row[1])
    return int(row[0]), json.loads(raw) if raw else {}


def persist_observation(
    cur: Any,
    *,
    body: Any,
    device_id: int,
    legacy_product_id: int,
    payload_sha256: str,
    decision: QualityDecision,
    enterprise_id: int = 1,
    workspace_id: int = 1,
) -> ObservationResult:
    request_key = str(body.idempotency_key)
    daily_reservation = reserve(
        cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=DAILY_SNAPSHOT,
        amount=1, resource_type="snapshot", resource_key=request_key,
    )
    raw_size = max(1, len(canonical_json(sanitized_raw_payload(body)).encode("utf-8")))
    storage_reservation = reserve(
        cur, enterprise_id=enterprise_id, workspace_id=workspace_id, metric=STORAGE_BYTES,
        amount=raw_size, resource_type="raw", resource_key=request_key,
    )
    raw_id = _insert_raw(cur, body=body, device_id=device_id, payload_sha256=payload_sha256,
                         enterprise_id=enterprise_id, workspace_id=workspace_id)
    normalized = normalized_snapshot(body, decision)
    master_id = _master(cur, normalized["platform_code"], normalized["platform_product_id"])
    cur.execute("""SELECT ENTERPRISE_PRODUCT_ID FROM SJZQ_ENTERPRISE_PRODUCT
                    WHERE ENTERPRISE_ID=:enterprise_id AND IDENTITY_ID=:master_id FOR UPDATE""",
                {"enterprise_id": enterprise_id, "master_id": master_id})
    enterprise_product = cur.fetchone()
    if enterprise_product:
        enterprise_product_id = int(enterprise_product[0])
    else:
        enterprise_product_id = next_id(cur, "SJZQ_SEQ_ENTERPRISE_PRODUCT")
        cur.execute("""INSERT INTO SJZQ_ENTERPRISE_PRODUCT
            (ENTERPRISE_PRODUCT_ID,ENTERPRISE_ID,IDENTITY_ID)
            VALUES (:enterprise_product_id,:enterprise_id,:master_id)""",
            {"enterprise_product_id": enterprise_product_id, "enterprise_id": enterprise_id, "master_id": master_id})
    previous_id, previous = _previous(cur, master_id, enterprise_product_id, enterprise_id, workspace_id)
    diff = detect_difference(previous, normalized)
    snapshot_id = next_id(cur, "SJZQ_SEQ_PRODUCT_SNAPSHOT")
    cur.execute(
        """INSERT INTO SJZQ_PRODUCT_SNAPSHOT (
             SNAPSHOT_ID,MASTER_PRODUCT_ID,RAW_ID,LEGACY_PRODUCT_ID,TASK_ID,JOB_ID,ATTEMPT_ID,
             REQUEST_KEY,COLLECTED_AT,CONTENT_SHA256,NORMALIZED_JSON,TITLE,SHOP_NAME,SHOP_ID,
             AVAILABILITY,PRICE,DISPLAY_PRICE,GROUP_PRICE,DEAL_PRICE,ORIGINAL_PRICE,SALES_NUM,
             SKU_JSON,FIELD_SOURCES,PARSER_VERSION,QUALITY_RULES_VERSION,PARSE_STATUS,PAGE_STATUS,
             QUALITY_STATUS,PREVIOUS_SNAPSHOT_ID,ENTERPRISE_ID,WORKSPACE_ID,ENTERPRISE_PRODUCT_ID
           ) VALUES (:snapshot_id,:master_id,:raw_id,:legacy_product_id,:task_id,:job_id,:attempt_id,
             :request_key,SYSTIMESTAMP,:content_sha,:normalized_json,:title,:shop_name,:shop_id,
             :availability,:price,:display_price,:group_price,:deal_price,:original_price,:sales_num,
             :sku_json,:field_sources,:parser_version,:rules_version,:parse_status,:page_status,
             :quality_status,:previous_id,:enterprise_id,:workspace_id,:enterprise_product_id)""",
        {
            "snapshot_id": snapshot_id, "master_id": master_id, "raw_id": raw_id,
            "legacy_product_id": legacy_product_id, "task_id": body.task_id,
            "job_id": body.job_id, "attempt_id": body.attempt_id,
            "request_key": body.idempotency_key, "content_sha": content_sha256(normalized),
            "normalized_json": canonical_json(normalized), "title": normalized["title"][:512],
            "shop_name": normalized["shop_name"], "shop_id": normalized["shop_id"],
            "availability": normalized["availability"], "price": normalized["price"],
            "display_price": normalized["display_price"], "group_price": normalized["group_price"],
            "deal_price": normalized["deal_price"], "original_price": normalized["original_price"],
            "sales_num": normalized["sales_num"], "sku_json": canonical_json(normalized["sku"]),
            "field_sources": canonical_json(normalized["field_sources"]),
            "parser_version": decision.parser_version, "rules_version": decision.quality_rules_version,
            "parse_status": decision.parse_status, "page_status": decision.page_status,
            "quality_status": decision.quality_status, "previous_id": previous_id,
            "enterprise_id": enterprise_id, "workspace_id": workspace_id,
            "enterprise_product_id": enterprise_product_id,
        },
    )
    quality_result_id = next_id(cur, "SJZQ_SEQ_QUALITY_RESULT")
    cur.execute(
        """INSERT INTO SJZQ_QUALITY_RESULT (
             QUALITY_RESULT_ID,RAW_ID,SNAPSHOT_ID,ACCEPTED,STATUS,PAGE_STATUS,PARSE_STATUS,QUALITY_STATUS,
             PARSER_VERSION,QUALITY_RULES_VERSION,MISSING_FIELDS_JSON,ERROR_CODES_JSON,WARNINGS_JSON,ENTERPRISE_ID,WORKSPACE_ID
           ) VALUES (:id,:raw_id,:snapshot_id,1,:status,:page_status,:parse_status,:quality_status,
             :parser_version,:rules_version,'[]','[]',:warnings,:enterprise_id,:workspace_id)""",
        {
            "id": quality_result_id, "raw_id": raw_id, "snapshot_id": snapshot_id,
            "status": "warning" if decision.warnings else "passed",
            "page_status": decision.page_status, "parse_status": decision.parse_status,
            "quality_status": decision.quality_status, "parser_version": decision.parser_version,
            "rules_version": decision.quality_rules_version,
            "warnings": canonical_json(list(decision.warnings)),
            "enterprise_id": enterprise_id, "workspace_id": workspace_id,
        },
    )
    for field, source_type in normalized["field_sources"].items():
        provenance_id = next_id(cur, "SJZQ_SEQ_FIELD_PROVENANCE")
        original_source = str((getattr(body, "field_sources", {}) or {}).get(field, source_type))
        transformation = "alias_normalized" if normalize_sources({field: original_source}).get(field) != original_source else None
        cur.execute(
            """INSERT INTO SJZQ_FIELD_PROVENANCE (
                 PROVENANCE_ID,SNAPSHOT_ID,FIELD_NAME,SOURCE_TYPE,SOURCE_REF,TRANSFORMATION
               ) VALUES (:id,:snapshot_id,:field_name,:source_type,:source_ref,:transformation)""",
            {"id": provenance_id, "snapshot_id": snapshot_id, "field_name": field[:64],
             "source_type": source_type[:32], "source_ref": f"raw:{raw_id}",
             "transformation": transformation},
        )
    diff_id = _insert_diff(cur, master_id, snapshot_id, previous_id, diff,
                           enterprise_id, workspace_id, enterprise_product_id)
    cur.execute(
        """UPDATE SJZQ_PRODUCT SET MASTER_PRODUCT_ID=:master_id,SNAPSHOT_ID=:snapshot_id,
                  ENTERPRISE_PRODUCT_ID=:enterprise_product_id
             WHERE PRODUCT_ID=:legacy_id AND ENTERPRISE_ID=:enterprise_id""",
        {"master_id": master_id, "snapshot_id": snapshot_id, "legacy_id": legacy_product_id,
         "enterprise_product_id": enterprise_product_id, "enterprise_id": enterprise_id},
    )
    commit(cur, daily_reservation.reservation_id)
    commit(cur, storage_reservation.reservation_id)
    return ObservationResult(
        master_id, snapshot_id, raw_id, quality_result_id, diff_id, previous_id, diff.changed_fields,
        enterprise_product_id
    )


def _insert_diff(
    cur: Any,
    master_id: int,
    snapshot_id: int,
    previous_id: int | None,
    diff: SnapshotDiff,
    enterprise_id: int = 1,
    workspace_id: int = 1,
    enterprise_product_id: int | None = None,
) -> int:
    diff_id = next_id(cur, "SJZQ_SEQ_SNAPSHOT_DIFF")
    cur.execute(
        """INSERT INTO SJZQ_SNAPSHOT_DIFF (
             DIFF_ID,SNAPSHOT_ID,PREVIOUS_SNAPSHOT_ID,MASTER_PRODUCT_ID,CHANGED_FIELDS_JSON,
             PRICE_CHANGED,SALES_CHANGED,SKU_CHANGED,AVAILABILITY_CHANGED,TITLE_CHANGED,SHOP_CHANGED,
             ENTERPRISE_ID,WORKSPACE_ID,ENTERPRISE_PRODUCT_ID
           ) VALUES (:id,:snapshot_id,:previous_id,:master_id,:changes,:price,:sales,:sku,
             :availability,:title,:shop,:enterprise_id,:workspace_id,:enterprise_product_id)""",
        {
            "id": diff_id, "snapshot_id": snapshot_id, "previous_id": previous_id,
            "master_id": master_id, "changes": canonical_json(diff.changes),
            "price": int(diff.changed("price")), "sales": int(diff.changed("sales")),
            "sku": int(diff.changed("sku")), "availability": int(diff.changed("availability")),
            "title": int(diff.changed("title")), "shop": int(diff.changed("shop")),
            "enterprise_id": enterprise_id, "workspace_id": workspace_id,
            "enterprise_product_id": enterprise_product_id,
        },
    )
    return diff_id

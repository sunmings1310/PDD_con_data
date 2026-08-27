"""Read-only Phase 4 management queries.

All growing collections are paged by Oracle.  This module deliberately owns
only query/response shaping; the Phase 1--3 write contracts remain untouched.
"""
from __future__ import annotations

import json
from typing import Any

from server.db import row_as_dict, rows_as_dicts


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _page(cur: Any, count_sql: str, select_sql: str, params: dict[str, Any], page: int, limit: int) -> dict:
    cur.execute(count_sql, params)
    total_row = cur.fetchone()
    total = int(total_row[0] or 0) if total_row else 0
    page_params = {**params, "offset": (page - 1) * limit, "limit": limit}
    cur.execute(select_sql, page_params)
    return {"items": rows_as_dicts(cur), "total": total, "page": page, "limit": limit}


def list_quarantines(cur: Any, *, page: int, limit: int, filters: dict[str, Any], tenant: Any | None = None) -> dict:
    where = ["1=1"]
    params: dict[str, Any] = _tenant_binds(tenant)
    if tenant is not None: where.extend(["q.ENTERPRISE_ID=:enterprise_id", "q.WORKSPACE_ID=:workspace_id"])
    mapping = {
        "status": "q.STATUS=:status", "task_id": "q.TASK_ID=:task_id", "job_id": "q.JOB_ID=:job_id",
        "parser_version": "q.PARSER_VERSION=:parser_version",
        "quality_rules_version": "q.QUALITY_RULES_VERSION=:quality_rules_version",
    }
    for key, predicate in mapping.items():
        if filters.get(key) is not None:
            where.append(predicate); params[key] = filters[key]
    if filters.get("start_at") is not None:
        where.append("q.COLLECTED_AT>=:start_at"); params["start_at"] = filters["start_at"]
    if filters.get("end_at") is not None:
        where.append("q.COLLECTED_AT<:end_at"); params["end_at"] = filters["end_at"]
    if filters.get("failure_reason"):
        where.append("LOWER(q.FAILURE_REASON) LIKE :failure_reason")
        params["failure_reason"] = f"%{str(filters['failure_reason']).lower()}%"
    if filters.get("error_code"):
        # Stored as a canonical JSON string array. Quoting the needle preserves
        # exact member semantics (SKU_INVALID does not match SKU_INVALID_PRICE).
        where.append("DBMS_LOB.INSTR(q.ERROR_CODES_JSON,:error_code)>0")
        params["error_code"] = json.dumps(str(filters["error_code"]), ensure_ascii=False)
    evidence_platform = "JSON_VALUE(q.EVIDENCE_JSON,'$.platform_code' RETURNING VARCHAR2(32))"
    evidence_identity = "JSON_VALUE(q.EVIDENCE_JSON,'$.platform_product_id' RETURNING VARCHAR2(128))"
    platform_expr = f"COALESCE(m.PLATFORM_CODE,{evidence_platform})"
    identity_expr = f"COALESCE(m.PLATFORM_PRODUCT_ID,{evidence_identity})"
    if filters.get("platform"):
        where.append(f"{platform_expr}=:platform"); params["platform"] = filters["platform"]
    if filters.get("product_identity"):
        where.append(f"{identity_expr}=:product_identity"); params["product_identity"] = filters["product_identity"]
    joins = f""" FROM SJZQ_DATA_QUARANTINE q LEFT JOIN SJZQ_PRODUCT_MASTER m
                   ON m.MASTER_PRODUCT_ID=q.MASTER_PRODUCT_ID
                   OR (q.MASTER_PRODUCT_ID IS NULL AND m.PLATFORM_CODE={evidence_platform}
                       AND m.PLATFORM_PRODUCT_ID={evidence_identity}) """
    predicate = " WHERE " + " AND ".join(where)
    result = _page(
        cur, "SELECT COUNT(*)" + joins + predicate,
        f"""SELECT q.QUARANTINE_ID,q.STATUS,q.FAILURE_REASON,q.ERROR_CODES_JSON,q.ERROR_MESSAGE,
                   q.COLLECTED_AT,q.CREATE_TIME,q.TASK_ID,q.JOB_ID,q.ATTEMPT_ID,q.RAW_ID,
                   q.QUALITY_RESULT_ID,COALESCE(q.MASTER_PRODUCT_ID,m.MASTER_PRODUCT_ID) MASTER_PRODUCT_ID,
                   q.PARSER_VERSION,q.QUALITY_RULES_VERSION,
                   {platform_expr} PLATFORM_CODE,{identity_expr} PLATFORM_PRODUCT_ID
              {joins} {predicate}
             ORDER BY q.COLLECTED_AT DESC,q.QUARANTINE_ID DESC
             OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY""", params, page, limit,
    )
    for item in result["items"]:
        item["error_codes"] = _json(item.pop("error_codes_json", None), [])
    return result


def quarantine_detail(cur: Any, quarantine_id: int, tenant: Any | None = None) -> dict | None:
    if not _owns(cur, "SJZQ_DATA_QUARANTINE", "QUARANTINE_ID", quarantine_id, tenant): return None
    cur.execute(
        """SELECT q.*,r.REQUEST_KEY RAW_REQUEST_KEY,r.DEVICE_ID,r.SOURCE_TYPE,r.PAYLOAD_SHA256,
                  r.RAW_JSON,r.COLLECTED_AT RAW_COLLECTED_AT,
                  qr.ACCEPTED,qr.STATUS QUALITY_RESULT_STATUS,qr.PAGE_STATUS,qr.PARSE_STATUS,
                  qr.QUALITY_STATUS,qr.MISSING_FIELDS_JSON,qr.ERROR_CODES_JSON QUALITY_ERROR_CODES_JSON,
                  qr.WARNINGS_JSON,qr.PARSER_VERSION QUALITY_PARSER_VERSION,
                  qr.QUALITY_RULES_VERSION QUALITY_RULES_VERSION_ACTUAL,
                  m.PLATFORM_CODE,m.PLATFORM_PRODUCT_ID,
                  COALESCE(q.MASTER_PRODUCT_ID,m.MASTER_PRODUCT_ID) LINKED_MASTER_PRODUCT_ID,
                  t.TASK_NAME,j.STATUS JOB_STATUS,
                  a.STATUS ATTEMPT_STATUS,a.DEVICE_ID ATTEMPT_DEVICE_ID,a.TRACE_ID,a.ERROR_CLASS,
                  a.ERROR_CODE ATTEMPT_ERROR_CODE,a.ERROR_MESSAGE ATTEMPT_ERROR_MESSAGE,
                  d.DEVICE_KEY,d.DEVICE_NAME
             FROM SJZQ_DATA_QUARANTINE q
             JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=q.RAW_ID
             JOIN SJZQ_QUALITY_RESULT qr ON qr.QUALITY_RESULT_ID=q.QUALITY_RESULT_ID
             LEFT JOIN SJZQ_PRODUCT_MASTER m ON m.MASTER_PRODUCT_ID=q.MASTER_PRODUCT_ID
                  OR (q.MASTER_PRODUCT_ID IS NULL
                      AND m.PLATFORM_CODE=JSON_VALUE(q.EVIDENCE_JSON,'$.platform_code' RETURNING VARCHAR2(32))
                      AND m.PLATFORM_PRODUCT_ID=JSON_VALUE(q.EVIDENCE_JSON,'$.platform_product_id' RETURNING VARCHAR2(128)))
             LEFT JOIN SJZQ_TASK t ON t.TASK_ID=q.TASK_ID
             LEFT JOIN SJZQ_COLLECTION_JOB j ON j.JOB_ID=q.JOB_ID
             LEFT JOIN SJZQ_COLLECTION_ATTEMPT a ON a.ATTEMPT_ID=q.ATTEMPT_ID
             LEFT JOIN SJZQ_DEVICE d ON d.DEVICE_ID=COALESCE(a.DEVICE_ID,r.DEVICE_ID)
            WHERE q.QUARANTINE_ID=:id""", {"id": quarantine_id})
    row = row_as_dict(cur)
    if not row:
        return None
    raw = _json(row.pop("raw_json", None), {})
    evidence = _json(row.pop("evidence_json", None), {})
    row["platform_code"] = row.get("platform_code") or evidence.get("platform_code")
    row["platform_product_id"] = row.get("platform_product_id") or evidence.get("platform_product_id")
    row["master_product_id"] = row.pop("linked_master_product_id", None) or row.get("master_product_id")
    row["raw_data"] = raw
    row["field_sources"] = raw.get("field_sources") or {}
    row["evidence"] = evidence
    row["error_codes"] = _json(row.pop("error_codes_json", None), [])
    row["quality_gate"] = {
        "quality_result_id": row.get("quality_result_id"), "accepted": bool(row.pop("accepted", 0)),
        "status": row.pop("quality_result_status", None), "page_status": row.pop("page_status", None),
        "parse_status": row.pop("parse_status", None), "quality_status": row.pop("quality_status", None),
        "missing_fields": _json(row.pop("missing_fields_json", None), []),
        "error_codes": _json(row.pop("quality_error_codes_json", None), []),
        "warnings": _json(row.pop("warnings_json", None), []),
        "parser_version": row.pop("quality_parser_version", None),
        "quality_rules_version": row.pop("quality_rules_version_actual", None),
    }
    return row


def list_snapshots(cur: Any, master_product_id: int, *, page: int, limit: int, tenant: Any | None = None) -> dict:
    if tenant is not None:
        cur.execute("""SELECT IDENTITY_ID FROM SJZQ_ENTERPRISE_PRODUCT
                        WHERE ENTERPRISE_PRODUCT_ID=:resource_id AND ENTERPRISE_ID=:enterprise_id""",
                    {"resource_id": master_product_id, "enterprise_id": tenant.enterprise_id})
        owned = cur.fetchone()
        if not owned: return {"product": None, "items": [], "total": 0, "page": page, "limit": limit}
        master_product_id = int(owned[0])
    cur.execute("""SELECT MASTER_PRODUCT_ID,PLATFORM_CODE,PLATFORM_PRODUCT_ID,STATUS,FIRST_SEEN_AT,LAST_SEEN_AT
                     FROM SJZQ_PRODUCT_MASTER WHERE MASTER_PRODUCT_ID=:master_id""", {"master_id": master_product_id})
    product = row_as_dict(cur)
    if not product:
        return {"product": None, "items": [], "total": 0, "page": page, "limit": limit}
    params = {"master_id": master_product_id, **_tenant_binds(tenant)}
    tenant_where = " AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id" if tenant is not None else ""
    result = _page(cur,
        "SELECT COUNT(*) FROM SJZQ_PRODUCT_SNAPSHOT WHERE MASTER_PRODUCT_ID=:master_id" + tenant_where,
        """SELECT s.SNAPSHOT_ID,s.MASTER_PRODUCT_ID,s.RAW_ID,s.LEGACY_PRODUCT_ID,s.TASK_ID,s.JOB_ID,
                  s.ATTEMPT_ID,s.REQUEST_KEY,s.COLLECTED_AT,s.TITLE,s.SHOP_NAME,s.SHOP_ID,s.AVAILABILITY,
                  s.PRICE,s.DISPLAY_PRICE,s.GROUP_PRICE,s.DEAL_PRICE,s.ORIGINAL_PRICE,s.SALES_NUM,s.SKU_JSON,
                  s.PARSER_VERSION,s.QUALITY_RULES_VERSION,s.PARSE_STATUS,s.PAGE_STATUS,s.QUALITY_STATUS,
                  s.PREVIOUS_SNAPSHOT_ID,m.PLATFORM_CODE,m.PLATFORM_PRODUCT_ID,
                  d.DIFF_ID,d.CHANGED_FIELDS_JSON,d.PRICE_CHANGED,d.SALES_CHANGED,d.SKU_CHANGED,
                  d.AVAILABILITY_CHANGED,d.TITLE_CHANGED,d.SHOP_CHANGED
             FROM SJZQ_PRODUCT_SNAPSHOT s
             JOIN SJZQ_PRODUCT_MASTER m ON m.MASTER_PRODUCT_ID=s.MASTER_PRODUCT_ID
             LEFT JOIN SJZQ_SNAPSHOT_DIFF d ON d.SNAPSHOT_ID=s.SNAPSHOT_ID
            WHERE s.MASTER_PRODUCT_ID=:master_id""" + (" AND s.ENTERPRISE_ID=:enterprise_id AND s.WORKSPACE_ID=:workspace_id" if tenant is not None else "") + """
            ORDER BY s.COLLECTED_AT DESC,s.SNAPSHOT_ID DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY""", params, page, limit)
    ids = [int(x["snapshot_id"]) for x in result["items"]]
    provenance: dict[int, list[dict]] = {i: [] for i in ids}
    if ids:
        binds = ",".join(f":sid{i}" for i in range(len(ids)))
        cur.execute(f"""SELECT SNAPSHOT_ID,FIELD_NAME,SOURCE_TYPE,SOURCE_REF,TRANSFORMATION
                          FROM SJZQ_FIELD_PROVENANCE WHERE SNAPSHOT_ID IN ({binds})
                         ORDER BY SNAPSHOT_ID,FIELD_NAME""", {f"sid{i}": v for i, v in enumerate(ids)})
        for source in rows_as_dicts(cur):
            provenance[int(source["snapshot_id"])].append(source)
    for item in result["items"]:
        item["sku"] = _json(item.pop("sku_json", None), None)
        item["difference"] = {
            "diff_id": item.pop("diff_id", None),
            "changes": _json(item.pop("changed_fields_json", None), {}),
            "price_changed": bool(item.pop("price_changed", 0)),
            "sales_changed": bool(item.pop("sales_changed", 0)),
            "sku_changed": bool(item.pop("sku_changed", 0)),
            "availability_changed": bool(item.pop("availability_changed", 0)),
            "title_changed": bool(item.pop("title_changed", 0)),
            "shop_changed": bool(item.pop("shop_changed", 0)),
        }
        item["provenance"] = provenance[int(item["snapshot_id"])]
    result["product"] = product
    return result


def quality_metrics(cur: Any, *, start_at: Any = None, end_at: Any = None, platform: str | None = None, tenant: Any | None = None) -> dict:
    where = ["1=1"]
    params: dict[str, Any] = _tenant_binds(tenant)
    if tenant is not None: where.extend(["q.ENTERPRISE_ID=:enterprise_id", "q.WORKSPACE_ID=:workspace_id"])
    if start_at is not None: where.append("r.COLLECTED_AT>=:start_at"); params["start_at"] = start_at
    if end_at is not None: where.append("r.COLLECTED_AT<:end_at"); params["end_at"] = end_at
    if platform:
        where.append("JSON_VALUE(r.RAW_JSON,'$.platform_code' RETURNING VARCHAR2(32))=:platform")
        params["platform"] = platform
    predicate = " AND ".join(where)
    parser_expr = "(DBMS_LOB.INSTR(q.ERROR_CODES_JSON,'\"PARSE_FAILED\"')>0 OR DBMS_LOB.INSTR(q.ERROR_CODES_JSON,'\"PARSE_NOT_ATTEMPTED\"')>0)"
    cur.execute(f"""SELECT COUNT(*) TOTAL_COUNT,SUM(CASE WHEN q.ACCEPTED=1 THEN 1 ELSE 0 END) ACCEPTED_COUNT,
                   SUM(CASE WHEN q.ACCEPTED=0 THEN 1 ELSE 0 END) QUARANTINE_COUNT,
                   SUM(CASE WHEN {parser_expr} THEN 1 ELSE 0 END) PARSER_FAILURE_COUNT,
                   SUM(CASE WHEN q.PARSE_STATUS='failed' THEN 1 ELSE 0 END) PARSE_STATUS_FAILED_COUNT,
                   SUM(CASE WHEN DBMS_LOB.INSTR(q.MISSING_FIELDS_JSON,'\"platform_code\"')>0
                                  OR DBMS_LOB.INSTR(q.MISSING_FIELDS_JSON,'\"platform_product_id\"')>0
                            THEN 1 ELSE 0 END) IDENTITY_MISSING_COUNT,
                   SUM(CASE WHEN DBMS_LOB.INSTR(q.MISSING_FIELDS_JSON,'\"title\"')>0 THEN 1 ELSE 0 END) TITLE_MISSING_COUNT,
                   SUM(CASE WHEN DBMS_LOB.INSTR(q.MISSING_FIELDS_JSON,'\"price\"')>0 THEN 1 ELSE 0 END) PRICE_MISSING_COUNT,
                   SUM(CASE WHEN DBMS_LOB.INSTR(q.ERROR_CODES_JSON,'\"SKU_INVALID_')>0 THEN 1 ELSE 0 END) SKU_ABNORMAL_COUNT
              FROM SJZQ_QUALITY_RESULT q JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=q.RAW_ID WHERE {predicate}""", params)
    overall = row_as_dict(cur) or {}
    total = int(overall.get("total_count") or 0)
    def rate(key: str) -> float: return round(int(overall.get(key) or 0) / total, 6) if total else 0.0
    overall.update({"quality_pass_rate": rate("accepted_count"), "quarantine_rate": rate("quarantine_count"),
                    "parser_failure_rate": rate("parser_failure_count"), "price_missing_rate": rate("price_missing_count"),
                    "sku_abnormal_rate": rate("sku_abnormal_count")})
    overall["sku_anomaly_rate"] = overall["sku_abnormal_rate"]
    cur.execute(f"""SELECT q.PARSER_VERSION VERSION,COUNT(*) TOTAL_COUNT,
                   SUM(CASE WHEN q.ACCEPTED=1 THEN 1 ELSE 0 END) ACCEPTED_COUNT,
                   SUM(CASE WHEN q.ACCEPTED=0 THEN 1 ELSE 0 END) QUARANTINE_COUNT,
                   SUM(CASE WHEN {parser_expr} THEN 1 ELSE 0 END) PARSER_FAILURE_COUNT
              FROM SJZQ_QUALITY_RESULT q JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=q.RAW_ID WHERE {predicate}
             GROUP BY q.PARSER_VERSION ORDER BY TOTAL_COUNT DESC,q.PARSER_VERSION""", params)
    by_parser = rows_as_dicts(cur)
    cur.execute(f"""SELECT q.QUALITY_RULES_VERSION VERSION,COUNT(*) TOTAL_COUNT,
                   SUM(CASE WHEN q.ACCEPTED=1 THEN 1 ELSE 0 END) ACCEPTED_COUNT,
                   SUM(CASE WHEN q.ACCEPTED=0 THEN 1 ELSE 0 END) QUARANTINE_COUNT
              FROM SJZQ_QUALITY_RESULT q JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=q.RAW_ID WHERE {predicate}
             GROUP BY q.QUALITY_RULES_VERSION ORDER BY TOTAL_COUNT DESC,q.QUALITY_RULES_VERSION""", params)
    by_rules = rows_as_dicts(cur)
    cur.execute(f"""SELECT jt.ERROR_CODE,COUNT(*) ERROR_COUNT
              FROM SJZQ_QUALITY_RESULT q JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=q.RAW_ID
              CROSS APPLY JSON_TABLE(q.ERROR_CODES_JSON,'$[*]' COLUMNS (ERROR_CODE VARCHAR2(128) PATH '$')) jt
             WHERE {predicate} GROUP BY jt.ERROR_CODE ORDER BY ERROR_COUNT DESC,jt.ERROR_CODE
             FETCH FIRST 10 ROWS ONLY""", params)
    errors = rows_as_dicts(cur)
    for groups in (by_parser, by_rules):
        for item in groups:
            n = int(item.get("total_count") or 0)
            item["quality_pass_rate"] = round(int(item.get("accepted_count") or 0) / n, 6) if n else 0.0
            item["quarantine_rate"] = round(int(item.get("quarantine_count") or 0) / n, 6) if n else 0.0
            if "parser_failure_count" in item:
                item["parser_failure_rate"] = round(int(item.get("parser_failure_count") or 0) / n, 6) if n else 0.0
    anomalies = []
    if total and overall["quarantine_rate"] >= .2:
        anomalies.append({"type": "quarantine_rate_high", "title": "隔离率偏高", "message": "当前筛选范围内隔离率达到阈值", "rate": overall["quarantine_rate"]})
    if total and overall["parser_failure_rate"] >= .1:
        anomalies.append({"type": "parser_failure_rate_high", "title": "解析失败率偏高", "message": "当前筛选范围内解析失败率达到阈值", "rate": overall["parser_failure_rate"]})
    for item in by_parser:
        if int(item["total_count"]) >= 5 and item["quality_pass_rate"] + .2 < overall["quality_pass_rate"]:
            anomalies.append({"type": "parser_version_degraded", "title": "Parser 版本质量下降",
                              "message": f"{item['version']} 的通过率明显低于整体", "version": item["version"], "rate": item["quality_pass_rate"]})
    for item in errors:
        item["count"] = int(item.get("error_count") or 0)
        item["rate"] = round(int(item.get("error_count") or 0) / total, 6) if total else 0.0
    if errors and total and int(errors[0]["error_count"]) >= 3 and errors[0]["rate"] >= .3:
        anomalies.append({"type": "error_code_concentrated", "title": "错误类型集中",
                          "message": f"错误 {errors[0]['error_code']} 集中出现", **errors[0]})
    missing_rates = []
    for field, key in (("identity", "identity_missing_count"), ("title", "title_missing_count"), ("price", "price_missing_count")):
        count = int(overall.get(key) or 0)
        missing_rates.append({"field": field, "count": count, "missing_count": count, "total": total,
                              "rate": round(count / total, 6) if total else 0.0})
    for item in (*by_parser, *by_rules):
        item["pass_count"] = int(item.get("accepted_count") or 0)
    top = {
        "total_collections": total, "pass_count": int(overall.get("accepted_count") or 0),
        "quarantine_count": int(overall.get("quarantine_count") or 0),
        "quality_pass_rate": overall["quality_pass_rate"], "parser_failure_rate": overall["parser_failure_rate"],
        "sku_anomaly_rate": overall["sku_abnormal_rate"], "price_missing_rate": overall["price_missing_rate"],
    }
    return {**top, "overall": overall, "key_field_missing_rates": missing_rates,
            "by_parser_version": by_parser, "by_quality_rules_version": by_rules,
            "top_error_codes": errors, "anomalies": anomalies}


def _simple_page(cur: Any, table: str, id_col: str, where_col: str, value: int, select_cols: str,
                 order: str, page: int, limit: int) -> dict:
    params = {"id": value}
    return _page(cur, f"SELECT COUNT(*) FROM {table} WHERE {where_col}=:id",
                 f"SELECT {select_cols} FROM {table} WHERE {where_col}=:id ORDER BY {order} OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY",
                 params, page, limit)


def _resource_ref(value: Any, reason: str) -> dict[str, Any]:
    if value is None:
        return {"resource_id": None, "availability": "unavailable", "reason": reason}
    return {"resource_id": int(value), "availability": "available", "reason": None}


def _result_resources(row: dict[str, Any], result_kind: str) -> dict[str, dict[str, Any]]:
    is_legacy = result_kind == "legacy_product"
    is_quarantine = result_kind == "quarantine" or row.get("quarantine_id") is not None
    missing_strict = "not_captured_by_strict_protocol" if is_legacy else "not_recorded"
    return {
        "snapshot": _resource_ref(
            row.get("snapshot_id"),
            "no_normal_snapshot_for_quarantine" if is_quarantine else missing_strict,
        ),
        "master_product": _resource_ref(row.get("master_product_id"), "product_identity_unavailable"),
        "enterprise_product": _resource_ref(
            row.get("enterprise_product_id"), "tenant_product_identity_unavailable"
        ),
        "product": _resource_ref(
            row.get("product_id"),
            "no_normal_product_for_quarantine" if is_quarantine else "library_product_unavailable",
        ),
        "raw": _resource_ref(row.get("raw_id"), missing_strict),
        "quality": _resource_ref(row.get("quality_result_id"), missing_strict),
        "quarantine": _resource_ref(
            row.get("quarantine_id"),
            "not_applicable_for_accepted_snapshot" if result_kind == "snapshot" else missing_strict,
        ),
    }


def _shape_task_result(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("result_kind") or "legacy_product")
    library_status = str(row.get("library_status") or "unavailable").lower()
    if library_status not in {"draft", "saved"}:
        library_status = "unavailable"
    product_id = int(row["product_id"]) if row.get("product_id") is not None else None
    row["result_kind"] = kind
    row["result_id"] = int(
        row.get("snapshot_id") or row.get("quarantine_id") or row.get("product_id")
    )
    row["resources"] = _result_resources(row, kind)
    row["library"] = {
        "status": library_status,
        "product_id": product_id,
        "is_saved": library_status == "saved",
        "can_save": library_status == "draft" and product_id is not None,
        "reason": "normal_product_not_created" if kind == "quarantine" else (
            "library_product_unavailable" if product_id is None else None
        ),
    }
    row["library_status"] = library_status
    return row


def task_results(cur: Any, task_id: int, page: int, limit: int, tenant: Any | None = None) -> dict:
    """Return every Task business result without requiring library persistence.

    Accepted Snapshot, Quarantine and pre-strict/legacy Product facts remain
    separate rows.  Missing resource identities are reported as unavailable by
    ``_shape_task_result`` and are never inferred from another ID type.
    """
    if not _owns(cur, "SJZQ_TASK", "TASK_ID", task_id, tenant):
        return {"items": [], "total": 0, "page": page, "limit": limit}
    params = {"task_id": task_id, **_tenant_binds(tenant)}
    tenant_snapshot = (
        " AND s.ENTERPRISE_ID=:enterprise_id AND s.WORKSPACE_ID=:workspace_id"
        if tenant is not None else ""
    )
    tenant_quarantine = (
        " AND q.ENTERPRISE_ID=:enterprise_id AND q.WORKSPACE_ID=:workspace_id"
        if tenant is not None else ""
    )
    tenant_product = (
        " AND p.ENTERPRISE_ID=:enterprise_id AND p.WORKSPACE_ID=:workspace_id"
        if tenant is not None else ""
    )
    joined_tenant_product = (
        " AND p.ENTERPRISE_ID=s.ENTERPRISE_ID AND p.WORKSPACE_ID=s.WORKSPACE_ID"
        if tenant is not None else ""
    )
    joined_tenant_quality = (
        " AND qr.ENTERPRISE_ID=s.ENTERPRISE_ID AND qr.WORKSPACE_ID=s.WORKSPACE_ID"
        if tenant is not None else ""
    )
    duplicate_tenant = (
        " AND sx.ENTERPRISE_ID=p.ENTERPRISE_ID AND sx.WORKSPACE_ID=p.WORKSPACE_ID"
        if tenant is not None else ""
    )
    facts_sql = f"""
        SELECT 'snapshot' RESULT_KIND,s.TASK_ID,s.JOB_ID,s.ATTEMPT_ID,s.SNAPSHOT_ID,
               s.MASTER_PRODUCT_ID,s.ENTERPRISE_PRODUCT_ID,p.PRODUCT_ID,
               CAST(NULL AS NUMBER) QUARANTINE_ID,s.RAW_ID,qr.QUALITY_RESULT_ID,
               NVL(p.LIBRARY_STATUS,'unavailable') LIBRARY_STATUS,s.QUALITY_STATUS,
               COALESCE(p.SELL_NAME,s.TITLE) PLATFORM_TITLE,p.PRODUCT_NAME CANONICAL_NAME,
               p.SPEC_TEXT PRODUCT_ATTRIBUTE_SPEC,p.BRAND,p.APPROVAL_NO APPROVAL_NUMBER,
               p.MANUFACTURER,CAST(NULL AS VARCHAR2(2000)) FAILURE_REASON,
               s.COLLECTED_AT
          FROM SJZQ_PRODUCT_SNAPSHOT s
          LEFT JOIN SJZQ_QUALITY_RESULT qr ON qr.RAW_ID=s.RAW_ID{joined_tenant_quality}
          LEFT JOIN SJZQ_PRODUCT p ON p.PRODUCT_ID=s.LEGACY_PRODUCT_ID
               AND NVL(p.IS_DELETED,0)=0{joined_tenant_product}
         WHERE s.TASK_ID=:task_id{tenant_snapshot}
        UNION ALL
        SELECT 'quarantine' RESULT_KIND,q.TASK_ID,q.JOB_ID,q.ATTEMPT_ID,
               CAST(NULL AS NUMBER) SNAPSHOT_ID,q.MASTER_PRODUCT_ID,q.ENTERPRISE_PRODUCT_ID,
               CAST(NULL AS NUMBER) PRODUCT_ID,q.QUARANTINE_ID,q.RAW_ID,q.QUALITY_RESULT_ID,
               'unavailable' LIBRARY_STATUS,'quarantined' QUALITY_STATUS,
               JSON_VALUE(q.EVIDENCE_JSON,'$.title' RETURNING VARCHAR2(512)) PLATFORM_TITLE,
               CAST(NULL AS VARCHAR2(512)) CANONICAL_NAME,
               CAST(NULL AS VARCHAR2(512)) PRODUCT_ATTRIBUTE_SPEC,
               CAST(NULL AS VARCHAR2(128)) BRAND,CAST(NULL AS VARCHAR2(128)) APPROVAL_NUMBER,
               CAST(NULL AS VARCHAR2(256)) MANUFACTURER,q.FAILURE_REASON,q.COLLECTED_AT
          FROM SJZQ_DATA_QUARANTINE q
         WHERE q.TASK_ID=:task_id{tenant_quarantine}
        UNION ALL
        SELECT 'legacy_product' RESULT_KIND,p.TASK_ID,CAST(NULL AS NUMBER) JOB_ID,
               CAST(NULL AS NUMBER) ATTEMPT_ID,CAST(NULL AS NUMBER) SNAPSHOT_ID,
               p.MASTER_PRODUCT_ID,p.ENTERPRISE_PRODUCT_ID,p.PRODUCT_ID,
               CAST(NULL AS NUMBER) QUARANTINE_ID,CAST(NULL AS NUMBER) RAW_ID,
               CAST(NULL AS NUMBER) QUALITY_RESULT_ID,NVL(p.LIBRARY_STATUS,'saved') LIBRARY_STATUS,
               NVL(p.QUALITY_STATUS,'legacy') QUALITY_STATUS,p.SELL_NAME PLATFORM_TITLE,
               p.PRODUCT_NAME CANONICAL_NAME,p.SPEC_TEXT PRODUCT_ATTRIBUTE_SPEC,p.BRAND,
               p.APPROVAL_NO APPROVAL_NUMBER,p.MANUFACTURER,
               CAST(NULL AS VARCHAR2(2000)) FAILURE_REASON,p.COLLECT_TIME COLLECTED_AT
          FROM SJZQ_PRODUCT p
         WHERE p.TASK_ID=:task_id AND NVL(p.IS_DELETED,0)=0{tenant_product}
           AND NOT EXISTS (
               SELECT 1 FROM SJZQ_PRODUCT_SNAPSHOT sx
                WHERE sx.LEGACY_PRODUCT_ID=p.PRODUCT_ID{duplicate_tenant}
           )
    """
    result = _page(
        cur,
        f"SELECT COUNT(*) FROM ({facts_sql})",
        f"""SELECT RESULT_KIND,TASK_ID,JOB_ID,ATTEMPT_ID,SNAPSHOT_ID,MASTER_PRODUCT_ID,
                    ENTERPRISE_PRODUCT_ID,PRODUCT_ID,QUARANTINE_ID,RAW_ID,QUALITY_RESULT_ID,
                    LIBRARY_STATUS,QUALITY_STATUS,PLATFORM_TITLE,CANONICAL_NAME,
                    PRODUCT_ATTRIBUTE_SPEC,BRAND,APPROVAL_NUMBER,MANUFACTURER,
                    FAILURE_REASON,COLLECTED_AT
               FROM ({facts_sql})
              ORDER BY COLLECTED_AT DESC NULLS LAST,
                       COALESCE(SNAPSHOT_ID,QUARANTINE_ID,PRODUCT_ID) DESC
              OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY""",
        params,
        page,
        limit,
    )
    result["items"] = [_shape_task_result(item) for item in result["items"]]
    return result


def _shape_task_result_resource(kind: str, resource_id: int, row: dict[str, Any]) -> dict[str, Any]:
    details = dict(row)
    if "raw_json" in details:
        details["raw_data"] = _json(details.pop("raw_json", None), {})
    for source, target, default in (
        ("normalized_json", "normalized", {}),
        ("sku_json", "sku", None),
        ("field_sources", "field_sources", {}),
        ("missing_fields_json", "missing_fields", []),
        ("error_codes_json", "error_codes", []),
        ("warnings_json", "warnings", []),
    ):
        if source in details:
            value = details.pop(source, None)
            details[target] = _json(value, default)
    synthetic = {**row, "result_kind": kind}
    if synthetic.get("product_id") is None and synthetic.get("legacy_product_id") is not None:
        synthetic["product_id"] = synthetic["legacy_product_id"]
    if kind == "raw": synthetic["raw_id"] = resource_id
    elif kind == "quality": synthetic["quality_result_id"] = resource_id
    elif kind == "snapshot": synthetic["snapshot_id"] = resource_id
    elif kind == "quarantine": synthetic["quarantine_id"] = resource_id
    return {
        "resource_kind": kind,
        "resource_id": int(resource_id),
        "task_id": int(row["task_id"]),
        "snapshot_id": synthetic.get("snapshot_id"),
        "master_product_id": synthetic.get("master_product_id"),
        "enterprise_product_id": synthetic.get("enterprise_product_id"),
        "product_id": synthetic.get("product_id"),
        "quarantine_id": synthetic.get("quarantine_id"),
        "raw_id": synthetic.get("raw_id"),
        "quality_result_id": synthetic.get("quality_result_id"),
        "resources": _result_resources(synthetic, kind),
        "details": details,
    }


def task_result_resource(
    cur: Any,
    task_id: int,
    resource_kind: str,
    resource_id: int,
    tenant: Any | None = None,
) -> dict[str, Any] | None:
    """Read one evidence resource through its owning Task and tenant fence."""
    if resource_kind not in {"snapshot", "raw", "quality", "quarantine"}:
        raise ValueError("unsupported task result resource")
    if not _owns(cur, "SJZQ_TASK", "TASK_ID", task_id, tenant):
        return None
    params = {"resource_id": resource_id, "task_id": task_id, **_tenant_binds(tenant)}
    tenant_r = " AND r.ENTERPRISE_ID=:enterprise_id AND r.WORKSPACE_ID=:workspace_id" if tenant is not None else ""
    tenant_s = " AND s.ENTERPRISE_ID=:enterprise_id AND s.WORKSPACE_ID=:workspace_id" if tenant is not None else ""
    tenant_qr = " AND qr.ENTERPRISE_ID=:enterprise_id AND qr.WORKSPACE_ID=:workspace_id" if tenant is not None else ""
    tenant_q = " AND q.ENTERPRISE_ID=:enterprise_id AND q.WORKSPACE_ID=:workspace_id" if tenant is not None else ""
    if resource_kind == "raw":
        cur.execute(
            f"""SELECT 'raw' RESOURCE_KIND,r.RAW_ID,r.TASK_ID,r.JOB_ID,r.ATTEMPT_ID,r.DEVICE_ID,
                       r.REQUEST_KEY,r.SOURCE_TYPE,r.PAYLOAD_SHA256,r.RAW_JSON,r.COLLECTED_AT,
                       s.SNAPSHOT_ID,s.MASTER_PRODUCT_ID,s.ENTERPRISE_PRODUCT_ID,s.LEGACY_PRODUCT_ID,
                       qr.QUALITY_RESULT_ID,q.QUARANTINE_ID
                  FROM SJZQ_RAW_COLLECTION r
                  LEFT JOIN SJZQ_QUALITY_RESULT qr ON qr.RAW_ID=r.RAW_ID
                       AND qr.ENTERPRISE_ID=r.ENTERPRISE_ID AND qr.WORKSPACE_ID=r.WORKSPACE_ID
                  LEFT JOIN SJZQ_PRODUCT_SNAPSHOT s ON s.RAW_ID=r.RAW_ID
                       AND s.ENTERPRISE_ID=r.ENTERPRISE_ID AND s.WORKSPACE_ID=r.WORKSPACE_ID
                  LEFT JOIN SJZQ_DATA_QUARANTINE q ON q.RAW_ID=r.RAW_ID
                       AND q.ENTERPRISE_ID=r.ENTERPRISE_ID AND q.WORKSPACE_ID=r.WORKSPACE_ID
                 WHERE r.RAW_ID=:resource_id AND r.TASK_ID=:task_id{tenant_r}""",
            params,
        )
        row = row_as_dict(cur)
    elif resource_kind == "quality":
        cur.execute(
            f"""SELECT 'quality' RESOURCE_KIND,qr.QUALITY_RESULT_ID,qr.RAW_ID,r.TASK_ID,
                       r.JOB_ID,r.ATTEMPT_ID,qr.SNAPSHOT_ID,q.QUARANTINE_ID,
                       s.MASTER_PRODUCT_ID,s.ENTERPRISE_PRODUCT_ID,s.LEGACY_PRODUCT_ID,
                       qr.ACCEPTED,qr.STATUS,qr.PAGE_STATUS,qr.PARSE_STATUS,qr.QUALITY_STATUS,
                       qr.PARSER_VERSION,qr.QUALITY_RULES_VERSION,qr.MISSING_FIELDS_JSON,
                       qr.ERROR_CODES_JSON,qr.WARNINGS_JSON,qr.CREATE_TIME
                  FROM SJZQ_QUALITY_RESULT qr
                  JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=qr.RAW_ID
                       AND r.ENTERPRISE_ID=qr.ENTERPRISE_ID AND r.WORKSPACE_ID=qr.WORKSPACE_ID
                  LEFT JOIN SJZQ_PRODUCT_SNAPSHOT s ON s.SNAPSHOT_ID=qr.SNAPSHOT_ID
                       AND s.ENTERPRISE_ID=qr.ENTERPRISE_ID AND s.WORKSPACE_ID=qr.WORKSPACE_ID
                  LEFT JOIN SJZQ_DATA_QUARANTINE q ON q.QUALITY_RESULT_ID=qr.QUALITY_RESULT_ID
                       AND q.ENTERPRISE_ID=qr.ENTERPRISE_ID AND q.WORKSPACE_ID=qr.WORKSPACE_ID
                 WHERE qr.QUALITY_RESULT_ID=:resource_id AND r.TASK_ID=:task_id{tenant_qr}{tenant_r}""",
            params,
        )
        row = row_as_dict(cur)
    elif resource_kind == "snapshot":
        cur.execute(
            f"""SELECT 'snapshot' RESOURCE_KIND,s.SNAPSHOT_ID,s.MASTER_PRODUCT_ID,
                       s.ENTERPRISE_PRODUCT_ID,s.LEGACY_PRODUCT_ID,s.RAW_ID,qr.QUALITY_RESULT_ID,
                       s.TASK_ID,s.JOB_ID,s.ATTEMPT_ID,s.REQUEST_KEY,s.COLLECTED_AT,
                       s.NORMALIZED_JSON,s.TITLE,s.SHOP_NAME,s.SHOP_ID,s.AVAILABILITY,
                       s.PRICE,s.DISPLAY_PRICE,s.GROUP_PRICE,s.DEAL_PRICE,s.ORIGINAL_PRICE,
                       s.SALES_NUM,s.SKU_JSON,s.FIELD_SOURCES,s.PARSER_VERSION,
                       s.QUALITY_RULES_VERSION,s.PARSE_STATUS,s.PAGE_STATUS,s.QUALITY_STATUS,
                       s.PREVIOUS_SNAPSHOT_ID,p.LIBRARY_STATUS
                  FROM SJZQ_PRODUCT_SNAPSHOT s
                  JOIN SJZQ_RAW_COLLECTION r ON r.RAW_ID=s.RAW_ID
                       AND r.ENTERPRISE_ID=s.ENTERPRISE_ID AND r.WORKSPACE_ID=s.WORKSPACE_ID
                  LEFT JOIN SJZQ_QUALITY_RESULT qr ON qr.RAW_ID=s.RAW_ID
                       AND qr.ENTERPRISE_ID=s.ENTERPRISE_ID AND qr.WORKSPACE_ID=s.WORKSPACE_ID
                  LEFT JOIN SJZQ_PRODUCT p ON p.PRODUCT_ID=s.LEGACY_PRODUCT_ID
                       AND p.ENTERPRISE_ID=s.ENTERPRISE_ID AND p.WORKSPACE_ID=s.WORKSPACE_ID
                 WHERE s.SNAPSHOT_ID=:resource_id AND s.TASK_ID=:task_id{tenant_s}{tenant_r}""",
            params,
        )
        row = row_as_dict(cur)
        if row:
            cur.execute(
                f"""SELECT DIFF_ID,PREVIOUS_SNAPSHOT_ID,CHANGED_FIELDS_JSON,PRICE_CHANGED,
                            SALES_CHANGED,SKU_CHANGED,AVAILABILITY_CHANGED,TITLE_CHANGED,SHOP_CHANGED
                       FROM SJZQ_SNAPSHOT_DIFF
                      WHERE SNAPSHOT_ID=:resource_id""",
                {"resource_id": resource_id},
            )
            difference = row_as_dict(cur)
            if difference:
                difference["changes"] = _json(difference.pop("changed_fields_json", None), {})
            row["difference"] = difference
            cur.execute(
                """SELECT FIELD_NAME,SOURCE_TYPE,SOURCE_REF,TRANSFORMATION
                     FROM SJZQ_FIELD_PROVENANCE WHERE SNAPSHOT_ID=:resource_id
                    ORDER BY FIELD_NAME""",
                {"resource_id": resource_id},
            )
            row["provenance"] = rows_as_dicts(cur)
    else:
        cur.execute(
            f"""SELECT q.QUARANTINE_ID,q.MASTER_PRODUCT_ID,q.ENTERPRISE_PRODUCT_ID
                  FROM SJZQ_DATA_QUARANTINE q
                 WHERE q.QUARANTINE_ID=:resource_id AND q.TASK_ID=:task_id{tenant_q}""",
            params,
        )
        binding = cur.fetchone()
        if not binding:
            return None
        row = quarantine_detail(cur, resource_id, tenant=tenant)
        if row:
            # Task result DTOs expose only persisted resource bindings.  The
            # legacy quarantine detail may infer a global Master from evidence
            # for display, but that inference must not become a navigable ID.
            row["master_product_id"] = int(binding[1]) if binding[1] is not None else None
            row["enterprise_product_id"] = int(binding[2]) if binding[2] is not None else None
            row["resource_kind"] = "quarantine"
    if not row:
        return None
    return _shape_task_result_resource(resource_kind, resource_id, row)


def task_jobs(cur: Any, task_id: int, page: int, limit: int, tenant: Any | None = None) -> dict:
    if not _owns(cur, "SJZQ_TASK", "TASK_ID", task_id, tenant): return {"items":[],"total":0,"page":page,"limit":limit}
    cols = "JOB_ID,TASK_ID,TASK_ITEM_ID,DEVICE_ID,JOB_KEY,JOB_TYPE,STATUS,PRIORITY,MAX_ATTEMPTS,ATTEMPT_COUNT,NEXT_RUN_AT,ACTIVE_ATTEMPT_ID,LEASED_AT,LEASE_EXPIRES_AT,LAST_HEARTBEAT_AT,CHECKPOINT_VERSION,RESULT_RECEIPT_KEY,RESULT_PRODUCT_ID,PAUSE_REQUESTED,LAST_ERROR_CLASS,LAST_ERROR_CODE,LAST_ERROR_MESSAGE,CREATE_TIME,UPDATE_TIME"
    result = _simple_page(cur,"SJZQ_COLLECTION_JOB","JOB_ID","TASK_ID",task_id,cols,"CREATE_TIME DESC,JOB_ID DESC",page,limit)
    _attach_business_results(cur, result["items"], "job_id", tenant=tenant)
    return result


def job_attempts(cur: Any, job_id: int, page: int, limit: int, tenant: Any | None = None) -> dict:
    if not _owns(cur, "SJZQ_COLLECTION_JOB", "JOB_ID", job_id, tenant): return {"items":[],"total":0,"page":page,"limit":limit}
    cols = "ATTEMPT_ID,JOB_ID,ATTEMPT_NO,DEVICE_ID,WORKER_ID,TRACE_ID,STATUS,LEASED_AT,STARTED_AT,HEARTBEAT_AT,LEASE_EXPIRES_AT,FINISHED_AT,ERROR_CLASS,ERROR_CODE,ERROR_MESSAGE,RETRYABLE,RETRY_DELAY_SECONDS,START_CHECKPOINT_VERSION,FINAL_CHECKPOINT_VERSION,CREATE_TIME"
    result = _simple_page(cur,"SJZQ_COLLECTION_ATTEMPT","ATTEMPT_ID","JOB_ID",job_id,cols,"ATTEMPT_NO DESC,ATTEMPT_ID DESC",page,limit)
    _attach_business_results(cur, result["items"], "attempt_id", tenant=tenant)
    return result


def _attach_business_results(cur: Any, items: list[dict], key: str, tenant: Any | None = None) -> None:
    """Attach Snapshot/Quarantine facts to a page in one bounded query."""
    if not items:
        return
    ids = [int(item[key]) for item in items]
    by_id: dict[int, list[dict]] = {value: [] for value in ids}
    binds = ",".join(f":bid{i}" for i in range(len(ids)))
    params = {f"bid{i}": value for i, value in enumerate(ids)}
    params.update(_tenant_binds(tenant))
    column = "JOB_ID" if key == "job_id" else "ATTEMPT_ID"
    snapshot_tenant = " AND s.ENTERPRISE_ID=:enterprise_id AND s.WORKSPACE_ID=:workspace_id" if tenant is not None else ""
    quarantine_tenant = " AND q.ENTERPRISE_ID=:enterprise_id AND q.WORKSPACE_ID=:workspace_id" if tenant is not None else ""
    cur.execute(f"""SELECT JOB_ID,ATTEMPT_ID,RESULT_KIND,SNAPSHOT_ID,MASTER_PRODUCT_ID,
                           ENTERPRISE_PRODUCT_ID,PRODUCT_ID,QUARANTINE_ID,RAW_ID,
                           QUALITY_RESULT_ID,LIBRARY_STATUS,QUALITY_STATUS,COLLECTED_AT
                      FROM (
                        SELECT s.JOB_ID,s.ATTEMPT_ID,'snapshot' RESULT_KIND,s.SNAPSHOT_ID,
                               s.MASTER_PRODUCT_ID,s.ENTERPRISE_PRODUCT_ID,s.LEGACY_PRODUCT_ID PRODUCT_ID,
                               CAST(NULL AS NUMBER) QUARANTINE_ID,s.RAW_ID,qr.QUALITY_RESULT_ID,
                               NVL(p.LIBRARY_STATUS,'unavailable') LIBRARY_STATUS,
                               s.QUALITY_STATUS,s.COLLECTED_AT
                          FROM SJZQ_PRODUCT_SNAPSHOT s
                          LEFT JOIN SJZQ_QUALITY_RESULT qr ON qr.RAW_ID=s.RAW_ID
                               AND qr.ENTERPRISE_ID=s.ENTERPRISE_ID AND qr.WORKSPACE_ID=s.WORKSPACE_ID
                          LEFT JOIN SJZQ_PRODUCT p ON p.PRODUCT_ID=s.LEGACY_PRODUCT_ID
                               AND p.ENTERPRISE_ID=s.ENTERPRISE_ID AND p.WORKSPACE_ID=s.WORKSPACE_ID
                         WHERE s.{column} IN ({binds}){snapshot_tenant}
                        UNION ALL
                        SELECT q.JOB_ID,q.ATTEMPT_ID,'quarantine' RESULT_KIND,CAST(NULL AS NUMBER) SNAPSHOT_ID,
                               q.MASTER_PRODUCT_ID,q.ENTERPRISE_PRODUCT_ID,CAST(NULL AS NUMBER) PRODUCT_ID,
                               q.QUARANTINE_ID,q.RAW_ID,q.QUALITY_RESULT_ID,
                               'unavailable' LIBRARY_STATUS,'quarantined' QUALITY_STATUS,q.COLLECTED_AT
                          FROM SJZQ_DATA_QUARANTINE q
                         WHERE q.{column} IN ({binds}){quarantine_tenant}
                      ) ORDER BY COLLECTED_AT DESC,
                         COALESCE(SNAPSHOT_ID,QUARANTINE_ID) DESC""", params)
    for fact in rows_as_dicts(cur):
        _shape_task_result(fact)
        owner = fact.get(key)
        if owner is not None and int(owner) in by_id:
            by_id[int(owner)].append(fact)
    for item in items:
        item["business_results"] = by_id[int(item[key])]


EVENT_COLS = "EVENT_ID,EVENT_KEY,TASK_ID,JOB_ID,ATTEMPT_ID,DEVICE_ID,WORKER_ID,TRACE_ID,EVENT_TYPE,OLD_STATUS,NEW_STATUS,ERROR_CLASS,ERROR_CODE,DETAIL_JSON,CREATE_TIME"


def attempt_events(cur: Any, attempt_id: int, page: int, limit: int, tenant: Any | None = None) -> dict:
    if not _owns(cur, "SJZQ_COLLECTION_ATTEMPT", "ATTEMPT_ID", attempt_id, tenant): return {"items":[],"total":0,"page":page,"limit":limit}
    result = _simple_page(cur,"SJZQ_JOB_EVENT","EVENT_ID","ATTEMPT_ID",attempt_id,EVENT_COLS,"CREATE_TIME ASC,EVENT_ID ASC",page,limit)
    for x in result["items"]: x["detail"] = _json(x.pop("detail_json", None), {})
    return result


def task_events(cur: Any, task_id: int, page: int, limit: int, tenant: Any | None = None) -> dict:
    if not _owns(cur, "SJZQ_TASK", "TASK_ID", task_id, tenant): return {"items":[],"total":0,"page":page,"limit":limit}
    result = _simple_page(cur,"SJZQ_JOB_EVENT","EVENT_ID","TASK_ID",task_id,EVENT_COLS,"CREATE_TIME ASC,EVENT_ID ASC",page,limit)
    for x in result["items"]: x["detail"] = _json(x.pop("detail_json", None), {})
    return result


def task_trace(cur: Any, task_id: int, tenant: Any | None = None) -> dict | None:
    if not _owns(cur, "SJZQ_TASK", "TASK_ID", task_id, tenant): return None
    cur.execute("SELECT TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,DEVICE_ID,TARGET_COUNT,SUCCESS_COUNT,FAIL_COUNT,ERROR_MSG,START_TIME,END_TIME,CREATE_TIME,UPDATE_TIME FROM SJZQ_TASK WHERE TASK_ID=:id", {"id":task_id})
    task = row_as_dict(cur)
    if not task: return None
    cur.execute("SELECT STATUS,COUNT(*) CNT FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:id GROUP BY STATUS", {"id":task_id})
    task["job_status_counts"] = {str(x[0]).lower(): int(x[1]) for x in cur.fetchall()}
    # Independent scalar counts avoid the Attempt x Snapshot x Quarantine row
    # multiplication that a convenience multi-join would create on large Jobs.
    cur.execute("""SELECT
                    (SELECT COUNT(*) FROM SJZQ_COLLECTION_ATTEMPT a JOIN SJZQ_COLLECTION_JOB j ON j.JOB_ID=a.JOB_ID WHERE j.TASK_ID=:id),
                    (SELECT COUNT(*) FROM SJZQ_PRODUCT_SNAPSHOT WHERE TASK_ID=:id),
                    (SELECT COUNT(*) FROM SJZQ_DATA_QUARANTINE WHERE TASK_ID=:id)
                   FROM DUAL""", {"id":task_id})
    counts = cur.fetchone() or (0,0,0)
    task.update({"attempt_count":int(counts[0] or 0),"snapshot_count":int(counts[1] or 0),"quarantine_count":int(counts[2] or 0)})
    cur.execute("""SELECT ATTEMPT_ID,JOB_ID,DEVICE_ID,TRACE_ID,ERROR_CLASS,ERROR_CODE,ERROR_MESSAGE,FINISHED_AT
                     FROM SJZQ_COLLECTION_ATTEMPT WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:id)
                      AND ERROR_CODE IS NOT NULL ORDER BY COALESCE(FINISHED_AT,CREATE_TIME) DESC,ATTEMPT_ID DESC FETCH FIRST 1 ROWS ONLY""", {"id":task_id})
    task["latest_error"] = row_as_dict(cur)
    return task
def _tenant_binds(tenant: Any | None) -> dict[str, int]:
    if tenant is None:
        return {}
    return {"enterprise_id": int(tenant.enterprise_id), "workspace_id": int(tenant.workspace_id)}


def _owns(cur: Any, table: str, id_column: str, value: int, tenant: Any | None) -> bool:
    if tenant is None:
        return True
    cur.execute(f"SELECT 1 FROM {table} WHERE {id_column}=:resource_id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id",
                {"resource_id": value, **_tenant_binds(tenant)})
    return cur.fetchone() is not None

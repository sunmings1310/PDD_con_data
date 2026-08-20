"""商品上报、图片上传、查询。"""

from __future__ import annotations

import logging
import json
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, Request

from server.auth_util import require_perms, write_op_log
from server.tenant import require_tenant_perms
from server.config import settings
from server.db import get_conn, next_id, row_as_dict, rows_as_dicts
from server.image_filter import is_blocked_license_file, is_blocked_license_image
from server.schemas import (
    ApiOk, CaptureEditDTO, CaptureResultDTO, ProductDetailDTO, ProductEditDTO,
    ProductEditRequest, ProductUploadIn,
)
from server.services import append_task_log, get_device_by_key
from server.task_state import StateConflict, TaskItemStatus
from server.task_state_service import (
    lock_device,
    require_mutable_item,  # retained as a patch seam for compatibility tests
    require_running_task,
    state_error_data,
    transition_item,
)
from server.product_quality import evaluate_product
from server.data_quality import evaluate as evaluate_data_quality
from server.product_observation import (
    load_quarantine_replay,
    persist_observation,
    persist_quarantine,
)
from server.job_service import JobProtocolError, error_data as job_error_data, require_active_lease
from server.quota import QuotaExceeded, STORAGE_BYTES, adjust_used, commit as commit_quota, reserve as reserve_quota
from server.media_access import signed_media_url
from server.raw_capture import RawCaptureError, persist_raw_capture
from server.product_contract import (
    DYNAMIC_IMMUTABLE_FIELDS, EDITABLE_STABLE_FIELDS, RAW_IMMUTABLE_FIELDS,
    normalize_stable_edit,
)
from server.product_read_model import edit_dto, load_canonical_product

router = APIRouter(prefix="/api/products", tags=["products"])
logger = logging.getLogger("sjzq.products")


def _task_has_collection_jobs(cur, task_id: int) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id",
        {"task_id": task_id},
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _image_root() -> Path:
    p = Path(settings.image_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _product_payload_hash(body: ProductUploadIn) -> str:
    payload = body.model_dump(mode="json")
    payload.pop("idempotency_key", None)
    payload.pop("device_key", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_receipt(cur, key: str):
    cur.execute(
        """
        SELECT PAYLOAD_SHA256, PRODUCT_ID, STATUS, RESULT_JSON, DEVICE_ID
          FROM SJZQ_UPLOAD_RECEIPT WHERE IDEMPOTENCY_KEY=:key
        """,
        {"key": key},
    )
    row = cur.fetchone()
    if not row:
        return None
    result_raw = row[3].read() if hasattr(row[3], "read") else row[3]
    return {
        "payload_sha256": str(row[0]),
        "product_id": int(row[1]) if row[1] is not None else None,
        "status": str(row[2]).lower(),
        "result": json.loads(result_raw) if result_raw else {},
        "device_id": int(row[4]),
    }


def _receipt_ack(receipt, key: str, message: str = "already uploaded") -> ApiOk:
    return ApiOk(
        message=message,
        data={
            **receipt["result"],
            "product_id": receipt["product_id"],
            "idempotency_key": key,
            "acknowledged": receipt["status"] == "acked",
            "persisted": receipt["status"] == "acked",
            "idempotent": True,
        },
    )


def _business_dedup_ack(cur, body: ProductUploadIn, device: dict, payload_sha256: str, quality) -> ApiOk | None:
    if not body.task_id or not body.item_id:
        return None
    cur.execute(
        """
        SELECT PRODUCT_ID FROM SJZQ_PRODUCT
         WHERE TASK_ID=:tid AND PLATFORM_CODE=:plat AND ITEM_ID=:iid AND IS_DELETED=0
           AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
         ORDER BY PRODUCT_ID FETCH FIRST 1 ROWS ONLY
        """,
        {"tid": body.task_id, "plat": body.platform_code, "iid": body.item_id,
         "enterprise_id": int(device.get("enterprise_id") or 1),
         "workspace_id": int(device.get("workspace_id") or 1)},
    )
    existing = cur.fetchone()
    if not existing:
        return None
    existing_product_id = int(existing[0])
    observation = persist_observation(
        cur,
        body=body,
        device_id=int(device["device_id"]),
        legacy_product_id=existing_product_id,
        payload_sha256=payload_sha256,
        decision=quality,
        enterprise_id=int(device.get("enterprise_id") or 1), workspace_id=int(device.get("workspace_id") or 1),
    )
    result = {
        "product_id": existing_product_id,
        "master_product_id": observation.master_product_id,
        "snapshot_id": observation.snapshot_id,
        "quality_result_id": observation.quality_result_id,
        "diff_id": observation.diff_id,
        "changed_fields": list(observation.changed_fields),
        "idempotency_key": body.idempotency_key,
        "acknowledged": True,
        "persisted": True,
        "idempotent": False,
        "business_deduplicated": True,
    }
    if body.raw_capture:
        capture_manifest = persist_raw_capture(body, device)
        result.update({
            "capture_id": capture_manifest["capture_id"],
            "capture_manifest": str((Path(settings.image_dir).parent / "raw-captures" /
                                     capture_manifest["capture_id"] / "manifest.json").resolve()),
        })
    cur.execute(
        """
        INSERT INTO SJZQ_UPLOAD_RECEIPT (
            IDEMPOTENCY_KEY, TASK_ID, DEVICE_ID, OP_TYPE, PAYLOAD_SHA256,
            PRODUCT_ID, MASTER_PRODUCT_ID, SNAPSHOT_ID, RESULT_JSON, STATUS, ENTERPRISE_ID, WORKSPACE_ID
        ) VALUES (:key, :tid, :did, 'product', :sha, :pid, :master_id, :snapshot_id, :result_json, 'acked',
                  :enterprise_id,:workspace_id)
        """,
        {
            "key": body.idempotency_key,
            "tid": body.task_id,
            "did": device["device_id"],
            "sha": payload_sha256,
            "pid": existing_product_id,
            "master_id": observation.master_product_id,
            "snapshot_id": observation.snapshot_id,
            "result_json": json.dumps(result, ensure_ascii=False, sort_keys=True),
            "enterprise_id": int(device.get("enterprise_id") or 1), "workspace_id": int(device.get("workspace_id") or 1),
        },
    )
    return ApiOk(message="business product already persisted", data=result)


@router.post("/upload")
def upload_product(body: ProductUploadIn):
    strict_protocol = bool(body.idempotency_key)
    job_identity = (body.job_id, body.attempt_id, body.worker_id, body.lease_token)
    has_job_identity = any(value is not None for value in job_identity)
    if has_job_identity and not all(value is not None for value in job_identity):
        return ApiOk(
            ok=False,
            message="complete Job lease identity is required",
            data={"error_code": "LEASE_IDENTITY_REQUIRED"},
        )
    quality = evaluate_data_quality(body) if strict_protocol else None
    payload_sha256 = _product_payload_hash(body) if strict_protocol else None
    with get_conn() as conn:
        cur = conn.cursor()
        if strict_protocol:
            # Receipt replay precedes the current quality rules. An already
            # persisted request must keep returning its original acknowledgement
            # even after parser/quality rule upgrades.
            receipt = _load_receipt(cur, body.idempotency_key)
            if receipt:
                device = get_device_by_key(cur, body.device_key)
                if not device:
                    return ApiOk(ok=False, message="device not registered")
                if receipt["device_id"] != int(device["device_id"]):
                    return ApiOk(ok=False, message="receipt device mismatch", data={"error_code": "DEVICE_MISMATCH"})
                if receipt["payload_sha256"] != payload_sha256:
                    return ApiOk(
                        ok=False,
                        message="idempotency key payload conflict",
                        data={"error_code": "IDEMPOTENCY_CONFLICT"},
                    )
                return _receipt_ack(receipt, body.idempotency_key)
            quarantined = load_quarantine_replay(cur, request_key=body.idempotency_key)
            if quarantined:
                device = get_device_by_key(cur, body.device_key)
                if not device or quarantined["device_id"] != int(device["device_id"]):
                    return ApiOk(ok=False, message="quarantine device mismatch", data={"error_code": "DEVICE_MISMATCH"})
                if quarantined["payload_sha256"] != payload_sha256:
                    return ApiOk(ok=False, message="idempotency key payload conflict", data={"error_code": "IDEMPOTENCY_CONFLICT"})
                return ApiOk(ok=False, message="product remains quarantined", data={
                    "error_code": "QUALITY_REJECTED", "quarantine_id": quarantined["quarantine_id"],
                    "quality_result_id": quarantined["quality_result_id"], "persisted": True,
                    "quarantined": True, "idempotent": True,
                })
        device = get_device_by_key(cur, body.device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")
        if body.task_id:
            try:
                if has_job_identity:
                    job, _attempt = require_active_lease(
                        cur,
                        device_id=int(device["device_id"]),
                        job_id=int(body.job_id),
                        attempt_id=int(body.attempt_id),
                        worker_id=str(body.worker_id),
                        lease_token=str(body.lease_token),
                    )
                    if int(job["task_id"]) != int(body.task_id):
                        raise JobProtocolError("JOB_TASK_MISMATCH", "Job does not belong to product Task")
                    if body.task_item_id is not None and job.get("item_id") != int(body.task_item_id):
                        raise JobProtocolError("JOB_ITEM_MISMATCH", "Job does not own product TaskItem")
                else:
                    lock_device(cur, int(device["device_id"]))
                    require_running_task(cur, body.task_id, device["device_id"], for_update=True)
                    if _task_has_collection_jobs(cur, body.task_id):
                        raise JobProtocolError("LEASE_REQUIRED", "Phase 2 product upload requires current Job lease")
                # A concurrent first delivery can commit while this request waits on the task lock.
                # Recheck before task-item mutability so the replay receives the original ack.
                if strict_protocol:
                    receipt = _load_receipt(cur, body.idempotency_key)
                    if receipt:
                        if receipt["device_id"] != int(device["device_id"]):
                            return ApiOk(ok=False, message="receipt device mismatch", data={"error_code": "DEVICE_MISMATCH"})
                        if receipt["payload_sha256"] != payload_sha256:
                            return ApiOk(ok=False, message="idempotency key payload conflict", data={"error_code": "IDEMPOTENCY_CONFLICT"})
                        return _receipt_ack(receipt, body.idempotency_key)
                    quarantined = load_quarantine_replay(cur, request_key=body.idempotency_key)
                    if quarantined:
                        if quarantined["device_id"] != int(device["device_id"]):
                            return ApiOk(ok=False, message="quarantine device mismatch", data={"error_code": "DEVICE_MISMATCH"})
                        if quarantined["payload_sha256"] != payload_sha256:
                            return ApiOk(ok=False, message="idempotency key payload conflict", data={"error_code": "IDEMPOTENCY_CONFLICT"})
                        return ApiOk(ok=False, message="product remains quarantined", data={
                            "error_code": "QUALITY_REJECTED", "quarantine_id": quarantined["quarantine_id"],
                            "quality_result_id": quarantined["quality_result_id"], "persisted": True,
                            "quarantined": True, "idempotent": True,
                        })
                    if quality is None or not quality.accepted:
                        try:
                            quarantine = persist_quarantine(
                                cur, body=body, device_id=int(device["device_id"]),
                                payload_sha256=payload_sha256, decision=quality,
                                enterprise_id=int(device.get("enterprise_id") or 1), workspace_id=int(device.get("workspace_id") or 1),
                            )
                        except QuotaExceeded as exc:
                            conn.rollback()
                            return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})
                        return ApiOk(ok=False, message="product rejected by quality gate", data={
                            "error_code": "QUALITY_REJECTED", "quarantine_id": quarantine.quarantine_id,
                            "quality_result_id": quarantine.quality_result_id, "persisted": True,
                            "quarantined": True, "idempotent": False,
                            "page_status": quality.page_status, "parse_status": quality.parse_status,
                            "quality_status": quality.quality_status,
                            "quality_rules_version": quality.quality_rules_version,
                            "missing_fields": list(quality.missing_fields),
                            "errors": list(quality.error_codes), "warnings": list(quality.warnings),
                        })
                    try:
                        deduplicated = _business_dedup_ack(cur, body, device, payload_sha256, quality)
                    except QuotaExceeded as exc:
                        conn.rollback()
                        return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})
                    if deduplicated is not None:
                        return deduplicated
                if body.task_item_id:
                    if not has_job_identity:
                        require_mutable_item(cur, body.task_id, body.task_item_id)
            except StateConflict as exc:
                return ApiOk(ok=False, message=str(exc), data=state_error_data(exc))
            except JobProtocolError as exc:
                return ApiOk(ok=False, message=str(exc), data=job_error_data(exc))

        product_id = next_id(cur, "SJZQ_SEQ_PRODUCT")
        cur.execute(
            """
            INSERT INTO SJZQ_PRODUCT (
                PRODUCT_ID, TASK_ID, DEVICE_ID, PLATFORM_CODE, KEYWORD, ITEM_ID,
                SELL_NAME, PRODUCT_NAME, BRAND, SHOP_NAME, SHOP_ID,
                PRICE, DISPLAY_PRICE, GROUP_PRICE, DEAL_PRICE, ORIGINAL_PRICE,
                SALES_NUM, SHOP_SALES_NUM, COMMENT_NUM, SPEC_TEXT,
                SKU_PRICES_TEXT, SKU_PRICES_JSON, DOSAGE_FORM, APPROVAL_NO,
                MANUFACTURER, EXPIRY_TEXT, CATEGORY, COUPON_INFO, ITEM_URL,
                PICK_TAG, SPEC_LIST, RAW_JSON, PARSE_STATUS, PAGE_STATUS,
                QUALITY_STATUS, FIELD_SOURCES, PARSER_VERSION, QUALITY_RULES_VERSION,
                LIBRARY_STATUS, IS_DELETED, ENTERPRISE_ID, WORKSPACE_ID
            ) VALUES (
                :pid, :tid, :did, :plat, :kw, :iid,
                :sn, :pn, :br, :shop_name, :shop_id,
                :price_v, :dprice, :gprice, :deal_price, :oprice,
                :sales_num, :ssales, :cmt, :spec_text,
                :sku_t, :sku_j, :dose, :appr,
                :mfr, :expiry_text, :category, :coupon, :item_url,
                :pick_tag, :slist, :raw_json, :parse_status, :page_status,
                :quality_status, :field_sources, :parser_version, :quality_rules_version,
                'draft', 0, :enterprise_id, :workspace_id
            )
            """,
            {
                "pid": product_id,
                "tid": body.task_id,
                "did": device["device_id"],
                "plat": body.platform_code,
                "kw": body.keyword,
                "iid": body.item_id,
                "sn": (body.sell_name or "")[:512] or None,
                "pn": (body.product_name or "")[:512] or None,
                "br": (body.brand or "")[:128] or None,
                "shop_name": (body.shop_name or "")[:256] or None,
                "shop_id": body.shop_id,
                "price_v": body.price,
                "dprice": body.display_price,
                "gprice": body.group_price,
                "deal_price": body.deal_price,
                "oprice": body.original_price,
                "sales_num": body.sales_num,
                "ssales": body.shop_sales_num,
                "cmt": body.comment_num,
                "spec_text": (body.spec or "")[:512] or None,
                "sku_t": (body.sku_prices_text or "")[:2000] or None,
                "sku_j": body.sku_prices,
                "dose": (body.dosage_form or "")[:128] or None,
                "appr": (body.approval_no or "")[:128] or None,
                "mfr": (body.manufacturer or "")[:256] or None,
                "expiry_text": (body.expiry or "")[:128] or None,
                "category": (body.category or "")[:256] or None,
                "coupon": (body.coupon_info or "")[:512] or None,
                "item_url": (body.item_url or "")[:1000] or None,
                "pick_tag": (body.pick_tag or "")[:64] or None,
                "slist": body.spec_list,
                "raw_json": body.raw_json,
                "parse_status": quality.parse_status if quality else body.parse_status,
                "page_status": quality.page_status if quality else body.page_status,
                "quality_status": quality.quality_status if quality else body.quality_status,
                "field_sources": json.dumps(body.field_sources, ensure_ascii=False, sort_keys=True)
                if body.field_sources else None,
                "parser_version": body.parser_version,
                "quality_rules_version": quality.quality_rules_version if quality else body.quality_rules_version,
                "enterprise_id": int(device.get("enterprise_id") or 1),
                "workspace_id": int(device.get("workspace_id") or 1),
            },
        )

        observation = None
        if strict_protocol:
            try:
                observation = persist_observation(
                    cur,
                    body=body,
                    device_id=int(device["device_id"]),
                    legacy_product_id=product_id,
                    payload_sha256=payload_sha256,
                    decision=quality,
                    enterprise_id=int(device.get("enterprise_id") or 1), workspace_id=int(device.get("workspace_id") or 1),
                )
            except QuotaExceeded as exc:
                conn.rollback()
                return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})

        # 仅记录远端 URL，本地文件走 /images 接口
        for i, url in enumerate(body.image_urls or []):
            if not url:
                continue
            image_id = next_id(cur, "SJZQ_SEQ_PRODUCT_IMAGE")
            cur.execute(
                """
                INSERT INTO SJZQ_PRODUCT_IMAGE (
                    IMAGE_ID, PRODUCT_ID, PLATFORM_CODE, SORT_NO,
                    FILE_NAME, REL_PATH, SOURCE_URL, ENTERPRISE_ID, WORKSPACE_ID
                ) VALUES (
                    :img_id, :pid, :plat, :sn, :fn, :rp, :src_url, :enterprise_id, :workspace_id
                )
                """,
                {
                    "img_id": image_id,
                    "pid": product_id,
                    "plat": body.platform_code,
                    "sn": i,
                    "fn": f"remote_{i}",
                    "rp": "",
                    "src_url": url[:1000],
                    "enterprise_id": int(device.get("enterprise_id") or 1), "workspace_id": int(device.get("workspace_id") or 1),
                },
            )

        if body.task_id:
            cur.execute(
                """
                UPDATE SJZQ_TASK
                   SET SUCCESS_COUNT = SUCCESS_COUNT + 1,
                       UPDATE_TIME = SYSTIMESTAMP
                 WHERE TASK_ID = :id
                """,
                {"id": body.task_id},
            )
            # Android 目标匹配任务优先按服务端明细 ID 精确回填，避免规格文本等价格式导致成功商品无法绑定。
            item = None
            if body.task_item_id:
                cur.execute(
                    """
                    SELECT ITEM_ID, STATUS, TARGET_APPROVAL, TARGET_SPEC FROM SJZQ_TASK_ITEM
                     WHERE TASK_ID = :tid AND ITEM_ID = :item_id
                    """,
                    {"tid": body.task_id, "item_id": body.task_item_id},
                )
                item_row = cur.fetchone()
                if item_row:
                    # Older integration fakes and pre-Phase-1 projections may expose only ITEM_ID.
                    is_plain_keyword = len(item_row) >= 4 and item_row[2] is None and item_row[3] is None
                    item = None if is_plain_keyword and str(item_row[1]).lower() in {"succeeded", "done"} else (item_row[0],)
            # 兼容旧版 Android：按关键词、准字和规格匹配 pending 明细。
            elif body.keyword:
                cur.execute(
                    """
                    SELECT ITEM_ID FROM SJZQ_TASK_ITEM
                     WHERE TASK_ID = :tid AND STATUS = 'pending' AND KEYWORD = :kw
                       AND (
                           TARGET_APPROVAL IS NULL OR
                           REPLACE(UPPER(TRIM(TARGET_APPROVAL)), ' ', '') =
                           REPLACE(UPPER(TRIM(:approval)), ' ', '')
                       )
                       AND (
                           TARGET_SPEC IS NULL OR
                           REPLACE(REPLACE(UPPER(TRIM(TARGET_SPEC)), '×', '*'), 'Ｘ', '*') =
                           REPLACE(REPLACE(UPPER(TRIM(:spec)), '×', '*'), 'Ｘ', '*')
                       )
                     ORDER BY ROW_INDEX FETCH FIRST 1 ROWS ONLY
                    """,
                    {
                        "tid": body.task_id,
                        "kw": body.keyword,
                        "approval": body.approval_no,
                        "spec": body.spec,
                    },
                )
                item = cur.fetchone()
                if not item:
                    cur.execute(
                        """
                        SELECT ITEM_ID FROM SJZQ_TASK_ITEM
                         WHERE TASK_ID = :tid AND STATUS = 'pending' AND KEYWORD = :kw
                           AND (
                               TARGET_APPROVAL IS NULL OR
                               REPLACE(UPPER(TRIM(TARGET_APPROVAL)), ' ', '') =
                               REPLACE(UPPER(TRIM(:approval)), ' ', '')
                           )
                           AND (
                               TARGET_SPEC IS NULL OR
                               REPLACE(REPLACE(UPPER(TRIM(TARGET_SPEC)), '×', '*'), 'Ｘ', '*') =
                               REPLACE(REPLACE(UPPER(TRIM(:spec)), '×', '*'), 'Ｘ', '*')
                           )
                         ORDER BY ROW_INDEX
                        """,
                        {
                            "tid": body.task_id,
                            "kw": body.keyword,
                            "approval": body.approval_no,
                            "spec": body.spec,
                        },
                    )
                    item = cur.fetchone()
            if item:
                try:
                    transition_item(cur, body.task_id, int(item[0]), TaskItemStatus.SUCCEEDED,
                                    product_id=product_id, message="采集成功，目标匹配成功")
                except StateConflict as exc:
                    conn.rollback()
                    return ApiOk(ok=False, message=str(exc), data=state_error_data(exc))
            append_task_log(
                cur,
                body.task_id,
                f"上报商品 item_id={body.item_id or '-'} name={(body.sell_name or body.product_name or '')[:40]}",
                device_id=device["device_id"],
            )

        result = {
            "product_id": product_id,
            "idempotency_key": body.idempotency_key,
            "acknowledged": True,
            "persisted": True,
            "idempotent": False,
        }
        if body.raw_capture:
            try:
                capture_manifest = persist_raw_capture(body, device)
            except RawCaptureError as exc:
                raise StateConflict("RAW_CAPTURE_INVALID", "invalid", str(exc)) from exc
            result.update({
                "capture_id": capture_manifest["capture_id"],
                "capture_manifest": str((Path(settings.image_dir).parent / "raw-captures" /
                                         capture_manifest["capture_id"] / "manifest.json").resolve()),
            })
        if observation is not None:
            result.update({
                "master_product_id": observation.master_product_id,
                "snapshot_id": observation.snapshot_id,
                "quality_result_id": observation.quality_result_id,
                "diff_id": observation.diff_id,
                "previous_snapshot_id": observation.previous_snapshot_id,
                "changed_fields": list(observation.changed_fields),
                "quality_rules_version": quality.quality_rules_version,
            })
        if strict_protocol:
            cur.execute(
                """
                INSERT INTO SJZQ_UPLOAD_RECEIPT (
                    IDEMPOTENCY_KEY, TASK_ID, DEVICE_ID, OP_TYPE, PAYLOAD_SHA256,
                    PRODUCT_ID, MASTER_PRODUCT_ID, SNAPSHOT_ID, RESULT_JSON, STATUS, ENTERPRISE_ID, WORKSPACE_ID
                ) VALUES (:key, :tid, :did, 'product', :sha, :pid, :master_id, :snapshot_id, :result_json, 'acked',
                          :enterprise_id,:workspace_id)
                """,
                {
                    "key": body.idempotency_key,
                    "tid": body.task_id,
                    "did": device["device_id"],
                    "sha": payload_sha256,
                    "pid": product_id,
                    "master_id": observation.master_product_id,
                    "snapshot_id": observation.snapshot_id,
                    "result_json": json.dumps(result, ensure_ascii=False, sort_keys=True),
                    "enterprise_id": int(device.get("enterprise_id") or 1), "workspace_id": int(device.get("workspace_id") or 1),
                },
            )
        return ApiOk(message="uploaded", data=result)


@router.post("/{product_id}/images")
async def upload_images(
    product_id: int,
    device_key: str = Form(...),
    idempotency_key: str | None = Form(None),
    files: list[UploadFile] = File(...),
    job_id: int | None = Form(None),
    attempt_id: int | None = Form(None),
    worker_id: str | None = Form(None),
    lease_token: str | None = Form(None),
):
    job_identity = (job_id, attempt_id, worker_id, lease_token)
    has_job_identity = any(value is not None for value in job_identity)
    if has_job_identity and not all(value is not None for value in job_identity):
        return ApiOk(ok=False, message="complete Job lease identity is required",
                     data={"error_code": "LEASE_IDENTITY_REQUIRED"})
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")
        device_enterprise_id = int(device.get("enterprise_id") or 1)
        device_workspace_id = int(device.get("workspace_id") or 1)
        cur.execute(
            """SELECT PRODUCT_ID, PLATFORM_CODE, TASK_ID, ENTERPRISE_ID, WORKSPACE_ID
                 FROM SJZQ_PRODUCT WHERE PRODUCT_ID = :id
                  AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
            {"id": product_id, "enterprise_id": device_enterprise_id,
             "workspace_id": device_workspace_id},
        )
        prod = row_as_dict(cur)
        if not prod:
            return ApiOk(ok=False, message="product not found")

        file_rows = [(upload, await upload.read()) for upload in files]
        payload_digest = hashlib.sha256()
        payload_digest.update(str(product_id).encode("ascii"))
        for upload, raw in file_rows:
            payload_digest.update((upload.filename or "").encode("utf-8"))
            payload_digest.update((upload.content_type or "").encode("ascii", errors="ignore"))
            payload_digest.update(hashlib.sha256(raw).digest())
        payload_sha256 = payload_digest.hexdigest()
        if idempotency_key:
            receipt = _load_receipt(cur, idempotency_key)
            if receipt:
                if receipt["device_id"] != int(device["device_id"]):
                    return ApiOk(ok=False, message="receipt device mismatch", data={"error_code": "DEVICE_MISMATCH"})
                if receipt["payload_sha256"] != payload_sha256:
                    return ApiOk(ok=False, message="idempotency key payload conflict", data={"error_code": "IDEMPOTENCY_CONFLICT"})
                return ApiOk(
                    message="images already uploaded",
                    data={**receipt["result"], "acknowledged": True, "idempotent": True},
                )

        task_id = prod.get("task_id")
        if task_id is not None:
            try:
                if has_job_identity:
                    job, _attempt = require_active_lease(
                        cur,
                        device_id=int(device["device_id"]),
                        job_id=int(job_id),
                        attempt_id=int(attempt_id),
                        worker_id=str(worker_id),
                        lease_token=str(lease_token),
                    )
                    if int(job["task_id"]) != int(task_id):
                        raise JobProtocolError("JOB_TASK_MISMATCH", "Job does not own image Product")
                else:
                    if _task_has_collection_jobs(cur, int(task_id)):
                        raise JobProtocolError("LEASE_REQUIRED", "Phase 2 image upload requires current Job lease")
            except JobProtocolError as exc:
                return ApiOk(ok=False, message=str(exc), data=job_error_data(exc))
        # Acquire the business child lock only after the execution ownership
        # rows, preserving Device -> Task -> Job -> Attempt -> Lease -> Product.
        cur.execute(
            "SELECT PRODUCT_ID FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:id FOR UPDATE",
            {"id": product_id},
        )
        if not cur.fetchone():
            return ApiOk(ok=False, message="product not found")

        platform = prod["platform_code"]
        saved = []
        base = _image_root() / platform / str(product_id)
        base.mkdir(parents=True, exist_ok=True)

        # 当前最大 sort
        cur.execute(
            "SELECT NVL(MAX(SORT_NO), -1) FROM SJZQ_PRODUCT_IMAGE WHERE PRODUCT_ID = :id",
            {"id": product_id},
        )
        sort_no = int(cur.fetchone()[0])

        skipped = []
        planned = []
        for f, raw in file_rows:
            blocked, reason = is_blocked_license_image(raw)
            if blocked:
                skipped.append(
                    {
                        "filename": f.filename,
                        "reason": reason or "药品经营许可证",
                    }
                )
                logger.info(
                    "跳过证照图 product_id=%s file=%s reason=%s",
                    product_id,
                    f.filename,
                    reason,
                )
                continue

            content_hash = hashlib.sha256(raw).hexdigest()[:12]
            if idempotency_key:
                cur.execute(
                    """
                    SELECT IMAGE_ID, REL_PATH FROM SJZQ_PRODUCT_IMAGE
                     WHERE PRODUCT_ID=:pid AND INSTR(FILE_NAME, :content_hash) > 0
                     ORDER BY IMAGE_ID FETCH FIRST 1 ROWS ONLY
                    """,
                    {"pid": product_id, "content_hash": content_hash},
                )
                existing_image = cur.fetchone()
                if existing_image:
                    rel = str(existing_image[1] or "")
                    saved.append({"image_id": int(existing_image[0]), "rel_path": rel,
                                  "url": signed_media_url(rel, int(prod.get("enterprise_id") or device_enterprise_id),
                                                          int(prod.get("workspace_id") or device_workspace_id))})
                    continue

            planned.append((f, raw, content_hash))

        storage_reservation = None
        planned_bytes = sum(len(raw) for _, raw, _ in planned)
        if planned_bytes:
            storage_key = idempotency_key or f"image:{product_id}:{payload_sha256}"
            try:
                storage_reservation = reserve_quota(
                    cur, enterprise_id=int(prod.get("enterprise_id") or device_enterprise_id),
                    workspace_id=int(prod.get("workspace_id") or device_workspace_id),
                    metric=STORAGE_BYTES, amount=planned_bytes, resource_type="image", resource_key=storage_key,
                )
            except QuotaExceeded as exc:
                conn.rollback()
                return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})

        for f, raw, content_hash in planned:
            sort_no += 1
            ext = Path(f.filename or "img.jpg").suffix or ".jpg"
            if len(ext) > 8:
                ext = ".jpg"
            fname = f"{sort_no:02d}_{content_hash}{ext}"
            dest = base / fname
            with dest.open("wb") as out:
                out.write(raw)
            rel = f"{platform}/{product_id}/{fname}".replace("\\", "/")
            image_id = next_id(cur, "SJZQ_SEQ_PRODUCT_IMAGE")
            size = dest.stat().st_size
            cur.execute(
                """
                INSERT INTO SJZQ_PRODUCT_IMAGE (
                    IMAGE_ID, PRODUCT_ID, PLATFORM_CODE, SORT_NO,
                    FILE_NAME, REL_PATH, FILE_SIZE, CONTENT_TYPE, ENTERPRISE_ID, WORKSPACE_ID
                ) VALUES (
                    :id, :pid, :plat, :sn, :fn, :rp, :sz, :ct, :enterprise_id, :workspace_id
                )
                """,
                {
                    "id": image_id,
                    "pid": product_id,
                    "plat": platform,
                    "sn": sort_no,
                    "fn": fname,
                    "rp": rel,
                    "sz": size,
                    "ct": f.content_type,
                    "enterprise_id": int(prod.get("enterprise_id") or device_enterprise_id),
                    "workspace_id": int(prod.get("workspace_id") or device_workspace_id),
                },
            )
            saved.append({"image_id": image_id, "rel_path": rel,
                          "url": signed_media_url(rel, int(prod.get("enterprise_id") or device_enterprise_id),
                                                  int(prod.get("workspace_id") or device_workspace_id))})

        if storage_reservation is not None:
            commit_quota(cur, storage_reservation.reservation_id)

        result = {
            "product_id": product_id,
            "images": saved,
            "skipped_license": skipped,
            "idempotency_key": idempotency_key,
            "acknowledged": True,
            "idempotent": False,
        }
        if idempotency_key:
            cur.execute(
                """
                INSERT INTO SJZQ_UPLOAD_RECEIPT (
                    IDEMPOTENCY_KEY, TASK_ID, DEVICE_ID, OP_TYPE, PAYLOAD_SHA256,
                    PRODUCT_ID, RESULT_JSON, STATUS, ENTERPRISE_ID, WORKSPACE_ID
                ) SELECT :key, TASK_ID, :did, 'image', :sha, PRODUCT_ID, :result_json, 'acked',ENTERPRISE_ID,WORKSPACE_ID
                    FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:pid
                """,
                {
                    "key": idempotency_key,
                    "did": device["device_id"],
                    "sha": payload_sha256,
                    "pid": product_id,
                    "result_json": json.dumps(result, ensure_ascii=False, sort_keys=True),
                },
            )
        return ApiOk(data=result)


@router.post("/images/purge-licenses")
def purge_license_images(
    limit: int = Query(500, ge=1, le=5000),
    tenant=Depends(require_tenant_perms("data:delete")),
):
    """扫描已入库本地图片，识别药品经营许可证等证照并删除文件与库记录。"""
    root = _image_root()
    deleted = []
    scanned = 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT IMAGE_ID, PRODUCT_ID, REL_PATH, FILE_NAME,FILE_SIZE
              FROM SJZQ_PRODUCT_IMAGE
             WHERE REL_PATH IS NOT NULL AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
             ORDER BY IMAGE_ID DESC
             FETCH FIRST :lim ROWS ONLY
            """,
            {"lim": int(limit), **tenant.binds},
        )
        rows = rows_as_dicts(cur)
        for row in rows:
            rel = (row.get("rel_path") or "").replace("\\", "/").lstrip("/")
            if not rel:
                continue
            path = root / rel
            if not path.is_file():
                continue
            scanned += 1
            blocked, reason = is_blocked_license_file(path)
            if not blocked:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("删除证照文件失败 %s: %s", path, e)
                continue
            cur.execute(
                """DELETE FROM SJZQ_PRODUCT_IMAGE WHERE IMAGE_ID = :id
                    AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
                {"id": int(row["image_id"]), **tenant.binds},
            )
            adjust_used(cur, enterprise_id=tenant.enterprise_id, workspace_id=tenant.workspace_id,
                        metric=STORAGE_BYTES, amount_delta=-int(row.get("file_size") or 0),
                        event_key=f"image-delete:{row['image_id']}", resource_type="image",
                        resource_key=str(row["image_id"]))
            deleted.append(
                {
                    "image_id": row["image_id"],
                    "product_id": row["product_id"],
                    "rel_path": rel,
                    "reason": reason,
                }
            )
    return ApiOk(
        message=f"已删除 {len(deleted)} 张证照图",
        data={"scanned": scanned, "deleted": len(deleted), "items": deleted},
    )


@router.get("")
def list_products(
    platform_code: str | None = None,
    keyword: str | None = None,
    brand: str | None = None,
    item_id: str | None = None,
    approval_no: str | None = None,
    task_id: int | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    tenant=Depends(require_tenant_perms("data:view")),
):
    with get_conn() as conn:
        cur = conn.cursor()
        select_sql = """
            SELECT PRODUCT_ID, TASK_ID, PLATFORM_CODE, KEYWORD, ITEM_ID,
                   SELL_NAME, PRODUCT_NAME, BRAND, SHOP_NAME, SHOP_ID,
                   PRICE, DISPLAY_PRICE, GROUP_PRICE, DEAL_PRICE, ORIGINAL_PRICE,
                   SALES_NUM, SHOP_SALES_NUM, COMMENT_NUM,
                   SPEC_TEXT, SKU_PRICES_TEXT,
                   APPROVAL_NO, MANUFACTURER, ITEM_URL, PICK_TAG,
                   COLLECT_TIME, LIBRARY_STATUS, IS_DELETED, SAVED_BY, SAVED_TIME,
                   MASTER_PRODUCT_ID, SNAPSHOT_ID
              FROM SJZQ_PRODUCT
             WHERE NVL(IS_DELETED,0)=0 AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
        """
        where_sql = ""
        params: dict = dict(tenant.binds)
        if platform_code:
            where_sql += " AND PLATFORM_CODE = :p"
            params["p"] = platform_code
        if keyword:
            where_sql += " AND KEYWORD LIKE :kw"
            params["kw"] = f"%{keyword}%"
        if brand:
            where_sql += " AND BRAND LIKE :br"
            params["br"] = f"%{brand}%"
        if item_id:
            where_sql += " AND ITEM_ID = :iid"
            params["iid"] = item_id
        if approval_no:
            where_sql += " AND APPROVAL_NO LIKE :ap"
            params["ap"] = f"%{approval_no}%"
        if task_id is not None:
            where_sql += " AND TASK_ID = :tid"
            params["tid"] = task_id
        else:
            where_sql += " AND NVL(LIBRARY_STATUS,'saved')='saved'"
        cur.execute(
            "SELECT COUNT(*) FROM SJZQ_PRODUCT WHERE NVL(IS_DELETED,0)=0 AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id" + where_sql,
            params,
        )
        total = int(cur.fetchone()[0])
        page_params = {**params, "offset": (page - 1) * limit, "limit": limit}
        cur.execute(
            select_sql + where_sql
            + " ORDER BY COLLECT_TIME DESC NULLS LAST, PRODUCT_ID DESC"
            + " OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY",
            page_params,
        )
        items = rows_as_dicts(cur)
        _attach_product_images(cur, items, tenant)
        for item in items:
            # Canonical aliases are the public read contract.  Legacy keys remain
            # temporarily for non-P0 clients but are not consumed by new Web code.
            item.update({
                "platform_product_id": item.get("item_id"),
                "platform_title": item.get("sell_name"),
                "canonical_name": item.get("product_name"),
                "product_attribute_spec": item.get("spec_text"),
                "approval_number": item.get("approval_no"),
                "list_price": item.get("price"),
                "detail_price": item.get("display_price"),
                "single_purchase_price": item.get("deal_price"),
                "sales": item.get("sales_num"),
                "shop_sales": item.get("shop_sales_num"),
            })
        return ApiOk(data={"total": total, "page": page, "limit": limit, "items": items})


def _attach_product_images(cur, products: list[dict], tenant) -> None:
    """为列表页附带图片数量与附件 URL。"""
    if not products:
        return
    ids = [int(p["product_id"]) for p in products if p.get("product_id") is not None]
    if not ids:
        return
    # Oracle 绑定列表：逐条查或分批 IN
    by_pid: dict[int, list[dict]] = {i: [] for i in ids}
    for pid in ids:
        cur.execute(
            """
            SELECT IMAGE_ID, SORT_NO, FILE_NAME, REL_PATH, SOURCE_URL
              FROM SJZQ_PRODUCT_IMAGE
             WHERE PRODUCT_ID = :id
             ORDER BY SORT_NO, IMAGE_ID
            """,
            {"id": pid},
        )
        imgs = []
        for img in rows_as_dicts(cur):
            rel = img.get("rel_path") or ""
            url = signed_media_url(rel, tenant.enterprise_id, tenant.workspace_id) if rel else (img.get("source_url") or "")
            if url:
                imgs.append({"image_id": img.get("image_id"), "url": url})
        by_pid[pid] = imgs
    for p in products:
        pid = int(p["product_id"])
        imgs = by_pid.get(pid) or []
        p["images"] = imgs
        p["image_count"] = len(imgs)
        p["cover_url"] = imgs[0]["url"] if imgs else ""


@router.get("/{product_id}")
def get_product(product_id: int, tenant=Depends(require_tenant_perms("data:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        model = load_canonical_product(cur, product_id, tenant)
        if not model:
            return ApiOk(ok=False, message="product not found")
        return ApiOk(data=ProductDetailDTO.model_validate(model).model_dump(mode="json"))


@router.get("/{product_id}/capture-result")
def get_capture_result(product_id: int, tenant=Depends(require_tenant_perms("data:view"))):
    with get_conn() as conn:
        model = load_canonical_product(conn.cursor(), product_id, tenant)
        if not model:
            return ApiOk(ok=False, message="product not found")
        return ApiOk(data=CaptureResultDTO.model_validate(model).model_dump(mode="json"))


@router.get("/{product_id}/edit")
def get_product_edit(
    product_id: int,
    scope: str = Query("library", pattern="^(library|capture)$"),
    user=Depends(require_perms("data:view")),
    tenant=Depends(require_tenant_perms("data:view")),
):
    with get_conn() as conn:
        cur = conn.cursor()
        model = load_canonical_product(cur, product_id, tenant)
        if not model:
            return ApiOk(ok=False, message="product not found")
        before = _snapshot(cur, product_id)
        if not before or not _can_edit_product(cur, before, user, tenant):
            return ApiOk(ok=False, message="没有修改权限")
        payload = edit_dto(model, scope)
        dto = CaptureEditDTO if scope == "capture" else ProductEditDTO
        return ApiOk(data=dto.model_validate(payload).model_dump(mode="json"))


def _snapshot(cur, product_id: int) -> dict | None:
    cur.execute("SELECT * FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:id", {"id": product_id})
    row = row_as_dict(cur)
    if not row:
        return None
    return {k: (str(v) if v is not None else None) for k, v in row.items() if k not in {"raw_json", "sku_prices_json"}}


def _can_edit_product(cur, product: dict, user: dict, tenant) -> bool:
    if tenant.role_code == "super_admin":
        return True
    task_id = product.get("task_id")
    if not task_id or str(product.get("library_status") or "saved") != "draft":
        return False
    cur.execute("SELECT CREATE_USER_ID FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": task_id})
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) == int(user["user_id"]))


def _record_change(cur, product_id: int, action: str, before: dict | None, after: dict | None, user: dict):
    cur.execute("""
        INSERT INTO SJZQ_PRODUCT_CHANGE
        (CHANGE_ID, PRODUCT_ID, TASK_ID, ACTION_CODE, BEFORE_JSON, AFTER_JSON, USER_ID, USERNAME)
        VALUES (SJZQ_SEQ_PRODUCT_CHANGE.NEXTVAL, :pid, :tid, :action, :before_v, :after_v, :uid, :username)
    """, {
        "pid": product_id, "tid": (before or after or {}).get("task_id"), "action": action,
        "before_v": json.dumps(before, ensure_ascii=False, default=str) if before else None,
        "after_v": json.dumps(after, ensure_ascii=False, default=str) if after else None,
        "uid": user["user_id"], "username": user["username"],
    })


@router.put("/{product_id}")
def update_product(product_id: int, body: dict, request: Request, user=Depends(require_perms("data:view")), tenant=Depends(require_tenant_perms("data:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id",
                    {"id":product_id,**tenant.binds})
        if not cur.fetchone(): return ApiOk(ok=False,message="商品不存在")
        before = _snapshot(cur, product_id)
        if not before:
            return ApiOk(ok=False, message="商品不存在")
        if not _can_edit_product(cur, before, user, tenant):
            return ApiOk(ok=False, message="仅任务创建人可修改本次草稿，正式资料仅超级管理员可修改")
        immutable = sorted(set(body) & (DYNAMIC_IMMUTABLE_FIELDS | RAW_IMMUTABLE_FIELDS))
        if immutable:
            return ApiOk(
                ok=False,
                message="动态观察、Snapshot 和 Raw Evidence 不允许通过普通修改接口覆盖",
                data={"error_code": "OBSERVED_FIELD_IMMUTABLE", "fields": immutable},
            )
        changes, unsupported = normalize_stable_edit(body)
        if unsupported:
            return ApiOk(
                ok=False, message="包含非 ProductEditDTO 字段",
                data={"error_code": "EDIT_FIELD_NOT_ALLOWED", "fields": sorted(unsupported)},
            )
        if not changes:
            return ApiOk(ok=False, message="没有可修改字段")
        # Validate the canonical write contract before translating once at the
        # persistence boundary.
        ProductEditRequest.model_validate(changes)
        sets = []
        params = {"id": product_id}
        for canonical, value in changes.items():
            column = EDITABLE_STABLE_FIELDS[canonical]
            sets.append(f"{column}=:{canonical}")
            params[canonical] = value
        sets.append("UPDATE_TIME=SYSTIMESTAMP")
        cur.execute(f"UPDATE SJZQ_PRODUCT SET {', '.join(sets)} WHERE PRODUCT_ID=:id", params)
        after = _snapshot(cur, product_id)
        _record_change(cur, product_id, "update", before, after, user)
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="product_update",
                     module="product", detail=f"修改商品 #{product_id}", ip=request.client.host if request.client else None)
        model = load_canonical_product(cur, product_id, tenant)
        scope = str(body.get("scope") or ("capture" if before.get("library_status") == "draft" else "library"))
        dto = CaptureEditDTO if scope == "capture" else ProductEditDTO
        return ApiOk(message="已保存", data=dto.model_validate(edit_dto(model, scope)).model_dump(mode="json"))


@router.delete("/{product_id}")
def delete_product(product_id: int, request: Request, user=Depends(require_perms("data:view")), tenant=Depends(require_tenant_perms("data:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id",
                    {"id":product_id,**tenant.binds})
        if not cur.fetchone(): return ApiOk(ok=False,message="商品不存在")
        before = _snapshot(cur, product_id)
        if not before:
            return ApiOk(ok=False, message="商品不存在")
        if not _can_edit_product(cur, before, user, tenant):
            return ApiOk(ok=False, message="没有删除权限")
        cur.execute("UPDATE SJZQ_PRODUCT SET IS_DELETED=1, UPDATE_TIME=SYSTIMESTAMP WHERE PRODUCT_ID=:id", {"id": product_id})
        _record_change(cur, product_id, "delete", before, None, user)
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="product_delete",
                     module="product", detail=f"删除商品 #{product_id}", ip=request.client.host if request.client else None)
        return ApiOk(message="已删除")


@router.post("/save-batch")
def save_products(body: dict, request: Request, user=Depends(require_perms("data:view")), tenant=Depends(require_tenant_perms("data:view"))):
    ids = [int(x) for x in body.get("product_ids", []) if str(x).isdigit()]
    if not ids:
        return ApiOk(ok=False, message="请选择商品")
    saved = 0
    with get_conn() as conn:
        cur = conn.cursor()
        for pid in ids[:500]:
            cur.execute("SELECT 1 FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id",
                        {"id":pid,**tenant.binds})
            if not cur.fetchone(): continue
            before = _snapshot(cur, pid)
            if not before or not _can_edit_product(cur, before, user, tenant):
                continue
            cur.execute("""
                UPDATE SJZQ_PRODUCT SET LIBRARY_STATUS='saved', SAVED_BY=:uid,
                       SAVED_TIME=SYSTIMESTAMP, UPDATE_TIME=SYSTIMESTAMP
                 WHERE PRODUCT_ID=:id AND NVL(IS_DELETED,0)=0
            """, {"uid": user["user_id"], "id": pid})
            after = _snapshot(cur, pid)
            _record_change(cur, pid, "save_library", before, after, user)
            saved += 1
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="product_save_library",
                     module="product", detail=f"保存正式资料 {saved} 条", ip=request.client.host if request.client else None)
        return ApiOk(message=f"已保存 {saved} 条到商品资料库", data={"saved": saved})


@router.get("/media-info/ping")
def media_ping():
    return ApiOk(data={"image_dir": str(_image_root())})

"""商品上报、图片上传、查询。"""

from __future__ import annotations

import logging
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, Request

from server.auth_util import require_perms, write_op_log
from server.config import settings
from server.db import get_conn, next_id, row_as_dict, rows_as_dicts
from server.image_filter import is_blocked_license_file, is_blocked_license_image
from server.schemas import ApiOk, ProductUploadIn
from server.services import append_task_log, get_device_by_key

router = APIRouter(prefix="/api/products", tags=["products"])
logger = logging.getLogger("sjzq.products")


def _image_root() -> Path:
    p = Path(settings.image_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/upload")
def upload_product(body: ProductUploadIn):
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, body.device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")

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
                PICK_TAG, SPEC_LIST, RAW_JSON, LIBRARY_STATUS, IS_DELETED
            ) VALUES (
                :pid, :tid, :did, :plat, :kw, :iid,
                :sn, :pn, :br, :shop_name, :shop_id,
                :price_v, :dprice, :gprice, :deal_price, :oprice,
                :sales_num, :ssales, :cmt, :spec_text,
                :sku_t, :sku_j, :dose, :appr,
                :mfr, :expiry_text, :category, :coupon, :item_url,
                :pick_tag, :slist, :raw_json, 'draft', 0
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
            },
        )

        # 仅记录远端 URL，本地文件走 /images 接口
        for i, url in enumerate(body.image_urls or []):
            if not url:
                continue
            image_id = next_id(cur, "SJZQ_SEQ_PRODUCT_IMAGE")
            cur.execute(
                """
                INSERT INTO SJZQ_PRODUCT_IMAGE (
                    IMAGE_ID, PRODUCT_ID, PLATFORM_CODE, SORT_NO,
                    FILE_NAME, REL_PATH, SOURCE_URL
                ) VALUES (
                    :img_id, :pid, :plat, :sn, :fn, :rp, :src_url
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
                    SELECT ITEM_ID FROM SJZQ_TASK_ITEM
                     WHERE TASK_ID = :tid AND ITEM_ID = :item_id
                    """,
                    {"tid": body.task_id, "item_id": body.task_item_id},
                )
                item = cur.fetchone()
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
                cur.execute(
                    """
                    UPDATE SJZQ_TASK_ITEM
                       SET STATUS = 'done', PRODUCT_ID = :pid,
                           MESSAGE = '采集成功，目标匹配成功', UPDATE_TIME = SYSTIMESTAMP
                     WHERE ITEM_ID = :iid
                    """,
                    {"pid": product_id, "iid": int(item[0])},
                )
            append_task_log(
                cur,
                body.task_id,
                f"上报商品 item_id={body.item_id or '-'} name={(body.sell_name or body.product_name or '')[:40]}",
                device_id=device["device_id"],
            )

        return ApiOk(message="uploaded", data={"product_id": product_id})


@router.post("/{product_id}/images")
async def upload_images(
    product_id: int,
    device_key: str = Form(...),
    files: list[UploadFile] = File(...),
):
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")
        cur.execute(
            "SELECT PRODUCT_ID, PLATFORM_CODE FROM SJZQ_PRODUCT WHERE PRODUCT_ID = :id",
            {"id": product_id},
        )
        prod = row_as_dict(cur)
        if not prod:
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
        for f in files:
            raw = await f.read()
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

            sort_no += 1
            ext = Path(f.filename or "img.jpg").suffix or ".jpg"
            if len(ext) > 8:
                ext = ".jpg"
            fname = f"{sort_no:02d}_{uuid.uuid4().hex[:8]}{ext}"
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
                    FILE_NAME, REL_PATH, FILE_SIZE, CONTENT_TYPE
                ) VALUES (
                    :id, :pid, :plat, :sn, :fn, :rp, :sz, :ct
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
                },
            )
            saved.append({"image_id": image_id, "rel_path": rel, "url": f"/media/{rel}"})

        return ApiOk(
            data={
                "product_id": product_id,
                "images": saved,
                "skipped_license": skipped,
            }
        )


@router.post("/images/purge-licenses")
def purge_license_images(
    limit: int = Query(500, ge=1, le=5000),
    _=Depends(require_perms("data:delete")),
):
    """扫描已入库本地图片，识别药品经营许可证等证照并删除文件与库记录。"""
    root = _image_root()
    deleted = []
    scanned = 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT IMAGE_ID, PRODUCT_ID, REL_PATH, FILE_NAME
              FROM SJZQ_PRODUCT_IMAGE
             WHERE REL_PATH IS NOT NULL
             ORDER BY IMAGE_ID DESC
             FETCH FIRST :lim ROWS ONLY
            """,
            {"lim": int(limit)},
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
                "DELETE FROM SJZQ_PRODUCT_IMAGE WHERE IMAGE_ID = :id",
                {"id": int(row["image_id"])},
            )
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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _=Depends(require_perms("data:view")),
):
    with get_conn() as conn:
        cur = conn.cursor()
        sql = """
            SELECT PRODUCT_ID, TASK_ID, PLATFORM_CODE, KEYWORD, ITEM_ID,
                   SELL_NAME, PRODUCT_NAME, BRAND, SHOP_NAME, SHOP_ID,
                   PRICE, DISPLAY_PRICE, GROUP_PRICE, DEAL_PRICE, ORIGINAL_PRICE,
                   SALES_NUM, SHOP_SALES_NUM, COMMENT_NUM,
                   SPEC_TEXT, SKU_PRICES_TEXT,
                   APPROVAL_NO, MANUFACTURER, ITEM_URL, PICK_TAG,
                   COLLECT_TIME, LIBRARY_STATUS, IS_DELETED, SAVED_BY, SAVED_TIME
              FROM SJZQ_PRODUCT
             WHERE NVL(IS_DELETED,0)=0
        """
        params: dict = {}
        if platform_code:
            sql += " AND PLATFORM_CODE = :p"
            params["p"] = platform_code
        if keyword:
            sql += " AND KEYWORD LIKE :kw"
            params["kw"] = f"%{keyword}%"
        if brand:
            sql += " AND BRAND LIKE :br"
            params["br"] = f"%{brand}%"
        if item_id:
            sql += " AND ITEM_ID = :iid"
            params["iid"] = item_id
        if approval_no:
            sql += " AND APPROVAL_NO LIKE :ap"
            params["ap"] = f"%{approval_no}%"
        if task_id is not None:
            sql += " AND TASK_ID = :tid"
            params["tid"] = task_id
        else:
            sql += " AND NVL(LIBRARY_STATUS,'saved')='saved'"
        sql += " ORDER BY PRODUCT_ID DESC"
        cur.execute(sql, params)
        rows = rows_as_dicts(cur)
        sliced = rows[offset : offset + limit]
        _attach_product_images(cur, sliced)
        return ApiOk(data={"total": len(rows), "items": sliced})


def _attach_product_images(cur, products: list[dict]) -> None:
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
            url = f"/media/{rel}" if rel else (img.get("source_url") or "")
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
def get_product(product_id: int, _=Depends(require_perms("data:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM SJZQ_PRODUCT WHERE PRODUCT_ID = :id
            """,
            {"id": product_id},
        )
        prod = row_as_dict(cur)
        if not prod:
            return ApiOk(ok=False, message="product not found")
        cur.execute(
            """
            SELECT IMAGE_ID, SORT_NO, FILE_NAME, REL_PATH, SOURCE_URL, FILE_SIZE, CONTENT_TYPE
              FROM SJZQ_PRODUCT_IMAGE
             WHERE PRODUCT_ID = :id
             ORDER BY SORT_NO, IMAGE_ID
            """,
            {"id": product_id},
        )
        images = []
        for img in rows_as_dicts(cur):
            rel = img.get("rel_path") or ""
            img["url"] = f"/media/{rel}" if rel else img.get("source_url")
            images.append(img)
        prod["images"] = images
        return ApiOk(data=prod)


EDITABLE_FIELDS = {
    "sell_name", "product_name", "brand", "shop_name", "price", "display_price",
    "group_price", "deal_price", "original_price", "sales_num", "shop_sales_num",
    "spec_text", "approval_no", "manufacturer", "item_url", "category", "expiry_text",
}


def _snapshot(cur, product_id: int) -> dict | None:
    cur.execute("SELECT * FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:id", {"id": product_id})
    row = row_as_dict(cur)
    if not row:
        return None
    return {k: (str(v) if v is not None else None) for k, v in row.items() if k not in {"raw_json", "sku_prices_json"}}


def _can_edit_product(cur, product: dict, user: dict) -> bool:
    if user.get("role_code") == "super_admin":
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
def update_product(product_id: int, body: dict, request: Request, user=Depends(require_perms("data:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        before = _snapshot(cur, product_id)
        if not before:
            return ApiOk(ok=False, message="商品不存在")
        if not _can_edit_product(cur, before, user):
            return ApiOk(ok=False, message="仅任务创建人可修改本次草稿，正式资料仅超级管理员可修改")
        changes = {k: body.get(k) for k in EDITABLE_FIELDS if k in body}
        if not changes:
            return ApiOk(ok=False, message="没有可修改字段")
        sets = []
        params = {"id": product_id}
        for key, value in changes.items():
            sets.append(f"{key.upper()}=:{key}")
            params[key] = value
        sets.append("UPDATE_TIME=SYSTIMESTAMP")
        cur.execute(f"UPDATE SJZQ_PRODUCT SET {', '.join(sets)} WHERE PRODUCT_ID=:id", params)
        after = _snapshot(cur, product_id)
        _record_change(cur, product_id, "update", before, after, user)
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="product_update",
                     module="product", detail=f"修改商品 #{product_id}", ip=request.client.host if request.client else None)
        return ApiOk(message="已保存", data=after)


@router.delete("/{product_id}")
def delete_product(product_id: int, request: Request, user=Depends(require_perms("data:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        before = _snapshot(cur, product_id)
        if not before:
            return ApiOk(ok=False, message="商品不存在")
        if not _can_edit_product(cur, before, user):
            return ApiOk(ok=False, message="没有删除权限")
        cur.execute("UPDATE SJZQ_PRODUCT SET IS_DELETED=1, UPDATE_TIME=SYSTIMESTAMP WHERE PRODUCT_ID=:id", {"id": product_id})
        _record_change(cur, product_id, "delete", before, None, user)
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="product_delete",
                     module="product", detail=f"删除商品 #{product_id}", ip=request.client.host if request.client else None)
        return ApiOk(message="已删除")


@router.post("/save-batch")
def save_products(body: dict, request: Request, user=Depends(require_perms("data:view"))):
    ids = [int(x) for x in body.get("product_ids", []) if str(x).isdigit()]
    if not ids:
        return ApiOk(ok=False, message="请选择商品")
    saved = 0
    with get_conn() as conn:
        cur = conn.cursor()
        for pid in ids[:500]:
            before = _snapshot(cur, pid)
            if not before or not _can_edit_product(cur, before, user):
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

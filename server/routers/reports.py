"""销量、价格段、热门规格和多盒装单盒价分析。"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from server.tenant import require_tenant_perms
from server.db import get_conn, rows_as_dicts
from server.schemas import ApiOk
from server.services import clob_to_str
from server.product_contract import effective_price, effective_price_sql

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sku_rows(raw_json, raw_text: str) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    text = clob_to_str(raw_json) or ""
    try:
        obj = json.loads(text) if text else []
    except Exception:
        obj = []
    if isinstance(obj, dict):
        obj = obj.get("rows") or obj.get("skus") or obj.get("data") or []
    if isinstance(obj, list):
        for item in obj:
            if not isinstance(item, dict):
                continue
            spec = str(item.get("spec") or item.get("name") or item.get("sku_name") or "")
            price = _number(effective_price({
                "single_purchase_price": item.get("single_purchase_price", item.get("deal_price")),
                "detail_price": item.get("detail_price", item.get("normal_price", item.get("price"))),
                "group_price": item.get("group_price"),
                "list_price": item.get("list_price"),
                "original_price": item.get("original_price"),
            }))
            if spec and price is not None:
                rows.append((spec, price))
    if not rows:
        for line in (raw_text or "").splitlines():
            box = re.search(r"(\d+)\s*盒", line)
            price = re.search(r"(?:单买|到手|售价|价格)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)\s*元?", line)
            if box and price:
                rows.append((box.group(0), float(price.group(1))))
    return rows


@router.get("/overview")
def overview(
    platform_code: str = "pinduoduo",
    bucket_size: int = Query(20, ge=1, le=1000),
    product_name: str | None = None,
    spec: str | None = None,
    manufacturer: str | None = None,
    approval_no: str | None = None,
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    tenant=Depends(require_tenant_perms("report:view")),
):
    with get_conn() as conn:
        cur = conn.cursor()
        base = effective_price_sql()
        clauses = ["PLATFORM_CODE=:platform", "NVL(IS_DELETED,0)=0", "NVL(LIBRARY_STATUS,'saved')='saved'",
                   "ENTERPRISE_ID=:enterprise_id", "WORKSPACE_ID=:workspace_id"]
        params: dict = {"platform": platform_code, **tenant.binds}
        if product_name:
            clauses.append("(PRODUCT_NAME LIKE :product_name OR SELL_NAME LIKE :product_name OR KEYWORD LIKE :product_name)")
            params["product_name"] = f"%{product_name}%"
        if spec:
            clauses.append("SPEC_TEXT LIKE :spec")
            params["spec"] = f"%{spec}%"
        if manufacturer:
            clauses.append("MANUFACTURER LIKE :manufacturer")
            params["manufacturer"] = f"%{manufacturer}%"
        if approval_no:
            clauses.append("APPROVAL_NO LIKE :approval_no")
            params["approval_no"] = f"%{approval_no}%"
        if min_price is not None:
            clauses.append(f"{base}>=:min_price")
            params["min_price"] = min_price
        if max_price is not None:
            clauses.append(f"{base}<=:max_price")
            params["max_price"] = max_price
        where_sql = " AND ".join(clauses)
        cur.execute(
            f"""
            SELECT PRODUCT_ID, PRODUCT_NAME, SELL_NAME, SPEC_TEXT, MANUFACTURER,
                   {base} EFFECTIVE_PRICE, NVL(SALES_NUM,0) SALES_NUM, COLLECT_TIME
              FROM SJZQ_PRODUCT
             WHERE {where_sql} AND {base} IS NOT NULL
             ORDER BY NVL(SALES_NUM,0) DESC, PRODUCT_ID DESC
             FETCH FIRST 20 ROWS ONLY
            """,
            params,
        )
        top_sales = rows_as_dicts(cur)
        cur.execute(
            f"""
            SELECT PRODUCT_ID, PRODUCT_NAME, SELL_NAME, SPEC_TEXT,
                   {base} EFFECTIVE_PRICE, NVL(SALES_NUM,0) SALES_NUM, COLLECT_TIME
              FROM SJZQ_PRODUCT
             WHERE {where_sql} AND {base} IS NOT NULL
             ORDER BY {base} ASC, NVL(SALES_NUM,0) DESC
             FETCH FIRST 20 ROWS ONLY
            """,
            params,
        )
        lowest_prices = rows_as_dicts(cur)
        cur.execute(
            f"SELECT {base} EFFECTIVE_PRICE, NVL(SALES_NUM,0) SALES_NUM FROM SJZQ_PRODUCT WHERE {where_sql} AND {base} IS NOT NULL",
            params,
        )
        buckets: dict[int, dict] = {}
        for price, sales in cur.fetchall():
            p = float(price)
            start = int(p // bucket_size) * bucket_size
            item = buckets.setdefault(start, {"range": f"¥{start}-¥{start + bucket_size}", "product_count": 0, "sales_total": 0})
            item["product_count"] += 1
            item["sales_total"] += int(sales or 0)
        price_segments = [buckets[k] for k in sorted(buckets)]

        cur.execute(
            f"""
            SELECT SPEC_TEXT, COUNT(*) PRODUCT_COUNT, SUM(NVL(SALES_NUM,0)) SALES_TOTAL
              FROM SJZQ_PRODUCT
             WHERE {where_sql} AND SPEC_TEXT IS NOT NULL
             GROUP BY SPEC_TEXT
             ORDER BY SUM(NVL(SALES_NUM,0)) DESC, COUNT(*) DESC
             FETCH FIRST 30 ROWS ONLY
            """,
            params,
        )
        popular_specs = rows_as_dicts(cur)

        cur.execute(
            f"""
            SELECT PRODUCT_ID, PRODUCT_NAME, SELL_NAME, SKU_PRICES_JSON, SKU_PRICES_TEXT
              FROM SJZQ_PRODUCT
             WHERE {where_sql} AND (SKU_PRICES_JSON IS NOT NULL OR SKU_PRICES_TEXT IS NOT NULL)
             ORDER BY PRODUCT_ID DESC FETCH FIRST 500 ROWS ONLY
            """,
            params,
        )
        unit_prices = []
        for product_id, product_name, sell_name, sku_json, sku_text in cur.fetchall():
            for spec, total_price in _sku_rows(sku_json, sku_text or ""):
                match = re.search(r"(\d+)\s*盒", spec)
                if not match or int(match.group(1)) <= 0:
                    continue
                boxes = int(match.group(1))
                unit_prices.append({
                    "product_id": int(product_id), "product_name": product_name or sell_name,
                    "spec": spec, "boxes": boxes, "total_price": round(total_price, 2),
                    "unit_price": round(total_price / boxes, 2),
                })
        unit_prices.sort(key=lambda x: (x["unit_price"], -x["boxes"]))

        cur.execute(f"SELECT COUNT(*), SUM(NVL(SALES_NUM,0)), AVG({base}) FROM SJZQ_PRODUCT WHERE {where_sql}", params)
        product_count, sales_total, avg_price = cur.fetchone()
        return ApiOk(data={
            "summary": {"product_count": int(product_count or 0), "sales_total": int(sales_total or 0), "avg_price": round(float(avg_price or 0), 2)},
            "top_sales": top_sales,
            "lowest_prices": lowest_prices,
            "price_segments": price_segments,
            "popular_specs": popular_specs,
            "multi_box_unit_prices": unit_prices[:50],
        })

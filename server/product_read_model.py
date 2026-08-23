"""Canonical Product Read Model over legacy and strict-protocol storage."""

from __future__ import annotations

import json
from typing import Any, Mapping

from server.db import row_as_dict, rows_as_dicts
from server.media_access import signed_media_url
from server.product_contract import effective_price


def _json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if hasattr(value, "read"):
        value = value.read()
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _sku_combinations(value: Any) -> list[dict[str, Any]]:
    parsed = _json(value, [])
    if isinstance(parsed, dict):
        parsed = parsed.get("rows") or parsed.get("skus") or parsed.get("data") or []
    if not isinstance(parsed, list):
        return []
    result = []
    for item in parsed:
        if not isinstance(item, Mapping):
            continue
        result.append({
            "platform_sku_id": item.get("platform_sku_id") or item.get("sku_id"),
            "selected_options": item.get("selected_options") or [],
            "spec_text": item.get("spec") or item.get("name") or item.get("sku_name"),
            "list_price": item.get("list_price"),
            "detail_price": item.get("detail_price") or item.get("normal_price") or item.get("price"),
            "single_purchase_price": item.get("single_purchase_price") or item.get("deal_price"),
            "group_price": item.get("group_price"),
            "original_price": item.get("original_price"),
            "availability": item.get("availability"),
            "stock": item.get("stock"),
            "evidence_source": item.get("evidence_source") or "legacy_sku_json",
        })
    return result


def _attributes(value: Any) -> list[dict[str, str]]:
    parsed = _json(value, [])
    if not isinstance(parsed, list):
        return []
    return [
        {"name": str(item.get("key") or item.get("name") or ""),
         "value": str(item.get("value") or "")}
        for item in parsed if isinstance(item, Mapping) and (item.get("key") or item.get("name"))
    ]


def _snapshot(cur: Any, product: Mapping[str, Any], tenant: Any) -> dict[str, Any] | None:
    snapshot_id = product.get("snapshot_id")
    if snapshot_id is None:
        return None
    cur.execute(
        """SELECT * FROM SJZQ_PRODUCT_SNAPSHOT
             WHERE SNAPSHOT_ID=:snapshot_id AND ENTERPRISE_ID=:enterprise_id
               AND WORKSPACE_ID=:workspace_id""",
        {"snapshot_id": snapshot_id, **tenant.binds},
    )
    return row_as_dict(cur)


def load_canonical_product(cur: Any, product_id: int, tenant: Any) -> dict[str, Any] | None:
    cur.execute(
        """SELECT * FROM SJZQ_PRODUCT
             WHERE PRODUCT_ID=:product_id AND NVL(IS_DELETED,0)=0
               AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
        {"product_id": product_id, **tenant.binds},
    )
    product = row_as_dict(cur)
    if not product:
        return None

    snapshot = _snapshot(cur, product, tenant)
    normalized = _json(snapshot.get("normalized_json") if snapshot else None, {})

    def observed(canonical: str, legacy: str) -> Any:
        return normalized[canonical] if canonical in normalized else product.get(legacy)

    observation = {
        "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
        "observed_at": snapshot.get("collected_at") if snapshot else product.get("collect_time"),
        "list_price": observed("price", "price"),
        "detail_price": observed("display_price", "display_price"),
        "single_purchase_price": observed("deal_price", "deal_price"),
        "group_price": observed("group_price", "group_price"),
        "original_price": observed("original_price", "original_price"),
        "sales": observed("sales_num", "sales_num"),
        "shop_sales": observed("shop_sales_num", "shop_sales_num"),
        "comment_count": observed("comment_num", "comment_num"),
        "promotion": observed("promotion", "coupon_info"),
        "availability": observed("availability", "page_status"),
        "shop_name": observed("shop_name", "shop_name"),
        "shop_id": observed("shop_id", "shop_id"),
        "source": "product_snapshot" if snapshot else "legacy_product_observation",
    }
    observation["effective_price"] = effective_price(observation)

    snapshot_sku = snapshot.get("sku_json") if snapshot else None
    combinations = _sku_combinations(snapshot_sku)
    if not combinations:
        combinations = _sku_combinations(product.get("sku_prices_json"))

    cur.execute(
        """SELECT IMAGE_ID,SORT_NO,FILE_NAME,REL_PATH,SOURCE_URL,FILE_SIZE,CONTENT_TYPE
             FROM SJZQ_PRODUCT_IMAGE WHERE PRODUCT_ID=:product_id
             ORDER BY SORT_NO,IMAGE_ID""",
        {"product_id": product_id},
    )
    media = []
    for image in rows_as_dicts(cur):
        rel = image.get("rel_path") or ""
        media.append({
            "media_id": image.get("image_id"), "media_type": "image",
            "sort_order": image.get("sort_no"), "file_name": image.get("file_name"),
            "url": signed_media_url(rel, tenant.enterprise_id, tenant.workspace_id)
            if rel else image.get("source_url"),
            "file_size": image.get("file_size"), "content_type": image.get("content_type"),
        })

    raw_id = snapshot.get("raw_id") if snapshot else None
    provenance = {
        "status": "available" if raw_id else "unavailable",
        "reason": None if raw_id else "legacy_product_has_no_raw_or_snapshot_link",
        "raw_id": raw_id,
        "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
        "field_sources": _json(snapshot.get("field_sources") if snapshot else product.get("field_sources"), {}),
        "parser_version": snapshot.get("parser_version") if snapshot else product.get("parser_version"),
        "quality_rules_version": snapshot.get("quality_rules_version") if snapshot else product.get("quality_rules_version"),
    }

    return {
        "identity": {
            "product_id": product.get("product_id"),
            "platform_code": product.get("platform_code"),
            "platform_product_id": product.get("item_id"),
            "master_product_id": product.get("master_product_id"),
            "enterprise_product_id": product.get("enterprise_product_id"),
            "source_url": product.get("item_url"),
        },
        "stable_profile": {
            "platform_title": product.get("sell_name"),
            "canonical_name": product.get("product_name"),
            "brand": product.get("brand"),
            "product_attribute_spec": product.get("spec_text"),
            "approval_number": product.get("approval_no"),
            "manufacturer": product.get("manufacturer"),
            "dosage_form": product.get("dosage_form"),
            "category": product.get("category"),
            "expiry": product.get("expiry_text"),
            "attributes": _attributes(product.get("spec_list")),
        },
        "latest_observation": observation,
        "sku": {
            "sku_dimensions": [],
            "sku_dimensions_state": "not_observed",
            "sku_combinations": combinations,
            "source": "snapshot_sku_json" if snapshot_sku and combinations else "legacy_sku_prices_json",
        },
        "media": media,
        "provenance": provenance,
        "quality": {
            "parse_status": snapshot.get("parse_status") if snapshot else product.get("parse_status"),
            "page_status": snapshot.get("page_status") if snapshot else product.get("page_status"),
            "quality_status": snapshot.get("quality_status") if snapshot else product.get("quality_status"),
        },
        "capture_context": {
            "task_id": product.get("task_id"), "device_id": product.get("device_id"),
            "keyword": product.get("keyword"), "library_status": product.get("library_status"),
            "collected_at": product.get("collect_time"),
        },
    }


def edit_dto(model: Mapping[str, Any], scope: str) -> dict[str, Any]:
    profile = dict(model["stable_profile"])
    profile.pop("attributes", None)
    return {
        "product_id": model["identity"]["product_id"],
        "scope": scope,
        **profile,
    }

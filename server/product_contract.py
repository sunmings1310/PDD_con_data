"""Frozen P0 product semantics, price policy and editable-field policy.

This module is the single compatibility boundary between canonical API names and
the legacy ``SJZQ_PRODUCT`` column names.  Dynamic observations are deliberately
absent from ``EDITABLE_STABLE_FIELDS``.
"""

from __future__ import annotations

from typing import Any, Mapping


LEGACY_FIELD_MAP = {
    "platform_title": "sell_name",
    "canonical_name": "product_name",
    "product_attribute_spec": "spec_text",
    "sku_combinations": "sku_prices_json",
}

PRICE_FIELDS = (
    "list_price",
    "detail_price",
    "single_purchase_price",
    "group_price",
    "original_price",
)

# Effective/display policy is frozen here.  It is not evidence rewriting: all
# five source prices remain independently available on ObservationDTO.
EFFECTIVE_PRICE_PRIORITY = (
    "single_purchase_price",
    "detail_price",
    "group_price",
    "list_price",
    "original_price",
)

LEGACY_PRICE_MAP = {
    "list_price": "price",
    "detail_price": "display_price",
    "single_purchase_price": "deal_price",
    "group_price": "group_price",
    "original_price": "original_price",
}

EDITABLE_STABLE_FIELDS = {
    "platform_title": "SELL_NAME",
    "canonical_name": "PRODUCT_NAME",
    "brand": "BRAND",
    "product_attribute_spec": "SPEC_TEXT",
    "approval_number": "APPROVAL_NO",
    "manufacturer": "MANUFACTURER",
    "dosage_form": "DOSAGE_FORM",
    "category": "CATEGORY",
    "expiry": "EXPIRY_TEXT",
}

# Accepted only at the compatibility PUT boundary; responses and Web clients use
# canonical names exclusively.
LEGACY_STABLE_ALIASES = {
    "sell_name": "platform_title",
    "product_name": "canonical_name",
    "spec_text": "product_attribute_spec",
    "approval_no": "approval_number",
    "expiry_text": "expiry",
}

DYNAMIC_IMMUTABLE_FIELDS = frozenset({
    *PRICE_FIELDS,
    "price", "display_price", "deal_price", "group_price", "original_price",
    "sales", "sales_num", "shop_sales", "shop_sales_num",
    "comment_count", "comment_num", "promotion", "coupon_info", "stock",
    "availability", "sku", "sku_dimensions", "sku_combinations",
    "sku_prices", "sku_prices_json", "sku_prices_text", "observed_price",
})

RAW_IMMUTABLE_FIELDS = frozenset({
    "raw", "raw_json", "raw_capture", "raw_id", "snapshot", "snapshot_id",
    "provenance", "field_sources", "parser_version", "quality_rules_version",
})


def normalize_stable_edit(payload: Mapping[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Return canonical stable edits and all unsupported keys."""

    canonical: dict[str, Any] = {}
    unsupported: set[str] = set()
    for key, value in payload.items():
        if key in {"product_id", "scope"}:
            continue
        normalized = LEGACY_STABLE_ALIASES.get(key, key)
        if normalized not in EDITABLE_STABLE_FIELDS:
            unsupported.add(key)
            continue
        if normalized in canonical and canonical[normalized] != value:
            unsupported.add(key)
            continue
        canonical[normalized] = value
    return canonical, unsupported


def effective_price(values: Mapping[str, Any]) -> Any:
    """Return the single frozen effective price without changing source values."""

    for canonical in EFFECTIVE_PRICE_PRIORITY:
        legacy = LEGACY_PRICE_MAP[canonical]
        value = values.get(canonical, values.get(legacy))
        if value is not None and value != "":
            return value
    return None


def effective_price_sql() -> str:
    """Oracle expression equivalent to :func:`effective_price`."""

    return "COALESCE(DEAL_PRICE, DISPLAY_PRICE, GROUP_PRICE, PRICE, ORIGINAL_PRICE)"

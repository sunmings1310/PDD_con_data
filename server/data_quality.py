"""Phase 3 versioned normalization, quality decisions and snapshot differences."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from typing import Any, Mapping

from server.collectors import DynamicField, PlatformIdentity, collector_registry


QUALITY_RULES_VERSION = "phase3-1"
MAX_PRICE = Decimal("10000000")

SOURCE_ALIASES = {
    "detail": "detail_response",
    "fixture": "normalized_result",
    "name": "detail_text",
    "detail_or_share": "detail_response",
    "share_or_derived": "derived",
    "list_or_detail": "detail_response",
}
FIELD_ALIASES = {"name": "title", "sales": "sales_num", "itemid": "item_id"}
ALLOWED_SOURCES = frozenset({
    "search_response", "detail_response", "embedded_state", "list_card",
    "detail_text", "sku_panel", "share_link", "network", "embedded_json",
    "dom", "url", "normalized_result", "inferred", "derived", "none",
})


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    page_status: str
    parse_status: str
    quality_status: str
    missing_fields: tuple[str, ...]
    error_codes: tuple[str, ...]
    warnings: tuple[str, ...]
    parser_version: str
    quality_rules_version: str = QUALITY_RULES_VERSION

    @property
    def failure_reason(self) -> str:
        return ",".join((*self.error_codes, *(f"missing:{name}" for name in self.missing_fields)))


@dataclass(frozen=True)
class SnapshotDiff:
    changes: Mapping[str, Mapping[str, Any]]

    @property
    def changed_fields(self) -> tuple[str, ...]:
        return tuple(self.changes)

    def changed(self, name: str) -> bool:
        return name in self.changes


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def normalize_sources(raw: Mapping[str, Any] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field, source in (raw or {}).items():
        raw_name = str(field).strip().lower()
        name = FIELD_ALIASES.get(raw_name, raw_name)
        value = SOURCE_ALIASES.get(str(source).strip().lower(), str(source).strip().lower())
        if name:
            normalized[name] = value
    return normalized


def _sku_value(source: Any) -> tuple[Any, str | None]:
    raw = _value(source, "sku_prices") or _value(source, "sku_prices_text")
    if raw in (None, "", [], {}):
        return None, None
    if isinstance(raw, (list, dict)):
        parsed = raw
    else:
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError):
            return None, "SKU_INVALID_JSON"
    if not isinstance(parsed, (list, dict)):
        return None, "SKU_INVALID_STRUCTURE"
    rows = parsed if isinstance(parsed, list) else list(parsed.values())
    for row in rows:
        if not isinstance(row, Mapping):
            return None, "SKU_INVALID_STRUCTURE"
        for key in ("price", "group_price", "normal_price", "deal_price"):
            if key in row and row[key] is not None:
                price = _decimal(row[key])
                if price is None or price <= 0 or price > MAX_PRICE:
                    return None, "SKU_INVALID_PRICE"
    return parsed, None


def evaluate(source: Any, *, quality_rules_version: str = QUALITY_RULES_VERSION) -> QualityDecision:
    """Apply the single server-authoritative Phase 3 quality gate."""

    page_status = str(_value(source, "page_status", "unknown") or "unknown").lower()
    supplied_parse = str(_value(source, "parse_status", "") or "").lower()
    parser_version = str(_value(source, "parser_version", "") or "").strip()
    client_rules_version = str(_value(source, "quality_rules_version", "") or "").strip()
    missing: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    if page_status != "product":
        errors.append(f"PAGE_{page_status.upper()}")
    if supplied_parse not in {"success", "partial", "failed", "not_attempted"}:
        errors.append("PARSE_STATUS_UNKNOWN")
    elif supplied_parse in {"failed", "not_attempted"}:
        errors.append(f"PARSE_{supplied_parse.upper()}")

    platform = str(_value(source, "platform_code", "") or "").strip().lower()
    collector = collector_registry.get(platform) if platform else None
    item_id = str(_value(source, "item_id", "") or "").strip()
    title = str(_value(source, "sell_name", "") or _value(source, "product_name", "") or "").strip()
    if not platform:
        missing.append("platform_code")
    if not item_id:
        missing.append("platform_product_id")
    elif platform:
        if collector is None:
            errors.append("PLATFORM_NOT_SUPPORTED")
        elif not collector.validate_identity(
            PlatformIdentity(platform=platform, platform_product_id=item_id)
        ):
            errors.append("IDENTITY_INVALID")
    if not title:
        missing.append("title")
    if not parser_version:
        missing.append("parser_version")
    if not client_rules_version:
        missing.append("quality_rules_version")

    valid_prices: list[Decimal] = []
    for field in ("price", "display_price", "group_price", "deal_price"):
        raw = _value(source, field)
        if raw is None:
            continue
        value = _decimal(raw)
        if value is None or value <= 0 or value > MAX_PRICE:
            errors.append(f"{field.upper()}_INVALID")
        else:
            valid_prices.append(value)
    if not valid_prices:
        missing.append("price")
    original = _value(source, "original_price")
    if original is not None:
        original_value = _decimal(original)
        if original_value is None or original_value <= 0 or original_value > MAX_PRICE:
            errors.append("ORIGINAL_PRICE_INVALID")
        elif valid_prices and original_value < min(valid_prices):
            warnings.append("original_price_below_current")

    sales = _value(source, "sales_num")
    if collector is not None and DynamicField.SALES in collector.capabilities.dynamic_fields:
        if sales is None:
            warnings.append("sales_missing")
        elif isinstance(sales, bool) or not isinstance(sales, int) or sales < 0:
            errors.append("SALES_INVALID")

    sku, sku_error = _sku_value(source)
    if collector is not None and DynamicField.SKU_PRICE in collector.capabilities.dynamic_fields:
        if sku_error:
            errors.append(sku_error)
        elif sku is None:
            warnings.append("sku_missing")

    sources = normalize_sources(_value(source, "field_sources", {}) or {})
    required_sources = {"item_id", "price", "title"}
    if sales is not None:
        required_sources.add("sales_num")
    if sku is not None:
        required_sources.add("sku")
    if _value(source, "shop_name") or _value(source, "shop_id"):
        required_sources.add("shop")
    for field in sorted(required_sources):
        src = sources.get(field)
        if not src:
            errors.append(f"FIELD_SOURCE_MISSING:{field}")
        elif src not in ALLOWED_SOURCES:
            errors.append(f"FIELD_SOURCE_UNKNOWN:{field}:{src}")

    errors = list(dict.fromkeys(errors))
    missing = list(dict.fromkeys(missing))
    warnings = list(dict.fromkeys(warnings))
    accepted = page_status == "product" and not missing and not errors
    return QualityDecision(
        accepted=accepted,
        page_status=page_status,
        parse_status=("failed" if not accepted else ("partial" if warnings or supplied_parse == "partial" else "success")),
        quality_status=("quarantined" if not accepted else ("warning" if warnings else "passed")),
        missing_fields=tuple(missing),
        error_codes=tuple(errors),
        warnings=tuple(warnings),
        parser_version=parser_version,
        quality_rules_version=quality_rules_version,
    )


def normalized_snapshot(source: Any, decision: QualityDecision) -> dict[str, Any]:
    sku, _ = _sku_value(source)
    values = {
        "platform_code": str(_value(source, "platform_code", "") or "").strip().lower(),
        "platform_product_id": str(_value(source, "item_id", "") or "").strip(),
        "title": str(_value(source, "sell_name", "") or _value(source, "product_name", "") or "").strip(),
        "shop_name": str(_value(source, "shop_name", "") or "").strip() or None,
        "shop_id": str(_value(source, "shop_id", "") or "").strip() or None,
        "availability": "available" if decision.page_status == "product" else decision.page_status,
        "price": _number(_value(source, "price")),
        "display_price": _number(_value(source, "display_price")),
        "group_price": _number(_value(source, "group_price")),
        "deal_price": _number(_value(source, "deal_price")),
        "original_price": _number(_value(source, "original_price")),
        "sales_num": _value(source, "sales_num"),
        "sku": sku,
        "field_sources": normalize_sources(_value(source, "field_sources", {}) or {}),
        "parser_version": decision.parser_version,
        "quality_rules_version": decision.quality_rules_version,
        "parse_status": decision.parse_status,
        "page_status": decision.page_status,
        "quality_status": decision.quality_status,
    }
    return values


def _number(value: Any) -> float | None:
    decimal = _decimal(value)
    return float(decimal) if decimal is not None else None


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def detect_difference(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> SnapshotDiff:
    if previous is None:
        return SnapshotDiff({})
    groups = {
        "price": ("price", "display_price", "group_price", "deal_price", "original_price"),
        "sales": ("sales_num",),
        "sku": ("sku",),
        "availability": ("availability",),
        "title": ("title",),
        "shop": ("shop_name", "shop_id"),
    }
    changes: dict[str, Mapping[str, Any]] = {}
    for name, fields in groups.items():
        before = {field: previous.get(field) for field in fields}
        after = {field: current.get(field) for field in fields}
        if canonical_json(before) != canonical_json(after):
            changes[name] = {"before": before, "after": after}
    return SnapshotDiff(changes)

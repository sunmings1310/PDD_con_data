"""Pure Phase-1 page classification and minimum product quality gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from server.collectors import DynamicField, PlatformIdentity, collector_registry


DEFAULT_PLATFORM = collector_registry.platforms()[0]
PARSER_VERSION = collector_registry.require(DEFAULT_PLATFORM).parser_version
QUALITY_RULES_VERSION = "phase1-1"


class PageStatus(str, Enum):
    PRODUCT = "product"
    LOGIN_REQUIRED = "login_required"
    CHALLENGE = "challenge"
    BUSY = "busy"
    SOLD_OUT = "sold_out"
    NOT_FOUND = "not_found"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"


class ParseStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


class QualityStatus(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class QualityResult:
    page_status: PageStatus
    parse_status: ParseStatus
    quality_status: QualityStatus
    missing_fields: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return (
            self.page_status == PageStatus.PRODUCT
            and self.parse_status in {ParseStatus.SUCCESS, ParseStatus.PARTIAL}
            and self.quality_status in {QualityStatus.PASSED, QualityStatus.WARNING}
        )


def classify_page(text: str, platform: str | None = None) -> PageStatus:
    """Classify rendered page text before product parsing."""
    collector = collector_registry.get(platform or DEFAULT_PLATFORM)
    if collector is None:
        return PageStatus.UNKNOWN
    try:
        return PageStatus(collector.classify_page(text))
    except ValueError:
        return PageStatus.UNKNOWN


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _valid_item_url(platform: str, item_id: str, item_url: str) -> bool:
    collector = collector_registry.get(platform)
    if collector is None:
        return False
    return collector.validate_item_url(
        PlatformIdentity(platform=platform, platform_product_id=item_id),
        item_url,
    )


def evaluate_product(source: Any) -> QualityResult:
    """Recompute server-authoritative minimum quality from structured fields."""

    raw_page_status = str(_value(source, "page_status", PageStatus.UNKNOWN.value) or "").lower()
    try:
        page_status = PageStatus(raw_page_status)
    except ValueError:
        page_status = PageStatus.UNKNOWN
    if page_status != PageStatus.PRODUCT:
        return QualityResult(
            page_status=page_status,
            parse_status=ParseStatus.NOT_ATTEMPTED,
            quality_status=QualityStatus.QUARANTINED,
            missing_fields=(),
            errors=(f"page_status:{page_status.value}",),
            warnings=(),
        )

    platform = str(_value(source, "platform_code", DEFAULT_PLATFORM) or "").strip().lower()
    collector = collector_registry.get(platform)
    item_id = str(_value(source, "item_id", "") or "").strip()
    name = str(_value(source, "sell_name", "") or _value(source, "product_name", "") or "").strip()
    item_url = str(_value(source, "item_url", "") or "").strip()
    prices = [
        _value(source, "price"),
        _value(source, "display_price"),
        _value(source, "group_price"),
        _value(source, "deal_price"),
    ]
    valid_prices = [float(value) for value in prices if isinstance(value, (int, float)) and float(value) > 0]

    missing: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    if not item_id:
        missing.append("item_id")
    if not name:
        missing.append("name")
    if not item_url:
        missing.append("item_url")
    elif item_id and not _valid_item_url(platform, item_id, item_url):
        errors.append("item_url_mismatch")
    if not valid_prices:
        missing.append("price")
    original_price = _value(source, "original_price")
    if isinstance(original_price, (int, float)) and float(original_price) <= 0:
        errors.append("invalid_original_price")
    if (
        collector is not None
        and DynamicField.SKU_PRICE in collector.capabilities.dynamic_fields
        and not str(_value(source, "sku_prices", "") or _value(source, "sku_prices_text", "") or "").strip()
    ):
        warnings.append("sku_missing")
    if (
        collector is not None
        and DynamicField.SALES in collector.capabilities.dynamic_fields
        and _value(source, "sales_num") is None
    ):
        warnings.append("sales_missing")

    if missing or errors:
        return QualityResult(
            page_status=page_status,
            parse_status=ParseStatus.FAILED,
            quality_status=QualityStatus.QUARANTINED,
            missing_fields=tuple(missing),
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
    return QualityResult(
        page_status=page_status,
        parse_status=ParseStatus.PARTIAL if warnings else ParseStatus.SUCCESS,
        quality_status=QualityStatus.WARNING if warnings else QualityStatus.PASSED,
        missing_fields=(),
        errors=(),
        warnings=tuple(warnings),
    )

"""Pure Phase-1 page classification and minimum product quality gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse


PARSER_VERSION = "pdd-android-1"
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


def classify_page(text: str) -> PageStatus:
    """Classify rendered page text before product parsing."""

    value = (text or "").replace("\u200b", "").strip()
    compact = "".join(value.split())
    if not compact:
        return PageStatus.MALFORMED
    if any(marker in compact for marker in ("登录后继续", "手机号登录", "手机登录", "验证码登录", "请先登录")):
        return PageStatus.LOGIN_REQUIRED
    if any(marker in compact for marker in ("完成验证", "安全验证", "拖动滑块", "操作频繁", "验证后继续")):
        return PageStatus.CHALLENGE
    if any(marker in compact for marker in ("系统繁忙", "访问人数较多", "网络繁忙", "稍后再试")):
        return PageStatus.BUSY
    if any(marker in compact for marker in ("商品已售罄", "已下架", "商品已下架")):
        return PageStatus.SOLD_OUT
    if any(marker in compact for marker in ("商品不存在", "商品已失效", "页面不存在", "找不到该商品")):
        return PageStatus.NOT_FOUND
    product_markers = ("商品详情", "立即购买", "免拼购买", "单独购买", "去拼单", "拼单价", "已拼")
    if sum(marker in compact for marker in product_markers) >= 2:
        return PageStatus.PRODUCT
    return PageStatus.MALFORMED


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _valid_item_url(platform: str, item_id: str, item_url: str) -> bool:
    try:
        parsed = urlparse(item_url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if platform != "pinduoduo":
        return bool(item_id)
    if not item_id.isdigit() or "yangkeduo.com" not in parsed.netloc.lower():
        return False
    values = parse_qs(parsed.query).get("goods_id", [])
    return item_id in values


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

    platform = str(_value(source, "platform_code", "pinduoduo") or "").strip().lower()
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
    if not str(_value(source, "sku_prices", "") or _value(source, "sku_prices_text", "") or "").strip():
        warnings.append("sku_missing")
    if _value(source, "sales_num") is None:
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

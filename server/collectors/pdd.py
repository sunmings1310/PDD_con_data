"""Pinduoduo adapter preserving the existing identity and error semantics."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from server.collectors.contract import (
    CollectorCapabilities,
    CollectorCapability,
    DynamicField,
    IdentityKind,
    PlatformIdentity,
    SystemCollectorError,
)


class PddCollector:
    platform = "pinduoduo"
    parser_version = "pdd-android-1"
    capabilities = CollectorCapabilities(
        capabilities=frozenset(
            {
                CollectorCapability.SEARCH,
                CollectorCapability.DETAIL,
                CollectorCapability.PRICE_SORT,
                CollectorCapability.SALES_SORT,
                CollectorCapability.OFFSET_PAGINATION,
            }
        ),
        identities=frozenset({IdentityKind.PRODUCT}),
        dynamic_fields=frozenset(
            {
                DynamicField.PRICE,
                DynamicField.ORIGINAL_PRICE,
                DynamicField.SALES,
                DynamicField.SKU_PRICE,
                DynamicField.PROMOTION,
            }
        ),
    )

    def classify_page(self, text: str) -> str:
        compact = "".join((text or "").replace("\u200b", "").split())
        if not compact:
            return "malformed"
        if any(marker in compact for marker in ("登录后继续", "手机号登录", "手机登录", "验证码登录", "请先登录")):
            return "login_required"
        if any(marker in compact for marker in ("完成验证", "安全验证", "拖动滑块", "操作频繁", "验证后继续")):
            return "challenge"
        if any(marker in compact for marker in ("系统繁忙", "访问人数较多", "网络繁忙", "稍后再试")):
            return "busy"
        if any(marker in compact for marker in ("商品已售罄", "已下架", "商品已下架")):
            return "sold_out"
        if any(marker in compact for marker in ("商品不存在", "商品已失效", "页面不存在", "找不到该商品")):
            return "not_found"
        markers = ("商品详情", "立即购买", "免拼购买", "单独购买", "去拼单", "拼单价", "已拼")
        return "product" if sum(marker in compact for marker in markers) >= 2 else "malformed"

    def validate_identity(self, identity: PlatformIdentity) -> bool:
        return (
            identity.platform.strip().lower() == self.platform
            and bool(identity.platform_product_id)
            and identity.platform_product_id.isdigit()
            and identity.platform_sku_id is None
        )

    def validate_item_url(self, identity: PlatformIdentity, item_url: str) -> bool:
        if not self.validate_identity(identity):
            return False
        try:
            parsed = urlparse(item_url)
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"} or "yangkeduo.com" not in parsed.netloc.lower():
            return False
        return identity.platform_product_id in parse_qs(parsed.query).get("goods_id", [])

    def map_error(self, platform_error: str) -> SystemCollectorError:
        value = (platform_error or "").strip().lower()
        if value in {"login_required", "auth_required"}:
            return SystemCollectorError.AUTH_REQUIRED
        if value in {"challenge", "risk", "verification_required"}:
            return SystemCollectorError.MANUAL_INTERVENTION_REQUIRED
        if value in {"busy", "rate_limited", "too_many_requests"}:
            return SystemCollectorError.RATE_LIMITED
        if value in {"not_found", "item_not_found"}:
            return SystemCollectorError.ITEM_NOT_FOUND
        if value in {"sold_out", "delisted", "item_unavailable"}:
            return SystemCollectorError.ITEM_UNAVAILABLE
        if value in {"parse_error", "malformed"}:
            return SystemCollectorError.PARSE_ERROR
        if value in {"quality_failed", "quarantined"}:
            return SystemCollectorError.DATA_QUALITY_FAILURE
        return SystemCollectorError.TEMPORARY_FAILURE

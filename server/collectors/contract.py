"""Small platform-neutral collector contract used by core services.

The server does not execute the Android UI collector.  It consumes the same
declared capabilities, identity semantics and system error vocabulary so that
quality/task code does not need platform conditionals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


class CollectorCapability(str, Enum):
    SEARCH = "search"
    DETAIL = "detail"
    PRICE_SORT = "price_sort"
    SALES_SORT = "sales_sort"
    OFFSET_PAGINATION = "offset_pagination"
    CURSOR_PAGINATION = "cursor_pagination"


class IdentityKind(str, Enum):
    PRODUCT = "platform_product_id"
    SKU = "platform_sku_id"


class DynamicField(str, Enum):
    PRICE = "price"
    ORIGINAL_PRICE = "original_price"
    SALES = "sales"
    SKU_PRICE = "sku_price"
    SKU_STOCK = "sku_stock"
    PROMOTION = "promotion"


class SearchSort(str, Enum):
    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    SALES_DESC = "sales_desc"


class SystemCollectorError(str, Enum):
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
    ITEM_UNAVAILABLE = "ITEM_UNAVAILABLE"
    PARSE_ERROR = "PARSE_ERROR"
    DATA_QUALITY_FAILURE = "DATA_QUALITY_FAILURE"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"
    PLATFORM_NOT_SUPPORTED = "PLATFORM_NOT_SUPPORTED"
    CAPABILITY_NOT_SUPPORTED = "CAPABILITY_NOT_SUPPORTED"


class CollectorException(RuntimeError):
    def __init__(self, code: SystemCollectorError, message: str = "") -> None:
        self.code = code
        super().__init__(message or code.value)


@dataclass(frozen=True)
class CollectorCapabilities:
    capabilities: frozenset[CollectorCapability]
    identities: frozenset[IdentityKind]
    dynamic_fields: frozenset[DynamicField]

    def supports(self, capability: CollectorCapability) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class PlatformIdentity:
    platform: str
    platform_product_id: str
    platform_sku_id: str | None = None


@dataclass(frozen=True)
class SearchRequest:
    keyword: str
    limit: int = 20
    cursor: str | None = None
    sort: SearchSort = SearchSort.RELEVANCE


@dataclass(frozen=True)
class SearchResult:
    items: tuple[RawResult, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class DetailRequest:
    identity: PlatformIdentity


@dataclass(frozen=True)
class RawResult:
    platform: str
    identity: PlatformIdentity | None = None
    dynamic_fields: Mapping[DynamicField, Any] | None = None
    page_status: str = "unknown"
    parse_status: str = "not_attempted"
    field_sources: Mapping[str, str] | None = None
    parser_version: str = ""
    capabilities: CollectorCapabilities | None = None
    evidence_ref: str | None = None


class Collector(Protocol):
    platform: str
    parser_version: str
    capabilities: CollectorCapabilities

    def classify_page(self, text: str) -> str: ...

    def validate_identity(self, identity: PlatformIdentity) -> bool: ...

    def validate_item_url(self, identity: PlatformIdentity, item_url: str) -> bool: ...

    def map_error(self, platform_error: str) -> SystemCollectorError: ...


class CollectorRegistry:
    def __init__(self) -> None:
        self._collectors: dict[str, Collector] = {}

    def register(self, collector: Collector) -> None:
        platform = collector.platform.strip().lower()
        if not platform:
            raise ValueError("collector platform must not be blank")
        if platform in self._collectors:
            raise ValueError(f"collector already registered: {platform}")
        self._collectors[platform] = collector

    def get(self, platform: str) -> Collector | None:
        return self._collectors.get((platform or "").strip().lower())

    def require(self, platform: str) -> Collector:
        collector = self.get(platform)
        if collector is None:
            raise CollectorException(
                SystemCollectorError.PLATFORM_NOT_SUPPORTED,
                f"unsupported platform: {platform}",
            )
        return collector

    def platforms(self) -> tuple[str, ...]:
        return tuple(sorted(self._collectors))
